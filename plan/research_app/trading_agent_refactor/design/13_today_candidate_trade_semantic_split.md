# Design: `/today` candidate/trade semantic split

**Date:** 2026-06-25  
**Scope owner:** Codex session in auto mode  
**Depends on:** [11_today_ui_implementation_plan.md](./11_today_ui_implementation_plan.md), [12_today_ui_quality_pass.md](./12_today_ui_quality_pass.md)

## Why this follow-up exists

The current `/today` workstation mixes three different concepts:

- candidate evaluation state (`actionable`, `watch`, `blocked`)
- manual request mode (`review_only`, `paper_trade_eligible`)
- trade workflow state (`no_trade`, `hold`, `enter_long`, open position)

Because the read model blends those axes, the same ticker can appear to mean different things in
different tabs:

- an actionable candidate can still land in the Trades `watch` rail even before it has a trade
  decision row;
- `watch_only` candidates and `actionable but reviewed no-trade` tickers both read as "watch";
- `manual review` looks like a lifecycle outcome even though it is only a forced-evaluation source.

This slice fixes the semantic split, not the underlying trading logic.

## User-approved direction

- Adding a ticker through `manual review` does not change.
- Display location changes, not the request-creation workflow.
- `review_only` requests stay on the Candidates tab.
- Non-manual or `paper_trade_eligible` actionable rows move to the Trades tab.
- Non-actionable rows stay on the Candidates tab.

This is the approved **mode-priority** rule set.

## Goals

1. Make `manual review` mean "why this ticker is being evaluated", not "what state it is in."
2. Make `Candidates` mean "review-only or non-actionable evaluation outcomes."
3. Make `Trades` mean "trade-path tickers," including reviewed no-trade conclusions.
4. Remove the current fallback where arbitrary risk/signal/news/fundamental presence can make a
   ticker appear in the Trades workspace.
5. Keep existing trading logic, scheduler phases, and manual request creation/dismiss flows intact.

## Non-goals

- No changes to strategy scoring, risk rules, or order execution.
- No changes to `manual review` request creation, dismissal, or scheduler wiring.
- No schema changes.
- No attempt to redesign the broader `/today` IA beyond labels required to stop semantic leakage.

## Canonical display rules

### 1. Manual review remains a source, not a state

`manual review` continues to mean that a ticker was explicitly pinned by the operator and must be
evaluated until dismissed. It does **not** determine whether the ticker is a trade candidate or a
watch-only outcome.

### 2. Candidates tab ownership

The Candidates tab owns rows that are not ready to be treated as trade-path items:

- all `review_only` manual requests, regardless of score or strategy match
- all non-actionable candidates
- all `watch_only` / `ordinary_watch` / `catalyst_watch` / blocked outcomes

In other words, the Candidates tab becomes the home for:

- forced reviews that are intentionally non-executable
- naturally non-actionable outcomes from scanner/manual evaluation

### 3. Trades tab ownership

The Trades tab owns trade-path items:

- actionable scanner candidates
- actionable `paper_trade_eligible` manual requests
- actionable rows that later resolve to `no_trade` or `hold`
- open and recently closed positions that already belong to the trade lifecycle

The key rule is that an actionable row stays in the Trades workflow even if the final decision is
"do not enter."

### 4. Review-only precedence

`review_only` is the one explicit override to actionability-driven display routing:

- if a ticker is `review_only`, it stays on Candidates even if its candidate row would otherwise
  look actionable
- the system may still record candidate/trading-decision artifacts for audit, but the operator
  surface treats it as a review queue item, not a trade workflow item

### 5. Trades workspace seeding

The Trades workspace should no longer be seeded from every ticker that appears in:

- risk snapshots
- signal history
- news snippets
- fundamental snippets

Those datasets remain detail enrichers only. A ticker enters the Trades workspace only when it is
part of the trade path:

- actionable candidate display row
- persisted trade decision
- open position
- recent closed position

## Presenter / route implications

### Route-level split

`src/web/routers/today.py` should produce explicit display groups instead of asking presenters to
infer them from mixed raw rows:

- candidate-surface rows
- trade-workspace seed rows
- manual request queue rows

The split should happen once at the route/read-model boundary.

### Candidates presenter

`today_candidates.py` should assume its rows are already candidate-surface rows. It should stop
implicitly representing actionable trade-path rows as generic candidate cards.

### Trades presenter

`today_workspace.py` should stop using risk/news/fundamental presence as ticker discovery input.
Those datasets should only enrich items that are already in the trade workspace.

## Naming adjustments

The main confusion is the overloaded word `watch`. Naming should distinguish:

- `watch_only candidate` -> a candidate-surface non-actionable outcome
- `reviewed no-trade` -> a trade-path ticker whose decision resolved to `no_trade` or `hold`

The Trades rail should therefore stop presenting reviewed trade-path rows as generic `watch` items.
Exact user-facing copy can stay lightweight, but it should not collapse these concepts into the same
label.

## Testing strategy

### Route/read-model tests

- prove `review_only + actionable` stays on Candidates
- prove `paper_trade_eligible + actionable` moves to Trades
- prove actionable + `no_trade` decision stays in Trades
- prove non-actionable scanner/watch rows stay on Candidates
- prove risk/news/fundamental-only tickers no longer seed Trades

### Presenter tests

- `today_candidates.py` receives only candidate-surface rows
- `today_workspace.py` builds the trade rail from trade-path seed rows, not passive context rows

### Render tests

- the Candidates tab no longer presents trade-path reviewed no-trade rows as generic candidates
- the Trades tab no longer labels trade-path reviewed no-trade rows as `watch`

## Acceptance criteria

- `review_only` tickers remain on Candidates.
- Actionable non-review-only tickers appear on Trades even when their decision is `no_trade` or
  `hold`.
- `watch_only` / blocked / non-actionable outcomes remain on Candidates.
- Trades no longer picks up orphaned tickers just because they exist in risk/signal/news/fundamental
  detail datasets.
- The same ticker no longer means "watch-only candidate" in one place and "reviewed no-trade trade
  path" in another without explicit differentiation.
