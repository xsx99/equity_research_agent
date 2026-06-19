from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from src.web.presenters.today_overview import build_today_overview


def test_build_today_overview_exposes_operator_strip_and_metric_provenance():
    payload = build_today_overview(
        header={
            "trade_date": date(2026, 6, 16),
            "market_phase": "Pre-open",
            "macro_regime": "risk_off",
            "risk_appetite": "conservative",
            "runtime_mode": "live-manual-review",
            "live_status": "degraded",
            "open_alert_count": 3,
            "material_signal_change_count": 2,
            "buying_power": Decimal("245000.00"),
            "gross_exposure": Decimal("0.41"),
            "day_pnl": Decimal("-512.20"),
            "nav": Decimal("998250.00"),
            "llm_cost_estimate": Decimal("14.82"),
        },
        job_timeline=(
            {"label": "Manual Review", "status": "running"},
        ),
        risk_macro={
            "command_center": {
                "regime": "risk_off",
                "risk_appetite_label": "Conservative",
                "warning_banner": "Risk context degraded; review macro and provider availability before acting.",
                "updated_at": datetime(2026, 6, 16, 13, 31, tzinfo=timezone.utc),
                "basis_note": "Macro summary uses canonical risk + event context.",
            },
            "availability": {
                "status": "degraded",
                "issues": ("macro_regime_unavailable",),
            },
        },
        live_alerts=(
            {"ticker": "AAPL", "headline": "High-severity alert"},
        ),
        material_changes=(
            {"ticker": "NVDA", "summary": "Intraday refresh lowered risk appetite"},
        ),
        positions=(
            {"ticker": "AAPL", "summary": "Open position, risk within limits"},
        ),
        option_positions=(
            {"ticker": "QQQ", "summary": "Open option position, max loss $230.00"},
            {"ticker": "NVDA", "summary": "Open option position, max loss $220.00"},
        ),
        closed_positions=(
            {"ticker": "TSLA", "summary": "Closed today after event risk increased"},
        ),
    )

    assert payload["operator_strip"]["primary"][0] == {"label": "Market Phase", "value": "Pre-open", "tone": "neutral"}
    assert payload["operator_strip"]["context"][0]["label"] == "Macro Regime"
    assert payload["operator_strip"]["context"][0]["value"] == "Risk Off"
    assert payload["operator_strip"]["context"][2]["value"] == "Degraded"
    assert payload["operator_strip"]["context"][3]["value"] == "Manual Review / Running"
    assert payload["metric_cards"][0]["label"] == "Net Liquidation Value"
    assert payload["metric_cards"][0]["meta"]["source_of_truth_label"] == "Broker equity snapshot"
    assert payload["metric_cards"][1]["meta"]["basis_note"] == "Review-window realized and unrealized session P&L."
    assert payload["metric_cards"][-1]["meta"]["source_of_truth_label"] == "Estimated API and model usage"
    assert payload["alert_bar"]["count"] == 3
    assert payload["current_summary"]["meta"]["updated_at_label"] == "2026-06-16 13:31 UTC"
    assert payload["current_summary"]["hidden_item_count"] == 2
    assert payload["command_center"]["open_positions"] == (
        {"ticker": "AAPL", "summary": "Open position, risk within limits"},
        {"ticker": "QQQ", "summary": "Open option position, max loss $230.00"},
        {"ticker": "NVDA", "summary": "Open option position, max loss $220.00"},
    )


def test_build_today_overview_dedupes_closed_positions_by_ticker_for_needs_review():
    payload = build_today_overview(
        header={
            "trade_date": date(2026, 6, 16),
            "market_phase": "Pre-open",
            "macro_regime": "risk_off",
            "risk_appetite": "balanced",
            "runtime_mode": "live",
            "live_status": "live",
            "open_alert_count": None,
            "material_signal_change_count": None,
            "buying_power": Decimal("245000.00"),
            "gross_exposure": Decimal("0.41"),
            "day_pnl": Decimal("-512.20"),
            "nav": Decimal("998250.00"),
            "llm_cost_estimate": None,
        },
        job_timeline=(
            {"label": "Manual Review", "status": "idle"},
        ),
        risk_macro={
            "command_center": {
                "regime": "risk_off",
                "risk_appetite_label": "Balanced",
                "updated_at": datetime(2026, 6, 16, 13, 31, tzinfo=timezone.utc),
            },
            "availability": {
                "status": "available",
                "issues": (),
            },
        },
        live_alerts=(),
        material_changes=(),
        positions=(),
        option_positions=(),
        closed_positions=(
            {"ticker": "NVDA", "summary": "Closed recently and ready for review"},
            {"ticker": "NVDA", "summary": "Older NVDA close should not duplicate"},
            {"ticker": "TSLA"},
        ),
    )

    assert payload["command_center"]["needs_review"] == (
        {"ticker": "NVDA", "summary": "Closed recently and ready for review"},
        {"ticker": "TSLA", "summary": "Closed recently and ready for review"},
    )
    assert payload["current_summary"]["items"] == ("2 closed tickers pending review",)
