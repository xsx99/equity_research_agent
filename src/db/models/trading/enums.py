"""Trading model enums."""
from __future__ import annotations

from src.db.models.base import ChoiceEnum

class StrategyLifecycleStatus(ChoiceEnum):
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    EXPERIMENTAL = "experimental"
    ACTIVE = "active"
    RETIRED = "retired"

class StrategySource(ChoiceEnum):
    SEED = "seed"
    REFLECTION_LEARNING = "reflection_learning"
    MANUAL = "manual"

class LlmPromptLifecycleStatus(ChoiceEnum):
    ACTIVE = "active"
    RETIRED = "retired"

class LlmParseStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class LlmUsageStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class PortfolioIntentLifecycleStatus(ChoiceEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"

class PortfolioIntentType(ChoiceEnum):
    CORE_GROWTH = "core_growth"
    CORE_INDEX = "core_index"
    CORE_THEME = "core_theme"
    CORE_CASH_LIKE = "core_cash_like"

class TickerRelationshipType(ChoiceEnum):
    PEER = "peer"
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    COMPETITOR = "competitor"
    SECTOR_LEADER = "sector_leader"
    ETF_COMPONENT = "etf_component"
    THEME_LEADER = "theme_leader"
    THEME_CONSTITUENT = "theme_constituent"

class ThemeLifecycleStatus(ChoiceEnum):
    ACTIVE = "active"
    RETIRED = "retired"

class UniverseSymbolStatus(ChoiceEnum):
    INCLUDED = "included"
    EXCLUDED = "excluded"

class ManualTickerRequestMode(ChoiceEnum):
    REVIEW_ONLY = "review_only"
    PAPER_TRADE_ELIGIBLE = "paper_trade_eligible"

class ManualTickerRequestStatus(ChoiceEnum):
    ACTIVE = "active"
    DISMISSED = "dismissed"
    CANCELLED = "cancelled"

class ProviderRequestStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CACHE_HIT = "cache_hit"
    BUDGET_EXCEEDED = "budget_exceeded"
    CIRCUIT_OPEN = "circuit_open"

class SourceIngestionStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEGRADED = "degraded"

class StrategyRunStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"

class MacroCompatibility(ChoiceEnum):
    ALLOWED = "allowed"
    REDUCED_SIZE = "reduced_size"
    BLOCKED = "blocked"

class CandidateStatus(ChoiceEnum):
    ACTIONABLE = "actionable"
    WATCH = "watch"
    BLOCKED = "blocked"

class TradeIdentity(ChoiceEnum):
    CORE_HOLDING = "core_holding"
    TACTICAL_STOCK_TRADE = "tactical_stock_trade"
    TACTICAL_OPTION_TRADE = "tactical_option_trade"
    RISK_HEDGE_OVERLAY = "risk_hedge_overlay"
    WATCH_ONLY = "watch_only"

class WatchType(ChoiceEnum):
    CATALYST_WATCH = "catalyst_watch"
    ORDINARY_WATCH = "ordinary_watch"

class CandidateOutcomeEvaluationStatus(ChoiceEnum):
    INTERIM = "interim"
    FINAL = "final"

class DailyReflectionStatus(ChoiceEnum):
    SUCCEEDED = "succeeded"
    FALLBACK = "fallback"

class LearningFactorStatus(ChoiceEnum):
    CANDIDATE = "candidate"
    OBSERVATION = "observation"
    SHADOW = "shadow"
    ACTIVE = "active"
    SUPPRESSED = "suppressed"
    RETIRED = "retired"

class StrategyProposalStatus(ChoiceEnum):
    ACCEPTED = "accepted"
    DUPLICATE_REJECTED = "duplicate_rejected"
    PROPOSAL_FAILED = "proposal_failed"
    INSUFFICIENT_EVIDENCE_REJECTED = "insufficient_evidence_rejected"

class StrategyEvaluationStatus(ChoiceEnum):
    OBSERVED = "observed"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    RETIRED = "retired"

class RiskAppetite(ChoiceEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"

class RiskDecisionStatus(ChoiceEnum):
    APPROVED = "approved"
    REDUCED = "reduced"
    REJECTED = "rejected"
