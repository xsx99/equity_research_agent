"""Deterministic strategy matching for PR03 candidate scoring."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Iterable

from src.trading.signals import SignalSnapshotResult

if TYPE_CHECKING:
    from src.trading.learning.apply import LearningAdjustments


SELECTION_SOURCES = ("scanner", "manual_request", "watchlist_pin")
DEFAULT_ACTIONABLE_SCORE_THRESHOLD = 0.55
DEFERRED_SIGNAL_FAMILY_MARKERS = {
    "transcript": "full_transcript_interpretation",
    "option": "option_chain_availability",
    "readthrough": "macro_sector_readthrough",
    "macro": "macro_sector_readthrough",
}


@dataclass(frozen=True)
class StrategyDefinitionRecord:
    """In-memory view of one active strategy definition row."""

    strategy_definition_id: str
    strategy_id: str
    version: str
    display_name: str
    strategy_layer: str
    typical_horizon: str
    config_json: dict[str, Any]
    lifecycle_status: str
    is_active: bool
    source: str = "seed"

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "StrategyDefinitionRecord":
        """Build a record from seed catalog or ORM-like mappings."""
        return cls(
            strategy_definition_id=str(row.get("strategy_definition_id") or uuid.uuid4()),
            strategy_id=str(row["strategy_id"]),
            version=str(row.get("version") or "v1"),
            display_name=str(row.get("display_name") or row["strategy_id"]),
            strategy_layer=str(row.get("strategy_layer") or "tactical_pattern"),
            typical_horizon=str(row.get("typical_horizon") or "unknown"),
            config_json=dict(row.get("config_json") or {}),
            lifecycle_status=str(row.get("lifecycle_status") or "active"),
            is_active=bool(row.get("is_active", True)),
            source=str(row.get("source") or "seed"),
        )


@dataclass(frozen=True)
class StrategyRunRecord:
    """One deterministic candidate-scoring batch."""

    strategy_run_id: str
    decision_time: datetime
    snapshot_type: str
    status: str
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateScoreRecord:
    """Ranked strategy candidate produced from one point-in-time snapshot."""

    candidate_score_id: str
    strategy_run_id: str
    signal_snapshot_id: str
    ticker: str
    strategy_id: str
    strategy_version: str
    strategy_definition_id: str
    candidate_score: float
    direction: str
    action: str
    typical_horizon: str
    core_signal_evidence: dict[str, Any]
    missing_required_signals: list[str]
    unsupported_missing_signal_families: list[str]
    invalidators: list[str]
    risk_tags: list[str]
    macro_compatibility: str
    selection_source: str
    manual_request_id: str | None
    selection_reason: str
    rejection_reason: str | None
    benchmark_context: dict[str, Any]
    decision_time: datetime
    available_for_decision_at: datetime
    source_record_refs_json: list[dict[str, Any]]
    candidate_status: str = "actionable"
    actionable_score_threshold: float = DEFAULT_ACTIONABLE_SCORE_THRESHOLD
    strategy_lifecycle_status: str = "active"
    strategy_source: str = "seed"

    @property
    def is_actionable(self) -> bool:
        """Return whether this candidate can advance as an actionable primary strategy."""
        return (
            self.candidate_status == "actionable"
            and self.rejection_reason is None
            and not self.missing_required_signals
            and self.action != "no_trade"
            and self.macro_compatibility != "blocked"
            and self.candidate_score >= self.actionable_score_threshold
        )


class StrategyMatcher:
    """Score strategy definitions using only deterministic PR02 signal snapshots."""

    def __init__(self, *, learning_adjustments: "LearningAdjustments | None" = None) -> None:
        self._learning_adjustments = learning_adjustments

    def match_snapshot(
        self,
        snapshot: SignalSnapshotResult,
        strategy_definitions: Iterable[StrategyDefinitionRecord],
        *,
        strategy_run_id: str,
    ) -> list[CandidateScoreRecord]:
        """Return candidate rows for supported matches and useful rejected rows."""
        candidates: list[CandidateScoreRecord] = []
        for definition in strategy_definitions:
            if not _is_active_tactical_definition(definition):
                continue
            actionable_score_threshold = _actionable_score_threshold(definition)
            direction = _default_candidate_direction(definition)
            action = _default_candidate_action(definition)
            unsupported = _unsupported_missing_families(definition, snapshot)
            if unsupported:
                candidates.append(
                    self._build_candidate(
                        snapshot,
                        definition,
                        strategy_run_id=strategy_run_id,
                        score=0.0,
                        evidence={},
                        missing_required_signals=list(definition.config_json.get("required_signals") or []),
                        unsupported_missing_signal_families=unsupported,
                        direction=direction,
                        action="no_trade",
                        selection_reason="strategy requires source families not available in PR03 replay",
                        rejection_reason="unsupported_missing_signal_family",
                        actionable_score_threshold=actionable_score_threshold,
                    )
                )
                continue

            score, evidence, missing = _score_supported_strategy(snapshot, definition)
            if score <= 0 and not evidence:
                continue
            score = _apply_insider_modifier(score, snapshot)
            score = _apply_social_macro_modifier(score, snapshot)
            score = self._apply_learning_factor_modifier(score, definition)

            rejection_reason = None
            selection_reason = "deterministic PR02 signals matched strategy"
            negative_catalyst = _events(snapshot).get("direct_negative_catalyst_type")
            if negative_catalyst:
                score = min(score, 0.35)
                direction = "risk_warning"
                action = "no_trade"
                rejection_reason = "direct_negative_catalyst"
                selection_reason = "direct company-level negative catalyst blocks bullish candidate"

            if definition.strategy_id == "strong_theme_no_clear_near_term_entry_v1" and score > 0:
                rejection_reason = "no_clean_entry"
                action = "no_trade"
                direction = "neutral"
                selection_reason = "theme/catalyst interest exists but stock entry is not clean"

            macro_compatibility = _macro_compatibility(snapshot, definition)
            if macro_compatibility == "blocked":
                action = "no_trade"
                rejection_reason = rejection_reason or "macro_regime_blocked"
                selection_reason = "macro regime blocks this strategy"

            candidates.append(
                self._build_candidate(
                    snapshot,
                    definition,
                    strategy_run_id=strategy_run_id,
                    score=score,
                    evidence=evidence,
                    missing_required_signals=missing,
                    unsupported_missing_signal_families=[],
                    direction=direction,
                    action=action,
                    selection_reason=selection_reason,
                    rejection_reason=rejection_reason,
                    actionable_score_threshold=actionable_score_threshold,
                    macro_compatibility=macro_compatibility,
                )
            )
        return candidates

    def match(
        self,
        snapshots: Iterable[SignalSnapshotResult],
        strategy_definitions: Iterable[StrategyDefinitionRecord],
        *,
        strategy_run_id: str,
    ) -> list[CandidateScoreRecord]:
        """Score a batch of snapshots against active tactical strategies."""
        definitions = tuple(strategy_definitions)
        candidates: list[CandidateScoreRecord] = []
        for snapshot in snapshots:
            candidates.extend(
                self.match_snapshot(snapshot, definitions, strategy_run_id=strategy_run_id)
            )
        return candidates

    def _build_candidate(
        self,
        snapshot: SignalSnapshotResult,
        definition: StrategyDefinitionRecord,
        *,
        strategy_run_id: str,
        score: float,
        evidence: dict[str, Any],
        missing_required_signals: list[str],
        unsupported_missing_signal_families: list[str],
        direction: str,
        action: str,
        selection_reason: str,
        rejection_reason: str | None,
        actionable_score_threshold: float,
        macro_compatibility: str = "allowed",
    ) -> CandidateScoreRecord:
        candidate_status = _resolve_candidate_status(
            score=score,
            missing_required_signals=missing_required_signals,
            action=action,
            rejection_reason=rejection_reason,
            macro_compatibility=macro_compatibility,
            actionable_score_threshold=actionable_score_threshold,
            unsupported_missing_signal_families=unsupported_missing_signal_families,
        )
        return CandidateScoreRecord(
            candidate_score_id=str(uuid.uuid4()),
            strategy_run_id=strategy_run_id,
            signal_snapshot_id=snapshot.signal_snapshot_id,
            ticker=snapshot.ticker,
            strategy_id=definition.strategy_id,
            strategy_version=definition.version,
            strategy_definition_id=definition.strategy_definition_id,
            candidate_score=_clamp(score),
            direction=direction,
            action=action,
            typical_horizon=definition.typical_horizon,
            core_signal_evidence=evidence,
            missing_required_signals=missing_required_signals,
            unsupported_missing_signal_families=unsupported_missing_signal_families,
            invalidators=list(definition.config_json.get("invalidators") or []),
            risk_tags=list(definition.config_json.get("risk_tags") or []),
            macro_compatibility=macro_compatibility,
            selection_source=_selection_source(snapshot.selection_source),
            manual_request_id=snapshot.manual_request_id,
            selection_reason=selection_reason,
            rejection_reason=rejection_reason,
            benchmark_context=_benchmark_context(snapshot),
            decision_time=snapshot.decision_time,
            available_for_decision_at=snapshot.available_for_decision_at,
            source_record_refs_json=list(snapshot.source_record_refs_json),
            candidate_status=candidate_status,
            actionable_score_threshold=actionable_score_threshold,
            strategy_lifecycle_status=definition.lifecycle_status,
            strategy_source=definition.source,
        )

    def _apply_learning_factor_modifier(self, score: float, definition: StrategyDefinitionRecord) -> float:
        if self._learning_adjustments is None:
            return score
        multiplier = self._learning_adjustments.strategy_score_multiplier.get(definition.strategy_id, 1.0)
        return _clamp(score * multiplier)


def create_strategy_run(
    *,
    decision_time: datetime,
    snapshot_type: str = "pre_open",
    status: str = "succeeded",
    metadata_json: dict[str, Any] | None = None,
) -> StrategyRunRecord:
    """Create a strategy-run record with a generated identifier."""
    return StrategyRunRecord(
        strategy_run_id=str(uuid.uuid4()),
        decision_time=decision_time,
        snapshot_type=snapshot_type,
        status=status,
        metadata_json=metadata_json or {},
    )


def _is_active_tactical_definition(definition: StrategyDefinitionRecord) -> bool:
    return (
        definition.is_active
        and definition.lifecycle_status in {"active", "experimental", "shadow"}
        and definition.strategy_layer == "tactical_pattern"
    )


def _unsupported_missing_families(
    definition: StrategyDefinitionRecord,
    snapshot: SignalSnapshotResult,
) -> list[str]:
    missing = set(snapshot.missing_signals_json)
    unsupported: set[str] = set()
    for signal_name in definition.config_json.get("required_signals") or ():
        normalized = str(signal_name).casefold()
        for marker, family in DEFERRED_SIGNAL_FAMILY_MARKERS.items():
            if marker in normalized and family in missing:
                unsupported.add(family)
    return sorted(unsupported)


def _score_supported_strategy(
    snapshot: SignalSnapshotResult,
    definition: StrategyDefinitionRecord,
) -> tuple[float, dict[str, Any], list[str]]:
    strategy_id = definition.strategy_id
    if strategy_id in {"strong_theme_catalyst_continuation_v1", "catalyst_breakout_v1"}:
        return _score_catalyst_strength(snapshot)
    if strategy_id == "strong_theme_no_clear_near_term_entry_v1":
        score, evidence, missing = _score_catalyst_strength(snapshot)
        return min(score, 0.68), evidence, missing
    if strategy_id in {"relative_strength_rotation_v1", "base_breakout_v1"}:
        return _score_relative_strength(snapshot)
    if strategy_id == "insider_accumulation_momentum_v1":
        return _score_insider_accumulation(snapshot)
    if strategy_id == "valuation_repair_quality_software_v1":
        return _score_valuation_repair(snapshot)
    if strategy_id == "oversold_bounce_v1":
        return _score_oversold_bounce(snapshot)
    if strategy_id == "earnings_drift_v1":
        return _score_earnings_drift(snapshot)
    return _score_from_available_required_signals(snapshot, definition)


def _score_catalyst_strength(snapshot: SignalSnapshotResult) -> tuple[float, dict[str, Any], list[str]]:
    technical = _technical(snapshot)
    fundamental = _fundamental(snapshot)
    events = _events(snapshot)
    catalyst_quality = _as_float(events.get("catalyst_quality_score")) or 0.0
    high_signal_count = _as_float(events.get("high_signal_news_count_24h")) or 0.0
    sentiment_score = 1.0 if events.get("sentiment_direction") == "positive" else 0.0
    relative_strength = max(
        _as_float(technical.get("rs_vs_spy_1d")) or 0.0,
        _as_float(technical.get("rs_vs_qqq_1d")) or 0.0,
    )
    volume = min((_as_float(technical.get("relative_volume")) or 0.0) / 2.0, 1.0)
    quality = _as_float(fundamental.get("quality_score")) or 0.0
    score = (
        0.35 * catalyst_quality
        + 0.20 * min(high_signal_count, 1.0)
        + 0.15 * sentiment_score
        + 0.15 * min(max(relative_strength, 0.0) / 0.03, 1.0)
        + 0.10 * volume
        + 0.05 * quality
    )
    evidence = _compact_evidence(
        {
            "events_news.catalyst_quality_score": events.get("catalyst_quality_score"),
            "events_news.high_signal_news_count_24h": events.get("high_signal_news_count_24h"),
            "events_news.sentiment_direction": events.get("sentiment_direction"),
            "technical.rs_vs_spy_1d": technical.get("rs_vs_spy_1d"),
            "technical.rs_vs_qqq_1d": technical.get("rs_vs_qqq_1d"),
            "technical.relative_volume": technical.get("relative_volume"),
            "fundamental.quality_score": fundamental.get("quality_score"),
        }
    )
    missing = _missing_required(evidence, ("events_news.catalyst_quality_score", "technical.relative_volume"))
    return (score if evidence else 0.0), evidence, missing


def _score_relative_strength(snapshot: SignalSnapshotResult) -> tuple[float, dict[str, Any], list[str]]:
    technical = _technical(snapshot)
    rs_spy = _as_float(technical.get("rs_vs_spy_1d")) or 0.0
    rs_qqq = _as_float(technical.get("rs_vs_qqq_1d")) or 0.0
    return_20d = _as_float(technical.get("return_20d")) or 0.0
    relative_volume = _as_float(technical.get("relative_volume")) or 0.0
    liquidity = _as_float(technical.get("dollar_volume")) or 0.0
    score = (
        0.35 * min(max(rs_spy, 0.0) / 0.03, 1.0)
        + 0.25 * min(max(rs_qqq, 0.0) / 0.025, 1.0)
        + 0.20 * min(max(return_20d, 0.0) / 0.15, 1.0)
        + 0.10 * min(relative_volume / 1.5, 1.0)
        + 0.10 * (1.0 if liquidity >= 25_000_000 else 0.0)
    )
    evidence = _compact_evidence(
        {
            "technical.rs_vs_spy_1d": technical.get("rs_vs_spy_1d"),
            "technical.rs_vs_qqq_1d": technical.get("rs_vs_qqq_1d"),
            "technical.return_20d": technical.get("return_20d"),
            "technical.relative_volume": technical.get("relative_volume"),
            "technical.dollar_volume": technical.get("dollar_volume"),
        }
    )
    missing = _missing_required(evidence, ("technical.rs_vs_spy_1d", "technical.return_20d"))
    return (score if evidence else 0.0), evidence, missing


def _score_valuation_repair(snapshot: SignalSnapshotResult) -> tuple[float, dict[str, Any], list[str]]:
    technical = _technical(snapshot)
    fundamental = _fundamental(snapshot)
    quality = _as_float(fundamental.get("quality_score")) or 0.0
    growth = _as_float(fundamental.get("revenue_growth_score")) or 0.0
    margin = _as_float(fundamental.get("margin_trend_score")) or 0.0
    valuation = _as_float(fundamental.get("valuation_percentile"))
    valuation_component = 1.0 - valuation if valuation is not None else 0.0
    rs = max(_as_float(technical.get("rs_vs_spy_1d")) or 0.0, 0.0)
    score = 0.30 * quality + 0.25 * growth + 0.20 * margin + 0.15 * valuation_component + 0.10 * min(rs / 0.03, 1.0)
    evidence = _compact_evidence(
        {
            "fundamental.quality_score": fundamental.get("quality_score"),
            "fundamental.revenue_growth_score": fundamental.get("revenue_growth_score"),
            "fundamental.margin_trend_score": fundamental.get("margin_trend_score"),
            "fundamental.valuation_percentile": fundamental.get("valuation_percentile"),
            "technical.rs_vs_spy_1d": technical.get("rs_vs_spy_1d"),
        }
    )
    return (score if evidence else 0.0), evidence, []


def _score_oversold_bounce(snapshot: SignalSnapshotResult) -> tuple[float, dict[str, Any], list[str]]:
    technical = _technical(snapshot)
    rsi_3 = _as_float(technical.get("rsi_3"))
    drawdown = abs(_as_float(technical.get("drawdown_from_recent_high")) or 0.0)
    if rsi_3 is None:
        return 0.0, {}, ["technical.rsi_3"]
    oversold = max((35 - rsi_3) / 35, 0.0)
    score = 0.75 * min(oversold, 1.0) + 0.25 * min(drawdown / 0.12, 1.0)
    evidence = _compact_evidence(
        {
            "technical.rsi_3": technical.get("rsi_3"),
            "technical.drawdown_from_recent_high": technical.get("drawdown_from_recent_high"),
        }
    )
    return score, evidence, []


def _score_earnings_drift(snapshot: SignalSnapshotResult) -> tuple[float, dict[str, Any], list[str]]:
    events = _events(snapshot)
    event_type = str(events.get("own_earnings_event_type") or "")
    guidance = bool(events.get("guidance_news_flag"))
    upgrades = _as_float(events.get("analyst_upgrade_count")) or 0.0
    catalyst_quality = _as_float(events.get("catalyst_quality_score")) or 0.0
    beat_raise = 1.0 if "beat" in event_type or "raise" in event_type else 0.0
    score = 0.40 * beat_raise + 0.25 * (1.0 if guidance else 0.0) + 0.20 * min(upgrades / 2, 1.0) + 0.15 * catalyst_quality
    evidence = _compact_evidence(
        {
            "events_news.own_earnings_event_type": events.get("own_earnings_event_type"),
            "events_news.guidance_news_flag": events.get("guidance_news_flag"),
            "events_news.analyst_upgrade_count": events.get("analyst_upgrade_count"),
            "events_news.catalyst_quality_score": events.get("catalyst_quality_score"),
        }
    )
    return (score if evidence else 0.0), evidence, []


def _score_insider_accumulation(snapshot: SignalSnapshotResult) -> tuple[float, dict[str, Any], list[str]]:
    technical = _technical(snapshot)
    insider = _insider(snapshot)
    cluster_buys = _as_float(insider.get("insider_cluster_buy_count_90d")) or 0.0
    net_buy_value = _as_float(insider.get("insider_net_buy_value_30d")) or 0.0
    officer_buy_flag = 1.0 if insider.get("officer_buy_flag") else 0.0
    director_buy_flag = 1.0 if insider.get("director_buy_flag") else 0.0
    rs_spy = _as_float(technical.get("rs_vs_spy_1d")) or 0.0
    relative_volume = _as_float(technical.get("relative_volume")) or 0.0
    score = (
        0.30 * min(net_buy_value / 250_000.0, 1.0)
        + 0.25 * min(cluster_buys / 2.0, 1.0)
        + 0.15 * max(officer_buy_flag, director_buy_flag)
        + 0.20 * min(max(rs_spy, 0.0) / 0.02, 1.0)
        + 0.10 * min(relative_volume / 1.5, 1.0)
    )
    evidence = _compact_evidence(
        {
            "insider.insider_net_buy_value_30d": insider.get("insider_net_buy_value_30d"),
            "insider.insider_cluster_buy_count_90d": insider.get("insider_cluster_buy_count_90d"),
            "insider.officer_buy_flag": insider.get("officer_buy_flag"),
            "insider.director_buy_flag": insider.get("director_buy_flag"),
            "technical.rs_vs_spy_1d": technical.get("rs_vs_spy_1d"),
            "technical.relative_volume": technical.get("relative_volume"),
        }
    )
    missing = _missing_required(
        evidence,
        (
            "insider.insider_net_buy_value_30d",
            "insider.insider_cluster_buy_count_90d",
            "technical.rs_vs_spy_1d",
            "technical.relative_volume",
        ),
    )
    return (score if evidence else 0.0), evidence, missing


def _score_from_available_required_signals(
    snapshot: SignalSnapshotResult,
    definition: StrategyDefinitionRecord,
) -> tuple[float, dict[str, Any], list[str]]:
    evidence: dict[str, Any] = {}
    missing: list[str] = []
    flattened = _flatten_signal_json(snapshot)
    for signal_name in definition.config_json.get("required_signals") or ():
        primary = flattened.get(signal_name)
        fallback = flattened.get(str(signal_name).replace(".", "_"))
        value = primary if primary is not None else fallback
        if value is None:
            missing.append(str(signal_name))
        else:
            evidence[str(signal_name)] = value
    if not evidence:
        return 0.0, {}, missing
    score = len(evidence) / max(len(evidence) + len(missing), 1)
    return score, evidence, missing


def _technical(snapshot: SignalSnapshotResult) -> dict[str, Any]:
    return dict(snapshot.signal_json.get("technical") or {})


def _fundamental(snapshot: SignalSnapshotResult) -> dict[str, Any]:
    return dict(snapshot.signal_json.get("fundamental") or {})


def _events(snapshot: SignalSnapshotResult) -> dict[str, Any]:
    return dict(snapshot.signal_json.get("events_news") or {})


def _insider(snapshot: SignalSnapshotResult) -> dict[str, Any]:
    return dict(snapshot.signal_json.get("insider") or {})


def _social_macro(snapshot: SignalSnapshotResult) -> dict[str, Any]:
    return dict(snapshot.signal_json.get("social_macro") or {})


def _macro(snapshot: SignalSnapshotResult) -> dict[str, Any]:
    return dict(snapshot.signal_json.get("macro") or {})


def _flatten_signal_json(snapshot: SignalSnapshotResult) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for family, values in snapshot.signal_json.items():
        if isinstance(values, dict):
            for key, value in values.items():
                flattened[key] = value
                flattened[f"{family}.{key}"] = value
    return flattened


def _benchmark_context(snapshot: SignalSnapshotResult) -> dict[str, Any]:
    technical = _technical(snapshot)
    primary = "QQQ" if technical.get("rs_vs_qqq_1d") is not None else "SPY"
    return {
        "primary_benchmark": primary,
        "benchmark_symbols": ["SPY", "QQQ"],
    }


def _selection_source(value: str) -> str:
    return value if value in SELECTION_SOURCES else "scanner"


def _selection_policy(definition: StrategyDefinitionRecord) -> dict[str, Any]:
    return dict(definition.config_json.get("selection_policy") or {})


def _actionable_score_threshold(definition: StrategyDefinitionRecord) -> float:
    raw_value = _selection_policy(definition).get("actionable_score_threshold")
    if isinstance(raw_value, (int, float)):
        return float(raw_value)
    return DEFAULT_ACTIONABLE_SCORE_THRESHOLD


def _default_candidate_action(definition: StrategyDefinitionRecord) -> str:
    return str(_selection_policy(definition).get("default_candidate_action") or "enter_long")


def _default_candidate_direction(definition: StrategyDefinitionRecord) -> str:
    return str(_selection_policy(definition).get("default_candidate_direction") or "bullish")


def _macro_compatibility(snapshot: SignalSnapshotResult, definition: StrategyDefinitionRecord) -> str:
    macro = _macro(snapshot)
    regime = macro.get("regime")
    blocked_regimes = {
        str(item)
        for item in definition.config_json.get("macro_blocked_regimes") or ()
    }
    if regime is not None and str(regime) in blocked_regimes:
        return "blocked"
    if bool(macro.get("reduced_size")):
        return "reduced_size"
    return "allowed"


def _resolve_candidate_status(
    *,
    score: float,
    missing_required_signals: list[str],
    action: str,
    rejection_reason: str | None,
    macro_compatibility: str,
    actionable_score_threshold: float,
    unsupported_missing_signal_families: list[str],
) -> str:
    if macro_compatibility == "blocked" or unsupported_missing_signal_families:
        return "blocked"
    if (
        rejection_reason is None
        and not missing_required_signals
        and action != "no_trade"
        and score >= actionable_score_threshold
    ):
        return "actionable"
    return "watch"


def _compact_evidence(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _missing_required(evidence: dict[str, Any], required_keys: Iterable[str]) -> list[str]:
    return [key for key in required_keys if key not in evidence]


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _apply_insider_modifier(score: float, snapshot: SignalSnapshotResult) -> float:
    insider = _insider(snapshot)
    modifier = 0.0
    if (_as_float(insider.get("insider_net_buy_value_30d")) or 0.0) > 0:
        modifier += 0.05
    if (_as_float(insider.get("insider_cluster_buy_count_90d")) or 0.0) >= 2:
        modifier += 0.05
    if insider.get("officer_buy_flag") or insider.get("director_buy_flag"):
        modifier += 0.05
    return _clamp(score + min(modifier, 0.149))


def _apply_social_macro_modifier(score: float, snapshot: SignalSnapshotResult) -> float:
    social_macro = _social_macro(snapshot)
    if not social_macro:
        return _clamp(score)
    importance = _as_float(social_macro.get("social_macro_importance_score")) or 0.0
    headwind = bool(social_macro.get("policy_headwind_flag"))
    tailwind = bool(social_macro.get("policy_tailwind_flag"))
    explicit = bool(social_macro.get("explicit_ticker_mention_flag") or social_macro.get("explicit_theme_mention_flag"))
    modifier = 0.0
    if headwind and explicit:
        modifier -= min(0.15, 0.05 + importance * 0.1)
    elif tailwind and explicit:
        modifier += min(0.1, 0.03 + importance * 0.05)
    return _clamp(score + modifier)


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))
