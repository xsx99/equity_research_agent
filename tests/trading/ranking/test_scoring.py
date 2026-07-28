from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from src.trading.ranking import RankingConfig, RawRankingMetrics
from src.trading.ranking.forced import resolve_forced_tickers
from src.trading.ranking.peers import resolve_cohorts
from src.trading.ranking.records import (
    AssetSnapshot,
    CohortResolution,
    CohortSelection,
    NormalizedRankingComponents,
    PeerBasketMembership,
    TickerRelationship,
)
from src.trading.ranking.scoring import (
    rank_universe,
    score_components,
)


DECISION_TIME = datetime(2026, 7, 22, 13, 0, tzinfo=timezone.utc)


def _raw(ticker: str, **overrides: object) -> RawRankingMetrics:
    values: dict[str, object] = {
        "ticker": ticker,
        "return_1d": 0.01,
        "return_5d": 0.05,
        "return_20d": 0.20,
        "return_60d": 0.40,
        "alpha_vs_spy_5d": 0.01,
        "alpha_vs_spy_20d": 0.10,
        "alpha_vs_spy_60d": 0.20,
        "relative_volume_20d": 1.5,
        "realized_volatility_20d": 0.20,
        "drawdown_60d": -0.10,
        "one_day_concentration_20d": 0.20,
        "is_fully_eligible": True,
        "missing_inputs": (),
        "bar_count": 61,
        "last_bar_date": date(2026, 7, 21),
        "all_bars_adjusted": True,
        "all_bars_split_adjusted": True,
        "adjustment_sources": ("fixture",),
        "source_refs": (f"bars:{ticker}",),
        "max_available_for_decision_at": DECISION_TIME - timedelta(hours=1),
    }
    values.update(overrides)
    return RawRankingMetrics(**values)  # type: ignore[arg-type]


def _asset(
    ticker: str,
    dollar_volume: float | None,
    *,
    session_lag: int = 0,
    freshness_classification: str | None = None,
) -> AssetSnapshot:
    return AssetSnapshot(
        ticker=ticker,
        average_dollar_volume=dollar_volume,
        freshness_session_lag=session_lag,
        freshness_classification=freshness_classification,
        source_refs=(f"asset:{ticker}",),
    )


def _relationship(
    ticker: str,
    kind: str,
    value: str,
    *,
    available_at: datetime | None = None,
) -> TickerRelationship:
    return TickerRelationship(
        ticker=ticker,
        relationship_type=kind,
        relationship_id=value,
        valid_from=DECISION_TIME - timedelta(days=30),
        valid_to=None,
        available_for_decision_at=available_at or DECISION_TIME - timedelta(days=1),
        source_refs=(f"rel:{ticker}:{kind}:{value}",),
    )


def _basket(
    ticker: str,
    basket_id: str,
    *,
    available_at: datetime | None = None,
) -> PeerBasketMembership:
    return PeerBasketMembership(
        ticker=ticker,
        basket_id=basket_id,
        valid_from=DECISION_TIME - timedelta(days=30),
        valid_to=None,
        available_for_decision_at=available_at or DECISION_TIME - timedelta(days=1),
        source_refs=(f"basket:{basket_id}:{ticker}",),
    )


def _components(**overrides: object) -> NormalizedRankingComponents:
    values: dict[str, object] = {
        "peer_or_fallback_20d_percentile": 0.5,
        "sector_or_fallback_20d_percentile": 0.5,
        "market_20d_alpha_percentile": 0.5,
        "relative_strength_60d_persistence": 0.5,
        "multi_horizon_direction_agreement": 0.5,
        "relative_volume_percentile": 0.5,
        "realized_volatility_percentile": 0.0,
        "drawdown_severity_percentile": 0.0,
        "one_day_concentration_20d": 0.0,
    }
    values.update(overrides)
    return NormalizedRankingComponents(**values)  # type: ignore[arg-type]


def _unavailable_resolution(ticker: str, market: tuple[str, ...]) -> CohortResolution:
    return CohortResolution(
        ticker=ticker,
        configured_peer=CohortSelection.unavailable("configured_peer"),
        industry=CohortSelection.unavailable("industry"),
        peer=CohortSelection.unavailable("peer"),
        sector=CohortSelection.unavailable("sector"),
        relative_volume=CohortSelection("market", "market", market, ()),
        raw_configured_peer_relative_20d=None,
        raw_industry_relative_20d=None,
        raw_sector_relative_20d=None,
    )


def test_point_in_time_cohorts_prefer_valid_configured_peers_and_retain_provenance() -> None:
    metrics = {
        ticker: _raw(ticker, return_20d=value)
        for ticker, value in {"A": 0.30, "B": 0.10, "C": 0.20, "D": 0.00}.items()
    }
    assets = [_asset(ticker, volume) for ticker, volume in zip(metrics, (10, 20, 30, 40))]
    baskets = [_basket("A", "tech-leaders"), _basket("B", "tech-leaders")]
    baskets.append(_basket("C", "tech-leaders", available_at=DECISION_TIME + timedelta(seconds=1)))
    relationships = [
        *[_relationship(ticker, "industry", "chips") for ticker in metrics],
        *[_relationship(ticker, "sector", "technology") for ticker in metrics],
    ]

    resolutions = resolve_cohorts(
        metrics,
        assets,
        baskets,
        relationships,
        DECISION_TIME,
        RankingConfig(min_cohort_size=2),
    )

    resolution = resolutions["A"]
    assert resolution.market is not None
    assert resolution.market.members == ("A", "B", "C", "D")
    assert resolution.peer.cohort_type == "configured_peer"
    assert resolution.peer.cohort_id == "tech-leaders"
    assert resolution.peer.members == ("A", "B")
    assert resolution.peer.size == 2
    assert resolution.peer.fallback is None
    assert resolution.peer.source_refs == (
        "basket:tech-leaders:A",
        "basket:tech-leaders:B",
    )
    assert resolution.configured_peer.members == ("A", "B")
    assert resolution.industry.members == ("A", "B", "C", "D")
    assert resolution.sector.members == ("A", "B", "C", "D")
    assert resolution.raw_configured_peer_relative_20d == pytest.approx(0.10)
    assert resolution.raw_industry_relative_20d == pytest.approx(0.15)
    assert resolution.raw_sector_relative_20d == pytest.approx(0.15)
    assert "C" not in resolution.configured_peer.members


def test_peer_falls_back_only_to_sufficient_industry_and_sector_never_to_market() -> None:
    metrics = {ticker: _raw(ticker) for ticker in ("A", "B", "C")}
    assets = [_asset(ticker, 10.0) for ticker in metrics]
    relationships = [
        _relationship("A", "industry", "chips"),
        _relationship("B", "industry", "chips"),
        _relationship("A", "sector", "technology"),
    ]

    resolutions = resolve_cohorts(
        metrics,
        assets,
        (),
        relationships,
        DECISION_TIME,
        RankingConfig(min_cohort_size=2),
    )

    assert resolutions["A"].peer.cohort_type == "industry"
    assert resolutions["A"].peer.fallback == "configured_peer"
    assert resolutions["A"].peer.members == ("A", "B")
    assert resolutions["C"].peer.cohort_type == "unavailable"
    assert resolutions["A"].sector.cohort_type == "unavailable"
    assert resolutions["A"].raw_sector_relative_20d == 0.0
    assert resolutions["C"].sector.cohort_type == "unavailable"


def test_relative_volume_uses_liquidity_quartile_or_market_fallback() -> None:
    metrics = {ticker: _raw(ticker) for ticker in "ABCDEFGH"}
    assets = [_asset(ticker, float(index)) for index, ticker in enumerate(metrics, 1)]
    resolutions = resolve_cohorts(
        metrics,
        assets,
        (),
        (),
        DECISION_TIME,
        RankingConfig(min_cohort_size=2),
    )
    assert resolutions["A"].relative_volume.cohort_type == "liquidity"
    assert resolutions["A"].relative_volume.members == ("A", "B")

    missing_assets = [replace(asset, average_dollar_volume=None) if asset.ticker == "A" else asset for asset in assets]
    fallback = resolve_cohorts(
        metrics,
        missing_assets,
        (),
        (),
        DECISION_TIME,
        RankingConfig(min_cohort_size=2),
    )
    assert fallback["A"].relative_volume.cohort_type == "market"
    assert fallback["A"].relative_volume.fallback == "liquidity"
    assert fallback["A"].relative_volume.members == tuple(metrics)


@pytest.mark.parametrize(
    ("component", "expected"),
    [
        ("peer_or_fallback_20d_percentile", 0.30),
        ("sector_or_fallback_20d_percentile", 0.20),
        ("market_20d_alpha_percentile", 0.15),
        ("relative_strength_60d_persistence", 0.15),
        ("multi_horizon_direction_agreement", 0.10),
        ("relative_volume_percentile", 0.10),
    ],
)
def test_v1_positive_component_weights_are_exact(component: str, expected: float) -> None:
    values = {name: 0.0 for name in RankingConfig().positive_weights}
    values[component] = 1.0
    scored = score_components(_components(**values), RankingConfig())
    assert scored.score == pytest.approx(expected)


def test_missing_optional_peer_and_sector_are_omitted_and_weights_renormalize() -> None:
    scored = score_components(
        _components(
            peer_or_fallback_20d_percentile=None,
            sector_or_fallback_20d_percentile=None,
            market_20d_alpha_percentile=1.0,
            relative_strength_60d_persistence=1.0,
            multi_horizon_direction_agreement=1.0,
            relative_volume_percentile=1.0,
        ),
        RankingConfig(),
    )
    assert scored.status == "ranked"
    assert scored.positive_score == pytest.approx(1.0)
    assert scored.score == pytest.approx(1.0)
    assert scored.coverage == pytest.approx(0.50)


@pytest.mark.parametrize(
    "component",
    [
        "market_20d_alpha_percentile",
        "relative_strength_60d_persistence",
        "multi_horizon_direction_agreement",
        "relative_volume_percentile",
    ],
)
def test_each_required_missing_component_makes_score_insufficient(component: str) -> None:
    scored = score_components(replace(_components(), **{component: None}), RankingConfig())
    assert scored.status == "insufficient_data"
    assert scored.score is None
    assert scored.missing_inputs == (component,)


def test_insufficient_score_preserves_optional_and_required_missing_components() -> None:
    scored = score_components(
        _components(
            peer_or_fallback_20d_percentile=None,
            sector_or_fallback_20d_percentile=None,
            market_20d_alpha_percentile=None,
        ),
        RankingConfig(),
    )
    assert scored.missing_inputs == (
        "peer_or_fallback_20d_percentile",
        "sector_or_fallback_20d_percentile",
        "market_20d_alpha_percentile",
    )


@pytest.mark.parametrize(
    ("ratio", "expected"),
    [(0.35, 0.0), (0.50, 0.05), (0.65, 0.10), (0.95, 0.10)],
)
def test_concentration_penalty_threshold_slope_and_max(ratio: float, expected: float) -> None:
    scored = score_components(
        _components(one_day_concentration_20d=ratio),
        RankingConfig(),
    )
    assert scored.concentration_penalty == pytest.approx(expected)


@pytest.mark.parametrize(
    ("volatility", "drawdown", "expected_vol", "expected_drawdown"),
    [(0.50, 0.50, 0.0, 0.0), (0.75, 0.75, 0.025, 0.025), (1.0, 1.0, 0.05, 0.05)],
)
def test_risk_sub_penalties_and_combined_max(
    volatility: float,
    drawdown: float,
    expected_vol: float,
    expected_drawdown: float,
) -> None:
    scored = score_components(
        _components(
            realized_volatility_percentile=volatility,
            drawdown_severity_percentile=drawdown,
        ),
        RankingConfig(),
    )
    assert scored.volatility_penalty == pytest.approx(expected_vol)
    assert scored.drawdown_penalty == pytest.approx(expected_drawdown)
    assert scored.risk_penalty == pytest.approx(min(expected_vol + expected_drawdown, 0.10))


def test_final_score_clamps_at_zero_after_both_penalties() -> None:
    scored = score_components(
        _components(
            peer_or_fallback_20d_percentile=0.0,
            sector_or_fallback_20d_percentile=0.0,
            market_20d_alpha_percentile=0.0,
            relative_strength_60d_persistence=0.0,
            multi_horizon_direction_agreement=0.0,
            relative_volume_percentile=0.0,
            one_day_concentration_20d=1.0,
            realized_volatility_percentile=1.0,
            drawdown_severity_percentile=1.0,
        ),
        RankingConfig(),
    )
    assert scored.score == 0.0
    assert scored.concentration_penalty == 0.10
    assert scored.risk_penalty == 0.10


def test_confidence_and_explanations_preserve_all_inputs_deterministically() -> None:
    cohort = CohortSelection(
        "configured_peer",
        "leaders",
        ("A", *(f"T{i}" for i in range(14))),
        ("basket:1",),
    )
    resolution = CohortResolution(
        ticker="A",
        configured_peer=cohort,
        industry=CohortSelection.unavailable("industry"),
        peer=cohort,
        sector=CohortSelection.unavailable("sector"),
        relative_volume=CohortSelection("market", "market", ("A",), ()),
        raw_configured_peer_relative_20d=0.1,
        raw_industry_relative_20d=None,
        raw_sector_relative_20d=None,
    )
    result = rank_universe(
        {"A": _raw("A")},
        [_asset("A", 1_000_000.0)],
        resolutions={"A": resolution},
        benchmark_horizons_by_ticker={"A": 2},
        config=RankingConfig(),
    )
    row = result.full_cohort[0]
    assert row.coverage == 0.80
    assert row.freshness == 1.0
    assert row.cohort_quality == pytest.approx(0.5)
    assert row.benchmark_coverage == pytest.approx(2 / 3)
    assert row.confidence == pytest.approx(0.50 * 0.80 + 0.20 + 0.20 * 0.5 + 0.10 * 2 / 3)
    assert tuple(item.name for item in row.positive_contributors) == tuple(
        sorted(item.name for item in row.positive_contributors)
    )
    assert tuple(item.name for item in row.negative_contributors) == tuple(
        sorted(item.name for item in row.negative_contributors)
    )
    assert dict(row.normalized_metrics)["multi_horizon_direction_agreement"] == 1.0
    assert row.missing_inputs == ("sector_or_fallback_20d_percentile",)


def test_cohort_quality_uses_most_specific_component_actually_available() -> None:
    unavailable_peer_metric = CohortSelection("configured_peer", "leaders", ("Z",), ())
    sector = CohortSelection("sector", "technology", ("A", *(f"T{i}" for i in range(29))), ())
    resolution = CohortResolution(
        ticker="A",
        configured_peer=unavailable_peer_metric,
        industry=CohortSelection.unavailable("industry"),
        peer=unavailable_peer_metric,
        sector=sector,
        relative_volume=CohortSelection("market", "market", ("A",), ()),
        raw_configured_peer_relative_20d=None,
        raw_industry_relative_20d=None,
        raw_sector_relative_20d=0.0,
    )
    row = rank_universe(
        {"A": _raw("A")},
        [_asset("A", 100)],
        resolutions={"A": resolution},
        config=RankingConfig(),
    ).full_cohort[0]
    assert row.cohort_quality == pytest.approx(0.75)


def test_market_components_supply_primary_confidence_fallback_for_insufficient_forced_row() -> None:
    market = CohortSelection(
        "market",
        "market",
        ("A", *(f"T{i}" for i in range(14))),
        (),
    )
    resolution = CohortResolution(
        ticker="A",
        configured_peer=CohortSelection.unavailable("configured_peer"),
        industry=CohortSelection.unavailable("industry"),
        peer=CohortSelection.unavailable("peer"),
        sector=CohortSelection.unavailable("sector"),
        relative_volume=CohortSelection.unavailable("liquidity"),
        raw_configured_peer_relative_20d=None,
        raw_industry_relative_20d=None,
        raw_sector_relative_20d=None,
        market=market,
    )
    row = rank_universe(
        {"A": _raw("A")},
        [_asset("A", 100)],
        resolutions={"A": resolution},
        manual_requests=("A",),
        config=RankingConfig(),
    ).full_cohort[0]
    assert row.status == "insufficient_data"
    assert row.coverage == pytest.approx(0.40)
    assert row.cohort_quality == pytest.approx(0.40 * 1 / 30)
    assert row.confidence == pytest.approx(
        0.50 * 0.40 + 0.20 + 0.20 * (0.40 / 30) + 0.10
    )


def test_market_confidence_fallback_uses_eligible_universe_when_resolution_omits_market() -> None:
    metrics = {ticker: _raw(ticker) for ticker in "ABC"}
    resolutions = {
        ticker: CohortResolution(
            ticker=ticker,
            configured_peer=CohortSelection.unavailable("configured_peer"),
            industry=CohortSelection.unavailable("industry"),
            peer=CohortSelection.unavailable("peer"),
            sector=CohortSelection.unavailable("sector"),
            relative_volume=CohortSelection.unavailable("liquidity"),
            raw_configured_peer_relative_20d=None,
            raw_industry_relative_20d=None,
            raw_sector_relative_20d=None,
        )
        for ticker in metrics
    }
    result = rank_universe(
        metrics,
        [_asset(ticker, 100) for ticker in metrics],
        resolutions=resolutions,
        config=RankingConfig(),
    )
    assert result.full_cohort[0].cohort_quality == pytest.approx(0.40 * 3 / 30)


@pytest.mark.parametrize(
    ("alphas", "expected"),
    [
        ((-0.1, -0.2, -0.3), 0.0),
        ((0.1, -0.2, -0.3), 1 / 3),
        ((0.1, 0.2, -0.3), 2 / 3),
        ((0.1, 0.2, 0.3), 1.0),
    ],
)
def test_direction_agreement_is_exact_fraction_positive(
    alphas: tuple[float, float, float],
    expected: float,
) -> None:
    metrics = {
        "A": _raw(
            "A",
            alpha_vs_spy_5d=alphas[0],
            alpha_vs_spy_20d=alphas[1],
            alpha_vs_spy_60d=alphas[2],
        )
    }
    resolution = _unavailable_resolution("A", ("A",))
    row = rank_universe(
        metrics,
        [_asset("A", 100)],
        resolutions={"A": resolution},
        config=RankingConfig(confidence_floor=0.0),
    ).full_cohort[0]
    assert dict(row.normalized_metrics)["multi_horizon_direction_agreement"] == pytest.approx(expected)


def test_freshness_session_lag_scores_one_half_then_zero() -> None:
    metrics = {ticker: _raw(ticker) for ticker in "ABC"}
    assets = [_asset("A", 30, session_lag=0), _asset("B", 20, session_lag=1), _asset("C", 10, session_lag=2)]
    resolutions = {ticker: _unavailable_resolution(ticker, tuple(metrics)) for ticker in metrics}
    result = rank_universe(metrics, assets, resolutions=resolutions, config=RankingConfig())
    by_ticker = {row.ticker: row for row in result.full_cohort}
    assert by_ticker["A"].freshness == 1.0
    assert by_ticker["B"].freshness == 0.5
    assert by_ticker["C"].freshness == 0.0


def test_supplied_freshness_classification_overrides_session_lag() -> None:
    metrics = {ticker: _raw(ticker) for ticker in "ABC"}
    assets = [
        _asset("A", 30, session_lag=9, freshness_classification="expected"),
        _asset("B", 20, session_lag=9, freshness_classification="one_session_late"),
        _asset("C", 10, session_lag=0, freshness_classification="stale"),
    ]
    resolutions = {ticker: _unavailable_resolution(ticker, tuple(metrics)) for ticker in metrics}
    result = rank_universe(metrics, assets, resolutions=resolutions, config=RankingConfig())
    by_ticker = {row.ticker: row for row in result.full_cohort}
    assert by_ticker["A"].freshness == 1.0
    assert by_ticker["B"].freshness == 0.5
    assert by_ticker["C"].freshness == 0.0


def test_rank_order_percentiles_shortlist_and_low_confidence_rank() -> None:
    metrics = {
        "A": _raw("A", alpha_vs_spy_20d=0.30),
        "B": _raw("B", alpha_vs_spy_20d=0.20),
        "C": _raw("C", alpha_vs_spy_20d=0.10),
    }
    assets = [_asset("A", 100), _asset("B", 300), _asset("C", 200, session_lag=2)]
    resolutions = {ticker: _unavailable_resolution(ticker, tuple(metrics)) for ticker in metrics}
    result = rank_universe(
        metrics,
        assets,
        resolutions=resolutions,
        config=RankingConfig(top_n=2, confidence_floor=0.30),
    )
    assert tuple(row.ticker for row in result.full_cohort) == ("A", "B", "C")
    assert tuple(row.overall_rank for row in result.full_cohort) == (0, 1, 2)
    assert tuple(row.overall_percentile for row in result.full_cohort) == (1.0, 0.5, 0.0)
    assert result.automatic_tickers == ("A", "B")


def test_automatic_shortlist_can_be_smaller_than_top_n_after_confidence_filter() -> None:
    metrics = {ticker: _raw(ticker) for ticker in "ABC"}
    assets = [
        _asset("A", 30, session_lag=0),
        _asset("B", 20, session_lag=1),
        _asset("C", 10, session_lag=2),
    ]
    resolutions = {ticker: _unavailable_resolution(ticker, tuple(metrics)) for ticker in metrics}
    result = rank_universe(
        metrics,
        assets,
        resolutions=resolutions,
        config=RankingConfig(top_n=5, confidence_floor=0.50),
    )
    assert result.automatic_tickers == ("A",)


def test_tie_breakers_use_confidence_volume_missing_last_then_ticker() -> None:
    metrics = {ticker: _raw(ticker) for ticker in "ABCD"}
    assets = [_asset("A", None), _asset("B", 10), _asset("C", 20), _asset("D", 20)]
    resolutions = {ticker: _unavailable_resolution(ticker, tuple(metrics)) for ticker in metrics}
    result = rank_universe(metrics, assets, resolutions=resolutions, config=RankingConfig(confidence_floor=0.0))
    assert tuple(row.ticker for row in result.full_cohort) == ("C", "D", "B", "A")


def test_forced_reasons_are_independent_deduplicated_and_manual_exclude_wins() -> None:
    forced = resolve_forced_tickers(
        manual_requests=("a", "B", "A"),
        watchlist_pins=("A",),
        open_positions=("A", "C"),
        manual_includes=("A", "D"),
        manual_excludes=("D",),
    )
    assert forced == {
        "A": ("manual_request", "watchlist_pin", "open_position", "manual_include"),
        "B": ("manual_request",),
        "C": ("open_position",),
    }


def test_forced_insufficient_row_enters_research_without_score_or_rank() -> None:
    metrics = {
        "A": _raw("A"),
        "Z": _raw("Z", alpha_vs_spy_20d=None, is_fully_eligible=False, missing_inputs=("alpha_vs_spy_20d",)),
    }
    assets = [_asset("A", 100), _asset("Z", 50)]
    resolutions = {ticker: _unavailable_resolution(ticker, tuple(metrics)) for ticker in metrics}
    result = rank_universe(
        metrics,
        assets,
        resolutions=resolutions,
        manual_requests=("Z",),
        manual_excludes=("A",),
        config=RankingConfig(confidence_floor=0.0),
    )
    assert tuple(row.ticker for row in result.full_cohort) == ("Z",)
    row = result.full_cohort[0]
    assert row.status == "insufficient_data"
    assert row.score is None
    assert row.overall_rank is None
    assert row.overall_percentile is None
    assert row.forced_reasons == ("manual_request",)
    assert result.automatic_tickers == ()
    assert result.research_tickers == ("Z",)


def test_raw_metrics_eligibility_is_a_hard_gate_even_when_components_exist() -> None:
    metrics = {
        "A": _raw(
            "A",
            is_fully_eligible=False,
            missing_inputs=("unadjusted_bar",),
        )
    }
    result = rank_universe(
        metrics,
        [_asset("A", 100)],
        resolutions={"A": _unavailable_resolution("A", ("A",))},
        manual_requests=("A",),
        config=RankingConfig(confidence_floor=0.0),
    )
    row = result.full_cohort[0]
    assert row.status == "insufficient_data"
    assert row.score is None
    assert row.overall_rank is None
    assert row.overall_percentile is None
    assert row.missing_inputs == (
        "market_20d_alpha_percentile",
        "peer_or_fallback_20d_percentile",
        "raw_metrics_not_fully_eligible",
        "relative_strength_60d_persistence",
        "relative_volume_percentile",
        "sector_or_fallback_20d_percentile",
        "unadjusted_bar",
    )
    assert result.automatic_tickers == ()
    assert result.research_tickers == ("A",)


def test_ineligible_numeric_row_cannot_change_eligible_normalization_score_or_rank() -> None:
    config = RankingConfig(confidence_floor=0.0)
    alone_metrics = {"A": _raw("A")}
    alone = rank_universe(
        alone_metrics,
        [_asset("A", 100)],
        resolutions={"A": _unavailable_resolution("A", ("A",))},
        config=config,
    )
    with_outlier_metrics = {
        "A": _raw("A"),
        "Z": _raw(
            "Z",
            alpha_vs_spy_20d=999.0,
            alpha_vs_spy_60d=999.0,
            relative_volume_20d=999.0,
            realized_volatility_20d=999.0,
            drawdown_60d=-0.99,
            is_fully_eligible=False,
            missing_inputs=("invalid_adjustment",),
        ),
    }
    with_outlier = rank_universe(
        with_outlier_metrics,
        [_asset("A", 100), _asset("Z", 999)],
        resolutions={
            ticker: _unavailable_resolution(ticker, ("A", "Z"))
            for ticker in with_outlier_metrics
        },
        manual_requests=("Z",),
        config=config,
    )
    alone_a = alone.full_cohort[0]
    with_outlier_a = next(row for row in with_outlier.full_cohort if row.ticker == "A")
    assert with_outlier_a.normalized_metrics == alone_a.normalized_metrics
    assert with_outlier_a.score == alone_a.score
    assert with_outlier_a.overall_rank == alone_a.overall_rank == 0
    outlier = next(row for row in with_outlier.full_cohort if row.ticker == "Z")
    assert outlier.status == "insufficient_data"
    assert outlier.overall_rank is None
    assert with_outlier.research_tickers == ("A", "Z")


def test_ineligible_rows_do_not_count_toward_cohorts_liquidity_or_market_size() -> None:
    metrics = {ticker: _raw(ticker) for ticker in "ABCDEFGH"}
    metrics["Z"] = _raw("Z", is_fully_eligible=False, missing_inputs=("invalid_bar",))
    assets = [
        *[_asset(ticker, float(index)) for index, ticker in enumerate("ABCDEFGH", 1)],
        _asset("Z", 1.5),
    ]
    shared_relationships = [
        _relationship("A", "industry", "two-member-industry"),
        _relationship("Z", "industry", "two-member-industry"),
        _relationship("A", "sector", "two-member-sector"),
        _relationship("Z", "sector", "two-member-sector"),
    ]
    resolutions = resolve_cohorts(
        metrics,
        assets,
        (_basket("A", "two-member-basket"), _basket("Z", "two-member-basket")),
        shared_relationships,
        DECISION_TIME,
        RankingConfig(min_cohort_size=2),
    )
    resolution = resolutions["A"]
    assert resolution.peer.cohort_type == "unavailable"
    assert resolution.sector.cohort_type == "unavailable"
    assert resolution.relative_volume.cohort_type == "liquidity"
    assert resolution.relative_volume.members == ("A", "B")
    assert resolution.market is not None
    assert resolution.market.members == tuple("ABCDEFGH")
    assert resolutions["Z"].market is not None
    assert resolutions["Z"].market.size == 8
