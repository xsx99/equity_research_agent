# Risk Manager Lookahead Hedge Design

Date: 2026-06-13
Status: Draft approved in conversation, pending user review

## Summary

The current `RiskManager` is a deterministic single-trade gate with light portfolio checks. It can reject stale or incomplete trades and reduce size for simple concentration limits, but it does not manage future `1-5` trading day macro or event risk, and it does not generate `risk_hedge_overlay` actions.

This design upgrades risk handling into two explicit layers:

1. `PortfolioHedgePlanner` evaluates current portfolio exposure plus pending trade exposure against future macro and event risk.
2. `RiskManager` remains the final deterministic authority that approves, reduces, or rejects each trade and decides whether an approved alpha trade must be accompanied by a hedge overlay action.

The first implementation focuses on portfolio risk reduction, not return optimization. It uses deterministic rules, not an optimizer, and keeps the initial hedge toolset limited to index and sector ETF option overlays.

## User Decisions Captured

The design reflects the following approved choices from conversation:

- Risk reduction should cover both existing holdings and pending new trades.
- Risk handling should be split by source:
  - macro risk primarily uses hedge overlays
  - single-name binary event risk primarily uses size reduction or blocked opens
  - mixed risk combines both
- The first hedge implementation should use index and sector ETF option hedges rather than stock hedges.
- The first trigger scope should include:
  - hard near-term events
  - macro risk warnings
- Hedge underliers should start with:
  - broad index ETFs
  - sector ETFs
- Single-name binary event handling should depend on trade identity:
  - `core_holding` may be preserved and hedged
  - `tactical_stock_trade` and `tactical_option_trade` default to reduction or blocked opens
- Hedge intensity should be severity-based, not fixed or optimizer-driven.
- Hedge closure should happen when risk normalizes, not only when time passes.
- `PositionSizer` remains the owner of base size calculation.
- `RiskManager` remains the final owner of executable size via `approved_weight`.
- A new `PortfolioHedgePlanner` should be introduced rather than overloading `RiskManager` with all lookahead planning logic.

## Goals

- Add deterministic `1-5` trading day lookahead risk management for macro and event risk.
- Preserve clear ownership boundaries:
  - `TradingPipeline` suggests trade intent
  - `PositionSizer` computes base size
  - `PortfolioHedgePlanner` computes portfolio-level risk intent
  - `RiskManager` makes final executable decisions
- Support portfolio-level hedge overlays under `trade_identity = "risk_hedge_overlay"`.
- Let risk review consider:
  - current holdings
  - open option positions
  - open hedge overlays
  - pending trade incremental exposure
- Preserve auditability with deterministic rules, structured reason codes, and persisted risk artifacts.

## Non-Goals

- This design does not introduce a portfolio optimization solver.
- This design does not make the LLM decide hedge size or hedge structure.
- This design does not attempt full correlation-cluster optimization in V1.
- This design does not add stock-based hedge overlays in the initial version.
- This design does not replace current single-trade risk rails; it extends them.
- This design does not fully solve single-name event hedging with name-specific options in V1.

## Current Problems

### 1. Risk checks are mostly trade-local

The current `RiskManager.evaluate()` checks freshness, a few hard rails, and sector concentration, but it does not evaluate how the combined portfolio should be managed over the next few trading days.

### 2. Future macro and event risk are not active inputs

The design docs already expect macro snapshots and portfolio event assessments, but the active risk path does not use them to reduce, block, or hedge exposure.

### 3. Hedge overlay is defined but not planned

`risk_hedge_overlay` exists in taxonomy and persistence, but the runtime does not currently generate deterministic `open_hedge`, `adjust_hedge`, or `close_hedge` actions from portfolio-level risk conditions.

### 4. Single-name event risk and macro risk are not separated

The system needs different responses depending on risk source:

- macro and sector risk can often be reduced with portfolio hedges
- single-name binary event risk often cannot

Current logic has no first-class separation between these categories.

### 5. Size ownership is clear in code but not complete in contract

`PositionSizer` already computes base size, but the future design needs an explicit contract that says:

- planner can constrain size
- `RiskManager` outputs the only executable size
- hedge overlays are a separate risk action, not a replacement for alpha trade sizing

## Design Overview

The new pre-open risk path becomes:

```text
portfolio sync
  -> macro snapshot + portfolio event assessments
  -> alpha candidate / trading decisions
  -> position sizing
  -> PortfolioHedgePlanner
      -> portfolio risk intent
  -> RiskManager
      -> final alpha trade risk decisions
      -> final hedge overlay decisions
  -> paper execution
```

The new intraday path follows the same pattern after signal refresh and alert classification.

The core invariant is:

- `PortfolioHedgePlanner` decides what kind of risk action is needed
- `RiskManager` decides whether that action is executable and how it affects final alpha trade approval

## New Module: PortfolioHedgePlanner

### Responsibility

`PortfolioHedgePlanner` is a deterministic portfolio-level planning component. It does not place orders and does not own final trade approval.

It answers:

```text
Given the current portfolio, open hedges, pending trades, and the next 1-5 trading day macro/event window,
what risk actions should be applied to positions and what hedge overlay actions should be proposed?
```

### Inputs

The planner should receive:

- `decision_time`
- `risk_window`
  - initial value: `1-5` trading days
- `portfolio_context`
- current `portfolio_risk_snapshot`
- current `risk_factor_exposures`
- `macro_snapshot`
- `portfolio_event_risk_assessments`
- open `risk_hedge_overlay` positions or decisions
- pending trade incremental exposures
- `risk_limit_config`

The planner must evaluate both:

- current portfolio risk
- projected portfolio risk after pending proposed sized trades

The planner may reason about projected approved exposure, but it must not directly create executable hedge orders from that projection. Final hedge materialization happens only after `RiskManager` resolves final alpha trade approvals and residual portfolio risk.

### Outputs

The planner should produce one structured `PortfolioRiskIntent` artifact with:

- `risk_window`
- `aggregate_risk_state`
  - `risk_normalized`
  - `macro_watch`
  - `macro_high_risk`
  - `event_cluster_risk`
  - `mixed_risk`
- `position_actions`
  - `allow`
  - `reduce`
  - `block_open`
  - `force_reduce`
- `hedge_actions`
  - `open_hedge`
  - `adjust_hedge`
  - `close_hedge`
- `binding_constraints`
- deterministic metadata:
  - `risk_source`
  - `severity`
  - `coverage_ratio`
  - `target_underlier`
  - `reason_code`

The planner proposes intent only. It does not emit executable orders.

It also does not generate `risk_hedge_overlay` directly. That ownership remains with `RiskManager` so existing module contracts stay intact.

## Risk Manager Role After Improvement

`RiskManager` should become the final portfolio risk authority, not just a single-trade rule checker.

It keeps its current hard rail role but gains these responsibilities:

1. consume portfolio-level risk intent from `PortfolioHedgePlanner`
2. apply planner size or open-block constraints to each pending trade
3. approve, reduce, or reject trades after combining:
   - base size from `PositionSizer`
   - current portfolio context
   - lookahead risk intent
   - existing hard rails
4. attach or generate hedge overlay actions when portfolio-level risk still requires them
5. manage hedge lifecycle decisions:
   - `open_hedge`
   - `adjust_hedge`
   - `close_hedge`

`RiskManager` still does not compute base alpha size from scratch.

## Size Ownership Contract

The final ownership contract should be explicit:

- `TradingPipeline.target_weight` is advisory.
- `PositionSizer` computes `proposed_weight` / `final_weight` under sizing caps.
- `PortfolioHedgePlanner` may apply:
  - `block_open`
  - `max_allowed_weight_override`
  - `force_reduce`
- `RiskManager.approved_weight` is the only executable trade size.
- Hedge overlays are separate risk actions and must not blur alpha trade size ownership.

## Input Contract Changes

### TradeRiskRequest extension

`TradeRiskRequest` should be extended or wrapped so final evaluation can consume lookahead risk context:

- `event_date_distance`
- `event_through_horizon`
- `core_vs_tactical`
- `lookahead_macro_state`
- `lookahead_event_state`
- `lookahead_cluster_state`

The request should continue to hold current trade-local fields such as price, volatility, liquidity, estimated margin, and option metadata completeness.

### New planner-to-risk-manager context

`RiskManager.evaluate()` should accept portfolio-level intent, either directly or through an expanded evaluation context:

- `portfolio_risk_intent`
- `trade_incremental_exposure`

`trade_incremental_exposure` should describe the trade's future-risk profile:

- sector
- beta bucket
- macro sensitivity
- event type
- event timing
- trade identity

## Output Contract Changes

`RiskDecisionRecord` should be expanded or consistently populated so future-risk decisions are auditable:

- `status`
  - `approved`
  - `reduced`
  - `rejected`
- `approved_weight`
- `approved_notional`
- `reason_code`
- `applied_rules`
- `binding_constraint`
- `lookahead_risk_source`
  - `macro`
  - `own_event`
  - `sector_event`
  - `macro_plus_event`
- `generated_hedge_action`
  - structured hedge proposal payload when applicable

If a hedge overlay is approved as a separate action, that action should also produce a normal persisted risk decision and later a `RiskHedgeDecisionRecord` after execution.

## Hedge Expression Scope

This design is about hedge planning and risk approval, not full option-expression redesign. To stay compatible with the current option layer, V1 hedge overlays should remain inside the existing whitelisted option capability set.

Default V1 preference:

- broad or sector bearish hedge exposure should map to simple defined-risk ETF option expressions already supported by the system
- the initial default should prefer the simplest compatible structure, such as `long_put`, unless a later design explicitly expands hedge-specific option structures

The planner selects hedge intent:

- underlier
- severity
- coverage ratio

The downstream option layer remains responsible for validating the specific option structure and required metadata.

## Decision Rules

### A. Macro risk

If the next `1-5` trading day window is marked `macro_watch`, `macro_high_risk`, or equivalent by deterministic rules:

- existing `core_holding` positions are preserved by default
- existing `tactical_*` positions may remain, but new same-direction exposure is tightened first
- new trades with overlapping broad or sector risk may be:
  - reduced
  - blocked
- hedge overlays may be opened using broad or sector ETF option hedges

Macro risk should primarily be handled with hedge overlays, not by automatically liquidating the portfolio.

### B. Single-name own-event risk

For near-term binary events on the same name, such as earnings, guidance, FDA, litigation, or similar:

- `core_holding`
  - may remain open
  - may still be force-reduced if size is too large for the event
  - may also coexist with broad or sector hedge overlays
- `tactical_stock_trade` and `tactical_option_trade`
  - default to reduction
  - may be blocked from opening
  - may be force-reduced for existing positions

Broad hedges must not be treated as a complete substitute for handling single-name binary event risk.

### C. Sector leader / read-through / event cluster risk

If there is a near-term sector leader event or theme-cluster event that materially affects an overexposed portfolio cluster:

- new same-cluster trades are tightened first
- existing tactical positions in the cluster may be reduced if concentration remains too high
- sector ETF option hedges are preferred over broad index hedges when the risk source is sector-specific
- `core_holding` positions in the cluster are preserved unless they violate hard limits

### D. Mixed risk

If both macro risk and single-name or sector event risk are present:

1. apply single-name event rules first
2. then apply residual portfolio hedge logic for macro or sector exposure

This prevents broad hedges from being used to bypass trade reductions that should occur for name-specific binary risk.

## Hedge Underlier Scope

V1 hedge underliers are limited to:

- broad index ETF options
  - examples: `SPY`, `QQQ`, `IWM`
- sector ETF options
  - examples: `XLK`, `XLF`, `XLE`, `SMH`

This keeps the mapping deterministic and aligned with the existing `paper_option_hedge` portfolio identity.

Stock hedge overlays are out of scope for the first implementation.

## Hedge Intensity Rules

V1 uses severity-based hedge coverage instead of an optimizer or a single fixed percentage.

Suggested deterministic coverage tiers:

- `watch`
  - target hedge coverage around `25%`
- `high`
  - target hedge coverage around `50%`
- `critical`
  - target hedge coverage around `50%-75%`

For tactical books under severe macro or clustered event stress, the effective protection may approach full protection after combining:

- tighter new-trade approvals
- tactical position reductions
- hedge overlays

The exact percentage should still be deterministic and tied to persisted reason codes and severity tiers.

## Hedge Lifecycle Rules

Hedges should not be closed only because time passed.

Default lifecycle rules:

- `open_hedge`
  - when future macro or cluster risk is elevated and residual exposure remains above threshold
- `adjust_hedge`
  - when risk remains, but severity or exposure level changes
- `close_hedge`
  - only when risk normalizes and relevant exposures fall back inside configured thresholds

If risk moves from `high` to `watch`, the default action should be to reduce hedge coverage before fully closing it.

## Pre-Open Execution Order

1. sync the current portfolio, positions, account state, and open hedges
2. compute macro snapshot and portfolio event risk assessments for the next `1-5` trading days
3. run alpha strategy selection and trading decisions
4. run `PositionSizer` for pending trades
5. construct incremental future-risk exposure for those trades
6. run `PortfolioHedgePlanner`
7. run `RiskManager` for final alpha trade decisions
8. recompute residual portfolio risk using final alpha approvals
9. generate approved hedge overlay decisions from residual risk
10. execute approved alpha and hedge orders

The key invariant is:

- alpha proposals come before hedge planning
- hedge planning happens before final risk approval
- final hedge overlay materialization uses residual exposure after alpha approvals, not only pre-approval projections
- execution sees only risk-approved actions

## Intraday Execution Order

1. refresh portfolio-relevant signals and news
2. recompute risk-relevant macro or event state when material alerts occur
3. rebuild the current portfolio plus open-hedge exposure view
4. rerun `PortfolioHedgePlanner`
5. run `RiskManager` for:
   - rebalance proposals
   - hedge adjustments
   - forced reductions when needed
6. execute approved rebalance and hedge changes

This keeps pre-open and intraday risk logic aligned and deterministic.

## Testing Strategy

Add focused unit and integration coverage for:

- planner classification of:
  - macro-only hedge cases
  - single-name event reduction cases
  - mixed-risk cases
- `RiskManager` application of planner intent to:
  - new tactical trades
  - new core holding adds
  - existing tactical reductions
  - hedge overlay generation
- pre-open orchestration:
  - pending trade incremental exposure influences approval
  - hedge overlays are generated only after planner and risk approval
- intraday orchestration:
  - elevated risk can adjust or close existing hedges
  - tactical positions can be forced lower when event risk sharpens

Tests should preserve auditability by asserting reason codes, applied rules, and generated hedge payloads.

## Migration Notes

- Existing `RiskManager` tests should remain valid for current hard rails unless explicitly replaced by stronger equivalents.
- The initial implementation can introduce `PortfolioHedgePlanner` behind orchestration changes without rewriting every repository interface at once.
- `generated_hedge_action` should move from mostly-unused placeholder status into an actively populated field with stable structure.

## Recommended Implementation Shape

The recommended implementation path is:

1. add planner-side contracts and deterministic rule engine
2. wire planner into pre-open and intraday orchestration
3. extend `RiskManager` to consume planner intent while preserving current hard rails
4. add hedge overlay decision persistence and execution wiring
5. backfill tests and UI/debug payloads

This keeps the system additive and avoids collapsing sizing, portfolio planning, and final approval into one oversized class.
