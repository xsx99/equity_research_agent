"""Pure normalization, v1 scoring, confidence, ranking, and selection."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace

from src.trading.ranking.config import RankingConfig
from src.trading.ranking.forced import resolve_forced_tickers
from src.trading.ranking.percentiles import average_rank_percentiles
from src.trading.ranking.records import (
    AssetSnapshot,
    CohortResolution,
    Contributor,
    NormalizedRankingComponents,
    RankedTicker,
    RankingResult,
    RawRankingMetrics,
    ScoreBreakdown,
)


_REQUIRED_COMPONENTS = (
    "market_20d_alpha_percentile",
    "relative_strength_60d_persistence",
    "multi_horizon_direction_agreement",
    "relative_volume_percentile",
)
_SPECIFICITY = {
    "configured_peer": 1.0,
    "industry": 0.9,
    "sector": 0.75,
    "liquidity": 0.55,
    "market": 0.40,
}


def score_components(
    components: NormalizedRankingComponents,
    config: RankingConfig,
) -> ScoreBreakdown:
    """Apply frozen v1 positive weights and penalties."""
    available = {
        name: getattr(components, name)
        for name in config.positive_weights
        if getattr(components, name) is not None
    }
    coverage = sum(config.positive_weights[name] for name in available)
    missing = tuple(name for name in config.positive_weights if name not in available)
    required_missing = tuple(name for name in _REQUIRED_COMPONENTS if name not in available)
    concentration_penalty = config.concentration_penalty_max * _scaled_excess(
        components.one_day_concentration_20d,
        config.concentration_penalty_start,
        config.concentration_penalty_full,
    )
    volatility_penalty = config.volatility_penalty_max * _scaled_excess(
        components.realized_volatility_percentile,
        config.risk_percentile_penalty_start,
        1.0,
    )
    drawdown_penalty = config.drawdown_penalty_max * _scaled_excess(
        components.drawdown_severity_percentile,
        config.risk_percentile_penalty_start,
        1.0,
    )
    risk_penalty = min(volatility_penalty + drawdown_penalty, 0.10)
    negative = tuple(
        Contributor(name, value, -value)
        for name, value in sorted(
            (
                ("concentration_penalty", concentration_penalty),
                ("drawdown_penalty", drawdown_penalty),
                ("volatility_penalty", volatility_penalty),
            )
        )
        if value > 0
    )
    if required_missing:
        return ScoreBreakdown(
            "insufficient_data",
            None,
            None,
            concentration_penalty,
            volatility_penalty,
            drawdown_penalty,
            risk_penalty,
            coverage,
            missing,
            (),
            negative,
        )
    positive_score = sum(
        config.positive_weights[name] * float(value) for name, value in available.items()
    ) / coverage
    positive = tuple(
        Contributor(name, float(value), config.positive_weights[name] * float(value) / coverage)
        for name, value in sorted(available.items())
    )
    return ScoreBreakdown(
        "ranked",
        _clamp(positive_score - concentration_penalty - risk_penalty),
        positive_score,
        concentration_penalty,
        volatility_penalty,
        drawdown_penalty,
        risk_penalty,
        coverage,
        missing,
        positive,
        negative,
    )


def normalize_components(
    metrics_by_ticker: Mapping[str, RawRankingMetrics],
    resolutions: Mapping[str, CohortResolution],
    config: RankingConfig,
) -> dict[str, NormalizedRankingComponents]:
    """Normalize all v1 inputs against each resolved cohort."""
    tickers = tuple(sorted(metrics_by_ticker))
    alpha20 = average_rank_percentiles(
        {ticker: metrics_by_ticker[ticker].alpha_vs_spy_20d for ticker in tickers},
        singleton_percentile=config.singleton_percentile,
    )
    alpha60 = average_rank_percentiles(
        {ticker: metrics_by_ticker[ticker].alpha_vs_spy_60d for ticker in tickers},
        singleton_percentile=config.singleton_percentile,
    )
    volatility = average_rank_percentiles(
        {ticker: metrics_by_ticker[ticker].realized_volatility_20d for ticker in tickers},
        singleton_percentile=config.singleton_percentile,
    )
    drawdown = average_rank_percentiles(
        {
            ticker: (
                -metrics_by_ticker[ticker].drawdown_60d
                if metrics_by_ticker[ticker].drawdown_60d is not None
                else None
            )
            for ticker in tickers
        },
        singleton_percentile=config.singleton_percentile,
    )
    peer = _cohort_percentiles(metrics_by_ticker, resolutions, "peer", "return_20d", config)
    sector = _cohort_percentiles(metrics_by_ticker, resolutions, "sector", "return_20d", config)
    relative_volume = _cohort_percentiles(
        metrics_by_ticker,
        resolutions,
        "relative_volume",
        "relative_volume_20d",
        config,
    )
    return {
        ticker: NormalizedRankingComponents(
            peer_or_fallback_20d_percentile=peer[ticker],
            sector_or_fallback_20d_percentile=sector[ticker],
            market_20d_alpha_percentile=alpha20[ticker],
            relative_strength_60d_persistence=alpha60[ticker],
            multi_horizon_direction_agreement=_direction_agreement(metrics_by_ticker[ticker]),
            relative_volume_percentile=relative_volume[ticker],
            realized_volatility_percentile=volatility[ticker],
            drawdown_severity_percentile=drawdown[ticker],
            one_day_concentration_20d=metrics_by_ticker[ticker].one_day_concentration_20d,
        )
        for ticker in tickers
    }


def rank_universe(
    metrics_by_ticker: Mapping[str, RawRankingMetrics],
    assets: Iterable[AssetSnapshot],
    *,
    resolutions: Mapping[str, CohortResolution],
    benchmark_horizons_by_ticker: Mapping[str, int] | None = None,
    manual_requests: Iterable[str] = (),
    watchlist_pins: Iterable[str] = (),
    open_positions: Iterable[str] = (),
    manual_includes: Iterable[str] = (),
    manual_excludes: Iterable[str] = (),
    config: RankingConfig,
) -> RankingResult:
    """Score, rank, shortlist, and force tickers without external I/O."""
    excluded = {_ticker(value) for value in manual_excludes}
    metrics = {
        _ticker(ticker): metric
        for ticker, metric in metrics_by_ticker.items()
        if _ticker(ticker) not in excluded
    }
    filtered_resolutions = {ticker: resolutions[ticker] for ticker in metrics}
    asset_by_ticker = {
        asset.ticker: asset for asset in assets if asset.ticker in metrics
    }
    forced = resolve_forced_tickers(
        manual_requests=manual_requests,
        watchlist_pins=watchlist_pins,
        open_positions=open_positions,
        manual_includes=manual_includes,
        manual_excludes=manual_excludes,
    )
    normalized = normalize_components(metrics, filtered_resolutions, config)
    rows = [
        _build_row(
            ticker,
            metrics[ticker],
            asset_by_ticker.get(ticker),
            filtered_resolutions[ticker],
            normalized[ticker],
            forced.get(ticker, ()),
            (benchmark_horizons_by_ticker or {}).get(ticker),
            config,
        )
        for ticker in sorted(metrics)
    ]
    scored = sorted(
        (row for row in rows if row.status == "ranked"),
        key=lambda row: (
            -float(row.score),
            -row.confidence,
            row.average_dollar_volume is None,
            -(row.average_dollar_volume or 0.0),
            row.ticker,
        ),
    )
    count = len(scored)
    ranked = [
        replace(
            row,
            overall_rank=index,
            overall_percentile=(
                config.singleton_percentile if count == 1 else 1.0 - index / (count - 1)
            ),
        )
        for index, row in enumerate(scored)
    ]
    insufficient = sorted(
        (row for row in rows if row.status != "ranked"),
        key=lambda row: row.ticker,
    )
    full_cohort = tuple((*ranked, *insufficient))
    automatic = tuple(
        row.ticker
        for row in ranked
        if row.confidence >= config.confidence_floor
    )[: config.top_n]
    research_set = set(automatic)
    research_set.update(ticker for ticker in forced if ticker in metrics)
    research = tuple(row.ticker for row in full_cohort if row.ticker in research_set)
    return RankingResult(full_cohort, automatic, research)


def _build_row(
    ticker: str,
    metrics: RawRankingMetrics,
    asset: AssetSnapshot | None,
    resolution: CohortResolution,
    components: NormalizedRankingComponents,
    forced_reasons: tuple[str, ...],
    benchmark_horizons: int | None,
    config: RankingConfig,
) -> RankedTicker:
    score = score_components(components, config)
    freshness = _freshness(
        asset.freshness_classification if asset else None,
        asset.freshness_session_lag if asset else None,
    )
    specificity, size = _primary_cohort(resolution, components)
    cohort_quality = specificity * min(size / config.full_cohort_size, 1.0)
    benchmark_count = (
        benchmark_horizons
        if benchmark_horizons is not None
        else sum(
            value is not None
            for value in (
                metrics.alpha_vs_spy_5d,
                metrics.alpha_vs_spy_20d,
                metrics.alpha_vs_spy_60d,
            )
        )
    )
    benchmark_coverage = _clamp(benchmark_count / 3)
    confidence = _clamp(
        config.confidence_component_coverage_weight * score.coverage
        + config.confidence_freshness_weight * freshness
        + config.confidence_cohort_quality_weight * cohort_quality
        + config.confidence_benchmark_coverage_weight * benchmark_coverage
    )
    normalized_metrics = tuple(
        sorted((name, getattr(components, name)) for name in components.__dataclass_fields__)
    )
    missing = tuple(sorted(set((*metrics.missing_inputs, *score.missing_inputs))))
    return RankedTicker(
        ticker=ticker,
        status=score.status,
        score=score.score,
        confidence=confidence,
        coverage=score.coverage,
        freshness=freshness,
        cohort_quality=cohort_quality,
        benchmark_coverage=benchmark_coverage,
        average_dollar_volume=asset.average_dollar_volume if asset else None,
        overall_rank=None,
        overall_percentile=None,
        forced_reasons=forced_reasons,
        missing_inputs=missing,
        normalized_metrics=normalized_metrics,
        positive_contributors=score.positive_contributors,
        negative_contributors=score.negative_contributors,
        cohort_resolution=resolution,
    )


def _cohort_percentiles(
    metrics: Mapping[str, RawRankingMetrics],
    resolutions: Mapping[str, CohortResolution],
    selection_name: str,
    metric_name: str,
    config: RankingConfig,
) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    cache: dict[tuple[str, str | None, tuple[str, ...]], dict[str, float | None]] = {}
    for ticker in sorted(metrics):
        selection = getattr(resolutions[ticker], selection_name)
        if selection.cohort_type == "unavailable":
            result[ticker] = None
            continue
        key = (selection.cohort_type, selection.cohort_id, selection.members)
        if key not in cache:
            cache[key] = average_rank_percentiles(
                {
                    member: getattr(metrics[member], metric_name)
                    for member in selection.members
                    if member in metrics
                },
                singleton_percentile=config.singleton_percentile,
            )
        result[ticker] = cache[key].get(ticker)
    return result


def _direction_agreement(metrics: RawRankingMetrics) -> float | None:
    values = (
        metrics.alpha_vs_spy_5d,
        metrics.alpha_vs_spy_20d,
        metrics.alpha_vs_spy_60d,
    )
    if any(value is None for value in values):
        return None
    return sum(float(value) > 0 for value in values) / len(values)


def _primary_cohort(
    resolution: CohortResolution,
    components: NormalizedRankingComponents,
) -> tuple[float, int]:
    candidates = (
        (resolution.peer, components.peer_or_fallback_20d_percentile),
        (resolution.sector, components.sector_or_fallback_20d_percentile),
        (resolution.relative_volume, components.relative_volume_percentile),
    )
    for selection, value in candidates:
        if selection.cohort_type != "unavailable" and value is not None:
            return _SPECIFICITY[selection.cohort_type], len(selection.members)
    return 0.0, 0


def _freshness(classification: str | None, session_lag: int | None) -> float:
    if classification is not None:
        normalized = classification.strip().lower()
        if normalized in {"expected", "expected_last_completed_session", "current"}:
            return 1.0
        if normalized in {"one_session_late", "one_completed_session_late", "late"}:
            return 0.5
        return 0.0
    if session_lag == 0:
        return 1.0
    if session_lag == 1:
        return 0.5
    return 0.0


def _scaled_excess(value: float | None, start: float, full: float) -> float:
    if value is None:
        return 0.0
    return _clamp((float(value) - start) / (full - start))


def _clamp(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)


def _ticker(value: str) -> str:
    return str(value).strip().upper()
