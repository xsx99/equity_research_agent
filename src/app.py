"""FastAPI web application for the research app MVP.

Routes:
  GET  /watchlist               — list all watchlist tickers; form to add
  POST /watchlist/add           — add/reactivate a ticker
  POST /watchlist/{ticker}/delete — deactivate a ticker
  GET  /research                — list research runs with aggregated eval stats
  GET  /research/{run_id}       — run detail (input, output, eval)
  POST /admin/run-now           — trigger research pipeline
  POST /admin/eval-now          — trigger eval pipeline
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.agents.research import ResearchAgent
from src.db.connection import get_session, init_db
from src.db.models.evaluation import EvalResult
from src.db.models.research import ResearchOutput, ResearchRun
from src.db.models.watch_list import Watchlist
from src.research import repository
from src.prompts.registry import PromptRegistry
from src.research.eval_pipeline import EvalPipeline
from src.research.pipeline import ResearchPipeline
from src.tools import build_research_tool_registry

import os

_DIR = os.path.dirname(__file__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Insider Research App", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_DIR, "templates"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flash(request: Request, message: str, level: str = "info") -> None:
    """Store a one-shot flash message in the request state (rendered by templates)."""
    if not hasattr(request.state, "flash"):
        request.state.flash = []
    request.state.flash.append({"message": message, "level": level})


def _get_flash(request: Request) -> list[dict]:
    return getattr(request.state, "flash", [])


def _pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value * 100:+.2f}%"


def _fmt_conf(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.0%}"


def _fmt_currency(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _eval_params(eval_result: Any) -> dict[str, Any]:
    if eval_result is None:
        return {}
    params = getattr(eval_result, "evaluation_params", None)
    return params if isinstance(params, dict) else {}


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _iso_datetime(value: Any) -> str:
    dt = _coerce_datetime(value)
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _local_time(value: Any, display: str = "datetime") -> str:
    dt = _coerce_datetime(value)
    if dt is None:
        return "—"

    local_dt = dt.astimezone()
    if display == "date":
        return local_dt.strftime("%Y-%m-%d")
    if display == "month_day":
        return local_dt.strftime("%m-%d")
    if display == "datetime_seconds":
        return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    return local_dt.strftime("%Y-%m-%d %H:%M %Z")


# Register template globals/filters
templates.env.globals["pct"] = _pct
templates.env.globals["fmt_conf"] = _fmt_conf
templates.env.globals["fmt_currency"] = _fmt_currency
templates.env.filters["iso_datetime"] = _iso_datetime
templates.env.filters["local_time"] = _local_time


# ---------------------------------------------------------------------------
# Watchlist routes
# ---------------------------------------------------------------------------


@app.get("/watchlist", response_class=HTMLResponse)
def watchlist_page(request: Request):
    with get_session() as session:
        items = repository.get_watchlist(session)
        rows = [
            {
                "id": str(w.id),
                "ticker": w.ticker,
                "is_active": w.is_active,
                "created_at": w.created_at,
            }
            for w in items
        ]
    return templates.TemplateResponse(
        request, "watchlist.html", {"rows": rows, "flash": _get_flash(request)}
    )


@app.post("/watchlist/add")
def watchlist_add(request: Request, ticker: str = Form(...)):
    ticker = ticker.strip().upper()
    if not ticker:
        return RedirectResponse("/watchlist", status_code=303)
    try:
        with get_session() as session:
            repository.add_ticker(session, ticker)
    except Exception as exc:
        _flash(request, f"Error adding {ticker}: {exc}", "error")
    return RedirectResponse("/watchlist", status_code=303)


@app.post("/watchlist/{ticker}/delete")
def watchlist_delete(ticker: str, request: Request):
    try:
        with get_session() as session:
            found = repository.deactivate_ticker(session, ticker.upper())
        if not found:
            _flash(request, f"{ticker} not found", "error")
    except Exception as exc:
        _flash(request, f"Error removing {ticker}: {exc}", "error")
    return RedirectResponse("/watchlist", status_code=303)


# ---------------------------------------------------------------------------
# Research routes
# ---------------------------------------------------------------------------


@app.get("/research", response_class=HTMLResponse)
def research_list(request: Request):
    with get_session() as session:
        runs = (
            session.query(ResearchRun)
            .outerjoin(ResearchOutput, ResearchRun.run_id == ResearchOutput.run_id)
            .outerjoin(EvalResult, ResearchRun.run_id == EvalResult.run_id)
            .order_by(ResearchRun.created_at.desc())
            .all()
        )

        # Only show succeeded runs; group by ticker preserving recency order.
        outcome_counts: Counter = Counter()
        ticker_order: list[str] = []
        groups: dict[str, list[dict]] = {}

        for run in runs:
            if run.status != "succeeded":
                continue
            out = run.output
            ev = run.eval_result
            eval_params = _eval_params(ev)
            if ev and ev.outcome_label and eval_params.get("price_window") == "open_to_close":
                outcome_counts[ev.outcome_label] += 1
            row = {
                "run_id": str(run.run_id),
                "ticker": run.ticker,
                "as_of": run.as_of,
                "status": run.status,
                "decision": out.decision if out else None,
                "confidence": out.confidence if out else None,
                "actionability": out.actionability if out else None,
                "time_horizon": out.time_horizon if out else None,
                "thesis_summary": out.thesis_summary if out else None,
                "outcome_label": ev.outcome_label if ev else None,
                "evaluation_price_window": eval_params.get("price_window"),
                "created_at": run.created_at,
            }
            if run.ticker not in groups:
                ticker_order.append(run.ticker)
                groups[run.ticker] = []
            groups[run.ticker].append(row)

        # Ordered list of (ticker, rows) for the template
        grouped = [(t, groups[t]) for t in ticker_order]

        total = sum(len(v) for v in groups.values())
        total_evaled = sum(outcome_counts.values())
        correct = outcome_counts.get("correct", 0) + outcome_counts.get("partially_correct", 0)
        accuracy = correct / total_evaled if total_evaled else None

        stats = {
            "total": total,
            "total_evaled": total_evaled,
            "accuracy": accuracy,
            "outcome_counts": dict(outcome_counts),
        }

    return templates.TemplateResponse(
        request, "research.html", {"grouped": grouped, "stats": stats, "flash": _get_flash(request)},
    )


@app.get("/research/{run_id}", response_class=HTMLResponse)
def research_detail(run_id: str, request: Request):
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid run ID")

    with get_session() as session:
        run = session.query(ResearchRun).filter(ResearchRun.run_id == rid).first()
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")

        out = run.output
        ev = run.eval_result
        eval_params = _eval_params(ev)
        input_data = run.input_json or {}
        price_snapshot = input_data.get("price_snapshot") or {}
        research_context = input_data.get("context") or {}
        news_items = input_data.get("news") or []
        normalized_news = []
        for item in news_items:
            if isinstance(item, dict):
                normalized_news.append(
                    {
                        "title": item.get("title"),
                        "summary": item.get("summary"),
                    }
                )
            else:
                normalized_news.append({"title": str(item), "summary": None})

        # Ticker history: last 10 eval results for same ticker
        ticker_history = (
            session.query(ResearchRun, ResearchOutput, EvalResult)
            .join(ResearchOutput, ResearchRun.run_id == ResearchOutput.run_id)
            .join(EvalResult, ResearchRun.run_id == EvalResult.run_id)
            .filter(ResearchRun.ticker == run.ticker)
            .order_by(ResearchRun.as_of.desc())
            .limit(10)
            .all()
        )
        history = [
            {
                "run_id": str(r.run_id),
                "as_of": r.as_of,
                "decision": o.decision,
                "confidence": o.confidence,
                "outcome_label": e.outcome_label,
                "realized_return": e.realized_return,
            }
            for r, o, e in ticker_history
        ]

        detail = {
            "run_id": run_id,
            "ticker": run.ticker,
            "as_of": run.as_of,
            "status": run.status,
            "prompt_version": run.prompt_version,
            "model_name": run.model_name,
            "error_message": run.error_message,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "created_at": run.created_at,
            "has_input": bool(input_data),
            "input_ticker": input_data.get("ticker") or run.ticker,
            "input_as_of": input_data.get("as_of"),
            "input_last_price": price_snapshot.get("last_price"),
            "input_return_1d": price_snapshot.get("return_1d"),
            "input_return_5d": price_snapshot.get("return_5d"),
            "input_return_since_market_open": price_snapshot.get("return_since_market_open"),
            "input_sector": research_context.get("sector"),
            "input_earnings_in_days": research_context.get("earnings_in_days"),
            "input_news": normalized_news,
            "decision": out.decision if out else None,
            "confidence": out.confidence if out else None,
            "time_horizon": out.time_horizon if out else None,
            "time_horizon_rationale": (out.output_json or {}).get("time_horizon_rationale") if out else None,
            "actionability": out.actionability if out else None,
            "thesis_summary": out.thesis_summary if out else None,
            "key_drivers": (out.output_json or {}).get("key_drivers", []) if out else [],
            "counterarguments": (out.output_json or {}).get("counterarguments", []) if out else [],
            "invalidators": (out.output_json or {}).get("invalidators", []) if out else [],
            "outcome_label": ev.outcome_label if ev else None,
            "realized_return": ev.realized_return if ev else None,
            "benchmark_return": ev.benchmark_return if ev else None,
            "benchmark_symbol": ev.benchmark_symbol if ev else None,
            "evaluation_method": ev.evaluation_method if ev else None,
            "horizon_days": ev.horizon_days if ev else None,
            "evaluation_price_window": eval_params.get("price_window"),
            "evaluation_entry_price_source": eval_params.get("entry_price_source"),
            "evaluation_exit_price_source": eval_params.get("exit_price_source"),
            "evaluation_benchmark_entry_price_source": eval_params.get("benchmark_entry_price_source"),
            "evaluation_benchmark_exit_price_source": eval_params.get("benchmark_exit_price_source"),
        }

    return templates.TemplateResponse(
        request, "research_detail.html",
        {"detail": detail, "history": history, "flash": _get_flash(request)},
    )


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------


@app.post("/admin/run-now", response_class=HTMLResponse)
def admin_run_now(request: Request):
    try:
        with get_session() as session:
            agent = ResearchAgent(
                tool_registry=build_research_tool_registry(),
                prompt_registry=PromptRegistry.get_default(),
            )
            pipeline = ResearchPipeline(session=session, agent=agent)
            result = pipeline.run_all()
        msg = f"Research complete: {result.succeeded} succeeded, {result.failed} failed."
        level = "info" if result.failed == 0 else "warning"
    except Exception as exc:
        msg = f"Research pipeline error: {exc}"
        level = "error"
    _flash(request, msg, level)
    return RedirectResponse("/research", status_code=303)


@app.post("/admin/eval-now", response_class=HTMLResponse)
def admin_eval_now(request: Request):
    try:
        with get_session() as session:
            pipeline = EvalPipeline(session=session)
            result = pipeline.run_all()
        msg = (
            f"Eval complete: {result.evaluated} evaluated, "
            f"{result.skipped} skipped, {result.failed} failed."
        )
        level = "info" if result.failed == 0 else "warning"
    except Exception as exc:
        msg = f"Eval pipeline error: {exc}"
        level = "error"
    _flash(request, msg, level)
    return RedirectResponse("/research", status_code=303)


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def root():
    return RedirectResponse("/research", status_code=303)
