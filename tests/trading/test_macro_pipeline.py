from datetime import date, datetime, timezone

from src.trading.data_sources.provider_resilience import InMemoryProviderRequestRecorder
from src.trading.macro import MacroSnapshotRecord
from src.trading.macro.pipeline import MacroSnapshotPipeline


def _global_context(
    *,
    as_of: datetime,
    vix: float | None,
    treasury_10y: float | None,
    credit_spread: float | None,
    observed_on: str | None,
) -> dict[str, object]:
    return {
        "as_of": as_of.isoformat(),
        "indicators": {
            "vix": {
                "label": "CBOE Volatility Index",
                "source": "FRED:VIXCLS",
                "unit": "index",
                "value": vix,
                "observed_on": observed_on,
            },
            "us_treasury_10y": {
                "label": "US Treasury 10Y",
                "source": "FRED:DGS10",
                "unit": "pct",
                "value": treasury_10y,
                "observed_on": observed_on,
            },
            "credit_spread": {
                "label": "ICE BofA US High Yield OAS",
                "source": "FRED:BAMLH0A0HYM2",
                "unit": "pct",
                "value": credit_spread,
                "observed_on": observed_on,
            },
        },
    }


def test_macro_snapshot_pipeline_builds_balanced_snapshot():
    as_of = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    recorder = InMemoryProviderRequestRecorder()
    pipeline = MacroSnapshotPipeline(
        global_context_fetcher=lambda dt: _global_context(
            as_of=dt,
            vix=18.5,
            treasury_10y=4.2,
            credit_spread=3.6,
            observed_on="2026-06-16",
        ),
        recorder=recorder,
    )

    snapshot = pipeline.build_snapshot(as_of=as_of)

    assert isinstance(snapshot, MacroSnapshotRecord)
    assert snapshot.trade_date == date(2026, 6, 16)
    assert snapshot.regime == "balanced"
    assert snapshot.risk_budget_multiplier == 1.0
    assert snapshot.volatility_state == "normal"
    assert snapshot.blocked_strategy_tags == ()
    assert snapshot.source_freshness["global_context"]["status"] == "fresh"
    assert recorder.runs[-1].status == "succeeded"


def test_macro_snapshot_pipeline_builds_risk_off_snapshot_and_blocks_fragile_strategies():
    as_of = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    pipeline = MacroSnapshotPipeline(
        global_context_fetcher=lambda dt: _global_context(
            as_of=dt,
            vix=32.0,
            treasury_10y=4.95,
            credit_spread=5.4,
            observed_on="2026-06-16",
        ),
    )

    snapshot = pipeline.build_snapshot(as_of=as_of)

    assert snapshot.regime == "risk_off"
    assert snapshot.risk_budget_multiplier == 0.5
    assert snapshot.volatility_state == "elevated"
    assert snapshot.rates_state == "restrictive"
    assert snapshot.liquidity_state == "tight"
    assert "gap_and_go_v1" in snapshot.blocked_strategy_tags
    assert "macro_risk_off" in snapshot.invalidators


def test_macro_snapshot_pipeline_persists_unavailable_snapshot_when_provider_fails():
    as_of = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    recorder = InMemoryProviderRequestRecorder()

    def _failing_fetcher(_dt: datetime) -> dict[str, object]:
        raise RuntimeError("fred unavailable")

    pipeline = MacroSnapshotPipeline(
        global_context_fetcher=_failing_fetcher,
        recorder=recorder,
    )

    snapshot = pipeline.build_snapshot(as_of=as_of)

    assert snapshot.regime == "unavailable"
    assert snapshot.risk_budget_multiplier == 0.0
    assert snapshot.metadata_json["availability_issues"] == ["global_context_failed"]
    assert snapshot.source_freshness["global_context"]["status"] == "failed"
    assert recorder.runs[-1].status == "failed"


def test_macro_snapshot_pipeline_marks_stale_sources_and_reduces_budget():
    as_of = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
    pipeline = MacroSnapshotPipeline(
        global_context_fetcher=lambda dt: _global_context(
            as_of=dt,
            vix=20.0,
            treasury_10y=4.35,
            credit_spread=3.8,
            observed_on="2026-06-08",
        ),
    )

    snapshot = pipeline.build_snapshot(as_of=as_of)

    assert snapshot.regime == "balanced"
    assert snapshot.risk_budget_multiplier == 0.75
    assert snapshot.source_freshness["global_context"]["status"] == "stale"
    assert "stale_macro_inputs" in snapshot.invalidators
