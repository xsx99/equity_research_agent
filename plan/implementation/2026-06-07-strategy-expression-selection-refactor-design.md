# Strategy And Expression Selection Refactor

Date: 2026-06-07
Status: Draft approved in conversation, pending user review

## Summary

The current trading-strategy package mixes two different concepts under one misleading catalog name:

- underlying trading strategies that explain why a ticker is interesting
- expression buckets that explain how to express that idea

The current selector also hard-codes `long_stock` for almost every selected candidate, which blocks the intended architecture where one strategy can support multiple stock or option expressions.

This design separates strategy seeds from expression-bucket seeds behind a shared top-level definitions entrypoint, adds explicit `strategy -> allowed expressions` mappings, and refactors selection into two deterministic stages:

1. choose one primary strategy
2. choose one preferred expression plus ordered fallbacks for that strategy

## User Decisions Captured

The design reflects the following approved choices:

- Strategy and expression bucket remain separate concepts.
- One strategy may map to multiple expression buckets.
- Selector should choose strategy first, then expression.
- Catalog naming should be cleaned up.
- Keep one top-level import/loader entrypoint, but split the internal catalog into two submodules.
- Strategy-to-expression mapping should live on the strategy definitions.
- Selector should use only high-level option-suitability signals, not leg-level or chain-level feasibility checks.
- If the preferred expression fails in the option layer or risk manager, the system should fall back to the next allowed expression for the same strategy.
- Expression suitability should be driven by a mix of declarative definition metadata and selector tie-break rules.

## Goals

- Remove the misleading “strategy catalog” naming for a module that currently stores both strategies and expression buckets.
- Preserve a clean conceptual boundary:
  - `strategy` explains the edge
  - `expression bucket` explains the implementation
  - `option layer` validates option-plan structure
  - `risk manager` approves or rejects portfolio exposure
- Make one-to-many `strategy -> expression` relationships explicit in seed definitions.
- Let selector output both the chosen expression and deterministic same-strategy fallbacks.
- Keep downstream attribution clean by selecting one primary strategy before expression selection.

## Non-Goals

- This design does not move option leg construction into selector.
- This design does not make matcher score `strategy + expression` pairs directly.
- This design does not redesign paper option broker behavior.
- This design does not remove the existing trade-classification stage.
- This design does not require a full option-chain integration before expression selection can be improved.

## Current Problems

### 1. Naming is misleading

`src/trading/strategies/catalog.py` stores both tactical strategies and expression buckets, but every exported name implies “strategy only.” This makes the code harder to read and caused direct confusion in conversation.

### 2. Strategy and expression are not modeled as separate stages

The intended architecture says strategy describes the thesis while expression describes implementation, but the current selector does not actually implement that separation in a meaningful way.

### 3. Expression selection is effectively hard-coded

`PrimaryStrategySelector._choose_expression()` currently returns `core_stock_accumulation` for one special case and otherwise falls back to `long_stock`. This makes option expression buckets seed-only metadata instead of an active decision layer.

### 4. Same-strategy fallback does not exist

If a future option expression is selected and later rejected by option validation or portfolio risk, there is no persisted ordered fallback plan under the same strategy.

### 5. Option-specific responsibilities are blurred

The current codebase does not consistently separate:

- high-level expression suitability
- option-plan structural validation
- portfolio-level risk approval

This increases the chance that selector, option planning, and risk approval drift into overlapping responsibilities.

## Design Overview

The new strategy-selection flow becomes:

```text
signal snapshots
  -> StrategyMatcher
      -> candidate_scores by strategy
  -> PrimaryStrategySelector
      -> chosen primary strategy
  -> ExpressionSelector
      -> chosen expression bucket + ordered same-strategy fallbacks
  -> TradeClassifier
      -> trade identity for the chosen expression
  -> TradingPipeline / option layer / risk manager
      -> try preferred expression, then same-strategy fallbacks if needed
```

The core invariant is:

- never compare expression buckets across different strategies before choosing the primary strategy
- never fabricate a fixed one-to-one `strategy -> expression` relationship

## Module And Naming Changes

### New internal structure

Replace the single `catalog.py` seed module with a definitions package:

- `src/trading/strategies/definitions/__init__.py`
- `src/trading/strategies/definitions/strategies.py`
- `src/trading/strategies/definitions/expressions.py`

The top-level `src/trading/strategies/__init__.py` should continue to provide one import surface for consumers.

### Naming changes

Rename “catalog” terminology to “definitions” terminology.

Examples:

- `StrategyCatalogItem` -> `StrategyDefinitionSeed` and `ExpressionDefinitionSeed`
- `INITIAL_STRATEGY_CATALOG` -> `INITIAL_STRATEGY_DEFINITIONS` and `INITIAL_EXPRESSION_DEFINITIONS`
- `get_initial_strategy_definitions()` remains valid as the strategy loader name
- add `get_initial_expression_definitions()`
- add `get_initial_trading_definitions()` or `load_all_trading_definitions()` for the shared top-level entrypoint

The goal is to make names reflect actual semantics without forcing every consumer to know the internal split.

## Definition Model Changes

### Strategy definition fields

Each strategy definition should explicitly declare which expressions are allowed:

```python
allowed_expression_bucket_ids: tuple[str, ...]
```

Optional future-friendly fields are allowed but not required for the first implementation:

```python
preferred_expression_bucket_ids: tuple[str, ...] = ()
```

`allowed_expression_bucket_ids` is the source of truth for the selector whitelist.

### Loader and repository contract

The current repository-facing contract implicitly mixes strategy and expression definitions in one returned collection. After this refactor, the loading contract should become explicit:

- `load_active_strategy_definitions()`
- `load_active_expression_definitions()`

If a combined helper remains for convenience, it should be reserved for administrative or migration use rather than matcher-time consumption.

The matcher should consume only strategy definitions. Expression selection should consume only expression definitions.

### Expression definition fields

Expression definitions should gain high-level suitability metadata. This metadata must stay above the option-plan layer and must not require live leg construction.

Examples:

- `prefers_unclean_stock_entry`
- `prefers_defined_risk`
- `prefers_event_volatility`
- `requires_directional_clarity`
- `penalize_binary_event_through_horizon`
- `prefers_stock_when_entry_clean`

These fields can live in config JSON rather than as first-class dataclass fields if that better matches current patterns.

## Selection Architecture

### Stage 1: Primary strategy selection

Keep the existing strategy-level matcher behavior as the source of strategy candidates.

`PrimaryStrategySelector` should continue to answer one question only:

```text
Which strategy best explains the opportunity for this ticker/action namespace?
```

This stage must not compare option expressions against stock expressions.

### Stage 2: Expression selection

Introduce a dedicated deterministic expression-selection stage after primary strategy selection.

This stage answers:

```text
Given the chosen strategy, which allowed expression bucket is best, and what are the fallbacks?
```

It should consider only the selected strategy’s `allowed_expression_bucket_ids`.

### Why not select `(strategy, expression)` pairs directly

Direct pair scoring would blur thesis selection and implementation choice, pollute attribution, and make it harder to tell whether a bad outcome came from the strategy thesis or the chosen instrument expression.

Choosing the strategy first keeps attribution and replay cleaner.

## Expression Suitability Rules

Expression ranking should use three groups of high-level signals:

### 1. Entry quality and timing

Examples:

- stock entry is clean
- stock entry is not clean yet
- direction is clear
- timing window is short

### 2. Risk-shape preference

Examples:

- defined max loss is preferred
- convexity is preferable to linear stock exposure
- stock ownership is acceptable

### 3. Event context

Examples:

- event volatility matters
- earnings or another binary event sits inside the intended horizon
- event-through-horizon risk argues against common stock or against short premium

### Rules placement

Use a mixed model:

- expression definitions store base suitability preferences declaratively
- selector code owns a small set of deterministic tie-break and ordering rules

This keeps the definitions expressive without trying to encode every ranking edge case inside static metadata.

## Selector Output Contract

The selector result should explicitly persist both the chosen expression and the fallback plan.

Example logical contract:

```json
{
  "selected_strategy_id": "strong_theme_catalyst_continuation_v1",
  "selected_expression_bucket_id": "defined_risk_directional_option",
  "fallback_expression_bucket_ids": [
    "long_stock",
    "volatility_event_option"
  ],
  "expression_selection_context": {
    "ranking_reasons": {
      "defined_risk_directional_option": "direction clear, stock entry not clean, defined risk preferred",
      "long_stock": "clean fallback if option path is not feasible",
      "volatility_event_option": "event-sensitive backup when direction weakens"
    }
  }
}
```

The returned object must still expose the final selected `strategy + expression` pair, because downstream stages consume a concrete choice. The additional fallback ordering exists so downstream rejection does not require rerunning strategy selection.

Suggested shape:

```python
SelectedStrategyRecord(
    candidate=...,
    selected_expression_bucket_id="defined_risk_directional_option",
    selected_expression_bucket_version="v1",
    fallback_expression_bucket_ids=("long_stock", "volatility_event_option"),
    expression_selection_context={...},
)
```

## Fallback Behavior

If the preferred expression is rejected later by `OptionsStrategyLayer` or `RiskManager`, the system should retry the next expression bucket from `fallback_expression_bucket_ids` for the same strategy.

Important constraints:

- fallback must stay within the same selected strategy
- fallback must preserve deterministic ordering from selector output
- fallback must stop once an expression passes or the list is exhausted
- exhausting the list should downgrade to the appropriate non-trade outcome rather than silently re-running strategy selection

## Boundary With Option Layer And Risk Manager

### Expression selector

Owns only high-level suitability decisions such as:

- stock entry cleanliness
- directional clarity
- event-volatility preference
- defined-risk preference

### OptionsStrategyLayer

Owns option-plan structure validation and deterministic instrument metrics:

- whitelisted structure validation
- leg completeness
- net debit or credit
- max loss / max profit
- margin requirement estimate
- breakevens
- portfolio Greeks at the strategy-plan level

### RiskManager and OptionRiskManager

Own deterministic portfolio approval:

- concentration caps
- margin and buying-power approval
- missing risk metadata rejection
- assignment exposure and worst-case assignment concentration
- hedge overlay creation under `risk_hedge_overlay`

This boundary avoids duplication:

- selector chooses the best expression at a thesis level
- option layer says whether a concrete option plan is structurally valid
- risk manager says whether the portfolio can take the exposure

## Trade Classification Changes

`TradeClassifier` should consume the concrete selected expression bucket, not infer one through unsafe defaults.

The classifier should continue to derive trade identity from the chosen expression bucket and portfolio context, but it should stop acting as a placeholder gate for “option deferred” semantics once the selector and downstream fallback contract are in place.

In practical terms:

- stock expressions should still map to `tactical_stock_trade` or `core_holding`
- option expressions should map to `tactical_option_trade`
- downstream option validation and risk approval, not classifier-time blanket downgrades, should determine whether a selected option expression can execute

### Reclassification after fallback

Expression fallback can change trade identity semantics. Example:

- preferred expression: `defined_risk_directional_option`
- fallback expression: `long_stock`

If the active expression changes, any earlier classification derived from the rejected expression is stale. The implementation must therefore do one of the following deterministically:

1. delay final trade classification until the active expression is resolved, or
2. rerun deterministic classification immediately after fallback resolves the new active expression

The system must not persist a stock trade while still carrying a stale `tactical_option_trade` classification from the rejected preferred expression.

## Persistence And Read Models

The selected-strategy record should persist enough data for replay and audit:

- selected strategy id/version
- selected expression bucket id/version
- ordered fallback expression bucket ids
- expression selection context / reasons

This data may live in the selected-strategy artifact, classification context, or later trading-decision context, but it must be persisted before downstream option validation mutates the path.

## Testing Strategy

Add or update tests for:

1. Definitions split
   - strategy seeds load from the strategy submodule
   - expression seeds load from the expression submodule
   - top-level definitions entrypoint re-exports both correctly

2. Strategy-to-expression whitelisting
   - selector never chooses an expression not listed in `allowed_expression_bucket_ids`

3. Expression ranking
   - clean stock entry favors `long_stock`
   - unclear stock entry with directional clarity can favor `defined_risk_directional_option`
   - event-volatility setup can favor `volatility_event_option`

4. Fallback ordering
   - selector persists ordered same-strategy fallbacks
   - downstream retry uses that order without re-running strategy selection

5. Classifier integration
   - classifier consumes the concrete chosen expression instead of inheriting broad default behavior

## Migration Notes

The refactor should be staged to minimize churn:

1. introduce definitions submodules and top-level exports
2. move seed data without changing behavior
3. add `allowed_expression_bucket_ids`
4. introduce dedicated expression selection contract
5. remove hard-coded `long_stock` fallback
6. replace classifier-time option blanket downgrade with downstream validation plus same-strategy fallback

This order keeps the rename and the behavior change separable during implementation and review.

## Open Implementation Notes

- Existing tests that import `INITIAL_STRATEGY_CATALOG` or `StrategyCatalogItem` will need renaming updates.
- Existing `SelectedStrategyRecord` likely needs to evolve into a richer contract or be split so expression selection data has an obvious home.
- The earlier trade/watch cleanup design should remain compatible, but the implementation plan should call out whether both changes land together or sequentially.
