# Alpaca-Backed Option Paper Execution Design

**Date:** 2026-06-14

## Goal

Replace the current local-simulation-only option execution path with Alpaca paper-trading-backed option execution for the same live surfaces that already support stock paper trading:

1. live preopen tactical option trades
2. live intraday option lifecycle actions
3. live `risk_hedge_overlay` option hedges

The local database must remain in use, but only as the application audit and strategy-semantic mirror. Alpaca paper becomes the execution and broker-account source of truth for option orders, fills, positions, and account-side option exposure.

## Scope

In scope:

- Alpaca-backed option order submission for the existing whitelist:
  - `long_call`
  - `long_put`
  - `put_credit_spread`
  - `call_credit_spread`
  - `long_straddle`
  - `long_strangle`
- Broker-native support for:
  - `open_option_strategy`
  - `close_option_strategy`
  - `roll_option_strategy`
  - `adjust_option_strategy`
- Persistence updates required to reconcile broker-native option orders and positions
- Live runtime wiring, standalone smoke coverage, and operator runbook updates

Out of scope:

- live-money option execution
- manual-review runtime behavior changes
- new option strategy types
- options approval workflows for live accounts
- a full assignment/exercise operations subsystem beyond basic reconciliation against broker state and option-event activities

## Current State And Gaps

The repo already routes live stock paper orders through Alpaca, but option execution still behaves like a local simulator:

- `PaperOptionBroker` immediately fills locally and never submits to Alpaca.
- `paper_option_orders` / `paper_option_executions` do not persist broker-native identifiers such as `client_order_id` or `broker_order_id`.
- `option_strategy_legs` persist strikes, expiry, Greeks, and prices, but not the concrete Alpaca-tradable option contract symbol required for simple or multi-leg orders.
- `PaperExecutionWorkflow` models `roll_option_strategy` and `adjust_option_strategy` as local bookkeeping transitions, not as broker-native close/open leg payloads.
- `BrokerPortfolioSyncWorkflow` still overlays local `paper_option_positions` onto the Alpaca stock account snapshot, and `build_positions_from_broker(...)` currently treats every `/positions` row like a stock position. Once real broker option positions exist, this will misclassify or double-count exposure.

## Options Considered

### Option A: Keep the local simulator and mirror results into Alpaca later

Pros:

- smallest code change up front
- preserves all current local semantics

Cons:

- creates two divergent books for the same option trades
- cannot guarantee broker/account reconciliation
- still leaves lifecycle actions (`close` / `roll` / `adjust`) non-broker-native

Verdict: reject.

### Option B: Make Alpaca the option execution source of truth and keep local strategy state as a mirror

Pros:

- matches the existing PR06 stock-broker contract
- gives one real broker book for orders, fills, positions, and buying power
- preserves local strategy-level semantics, audit, and reflection inputs
- supports multi-leg open/close/roll workflows with the broker contract Alpaca already documents

Cons:

- requires contract-symbol persistence and richer lifecycle metadata
- requires reconciliation work in portfolio sync and local strategy positions

Verdict: recommended.

### Option C: Send only open orders to Alpaca and keep close/roll/adjust local

Pros:

- faster initial cut for tactical opens

Cons:

- splits the same option book across broker-backed and local-simulated lifecycle paths
- guarantees drift in intraday rebalance and hedge-overlay flows

Verdict: reject.

## Recommended Design

### 1. `PaperOptionBroker` becomes Alpaca-backed

Keep the public live-execution abstraction aligned with stocks:

- `PaperStockBroker` remains the Alpaca-backed stock broker
- `PaperOptionBroker` becomes the Alpaca-backed option broker

The current local immediate-fill implementation should move to a test-only/local-only helper so unit tests can still exercise strategy transitions without touching Alpaca.

`PaperOptionBroker` should support:

- deterministic idempotency via `client_order_id`
- single-leg simple option orders for `long_call` / `long_put`
- `mleg` orders for spreads, straddles, strangles, and broker-native rolls
- broker-status polling by `client_order_id`, mirroring the stock broker pattern
- optional account/position/activity sync helpers needed for reconciliation

### 2. Persist broker-native option contract and order metadata

The current option decision artifacts are not sufficient to submit or reconcile Alpaca orders. The app must persist:

- per-leg Alpaca option contract symbol
- per-leg ratio quantity
- order-level `client_order_id`
- order-level `broker_order_id`
- order class (`simple` vs `mleg`)
- enough serialized leg metadata to reconstruct close/roll/adjust payloads later

`paper_option_positions` should remain strategy-level rows, but their metadata must include the opened broker leg refs so intraday close/roll/adjust actions can map an existing strategy position back to concrete broker contracts and position intents.

### 3. Broker-native lifecycle execution replaces local-only transitions

`PaperExecutionWorkflow` should keep owning option execution, but it can no longer treat option lifecycle changes as synthetic local state changes.

Required behavior:

- `open_option_strategy`
  - submit a simple or `mleg` Alpaca order from the current option decision legs
- `close_option_strategy`
  - submit a broker-native close order using the existing strategy position's persisted leg refs
- `roll_option_strategy`
  - submit one `mleg` order that closes old legs and opens replacement legs when the combined strategy fits within Alpaca's multi-leg constraints
- `adjust_option_strategy`
  - use the same persisted leg-ref model and explicitly define whether the adjustment is a close/replace or partial reshape before order submission

If the workflow cannot build a complete broker-native payload, it must fail safe by rejecting execution instead of silently falling back to a local fill.

### 4. Alpaca account and positions become the live option exposure source of truth

Once option trades execute at Alpaca, the live portfolio view must stop treating local option rows as authoritative market exposure.

The new contract should be:

- Alpaca `/account` and `/positions` drive:
  - option market value
  - broker-reported account equity and buying power
  - current open broker option positions
- local `paper_option_positions` drive:
  - strategy ID
  - trade identity
  - lifecycle lineage
  - assignment-risk / hedge metadata
  - reflection attribution

`BrokerPortfolioSyncWorkflow` should split broker stock vs broker option rows, join broker option positions back to local strategy metadata where possible, and stop applying the old `broker_plus_local_option_overlay` path in live mode.

If a local strategy-level option position no longer has a matching broker position, the sync layer should mark it closed/reconciled. Broker option-event activities such as `OPEXC`, `OPASN`, and `OPEXP` can then backfill the close reason when those records become visible.

### 5. Runtime scope stays the same

No new runtime should be introduced. The same live surfaces remain in scope:

- `LivePreopenRuntime`
- `LiveIntradayRefreshRuntime`
- `risk_hedge_overlay` generated inside the existing risk workflow

The dependency builders should swap from the local simulator to the Alpaca-backed option broker and keep the explicit `execute_paper_option_orders` guardrail.

## Safety Rules

- Dry-run remains the default everywhere.
- Stock and option execution flags remain separate.
- No local-simulation fallback should occur inside live execution paths once option execution is enabled.
- Missing contract symbols, missing persisted broker leg refs, or unsupported lifecycle payloads must reject execution rather than guess.
- The existing option whitelist remains unchanged.
- Standalone smoke coverage is required because this path touches both external APIs and the DB.

## Implementation Notes

- Alpaca paper options are enabled by default in the paper environment according to the current official docs.
- Alpaca documents `simple` option orders, `mleg` orders, and position-intent fields such as `buy_to_open`, `buy_to_close`, `sell_to_open`, and `sell_to_close`.
- Alpaca also documents options event activities (`OPEXC`, `OPASN`, `OPEXP`), which should inform local reconciliation but do not need a full separate subsystem in this slice.
