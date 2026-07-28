"""Pure point-in-time peer and normalization-cohort resolution."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime
from statistics import fmean

from src.trading.ranking.config import RankingConfig
from src.trading.ranking.percentiles import liquidity_quartiles
from src.trading.ranking.records import (
    AssetSnapshot,
    CohortResolution,
    CohortSelection,
    PeerBasketMembership,
    RawRankingMetrics,
    TickerRelationship,
)


def resolve_cohorts(
    metrics_by_ticker: Mapping[str, RawRankingMetrics],
    assets: Iterable[AssetSnapshot],
    peer_baskets: Iterable[PeerBasketMembership],
    relationships: Iterable[TickerRelationship],
    decision_time: datetime,
    config: RankingConfig,
) -> dict[str, CohortResolution]:
    """Resolve exact cohorts using only relationships valid at decision time."""
    metrics = {_ticker(key): value for key, value in metrics_by_ticker.items()}
    all_tickers = tuple(sorted(metrics))
    eligible = tuple(
        ticker for ticker in all_tickers if metrics[ticker].is_fully_eligible
    )
    eligible_set = set(eligible)
    asset_by_ticker = {_ticker(asset.ticker): asset for asset in assets if _ticker(asset.ticker) in eligible_set}
    basket_records = tuple(
        record
        for record in peer_baskets
        if record.ticker in eligible_set and _valid_at(record, decision_time)
    )
    relationship_records = _latest_relationships(
        (record for record in relationships if record.ticker in eligible_set),
        decision_time,
    )
    baskets_by_id = _group_baskets(basket_records)
    basket_ids_by_ticker: dict[str, list[str]] = {}
    for basket_id, records in baskets_by_id.items():
        for record in records:
            basket_ids_by_ticker.setdefault(record.ticker, []).append(basket_id)
    relationship_groups = _group_relationships(relationship_records)
    quartiles = liquidity_quartiles(
        {ticker: getattr(asset_by_ticker.get(ticker), "average_dollar_volume", None) for ticker in eligible}
    )
    market = CohortSelection(
        "market",
        "market",
        eligible,
        tuple(
            ref
            for ticker in eligible
            for ref in asset_by_ticker.get(ticker, AssetSnapshot(ticker, None)).source_refs
        ),
    )

    resolutions: dict[str, CohortResolution] = {}
    for ticker in all_tickers:
        configured = _configured_selection(ticker, basket_ids_by_ticker, baskets_by_id)
        industry = _relationship_selection(ticker, "industry", relationship_records, relationship_groups)
        sector_candidate = _relationship_selection(
            ticker,
            "sector",
            relationship_records,
            relationship_groups,
        )
        raw_sector_relative_20d = _relative_return(
            ticker,
            sector_candidate.members,
            metrics,
        )
        sector = (
            sector_candidate
            if len(sector_candidate.members) >= config.min_cohort_size
            else CohortSelection.unavailable("sector")
        )
        peer = configured if len(configured.members) >= config.min_cohort_size else replace(
            industry,
            fallback="configured_peer",
        )
        if len(peer.members) < config.min_cohort_size:
            peer = CohortSelection.unavailable("peer")
        relative_volume = _liquidity_selection(
            ticker,
            quartiles,
            eligible,
            asset_by_ticker,
            config.min_cohort_size,
        )
        resolutions[ticker] = CohortResolution(
            ticker=ticker,
            configured_peer=configured,
            industry=industry,
            peer=peer,
            sector=sector,
            relative_volume=relative_volume,
            raw_configured_peer_relative_20d=_relative_return(ticker, configured.members, metrics),
            raw_industry_relative_20d=_relative_return(ticker, industry.members, metrics),
            raw_sector_relative_20d=raw_sector_relative_20d,
            market=market,
        )
    return resolutions


def _valid_at(record: object, decision_time: datetime) -> bool:
    return (
        record.available_for_decision_at <= decision_time  # type: ignore[attr-defined]
        and record.valid_from <= decision_time  # type: ignore[attr-defined]
        and (record.valid_to is None or decision_time < record.valid_to)  # type: ignore[attr-defined]
    )


def _latest_relationships(
    records: Iterable[TickerRelationship],
    decision_time: datetime,
) -> tuple[TickerRelationship, ...]:
    selected: dict[tuple[str, str], TickerRelationship] = {}
    for record in records:
        if record.relationship_type not in {"industry", "sector"} or not _valid_at(record, decision_time):
            continue
        key = (record.ticker, record.relationship_type)
        current = selected.get(key)
        ordering = (record.valid_from, record.available_for_decision_at, record.relationship_id)
        if current is None or ordering > (
            current.valid_from,
            current.available_for_decision_at,
            current.relationship_id,
        ):
            selected[key] = record
    return tuple(selected[key] for key in sorted(selected))


def _group_baskets(
    records: tuple[PeerBasketMembership, ...],
) -> dict[str, tuple[PeerBasketMembership, ...]]:
    groups: dict[str, list[PeerBasketMembership]] = {}
    for record in records:
        groups.setdefault(record.basket_id, []).append(record)
    return {
        key: tuple(sorted(value, key=lambda record: record.ticker))
        for key, value in groups.items()
    }


def _group_relationships(
    records: tuple[TickerRelationship, ...],
) -> dict[tuple[str, str], tuple[TickerRelationship, ...]]:
    groups: dict[tuple[str, str], list[TickerRelationship]] = {}
    for record in records:
        groups.setdefault((record.relationship_type, record.relationship_id), []).append(record)
    return {
        key: tuple(sorted(value, key=lambda record: record.ticker))
        for key, value in groups.items()
    }


def _configured_selection(
    ticker: str,
    basket_ids_by_ticker: Mapping[str, list[str]],
    baskets_by_id: Mapping[str, tuple[PeerBasketMembership, ...]],
) -> CohortSelection:
    basket_ids = sorted(set(basket_ids_by_ticker.get(ticker, ())))
    if not basket_ids:
        return CohortSelection.unavailable("configured_peer")
    basket_id = basket_ids[0]
    records = baskets_by_id[basket_id]
    return CohortSelection(
        "configured_peer",
        basket_id,
        tuple(record.ticker for record in records),
        tuple(ref for record in records for ref in record.source_refs),
    )


def _relationship_selection(
    ticker: str,
    relationship_type: str,
    records: tuple[TickerRelationship, ...],
    groups: Mapping[tuple[str, str], tuple[TickerRelationship, ...]],
) -> CohortSelection:
    target = next(
        (record for record in records if record.ticker == ticker and record.relationship_type == relationship_type),
        None,
    )
    if target is None:
        return CohortSelection.unavailable(relationship_type)
    members = groups[(relationship_type, target.relationship_id)]
    return CohortSelection(
        relationship_type,
        target.relationship_id,
        tuple(record.ticker for record in members),
        tuple(ref for record in members for ref in record.source_refs),
    )


def _liquidity_selection(
    ticker: str,
    quartiles: Mapping[str, str | None],
    eligible: tuple[str, ...],
    assets: Mapping[str, AssetSnapshot],
    min_size: int,
) -> CohortSelection:
    quartile = quartiles.get(ticker)
    members = tuple(sorted(key for key, value in quartiles.items() if value == quartile)) if quartile else ()
    if quartile is not None and len(members) >= min_size:
        refs = tuple(ref for member in members for ref in assets.get(member, AssetSnapshot(member, None)).source_refs)
        return CohortSelection("liquidity", quartile, members, refs)
    refs = tuple(ref for member in eligible for ref in assets.get(member, AssetSnapshot(member, None)).source_refs)
    return CohortSelection("market", "market", eligible, refs, fallback="liquidity")


def _relative_return(
    ticker: str,
    members: tuple[str, ...],
    metrics: Mapping[str, RawRankingMetrics],
) -> float | None:
    target = metrics[ticker].return_20d
    values = [metrics[member].return_20d for member in members if metrics[member].return_20d is not None]
    if target is None or not values:
        return None
    return target - fmean(values)


def _ticker(value: str) -> str:
    return str(value).strip().upper()
