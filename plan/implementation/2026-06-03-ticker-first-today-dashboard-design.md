# Ticker-First Today Dashboard Design

## Context

The current `/today` trading workstation surfaces the `Trades` area primarily as a flat, time-ordered table of trade decisions. This makes same-ticker context hard to follow because signal updates, risk decisions, watch outcomes, and orders are split across many rows. The operator intent is not to audit one row at a time first; it is to understand the current state of a ticker, why it is important now, and how that state evolved.

This spec defines a ticker-first redesign for the `/today` workstation that preserves auditability while making per-ticker operating context the primary UX.

## Goals

- Reorganize the `/today` scan/trade experience around tickers instead of individual decision rows.
- Put the most urgent tickers first, including both strong opportunity signals and high-risk situations.
- Make the default per-ticker view show the latest conclusion first.
- Preserve deeper audit trails for trend, decision history, risk history, and execution detail without making the main screen noisy.
- Reuse existing data already persisted by the trading pipeline wherever possible.

## Non-Goals

- This spec does not redesign every `/today` tab. It focuses on the ticker-first workstation pattern centered on the current `Trades` experience and adjacent detail context.
- This spec does not require a new front-end framework or SPA architecture.
- This spec does not define new market-data calculations beyond what is needed to visualize existing signal history.

## Primary Approach

Recommended approach: `ticker-first + priority buckets`.

Instead of a flat trade row list, the page should present:

- a left ticker rail organized by operator attention
- a right ticker detail panel for the selected ticker
- a latest-conclusion-first summary at the top of the detail panel
- a smaller set of focused tabs for audit and history

This is preferred over:

- a pure time stream, which keeps ticker context fragmented
- separate opportunities/risk lists, which can duplicate the same ticker in multiple places
- a raw grouped table, which still biases the UI toward row inspection instead of ticker understanding

## Information Architecture

### Page Layout

The main workstation area becomes a two-pane layout:

- Left pane: `Ticker Rail`
- Right pane: `Ticker Detail`

The surrounding `/today` page header, top metrics, and top-level workstation tabs can remain conceptually intact, but the main content area should prioritize this ticker-first structure.

### Left Pane: Ticker Rail

The ticker rail should be organized into three buckets:

1. `Action Now`
2. `In Position`
3. `Watch`

These buckets are semantic operator buckets, not raw database statuses.

#### `Action Now`

This bucket should include tickers that need immediate operator attention for any of these reasons:

- strong buy or strong sell signal
- critical/high risk alert
- new risk block or size reduction
- material signal change
- order pending, rejected, partial fill, or execution issue
- existing position with invalidator proximity or exit urgency

Important: this bucket must include strong buy opportunities, not only risky situations. The operator wants an attention-first queue, not a risk-only queue.

#### `In Position`

This bucket should include tickers with active positions or active option/hedge state that do not currently qualify for `Action Now`.

#### `Watch`

This bucket should include watch-only, no-trade, or lower-priority candidates that are still worth monitoring but do not currently require immediate action.

### Ticker Rail Card Content

Each ticker card should show only compact, high-signal fields:

- ticker and company name
- one highest-priority attention badge
- latest decision label
- one-line `why now` explanation
- latest scan/decision timestamp
- a minimal position/risk state line when applicable

Examples of attention badges:

- `Strong Buy`
- `Risk Alert`
- `Order Pending`
- `In Position`
- `Watch`

Examples of `why now` lines:

- `breakout confirmed + risk approved`
- `signal deterioration since preopen`
- `earnings risk block`
- `order accepted, awaiting fill`

The rail should avoid noisy raw fields such as long decimal confidence values, raw strategy ids without formatting, or full JSON.

### Attention Ordering Rules

The page should not rely on a fully opaque score-only sort. Ordering should use two layers:

1. bucket assignment by explicit rules
2. intra-bucket ordering by priority and recency

Within `Action Now`, recommended ordering precedence:

1. executable trade or order-state issue
2. strong directional opportunity
3. critical risk condition
4. material signal change
5. recency
6. confidence / importance tiebreakers

This keeps the system explainable while still surfacing the highest-value opportunities and risks together.

## Ticker Detail

The right pane should default to the selected ticker and be structured as:

- `Latest Conclusion`
- `Timeline`
- `Trend`
- `Decisions`
- `Risk`

The operator selected behavior is `latest conclusion first`, not timeline-first and not position-first.

## Latest Conclusion

This is the default top-of-detail summary and should contain four blocks in this order:

1. `Trade Decision`
2. `Signal Summary`
3. `Risk Manager Summary`
4. `Position / Execution State`

### 1. Trade Decision

Shows the latest operator-readable conclusion:

- decision label such as `Enter Long`, `No Trade`, `Trim`, `Exit`
- selected strategy
- expression bucket
- confidence band, not raw precision-heavy number
- optional decision delta vs previous state, for example:
  - `changed from watch to enter_long`
  - `still no_trade after risk review`

This block should present a concise human-readable summary, not raw LLM JSON.

### 2. Signal Summary

This block should have two layers:

- top summary bullets
- evidence modules below

The summary bullets should provide 3-5 short statements describing the signal state, for example:

- `relative strength improving vs QQQ`
- `price broke above preopen resistance`
- `news flow mildly positive`
- `no new fundamental change`

Below that, the signal summary should present evidence modules by source family.

#### Technical Module

If technical history exists, show compact historical line charts. The first version should prioritize the most decision-relevant series instead of adding many indicators:

- `price / key level trend`
- `relative strength trend`

Additional indicators such as RSI or ATR should only appear when they materially support the decision.

#### News Module

If material news exists, show structured snippet summaries instead of a raw article table:

- cluster headline or event name
- 1-2 sentence summary
- why it matters for the ticker or decision

Only top material items should be shown by default.

#### Fundamental / Catalyst Module

If relevant fundamental or catalyst context exists, show concise snippet summaries such as:

- revision or guidance changes
- margin or demand commentary
- product, regulatory, earnings, or backlog developments

If no material update exists for a module, the UI should explicitly show `No material update`.

### 3. Risk Manager Summary

This block should state the latest risk stance in plain language:

- `approved`
- `approved with size reduction`
- `blocked`

It should also show one short reason line, for example:

- `reduced for concentration`
- `blocked by event risk`
- `approved, invalidator distance acceptable`

### 4. Position / Execution State

If the ticker has a position or order state, show:

- current position size
- day PnL / unrealized PnL
- order status
- invalidator or exit-plan summary

If no position exists, explicitly show `No position`.

## Detail Tabs

The tab set under the latest conclusion should be:

- `Timeline`
- `Trend`
- `Decisions`
- `Risk`

Each tab must have a narrow responsibility to prevent the interface from collapsing back into duplicate tables.

### Timeline

Purpose: answer `what happened to this ticker today and recently`.

This should use a time-axis/card presentation, not a wide table. Supported event types:

- scan
- signal change
- news/fundamental update
- risk review
- trade decision
- order update

Each timeline item should show:

- time
- event type
- one-line summary
- link or expand affordance for detail

Timeline is the operator audit entry point, but it should remain summary-first.

### Trend

Purpose: answer `why does the system currently see this ticker this way`.

This tab should include:

- the technical line charts
- technical summary module
- news snippet summary module
- fundamental/catalyst snippet summary module

This is the primary evidence tab.

### Decisions

Purpose: answer `how has the system decided on this ticker over time`.

This tab should use a compact decision list rather than a raw table. Each item should show:

- decision
- strategy
- confidence band
- risk outcome
- order outcome
- whether it changed from the previous decision

Each item can expand into deeper audit details such as:

- full decision rationale
- strategy scores
- raw LLM JSON
- linked signal snapshot

### Risk

Purpose: answer `why is this tradable or blocked, and how is risk evolving`.

This tab should contain three sections:

- `Current risk stance`
- `Position / invalidator / exit`
- `Risk history`

`Risk history` should focus on meaningful risk-state changes such as approve/reduce/block transitions instead of replaying all signal history.

If there is no open position, this tab should still show the active decision-time risk context such as:

- event risk
- concentration
- freshness
- macro constraint

## Interaction Model

- Selecting a ticker in the rail updates the right detail panel.
- The first selected ticker should default to the highest-priority item in `Action Now`, then `In Position`, then `Watch`.
- The UI should preserve deep-link capability to a selected ticker and optionally to a specific decision within that ticker context.
- Expansions should be used for raw JSON and low-frequency debug fields, not for the primary human-facing summaries.

## Data and Presentation Requirements

The redesign should favor reshaping existing persisted artifacts over inventing new operator-only abstractions where possible.

Expected existing inputs include:

- `TradingDecision`
- `RiskDecision`
- `PaperOrder`
- `PaperPosition`
- `SignalSnapshot`
- `IntradaySignalSnapshot`
- `NewsAlert`
- `CandidateScore`
- `DailyReflection`

Likely presentation-layer additions may include:

- ticker-centric aggregation view models
- bucket assignment helpers
- attention-priority helpers
- summary-string builders for signal/risk/decision cards
- compact chart data extraction for technical history

## Error Handling and Empty States

- If a ticker lacks one source family, render the remaining modules and clearly show missing sections as unavailable or non-material.
- If chart history is not available, show a deterministic empty state instead of hiding the module.
- If no ticker qualifies for `Action Now`, the rail should still render the empty bucket and then show `In Position` / `Watch`.
- If no ticker data exists at all, show a clear workstation empty state instead of a partial broken layout.

## Testing Implications

The redesign should add or update deterministic web tests for:

- bucket assignment and ticker ordering
- default ticker selection behavior
- rendering of summary blocks
- presence of evidence modules for technical/news/fundamental inputs
- empty states for missing data
- selected ticker deep-link behavior
- expansion/detail rendering without requiring raw JSON as primary content

Where possible, keep aggregation and bucketing logic outside templates so it can be unit tested independently.

## Implementation Strategy

Recommended delivery shape:

1. add ticker-centric view-model helpers in the `/today` route layer or adjacent presenter module
2. reshape `Trades` from flat table UX to rail + detail layout
3. implement `Latest Conclusion`
4. add detail tabs with summary-first content
5. add technical mini-chart support
6. add news/fundamental snippet summaries

This sequence keeps the highest operator-value changes early while allowing chart/detail enhancements to land incrementally.

## Open Questions Resolved

- Default organization: ticker-first
- Default per-ticker landing content: latest conclusion first
- Left-rail priority: attention-first, not risk-only
- Strong buy opportunities must surface alongside high-risk situations in `Action Now`
- `Signal Summary` should support technical history charts
- `Signal Summary` should support concrete snippet summaries for news and fundamental/catalyst evidence
