from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from math import sqrt
from statistics import stdev

import pytest

from src.trading.ranking import (
    AdjustedDailyBar,
    RankingConfig,
    average_rank_percentiles,
    build_raw_metrics,
    liquidity_quartiles,
    normalize_adjusted_bars,
)


DECISION_TIME = datetime(2026, 7, 22, 13, 0, tzinfo=timezone.utc)


def _bars(
    closes: list[float | None],
    *,
    volumes: list[float | None] | None = None,
    start: date = date(2026, 4, 1),
    source_prefix: str = "fixture",
) -> list[AdjustedDailyBar]:
    volumes = volumes or [1_000.0] * len(closes)
    return [
        AdjustedDailyBar(
            session_date=start + timedelta(days=index),
            close=close,
            volume=volumes[index],
            available_for_decision_at=DECISION_TIME - timedelta(hours=len(closes) - index),
            is_adjusted=True,
            split_adjusted=True,
            adjustment_source="fixture_adjustments_v1",
            source_refs=(f"{source_prefix}:{index}",),
        )
        for index, close in enumerate(closes)
    ]


def test_raw_metrics_use_session_lookbacks_for_returns_and_spy_alpha() -> None:
    closes = [100.0 + index for index in range(61)]
    spy_closes = [200.0 + 0.5 * index for index in range(61)]

    metrics = build_raw_metrics(
        ticker="abc",
        bars=reversed(_bars(closes)),
        spy_bars=_bars(spy_closes, source_prefix="spy"),
        decision_time=DECISION_TIME,
    )

    assert metrics.ticker == "ABC"
    assert metrics.return_1d == pytest.approx(closes[-1] / closes[-2] - 1)
    assert metrics.return_5d == pytest.approx(closes[-1] / closes[-6] - 1)
    assert metrics.return_20d == pytest.approx(closes[-1] / closes[-21] - 1)
    assert metrics.return_60d == pytest.approx(closes[-1] / closes[-61] - 1)
    assert metrics.alpha_vs_spy_5d == pytest.approx(
        metrics.return_5d - (spy_closes[-1] / spy_closes[-6] - 1)
    )
    assert metrics.alpha_vs_spy_20d == pytest.approx(
        metrics.return_20d - (spy_closes[-1] / spy_closes[-21] - 1)
    )
    assert metrics.alpha_vs_spy_60d == pytest.approx(
        metrics.return_60d - (spy_closes[-1] / spy_closes[-61] - 1)
    )
    assert metrics.is_fully_eligible is True
    assert metrics.missing_inputs == ()


def test_relative_volume_excludes_latest_and_zero_baseline_is_missing() -> None:
    closes = [100.0 + index for index in range(61)]
    volumes = [500.0] * 40 + [10.0 + index for index in range(20)] + [90.0]
    metrics = build_raw_metrics(
        ticker="ABC",
        bars=_bars(closes, volumes=volumes),
        spy_bars=_bars(closes, source_prefix="spy"),
        decision_time=DECISION_TIME,
    )
    assert metrics.relative_volume_20d == pytest.approx(90.0 / sum(volumes[-21:-1]) * 20)

    zero_baseline = build_raw_metrics(
        ticker="ABC",
        bars=_bars(closes, volumes=[500.0] * 40 + [0.0] * 20 + [90.0]),
        spy_bars=_bars(closes, source_prefix="spy"),
        decision_time=DECISION_TIME,
    )
    assert zero_baseline.relative_volume_20d is None
    assert "relative_volume_20d_zero_baseline" in zero_baseline.missing_inputs
    assert zero_baseline.is_fully_eligible is False


def test_missing_latest_volume_does_not_shift_relative_volume_window() -> None:
    closes = [100.0 + index for index in range(61)]
    volumes: list[float | None] = [1_000.0] * 61
    volumes[-1] = None

    metrics = build_raw_metrics(
        ticker="ABC",
        bars=_bars(closes, volumes=volumes),
        spy_bars=_bars(closes, source_prefix="spy"),
        decision_time=DECISION_TIME,
    )

    assert metrics.relative_volume_20d is None
    assert metrics.is_fully_eligible is False
    assert "relative_volume_20d" in metrics.missing_inputs


def test_realized_volatility_drawdown_and_positive_return_concentration() -> None:
    closes = [100.0]
    daily_returns = [0.01, -0.005, 0.02, -0.01] * 15
    for daily_return in daily_returns:
        closes.append(closes[-1] * (1 + daily_return))

    metrics = build_raw_metrics(
        ticker="ABC",
        bars=_bars(closes),
        spy_bars=_bars([100.0 + index for index in range(61)], source_prefix="spy"),
        decision_time=DECISION_TIME,
    )

    last_20_returns = daily_returns[-20:]
    assert metrics.realized_volatility_20d == pytest.approx(stdev(last_20_returns) * sqrt(252))
    assert metrics.drawdown_60d == pytest.approx(closes[-1] / max(closes[-60:]) - 1)
    assert metrics.one_day_concentration_20d == pytest.approx(
        max(last_20_returns[-1], 0) / sum(max(value, 0) for value in last_20_returns)
    )


def test_zero_positive_return_sum_has_zero_concentration() -> None:
    closes = [100.0]
    for _ in range(60):
        closes.append(closes[-1] * 0.99)

    metrics = build_raw_metrics(
        ticker="ABC",
        bars=_bars(closes),
        spy_bars=_bars(closes, source_prefix="spy"),
        decision_time=DECISION_TIME,
    )

    assert metrics.one_day_concentration_20d == 0.0


def test_insufficient_history_keeps_inputs_explicit() -> None:
    metrics = build_raw_metrics(
        ticker="ABC",
        bars=_bars([100.0 + index for index in range(20)], volumes=[1_000.0] * 20),
        spy_bars=_bars([200.0 + index for index in range(61)], source_prefix="spy"),
        decision_time=DECISION_TIME,
    )

    assert metrics.is_fully_eligible is False
    assert metrics.return_1d is not None
    assert metrics.return_20d is None
    assert metrics.realized_volatility_20d is None
    assert "valid_closes_61" in metrics.missing_inputs
    assert "valid_volumes_21" in metrics.missing_inputs
    assert "return_20d" in metrics.missing_inputs
    assert "realized_volatility_20d" in metrics.missing_inputs


def test_missing_latest_close_does_not_relabel_previous_session_as_latest() -> None:
    closes: list[float | None] = [100.0 + index for index in range(61)]
    closes[-1] = None

    metrics = build_raw_metrics(
        ticker="ABC",
        bars=_bars(closes),
        spy_bars=_bars([200.0 + index for index in range(61)], source_prefix="spy"),
        decision_time=DECISION_TIME,
    )

    assert metrics.return_1d is None
    assert metrics.return_5d is None
    assert metrics.return_20d is None
    assert metrics.return_60d is None
    assert metrics.realized_volatility_20d is None
    assert metrics.drawdown_60d is None
    assert metrics.one_day_concentration_20d is None
    assert metrics.last_bar_date == date(2026, 4, 1) + timedelta(days=59)
    assert metrics.is_fully_eligible is False


def test_missing_close_keeps_return_lookbacks_on_original_sessions() -> None:
    closes: list[float | None] = [100.0 + index for index in range(61)]
    closes[-6] = None

    metrics = build_raw_metrics(
        ticker="ABC",
        bars=_bars(closes),
        spy_bars=_bars([200.0 + index for index in range(61)], source_prefix="spy"),
        decision_time=DECISION_TIME,
    )

    assert metrics.return_1d == pytest.approx(160.0 / 159.0 - 1)
    assert metrics.return_5d is None
    assert metrics.return_20d == pytest.approx(160.0 / 140.0 - 1)
    assert metrics.realized_volatility_20d is None
    assert metrics.drawdown_60d is None
    assert metrics.one_day_concentration_20d is None
    assert metrics.is_fully_eligible is False


def test_spy_alpha_requires_the_same_final_session_as_ticker() -> None:
    closes = [100.0 + index for index in range(61)]
    spy_bars = _bars(
        [200.0 + index for index in range(61)],
        start=date(2026, 3, 31),
        source_prefix="spy",
    )

    metrics = build_raw_metrics(
        ticker="ABC",
        bars=_bars(closes),
        spy_bars=spy_bars,
        decision_time=DECISION_TIME,
    )

    assert metrics.alpha_vs_spy_5d is None
    assert metrics.alpha_vs_spy_20d is None
    assert metrics.alpha_vs_spy_60d is None
    assert metrics.is_fully_eligible is False
    assert "spy_final_session_mismatch" in metrics.missing_inputs


def test_spy_alpha_requires_matching_baseline_session_for_each_horizon() -> None:
    closes = [100.0 + index for index in range(61)]
    spy_bars = _bars([200.0 + index for index in range(61)], source_prefix="spy")
    spy_bars[0] = replace(
        spy_bars[0],
        session_date=spy_bars[0].session_date - timedelta(days=1),
    )

    metrics = build_raw_metrics(
        ticker="ABC",
        bars=_bars(closes),
        spy_bars=spy_bars,
        decision_time=DECISION_TIME,
    )

    assert metrics.alpha_vs_spy_5d is not None
    assert metrics.alpha_vs_spy_20d is not None
    assert metrics.alpha_vs_spy_60d is None
    assert metrics.is_fully_eligible is False
    assert "spy_60d_session_mismatch" in metrics.missing_inputs


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
def test_non_finite_latest_bar_values_are_explicitly_missing(bad_value: float) -> None:
    closes = [100.0 + index for index in range(61)]
    volumes = [1_000.0] * 61
    closes[-1] = bad_value
    volumes[-1] = bad_value

    metrics = build_raw_metrics(
        ticker="ABC",
        bars=_bars(closes, volumes=volumes),
        spy_bars=_bars([200.0 + index for index in range(61)], source_prefix="spy"),
        decision_time=DECISION_TIME,
    )

    assert metrics.return_1d is None
    assert metrics.relative_volume_20d is None
    assert metrics.realized_volatility_20d is None
    assert metrics.drawdown_60d is None
    assert metrics.one_day_concentration_20d is None
    assert metrics.is_fully_eligible is False


def test_normalization_sorts_bars_and_excludes_future_available_bars() -> None:
    bars = _bars([100.0 + index for index in range(61)])
    future_bar = AdjustedDailyBar(
        session_date=date(2026, 7, 1),
        close=999.0,
        volume=999.0,
        available_for_decision_at=DECISION_TIME + timedelta(seconds=1),
        source_refs=("future",),
    )

    normalized = normalize_adjusted_bars([future_bar, *reversed(bars)], DECISION_TIME)

    assert normalized.invalid_reason is None
    assert len(normalized.bars) == 61
    assert [bar.session_date for bar in normalized.bars] == sorted(bar.session_date for bar in bars)
    assert "future" not in normalized.source_refs


def test_duplicate_available_session_dates_explicitly_invalidate_raw_row() -> None:
    bars = _bars([100.0 + index for index in range(61)])
    duplicate = AdjustedDailyBar(
        session_date=bars[-1].session_date,
        close=777.0,
        volume=1_000.0,
        available_for_decision_at=DECISION_TIME - timedelta(minutes=1),
        source_refs=("duplicate",),
    )

    metrics = build_raw_metrics(
        ticker="ABC",
        bars=[*bars, duplicate],
        spy_bars=_bars([200.0 + index for index in range(61)], source_prefix="spy"),
        decision_time=DECISION_TIME,
    )

    assert metrics.is_fully_eligible is False
    assert metrics.return_1d is None
    assert metrics.missing_inputs == (
        f"duplicate_session_date:{bars[-1].session_date.isoformat()}",
    )


def test_raw_metrics_retain_point_in_time_bar_provenance() -> None:
    bars = _bars([100.0 + index for index in range(61)])
    unadjusted = AdjustedDailyBar(
        session_date=bars[-1].session_date,
        close=bars[-1].close,
        volume=bars[-1].volume,
        available_for_decision_at=bars[-1].available_for_decision_at,
        is_adjusted=False,
        split_adjusted=False,
        adjustment_source="raw_provider_bar",
        source_refs=("replacement-source",),
    )
    bars[-1] = unadjusted

    metrics = build_raw_metrics(
        ticker="ABC",
        bars=bars,
        spy_bars=_bars([200.0 + index for index in range(61)], source_prefix="spy"),
        decision_time=DECISION_TIME,
    )

    assert metrics.bar_count == 61
    assert metrics.last_bar_date == bars[-1].session_date
    assert metrics.all_bars_adjusted is False
    assert metrics.all_bars_split_adjusted is False
    assert metrics.adjustment_sources == ("fixture_adjustments_v1", "raw_provider_bar")
    assert metrics.source_refs[0] == "fixture:0"
    assert "replacement-source" in metrics.source_refs
    assert "spy:0" in metrics.source_refs
    assert metrics.max_available_for_decision_at == max(
        bar.available_for_decision_at
        for bar in [*bars, *_bars([200.0 + index for index in range(61)], source_prefix="spy")]
    )


def test_unadjusted_spy_input_is_explicitly_ineligible() -> None:
    spy_bars = _bars([200.0 + index for index in range(61)], source_prefix="spy")
    spy_bars[-1] = AdjustedDailyBar(
        session_date=spy_bars[-1].session_date,
        close=spy_bars[-1].close,
        volume=spy_bars[-1].volume,
        available_for_decision_at=spy_bars[-1].available_for_decision_at,
        is_adjusted=False,
        split_adjusted=False,
        source_refs=("spy:unadjusted",),
    )

    metrics = build_raw_metrics(
        ticker="ABC",
        bars=_bars([100.0 + index for index in range(61)]),
        spy_bars=spy_bars,
        decision_time=DECISION_TIME,
    )

    assert metrics.is_fully_eligible is False
    assert metrics.alpha_vs_spy_20d is None
    assert "spy_adjusted_bars" in metrics.missing_inputs
    assert "spy_split_adjusted_bars" in metrics.missing_inputs


def test_average_rank_percentiles_handle_ties_missing_and_input_order() -> None:
    forward = average_rank_percentiles({"A": 10.0, "B": 20.0, "C": 20.0, "D": 40.0, "E": None})
    reverse = average_rank_percentiles({"E": None, "D": 40.0, "C": 20.0, "B": 20.0, "A": 10.0})

    assert forward == reverse
    assert forward == {"A": 0.0, "B": 0.5, "C": 0.5, "D": 1.0, "E": None}


def test_average_rank_percentiles_exclude_non_finite_values_deterministically() -> None:
    forward = average_rank_percentiles(
        {"NAN": float("nan"), "POS_INF": float("inf"), "NEG_INF": -float("inf"), "OK": 1.0}
    )
    reverse = average_rank_percentiles(
        {"OK": 1.0, "NEG_INF": -float("inf"), "POS_INF": float("inf"), "NAN": float("nan")}
    )

    expected = {"NAN": None, "POS_INF": None, "NEG_INF": None, "OK": 0.5}
    assert forward == expected
    assert reverse == {key: expected[key] for key in reverse}


def test_singleton_percentile_is_neutral() -> None:
    assert average_rank_percentiles({"ONLY": 42.0, "MISSING": None}) == {
        "ONLY": 0.5,
        "MISSING": None,
    }


@pytest.mark.parametrize(
    ("percentile", "expected"),
    [(0.0, "q1"), (0.249, "q1"), (0.25, "q2"), (0.5, "q3"), (0.75, "q4"), (1.0, "q4")],
)
def test_liquidity_quartile_boundaries(percentile: float, expected: str) -> None:
    quartiles = liquidity_quartiles({"ticker": percentile}, values_are_percentiles=True)
    assert quartiles["ticker"] == expected


def test_liquidity_quartiles_use_average_rank_dollar_volume_and_preserve_missing() -> None:
    assert liquidity_quartiles(
        {"LOW": 10.0, "MID1": 20.0, "MID2": 20.0, "HIGH": 40.0, "NONE": None}
    ) == {"LOW": "q1", "MID1": "q3", "MID2": "q3", "HIGH": "q4", "NONE": None}


def test_config_is_immutable_and_has_deterministic_v1_serialization() -> None:
    config = RankingConfig()

    assert config.model_version == "cross_sectional_rs_v1"
    assert config.top_n == 100
    assert config.min_cohort_size == 10
    assert config.confidence_floor == 0.60
    assert config.batch_request_sessions == 65
    assert config.positive_weights == {
        "peer_or_fallback_20d_percentile": 0.30,
        "sector_or_fallback_20d_percentile": 0.20,
        "market_20d_alpha_percentile": 0.15,
        "relative_strength_60d_persistence": 0.15,
        "multi_horizon_direction_agreement": 0.10,
        "relative_volume_percentile": 0.10,
    }
    assert config.to_json() == config.to_json()
    assert json.loads(config.to_json()) == config.to_dict()
    assert config.to_json().startswith('{"alpha_windows":[5,20,60],')
    with pytest.raises(FrozenInstanceError):
        config.top_n = 5  # type: ignore[misc]


def test_config_normalizes_sequence_inputs_to_immutable_tuples() -> None:
    return_windows = [1, 5, 20, 60]
    alpha_windows = [5, 20, 60]

    config = RankingConfig(
        return_windows=return_windows,  # type: ignore[arg-type]
        alpha_windows=alpha_windows,  # type: ignore[arg-type]
    )
    return_windows.append(120)
    alpha_windows.append(120)

    assert config.return_windows == (1, 5, 20, 60)
    assert config.alpha_windows == (5, 20, 60)
    assert json.loads(config.to_json())["return_windows"] == [1, 5, 20, 60]


@pytest.mark.parametrize(
    "overrides",
    [
        {"top_n": 0},
        {"min_cohort_size": 0},
        {"return_windows": (1, 0, 20, 60)},
        {"relative_volume_window": 0},
        {"confidence_floor": float("nan")},
        {"confidence_floor": 1.01},
        {"peer_weight": -0.01},
        {"peer_weight": float("inf")},
        {"peer_weight": 0.31},
        {"concentration_penalty_start": 0.8, "concentration_penalty_full": 0.7},
        {"concentration_penalty_max": 1.01},
    ],
)
def test_config_rejects_invalid_v1_invariants(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        RankingConfig(**overrides)  # type: ignore[arg-type]


def test_bar_records_are_immutable() -> None:
    bar = _bars([100.0])[0]
    with pytest.raises(FrozenInstanceError):
        bar.close = 99.0  # type: ignore[misc]
