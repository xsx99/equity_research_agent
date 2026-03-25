"""Research pipeline — batch orchestration for the research app.

Responsible for:
- Loading active watchlist tickers from Postgres.
- Fetching market snapshot and news via the tool registry (deterministic Python,
  not model-driven tool-calling).
- Fetching one replayable global macro/news context block per batch.
- Building a replayable ``input_json`` snapshot.
- Creating / updating ``ResearchRun`` status rows.
- Calling ``ResearchAgent`` for one model invocation per ticker.
- Persisting ``ResearchOutput`` on success or recording the error on failure.

Each ticker is processed independently so a single failure does not abort
the rest of the batch.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.agents.research import ResearchAgent
from src.core.logging import get_logger
from src.db.models.research import ResearchRun
from src.research import repository
from src.tools import ToolContext, ToolRegistry, build_research_tool_registry

logger = get_logger(__name__)

_CORP_SUFFIXES = frozenset(
    {"corp", "inc", "ltd", "llc", "co", "corporation", "incorporated",
     "limited", "holdings", "group", "technologies", "technology", "systems"}
)


def _core_company_name(company_name: str) -> str:
    """Strip trailing corporate suffixes and return the meaningful part lowercased.

    E.g. "SanDisk Corp" → "sandisk", "Western Digital Corp" → "western digital".
    """
    words = company_name.lower().split()
    while words and words[-1].rstrip(".,") in _CORP_SUFFIXES:
        words.pop()
    return " ".join(words)


def _filter_relevant_news(
    news: list[dict[str, Any]],
    ticker: str,
    company_name: Optional[str],
) -> list[dict[str, Any]]:
    """Keep only articles whose title mentions the ticker or company name."""
    needle_ticker = ticker.lower()
    needle_company = _core_company_name(company_name) if company_name else ""
    result = []
    for item in news:
        title = (item.get("title") or "").lower()
        if needle_ticker in title or (needle_company and needle_company in title):
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class TickerResult:
    """Outcome of a single-ticker research run."""

    ticker: str
    run_id: Optional[uuid.UUID]
    success: bool
    error: Optional[str] = None


@dataclass
class PipelineResult:
    """Aggregate outcome of a full batch run."""

    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    ticker_results: list[TickerResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class ResearchPipeline:
    """
    Orchestrates the full research batch pipeline.

    Parameters
    ----------
    session:
        SQLAlchemy session.  The pipeline does **not** commit; callers are
        responsible for transaction management.
    agent:
        A :class:`~src.agents.research.ResearchAgent` instance.
    tool_registry:
        Registry used to fetch market data and news.  Defaults to the standard
        research tool registry if not provided.
    """

    def __init__(
        self,
        session: Session,
        agent: ResearchAgent,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        self.session = session
        self.agent = agent
        self.tool_registry = tool_registry or build_research_tool_registry()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run_all(self, as_of: Optional[datetime] = None) -> PipelineResult:
        """Run the pipeline for every active watchlist ticker.

        Parameters
        ----------
        as_of:
            Timestamp to use as the research ``as_of`` field.  Defaults to
            ``datetime.now(timezone.utc)``.
        """
        as_of = as_of or datetime.now(timezone.utc)
        tickers = repository.get_active_tickers(self.session)

        if not tickers:
            logger.info("research_pipeline_no_active_tickers")
            return PipelineResult()

        logger.info("research_pipeline_started", ticker_count=len(tickers))
        result = PipelineResult()
        batch_global_context = self._fetch_global_context(as_of)

        for ticker in tickers:
            ticker_result = self.run_ticker(
                ticker,
                as_of=as_of,
                global_context=batch_global_context,
            )
            result.ticker_results.append(ticker_result)
            if ticker_result.success:
                result.succeeded += 1
            else:
                result.failed += 1

        logger.info(
            "research_pipeline_finished",
            succeeded=result.succeeded,
            failed=result.failed,
        )
        return result

    def run_ticker(
        self,
        ticker: str,
        as_of: Optional[datetime] = None,
        *,
        global_context: Optional[dict[str, Any]] = None,
        reuse_latest_global_context: bool = False,
    ) -> TickerResult:
        """Run the full research lifecycle for a single ticker.

        Status transitions:
          queued → running → succeeded  (happy path)
          queued → running → failed     (any exception)
        """
        as_of = as_of or datetime.now(timezone.utc)
        ticker = ticker.upper().strip()
        run: Optional[ResearchRun] = None

        try:
            if global_context is None and reuse_latest_global_context:
                global_context = self._get_reusable_global_context(as_of)
            if global_context is None:
                global_context = self._fetch_global_context(as_of)

            # 1. Fetch market data and news before creating the run row so that
            #    a data-fetch error does not leave a dangling queued run.
            input_json = self._build_input_json(
                ticker,
                as_of,
                global_context=global_context,
            )

            # 2. Create the run row (queued) and flush so run_id is available.
            run = repository.create_run(
                self.session,
                ticker=ticker,
                as_of=as_of,
                prompt_version=self.agent.prompt_version,
                model_name=self.agent.model_name,
                input_json=input_json,
            )
            self.session.flush()

            # 3. Mark running.
            repository.mark_run_running(self.session, run)

            # 4. Call the LLM agent.
            tool_context = ToolContext(session=self.session)
            agent_result = self.agent.run(input_json, tool_context)

            if not agent_result.success:
                raise RuntimeError(agent_result.error or "agent_returned_failure")

            # 5. Persist structured output.
            repository.persist_output(self.session, run.run_id, agent_result.output_data)

            # 6. Mark succeeded.
            repository.mark_run_succeeded(self.session, run)

            return TickerResult(ticker=ticker, run_id=run.run_id, success=True)

        except Exception as exc:
            error_msg = str(exc)
            if run is not None:
                repository.mark_run_failed(self.session, run, error_msg)
            else:
                # Data fetch failed before the run row was created — log and continue.
                logger.error(
                    "research_pipeline_prefetch_failed",
                    ticker=ticker,
                    error=error_msg,
                    exc_info=True,
                )
            return TickerResult(
                ticker=ticker,
                run_id=run.run_id if run is not None else None,
                success=False,
                error=error_msg,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_input_json(
        self,
        ticker: str,
        as_of: datetime,
        *,
        global_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Assemble the replayable input snapshot for *ticker*."""
        tool_context = ToolContext()

        market = self._fetch_market_data(ticker, tool_context)
        news = self._fetch_news(ticker, tool_context)
        news = _filter_relevant_news(news, ticker, market.get("company_name"))

        return {
            "ticker": ticker,
            "as_of": as_of.isoformat(),
            "price_snapshot": {
                "last_price": market.get("last_price"),
                "return_1d": market.get("return_1d"),
                "return_5d": market.get("return_5d"),
                "return_since_market_open": market.get("return_since_market_open"),
            },
            "context": {
                "sector": market.get("sector"),
                "earnings_in_days": market.get("earnings_in_days"),
            },
            "news": news[:5],
            "global_context": global_context or self._empty_global_context(as_of),
        }

    def _fetch_market_data(self, ticker: str, context: ToolContext) -> dict[str, Any]:
        """Dispatch the market snapshot tool; return empty snapshot on failure."""
        try:
            return self.tool_registry.dispatch(
                "get_market_snapshot", {"ticker": ticker}, context
            )
        except Exception as exc:
            logger.warning(
                "research_pipeline_market_data_failed",
                ticker=ticker,
                error=str(exc),
            )
            return {}

    def _fetch_news(self, ticker: str, context: ToolContext) -> list[dict[str, str]]:
        """Dispatch the news tool; return empty list on failure."""
        try:
            return self.tool_registry.dispatch(
                "get_recent_news", {"ticker": ticker, "limit": 5}, context
            )
        except Exception as exc:
            logger.warning(
                "research_pipeline_news_failed",
                ticker=ticker,
                error=str(exc),
            )
            return []

    def _fetch_global_context(self, as_of: datetime) -> dict[str, Any]:
        """Dispatch the global context tool; return an empty block on failure."""
        try:
            return self.tool_registry.dispatch(
                "get_global_context",
                {"as_of": as_of.isoformat(), "limit": 5},
                ToolContext(),
            )
        except Exception as exc:
            logger.warning(
                "research_pipeline_global_context_failed",
                error=str(exc),
            )
            return self._empty_global_context(as_of)

    def _get_reusable_global_context(self, as_of: datetime) -> Optional[dict[str, Any]]:
        """Return the latest same-day global context block if one already exists."""
        return repository.get_latest_global_context_for_trade_date(
            self.session,
            trade_date=as_of.date(),
        )

    @staticmethod
    def _empty_global_context(as_of: datetime) -> dict[str, Any]:
        return {
            "as_of": as_of.isoformat(),
            "indicators": {},
            "official_updates": [],
            "trump_updates": [],
            "geopolitical_news": [],
        }
