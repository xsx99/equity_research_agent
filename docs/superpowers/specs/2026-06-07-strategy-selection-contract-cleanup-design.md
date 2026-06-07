# Strategy Selection Contract Cleanup For Trade And Watch Separation

Date: 2026-06-07
Status: Draft approved in conversation, pending user review

## Summary

The current PR03 strategy-matching flow mixes three different concerns into one path:

- raw strategy matches (`candidate_scores`)
- selected trade candidates that should enter the trading pipeline
- rejected or downgraded watch outcomes that should not enter the trading pipeline

That mixing has produced six concrete problems in the current implementation:

1. `CandidateScoreRecord.is_actionable` is too permissive.
2. Matcher action and direction semantics are mostly hard-coded.
3. Rejected watch rows are returned as `SelectedStrategyRecord`.
4. `no_trade` and rejected rows can still inherit `long_stock`.
5. Falsey required-signal values such as `0`, `0.0`, and `False` can be misread as missing.
6. Macro compatibility is stored but not actually evaluated; risk tags and invalidators are copied through without clear stage ownership.

This design tightens the candidate contract, splits trade selection from watch retention, removes expression-bucket fallback to `long_stock`, and adds a dedicated persisted watch path.

## User Decisions Captured

The design reflects the following approved choices:

- Schema change is allowed.
- Trade-path and watch-path persistence should be separated.
- `trade_classifications` should keep trade semantics only.
- `watch_candidates` should be persisted separately instead of being disguised as selected trades.

## Goals

- Make `actionable` mean "eligible to advance into the trade pipeline" instead of "not obviously rejected."
- Separate selected trade records from retained watch outcomes in memory, persistence, and downstream read models.
- Remove implicit `long_stock` expression assignment for `no_trade` and rejected rows.
- Make action, direction, and expression-bucket eligibility strategy-config driven.
- Fix falsey required-signal handling.
- Make macro compatibility actually participate in candidate eligibility.

## Non-Goals

- This design does not add a full macro pipeline if one is not already wired in.
- This design does not add short-selling execution support.
- This design does not redesign PR05+ trading decisions beyond the contract changes needed to consume the cleaner PR03 outputs.
- This design does not attempt to make invalidators block candidates during matching unless the invalidator is explicitly represented as a deterministic pre-entry blocker.

## Current Problems

### 1. Actionability is under-specified

`is_actionable` currently checks only `rejection_reason is None` and `macro_compatibility != "blocked"`. A row can therefore be treated as actionable even when:

- required signals are still missing
- `action == "no_trade"`
- the score is below a strategy-specific threshold

This violates the intended meaning of "selected primary strategy."

### 2. Action and direction are not first-class strategy outputs

Most rows are born as `bullish + enter_long`, and only a few hard-coded branches downgrade them later. This weakens grouping by `(ticker, action)` and makes future support for `enter_short`, `add`, `trim`, `hedge`, and richer neutral/watch states harder.

### 3. Watch outcomes are modeled as selected trades

When no actionable candidate exists, the selector promotes a rejected candidate into `SelectedStrategyRecord`. The classifier then downgrades it into `watch_only`. This makes downstream code reason about trade-shaped objects that were never trade-eligible.

### 4. Expression fallback is unsafe

The selector currently falls back to `long_stock` for almost everything, including `no_trade` rows. This can attach stock-trade semantics to candidates that should have no selected trade expression at all.

### 5. Required-signal fallback mishandles falsey values

The current `flattened.get(a) or flattened.get(b)` logic treats valid values such as `0`, `0.0`, and `False` as absent.

### 6. Stage ownership is unclear for macro, risk, and invalidators

- `macro_compatibility` is always written as `"allowed"` even though strategy definitions already store `macro_blocked_regimes`.
- `risk_tags` and `invalidators` are propagated, but the system does not explicitly define which later stage is responsible for enforcing them versus simply displaying them.

## Design Overview

The cleaned-up PR03 contract becomes:

```text
signal snapshots + optional macro context
  -> StrategyMatcher
      -> candidate_scores (all retained scored rows)
  -> PrimaryStrategySelector
      -> selected_trades (trade-eligible only)
      -> watch_candidates (retained non-trade outcomes only)
  -> TradeClassifier
      -> trade_classifications (selected_trades only)
  -> TradingPipeline
      -> consumes selected_trades + trade_classifications
  -> UI / read models
      -> combine candidate_scores + trade_classifications + watch_candidates
```

The important boundary change is that watch rows stop pretending to be selected trades.

## Candidate Contract Changes

### 1. Candidate status becomes explicit

Add a new candidate-level status field on `CandidateScoreRecord` and `candidate_scores`, for example:

- `actionable`
- `watch`
- `blocked`

`is_actionable` remains as a convenience property, but it becomes a strict derived check from explicit candidate state rather than a loose shortcut.

### 2. Actionability becomes strict and config-driven

A candidate is actionable only when all of the following are true:

- `candidate_status == "actionable"`
- `rejection_reason is None`
- `missing_required_signals` is empty
- `action != "no_trade"`
- `macro_compatibility != "blocked"`
- `candidate_score >= actionable_score_threshold`

`actionable_score_threshold` moves into strategy config so the cutoff is not a global magic number.

### 3. Action and direction become strategy-config driven

Strategy config should explicitly declare the default trade-intent semantics it is allowed to emit. Initial support only needs the currently relevant values, but the contract must be future-safe:

- `action`: `enter_long`, `enter_short`, `add`, `trim`, `no_trade`
- `direction`: `bullish`, `bearish`, `neutral`, `risk_warning`

For current long-only V2 strategies, most seeds will still declare `enter_long + bullish`, but they will do so explicitly instead of inheriting hidden defaults.

### 4. Required-signal lookup uses `is None`, not truthiness

Required-signal fallback must preserve `0`, `0.0`, and `False` as present values. Only `None` means missing.

## Strategy Config Changes

Each tactical strategy definition should gain explicit selection policy fields in `config_json`, such as:

- `actionable_score_threshold`
- `default_candidate_action`
- `default_candidate_direction`
- `eligible_expression_bucket_ids`

The matcher may still apply deterministic overrides such as direct negative-catalyst blocking, but the base action/direction contract now comes from strategy config instead of hard-coded defaults.

## Macro, Risk, And Invalidator Ownership

### Macro compatibility

`StrategyMatcher` should accept optional macro context from the strategy-scoring workflow and compute real `macro_compatibility` values:

- `allowed`
- `reduced_size`
- `blocked`

At minimum, the first implementation must wire `macro_blocked_regimes` into `blocked`. `reduced_size` can be supported when the macro context exposes a compatible reduced-risk signal.

### Risk tags

`risk_tags` remain strategy metadata, not matcher-time blockers by default. Their primary consumers stay downstream sizing, risk, replay, and UI layers.

### Invalidators

`invalidators` remain strategy-defined exit or review conditions. They should continue to propagate through candidate, classification, trading decision, and UI contexts, but they are not automatically interpreted as pre-entry matcher rejects unless the strategy explicitly encodes a deterministic pre-entry blocker.

This design makes stage ownership explicit instead of pretending these fields are "implemented" simply because they are copied through.

## Selector Changes

### 1. Split outputs

Replace the current `list[SelectedStrategyRecord]` output with a structured selector result:

- `selected_trades: list[SelectedTradeRecord]`
- `watch_candidates: list[WatchCandidateRecord]`

`SelectedTradeRecord` means the candidate is actually eligible to proceed into trade classification.

`WatchCandidateRecord` means the system intentionally retained a non-trade outcome for manual review, UI surfacing, or later reflection.

### 2. Trade-path rules

The selector should choose selected trades only from actionable candidates.

Grouping can stay per `(ticker, action)` for trade selection, but only after action becomes a real strategy output rather than a hard-coded default.

### 3. Watch-path rules

If no selected trade exists for a ticker's current decision namespace, the selector may retain one watch candidate using deterministic ranking over allowed watch statuses such as:

- `catalyst_watch`
- `ordinary_watch`
- `no_trade`
- `blocked_by_missing_data`

The watch path is now explicit and separate.

## Expression Bucket Selection Changes

### 1. No default `long_stock` fallback

Expression buckets must be selected from strategy-declared eligibility only. If no eligible expression bucket can be resolved, the candidate cannot become a selected trade.

### 2. Explicit strategy-to-expression mapping

Each strategy declares allowed expression buckets in config. Example patterns:

- `strong_theme_catalyst_continuation_v1` -> `["long_stock", "defined_risk_directional_option"]`
- `strong_theme_no_clear_near_term_entry_v1` -> `["defined_risk_income_spread", "volatility_event_option"]`
- `core_accumulation_on_pullback_v1` -> `["core_stock_accumulation"]`

The initial deterministic selector can choose the first eligible bucket in declared order. Later work can evolve this into richer bucket scoring if needed.

### 3. Watch outcomes have no selected trade expression

A watch candidate should not receive a fake trade expression. If the UI wants a display label, it should come from watch semantics, not from a fabricated `long_stock` bucket.

## Persistence Changes

### 1. Keep `candidate_scores` as the raw scored layer

`candidate_scores` continues to persist all retained scored rows, including rejected and blocked rows that are useful for reflection and replay.

Schema additions:

- add `candidate_status`
- preserve `rejection_reason`
- preserve `macro_compatibility`

### 2. Keep `trade_classifications` for trade-path only

`trade_classifications` remains the persisted output of `TradeClassifier`, but it should now represent selected trade-path rows only.

Application invariant:

- new code must stop producing `watch_only` trade classifications

The enum can remain temporarily permissive if that reduces migration churn, but the behavior contract changes immediately.

### 3. Add `watch_candidates`

Add a dedicated `watch_candidates` table and in-memory record for retained non-trade outcomes.

Suggested fields:

- `watch_candidate_id`
- `candidate_score_id`
- `strategy_run_id`
- `ticker`
- `watch_strategy_id`
- `watch_strategy_version`
- `watch_type`
- `result_status`
- `watch_reason`
- `selection_context_json`
- `decision_time`

One watch candidate per `(strategy_run_id, ticker)` is sufficient for the initial design.

## Workflow Changes

### StrategyPipeline

`StrategyPipelineResult` should expand to include:

- `selected_trades`
- `watch_candidates`
- `classifications`

`StrategyPipeline.run()` should:

1. persist `candidate_scores`
2. persist `watch_candidates`
3. classify `selected_trades`
4. persist `trade_classifications`
5. update manual-request result status from either selected trades or watch candidates

### HistoricalReplayRunner

Replay should persist the same split outputs:

- candidates
- watch candidates
- trade classifications for selected trades only

Outcome evaluation can continue to evaluate all `candidate_scores`, but it should consume watch metadata from the dedicated watch table when available instead of inferring watch semantics from `trade_classifications`.

### TradingPipeline

Trading decisions should consume selected trade classifications only. Watch candidates should no longer generate trade-classification-shaped inputs just to be rejected again later.

## Repository And Read-Model Changes

### Repositories

Both in-memory and SQLAlchemy repositories need:

- save/load support for `watch_candidates`
- updated strategy-scoring persistence flow
- removal of fallbacks that inject `long_stock` or `tactical_stock_trade` when no trade classification exists

### Intraday context

Intraday candidate context loaders must stop defaulting to:

- `expression_bucket_id = "long_stock"`
- `trade_identity = "tactical_stock_trade"`

for rows that only have watch semantics.

### UI / Today read models

UI presenter logic should build candidate/watch state from explicit watch records rather than from `watch_only + long_stock` artifacts.

Compatibility expectations:

- selected trade rows still show expression bucket labels normally
- watch/no-trade rows show watch/result semantics without an expression bucket
- older rows can still be rendered with best-effort fallback until the repo is fully repopulated

## Testing Strategy

Add or update coverage in these groups:

- matcher unit tests for strict actionability, falsey required signals, macro blocking, and config-driven action/direction
- selector unit tests for trade/watch split and no `long_stock` fallback
- classifier tests that enforce trade-path-only inputs
- workflow tests for strategy scoring, manual request result updates, and replay persistence
- repository/model tests for new watch persistence and candidate status schema
- UI/read-model tests for no-trade/watch rows without trade expressions

## Rollout Notes

Because this version is not deployed, the implementation may take the cleaner schema-changing path instead of preserving the current mixed trade/watch persistence contract.

The implementation should still preserve best-effort read compatibility for any existing local rows during the transition, but correctness of the new contract is more important than maintaining the current accidental `watch_only + long_stock` semantics.
