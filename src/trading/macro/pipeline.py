"""Deterministic macro snapshot pipeline."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from src.trading.data_sources.provider_resilience import (
    InMemoryProviderRequestRecorder,
    ProviderRequestRecorder,
    ProviderResiliencePolicy,
)
from src.trading.macro.context import MacroSnapshotRecord


class MacroSnapshotPipeline:
    """Build one canonical macro snapshot from global-context indicators."""

    def __init__(
        self,
        *,
        global_context_fetcher: Callable[[datetime], dict[str, Any]] | None = None,
        recorder: ProviderRequestRecorder | None = None,
        provider_name: str = "global_context",
        now: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.global_context_fetcher = global_context_fetcher or (lambda as_of: {"as_of": as_of.isoformat(), "indicators": {}})
        self.recorder = recorder or InMemoryProviderRequestRecorder()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.policy = ProviderResiliencePolicy(
            provider=provider_name,
            endpoint="macro_snapshot",
            source_family="macro",
            recorder=self.recorder,
            now=self.now,
            sleeper=sleeper or (lambda _seconds: None),
        )

    def build_snapshot(self, *, as_of: datetime) -> MacroSnapshotRecord:
        try:
            payload = self.policy.execute(as_of.date().isoformat(), lambda: self.global_context_fetcher(as_of))
        except Exception:
            return MacroSnapshotRecord(
                macro_snapshot_id=str(uuid.uuid4()),
                snapshot_time=as_of,
                trade_date=as_of.date(),
                regime="unavailable",
                risk_budget_multiplier=0.0,
                volatility_state=None,
                rates_state=None,
                liquidity_state=None,
                blocked_strategy_tags=("gap_and_go_v1", "earnings_drift_v1"),
                invalidators=("global_context_failed",),
                source_freshness={"global_context": {"status": "failed"}},
                metadata_json={
                    "availability_issues": ["global_context_failed"],
                    "basis_note": "macro context unavailable",
                },
            )

        indicators = dict(payload.get("indicators") or {})
        freshness = _source_freshness(indicators=indicators, as_of=as_of)
        vix_value = _indicator_value(indicators, "vix")
        treasury_10y = _indicator_value(indicators, "us_treasury_10y")
        credit_spread = _indicator_value(indicators, "credit_spread")

        volatility_state = _volatility_state(vix_value)
        rates_state = _rates_state(treasury_10y)
        liquidity_state = _liquidity_state(credit_spread)
        regime = _regime(
            vix_value=vix_value,
            treasury_10y=treasury_10y,
            credit_spread=credit_spread,
        )
        risk_budget_multiplier = _risk_budget_multiplier(regime=regime, freshness_status=freshness["status"])
        invalidators = list(_invalidators(regime=regime, freshness_status=freshness["status"]))
        blocked_strategy_tags = _blocked_strategy_tags(regime=regime)

        return MacroSnapshotRecord(
            macro_snapshot_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"macro_snapshot:{as_of.isoformat()}")),
            snapshot_time=as_of,
            trade_date=as_of.date(),
            regime=regime,
            risk_budget_multiplier=risk_budget_multiplier,
            volatility_state=volatility_state,
            rates_state=rates_state,
            liquidity_state=liquidity_state,
            blocked_strategy_tags=blocked_strategy_tags,
            invalidators=tuple(invalidators),
            source_freshness={"global_context": freshness},
            metadata_json={
                "availability_issues": [] if freshness["status"] != "failed" else ["global_context_failed"],
                "basis_note": _basis_note(
                    regime=regime,
                    volatility_state=volatility_state,
                    rates_state=rates_state,
                    liquidity_state=liquidity_state,
                    freshness_status=freshness["status"],
                ),
            },
        )


def _indicator_value(indicators: dict[str, Any], key: str) -> float | None:
    payload = dict(indicators.get(key) or {})
    value = payload.get("value")
    if value is None:
        return None
    return float(value)


def _source_freshness(*, indicators: dict[str, Any], as_of: datetime) -> dict[str, Any]:
    observed_dates = []
    for payload in indicators.values():
        observed_on = dict(payload or {}).get("observed_on")
        if isinstance(observed_on, str) and observed_on:
            observed_dates.append(datetime.fromisoformat(observed_on).date())
    if not indicators:
        return {"status": "failed"}
    if not observed_dates:
        return {"status": "missing"}
    newest = max(observed_dates)
    age_days = (as_of.date() - newest).days
    if age_days > 5:
        return {"status": "stale", "observed_on": newest.isoformat(), "age_days": age_days}
    return {"status": "fresh", "observed_on": newest.isoformat(), "age_days": age_days}


def _volatility_state(vix_value: float | None) -> str | None:
    if vix_value is None:
        return None
    if vix_value >= 28.0:
        return "elevated"
    return "normal"


def _rates_state(treasury_10y: float | None) -> str | None:
    if treasury_10y is None:
        return None
    if treasury_10y >= 4.75:
        return "restrictive"
    return "stable"


def _liquidity_state(credit_spread: float | None) -> str | None:
    if credit_spread is None:
        return None
    if credit_spread >= 5.0:
        return "tight"
    return "ample"


def _regime(*, vix_value: float | None, treasury_10y: float | None, credit_spread: float | None) -> str:
    if vix_value is None and treasury_10y is None and credit_spread is None:
        return "unavailable"
    if (
        (vix_value is not None and vix_value >= 28.0)
        or (treasury_10y is not None and treasury_10y >= 4.75)
        or (credit_spread is not None and credit_spread >= 5.0)
    ):
        return "risk_off"
    return "balanced"


def _risk_budget_multiplier(*, regime: str, freshness_status: str) -> float:
    if regime == "unavailable":
        return 0.0
    if regime == "risk_off":
        return 0.5
    if freshness_status == "stale":
        return 0.75
    return 1.0


def _invalidators(*, regime: str, freshness_status: str) -> tuple[str, ...]:
    values: list[str] = []
    if regime == "risk_off":
        values.append("macro_risk_off")
    if freshness_status == "stale":
        values.append("stale_macro_inputs")
    return tuple(values)


def _blocked_strategy_tags(*, regime: str) -> tuple[str, ...]:
    if regime in {"risk_off", "unavailable"}:
        return ("gap_and_go_v1", "earnings_drift_v1")
    return ()


def _basis_note(
    *,
    regime: str,
    volatility_state: str | None,
    rates_state: str | None,
    liquidity_state: str | None,
    freshness_status: str,
) -> str:
    if regime == "unavailable":
        return "macro context unavailable"
    parts = [regime]
    if volatility_state:
        parts.append(f"volatility={volatility_state}")
    if rates_state:
        parts.append(f"rates={rates_state}")
    if liquidity_state:
        parts.append(f"liquidity={liquidity_state}")
    if freshness_status == "stale":
        parts.append("stale_inputs")
    return ", ".join(parts)
