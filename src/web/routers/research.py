"""Research routes."""
from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.db.connection import get_session
from src.db.models.evaluation import EvalResult
from src.db.models.research import ResearchOutput, ResearchRun
from src.web.flash import get_flash

router = APIRouter()
_templates: Jinja2Templates | None = None


def init(templates: Jinja2Templates) -> None:
    global _templates
    _templates = templates


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _eval_params(eval_result: Any) -> dict[str, Any]:
    if eval_result is None:
        return {}
    params = getattr(eval_result, "evaluation_params", None)
    return params if isinstance(params, dict) else {}


def _normalize_news(news_items: list[Any]) -> list[dict[str, Any]]:
    normalized = []
    for item in news_items:
        if isinstance(item, dict):
            normalized.append(
                {
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "source": item.get("source"),
                    "url": item.get("url"),
                    "signal_type": item.get("signal_type"),
                    "published_at": item.get("published_at"),
                }
            )
        else:
            normalized.append(
                {
                    "title": str(item),
                    "summary": None,
                    "source": None,
                    "url": None,
                    "signal_type": None,
                    "published_at": None,
                }
            )
    return normalized


def _normalize_global_events(items: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            normalized.append(
                {
                    "source": item.get("source"),
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "published_at": item.get("published_at"),
                    "url": item.get("url"),
                }
            )
        else:
            normalized.append(
                {
                    "source": None,
                    "title": str(item),
                    "summary": None,
                    "published_at": None,
                    "url": None,
                }
            )
    return normalized


def _normalize_insider_trades(items: list[Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (
            item.get("insider_name"),
            item.get("insider_title"),
            item.get("transaction_type"),
            item.get("transaction_date"),
        )
        if key not in grouped:
            grouped[key] = {
                "insider_name": item.get("insider_name"),
                "insider_title": item.get("insider_title"),
                "transaction_type": item.get("transaction_type"),
                "transaction_date": item.get("transaction_date"),
                "filing_date": item.get("filing_date"),
                "shares": item.get("shares") or 0,
                "total_value": item.get("total_value") or 0,
                "filing_url": item.get("filing_url"),
                "trade_count": 1,
            }
        else:
            grouped[key]["shares"] = (grouped[key]["shares"] or 0) + (item.get("shares") or 0)
            grouped[key]["total_value"] = (grouped[key]["total_value"] or 0) + (item.get("total_value") or 0)
            grouped[key]["trade_count"] += 1
    return list(grouped.values())


def _normalize_indicators(global_indicators: dict) -> list[dict[str, Any]]:
    normalized = []
    for key, item in global_indicators.items():
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "key": key,
                "label": item.get("label") or key,
                "source": item.get("source"),
                "unit": item.get("unit"),
                "value": item.get("value"),
                "observed_on": item.get("observed_on"),
            }
        )
    return normalized


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/research", response_class=HTMLResponse)
def research_list(request: Request):
    with get_session() as session:
        runs = (
            session.query(ResearchRun)
            .outerjoin(ResearchOutput, ResearchRun.run_id == ResearchOutput.run_id)
            .outerjoin(EvalResult, ResearchRun.run_id == EvalResult.run_id)
            .order_by(ResearchRun.created_at.desc())
            .all()
        )

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

        # Pull global context from the most recent succeeded run that has it
        global_context_display: dict | None = None
        latest_run_with_gc = (
            session.query(ResearchRun)
            .filter(ResearchRun.status == "succeeded")
            .order_by(ResearchRun.created_at.desc())
            .first()
        )
        if latest_run_with_gc:
            gc = (latest_run_with_gc.input_json or {}).get("global_context") or {}
            if gc:
                global_context_display = {
                    "as_of": gc.get("as_of"),
                    "indicators": _normalize_indicators(gc.get("indicators") or {}),
                    "official_updates": _normalize_global_events(gc.get("official_updates") or []),
                    "trump_updates": _normalize_global_events(gc.get("trump_updates") or []),
                    "geopolitical_news": _normalize_global_events(gc.get("geopolitical_news") or []),
                }

    return _templates.TemplateResponse(
        request, "research.html", {
            "grouped": grouped,
            "stats": stats,
            "global_context": global_context_display,
            "flash": get_flash(request),
        },
    )


@router.get("/research/{run_id}", response_class=HTMLResponse)
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
        fundamentals = input_data.get("fundamentals") or {}
        volume_snapshot = input_data.get("volume_snapshot") or {}
        technical_signals = input_data.get("technical_signals") or {}
        momentum_signals = technical_signals.get("momentum") or {}
        volatility_signals = technical_signals.get("volatility") or {}
        global_context = input_data.get("global_context") or {}
        global_indicators = global_context.get("indicators") or {}

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
            "input_company_name": research_context.get("company_name"),
            "input_earnings_in_days": research_context.get("earnings_in_days"),
            "input_pe_ratio": fundamentals.get("pe_ratio"),
            "input_ps_ratio": fundamentals.get("ps_ratio"),
            "input_short_interest_pct_float": fundamentals.get("short_interest_pct_float"),
            "input_session_volume": volume_snapshot.get("session_volume"),
            "input_avg_volume_20d": volume_snapshot.get("avg_volume_20d"),
            "input_relative_volume": volume_snapshot.get("relative_volume"),
            "input_rsi_14": momentum_signals.get("rsi_14"),
            "input_rsi_3": momentum_signals.get("rsi_3"),
            "input_atr_14": volatility_signals.get("atr_14"),
            "input_yesterday_range": volatility_signals.get("yesterday_range"),
            "input_atr_multiple": volatility_signals.get("atr_multiple"),
            "input_news": sorted(
                _normalize_news(input_data.get("news") or []),
                key=lambda x: x.get("published_at") or "",
                reverse=True,
            ),
            "input_insider_window_days": (input_data.get("insider_activity") or {}).get("window_days"),
            "input_insider_purchase_count": (input_data.get("insider_activity") or {}).get("purchase_count"),
            "input_insider_sale_count": (input_data.get("insider_activity") or {}).get("sale_count"),
            "input_insider_net_shares": (input_data.get("insider_activity") or {}).get("net_shares"),
            "input_insider_net_value": (input_data.get("insider_activity") or {}).get("net_value"),
            "input_insider_recent_trades": _normalize_insider_trades(
                (input_data.get("insider_activity") or {}).get("recent_trades") or []
            ),
            "input_global_context_as_of": global_context.get("as_of"),
            "input_global_indicators": _normalize_indicators(global_indicators),
            "input_official_updates": _normalize_global_events(global_context.get("official_updates") or []),
            "input_trump_updates": _normalize_global_events(global_context.get("trump_updates") or []),
            "input_geopolitical_news": _normalize_global_events(global_context.get("geopolitical_news") or []),
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

    return _templates.TemplateResponse(
        request, "research_detail.html",
        {"detail": detail, "history": history, "flash": get_flash(request)},
    )
