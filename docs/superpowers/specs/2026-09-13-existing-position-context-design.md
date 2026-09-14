# Existing-Position Context Design

## Goal

Ensure pre-open trading decisions recognize broker-synced open exposure for the
same ticker and give the decision agent enough quantity/value context to treat
repeated signals as target-exposure decisions rather than automatically as new
entries.

## Scope

The live pre-open and manual-review runners already obtain an authoritative
`PortfolioContext` from portfolio sync before generating trading decisions. The
decision pipeline will receive that context, match positions case-insensitively
by ticker, and add the matching position details to the validated input and
persisted decision snapshot. The missing-signal fallback will carry the same
position context for an auditable and safe result.

This change does not alter deterministic risk sizing, broker order quantities,
or the set of allowed decision actions. It only corrects the state supplied to
the decision agent and documents that `target_weight` describes desired total
exposure.

## Approaches considered

1. Have `TradingDecisionPipeline` query the repository for positions. Rejected:
   it couples the decision layer to storage and can diverge from the portfolio
   state already used by the risk workflow.
2. Pass the synced `PortfolioContext` through the live runners. Recommended:
   it preserves one authoritative snapshot and makes the behavior explicit and
   testable at the runtime boundary.
3. Infer position state from risk decisions or candidate metadata. Rejected:
   those artifacts are not complete portfolio state and can omit an exposure.

## Data contract

`TradingDecisionInput` gains a `position_context` object containing:

- `has_existing_position`: whether any stock or option exposure matches the
  candidate ticker;
- `positions`: matching exposures with quantity, market value, notional
  exposure, direction, trade identity, strategy id, and inferred instrument
  type;
- `total_market_value` and `current_weight` relative to account equity.

The existing top-level `has_existing_position` field is populated from the same
match. If no context is provided by a legacy direct caller, the current empty
portfolio behavior remains backward compatible; live pre-open and manual review
always pass the synced context.

## Prompt behavior

The trading prompt will state that `target_weight` is desired total exposure.
When matching exposure exists, a repeated signal must be evaluated against the
current position context and should not be treated as a fresh entry by default.

## Verification

Add regression coverage for:

- a same-ticker open position populating the boolean and quantity/value context;
- a ticker with no matching position remaining a new-exposure case;
- the missing-snapshot fallback preserving the same context;
- live pre-open forwarding portfolio context to the decision pipeline.

