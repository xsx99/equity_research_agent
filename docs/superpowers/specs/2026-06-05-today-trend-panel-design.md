# Today Trend Panel Redesign

## Context

The current `Trend` panel in `/today` does not match how the operator wants to consume historical context.

Two problems are driving the change:

- `Signal Summary` currently repeats similar technical, news, and fundamental bullets from multiple snapshots, which makes the summary hard to scan.
- `Trend` currently renders history as text-heavy lists, especially for fundamentals, where many repeated metric notes create visual noise instead of useful context.

The user wants the panel to separate `latest summary` from `historical trend`:

- `Signal Summary` should emphasize the latest conclusion rather than historical repetition.
- `Trend` should become the place for technical history.
- `Fundamental` history should be visually demoted because it changes infrequently.

The active `/today` architecture already uses a presenter-driven server-rendered pattern:

- `src/web/routers/today.py` loads raw route payloads
- `src/web/presenters/today_workspace.py` shapes the selected ticker workspace
- `src/templates/today.html` renders the final operator surface

This spec keeps that boundary intact.

## Goals

- Reduce duplicate and repetitive reading in the `Trades -> Trend` detail tab.
- Show technical history in a form that can be scanned visually rather than read line-by-line.
- Keep implementation aligned with the current FastAPI + Jinja + presenter architecture.
- Use only data already available in the current `/today` route pipeline where practical.
- Make the redesigned trend panel testable with deterministic presenter and route assertions.

## Non-Goals

- This spec does not introduce a JS-heavy charting library.
- This spec does not add a new API endpoint or client-side state model.
- This spec does not redesign all of `/today`; it is scoped to the selected ticker `Trend` surface and the related `Signal Summary` responsibilities.
- This spec does not add true moving-average overlay charts or new market-data persistence beyond the current signal snapshot history.
- This spec does not turn fundamentals into time-series charts for this slice.

## User-Approved Decisions

The following behavior has already been confirmed with the user:

- `Trend` should focus on technical history.
- The technical panel should show four charts:
  - `RSI14`
  - `Price vs MA20`
  - `Relative Volume`
  - `ATR`
- `Price vs MA20` should use the existing `price_vs_sma_20` data rather than adding a true price-and-MA overlay chart in this slice.
- All four technical charts should use a shared `30 trading day` window.
- Fundamentals should not be charted in this slice.
- The fundamental section should show only the latest three notes, ordered newest first.

## Primary Approach

Recommended approach: extend `today_workspace` so it emits a structured `trend` view model instead of pushing text-heavy raw lists into the template.

This is preferred over:

- a template-only rewrite, which would keep data shaping implicit and brittle
- a larger router/data-loader refactor, which would be disproportionate to the scope of this UI change

The presenter should become the single place that decides:

- which technical metrics are charted
- how the last `30` trading days are selected
- how missing history degrades
- which fundamental notes are considered the latest three

The template should only render already-shaped cards and notes.

## Information Architecture

The `Trend` tab should stop reading like three unbounded text columns and instead become a two-part surface:

1. `Technical Trend`
2. `Fundamental Latest`

### Technical Trend

This is the primary content in the panel.

Desktop layout should use a `2 x 2` card grid with equal visual weight across the four technical metrics. Mobile or narrow layouts should collapse the grid to a single column.

Each card should contain:

- metric label
- latest value
- short window label such as `30D trend`
- compact line chart
- short status text or quiet empty-state text

The four cards should remain fixed in order:

1. `RSI14`
2. `Price vs MA20`
3. `Relative Volume`
4. `ATR`

The page should not reorder cards based on availability. If a metric lacks sufficient data, its card stays in place and renders a quiet degraded state.

### Fundamental Latest

This is a secondary context block below the technical grid.

It should show at most the latest three notes in descending time order. Each note should render:

- title
- summary or value
- as-of timestamp when available

This section replaces the current long repeated stack of metric notes. Older fundamental items remain available in the underlying data flow if needed later, but they are not rendered in the primary trend surface.

## Presenter Design

`src/web/presenters/today_workspace.py` should shape `detail.tabs.trend` into a more explicit structure.

Recommended structure:

```python
{
    "technical_cards": [
        {
            "metric_id": "rsi_14",
            "label": "RSI14",
            "current_value": "58.2",
            "window_label": "30D trend",
            "series": [
                {"time": "2026-05-01", "value": 48.1},
                {"time": "2026-05-02", "value": 49.7},
            ],
            "status_text": "Rising vs recent baseline",
            "empty": False,
        },
    ],
    "fundamental_latest": [
        {
            "title": "Margin Trend",
            "summary": "0.93",
            "time": "2026-06-05T13:30:00Z",
        },
    ],
}
```

The exact text can vary, but the structure should make the template nearly logic-free.

### Technical Series Rules

The presenter should derive chart series from the historical signal data already loaded for the selected ticker.

For each metric:

- inspect the signal snapshot history available for that ticker
- extract the metric value and timestamp from each eligible snapshot
- sort ascending by time for chart rendering
- keep only the latest `30` trading observations

Metric mapping for this slice:

- `RSI14` -> `technical.rsi_14`
- `Price vs MA20` -> `technical.price_vs_sma_20`
- `Relative Volume` -> `technical.relative_volume`
- `ATR` -> `technical.atr_pct`

If a snapshot lacks a metric, that point is skipped for that metric rather than fabricating a value.

### Fundamental Latest Rules

The presenter should collect fundamental notes from the existing per-ticker route payload, sort them newest first, and keep only the latest three items.

If multiple notes have identical timestamps, stable ordering should preserve deterministic test output.

## Route and Loader Expectations

`src/web/routers/today.py` should remain the source of raw historical collections, but it may need light shaping support so the presenter can build the chart series cleanly.

The route layer should continue to provide:

- signal history by ticker
- fundamentals by ticker

This slice should avoid turning the router into a chart-specific presenter. Any new helper added in the route should stay generic and history-oriented, not template-oriented.

If the current signal-history loader does not preserve enough raw numeric history for the four target metrics, the smallest viable route-side extension is acceptable so long as it remains a raw-history concern rather than a UI concern.

## Template and Rendering Design

`src/templates/today.html` should render the `Trend` panel as:

- a summary header for the panel
- a `Technical Trend` section with four chart cards
- a `Fundamental Latest` section with up to three notes

The current trend summary counts should be updated so they match the new surface and do not amplify noise. Good examples:

- `4 technical charts`
- `3 latest fundamental notes`

Bad examples:

- `76 notes`
- other counts that describe raw history volume rather than useful operator content

### Chart Rendering

The charts should use lightweight inline `SVG` rendered server-side by the template from presenter-provided point data.

Reasons:

- matches the current server-rendered `/today` stack
- avoids introducing a JS charting dependency for four small sparkline-style charts
- keeps behavior deterministic in tests
- keeps the implementation proportional to the size of the change

The goal is not a fully interactive charting system. The goal is a compact trend read.

Each chart should therefore be:

- small
- single-series
- visually clear
- non-interactive

## Signal Summary Role After This Change

`Signal Summary` should no longer function as a dump of historical bullet repetition.

For this slice, its role should be clarified as:

- latest conclusion summary
- latest high-signal technical/news/fundamental takeaways
- no historical repetition that belongs in `Trend`

The exact follow-up trimming of `Signal Summary` can be implemented in the same change if it stays scoped to “latest summary only” behavior and does not introduce new data semantics.

## Empty-State and Degradation Rules

The redesigned surface must degrade quietly.

### Technical cards

If a metric has no usable history:

- render the card in the normal fixed position
- show the metric label
- show `Unavailable` or equivalent quiet copy for the value
- render no line path or a standardized empty visual
- show a subdued explanation such as `Insufficient history`

### Fundamental section

If there are zero notes:

- render the section heading
- show one quiet empty-state line

If there are one or two notes:

- render only those notes
- do not add filler rows

### Panel integrity

The panel should never disappear entirely because one or more metrics are missing.

## Testing Strategy

Testing should lock both the presenter contract and the route-rendered HTML.

### Presenter tests

Extend `tests/web/test_today_workspace.py` to verify:

- the trend payload contains exactly four technical cards in the fixed approved order
- each technical card uses at most the latest `30` observations
- series points are sorted ascending for chart rendering
- the correct metric mapping is used for `RSI14`, `Price vs MA20`, `Relative Volume`, and `ATR`
- fundamental notes are sorted newest first and truncated to three items
- missing data produces quiet empty-state payloads rather than dropped cards

### Route/template tests

Extend `tests/web/test_today.py` to verify:

- `detail_tab=trend` renders the four technical chart cards
- the response includes the new section headings and no longer uses noisy repeated note counts
- only the latest three fundamental notes render in the primary trend surface
- standardized empty-state copy appears when trend data is unavailable

## Scope Control

This spec deliberately does not include:

- technical overlays with multiple lines per chart
- chart zooming, hovering, or client-side interaction
- configurable trend windows
- additional technical indicators beyond the approved four
- charted fundamentals

Those can be added later if needed, but they are outside the scope of this planning slice.

## Files Expected to Change

- `src/web/presenters/today_workspace.py`
- `src/templates/today.html`
- `src/static/style.css`
- `tests/web/test_today_workspace.py`
- `tests/web/test_today.py`
- `src/web/routers/today.py` only if raw-history shaping is required to support the presenter cleanly

## Implementation Readiness

This change is ready for implementation planning once the spec is reviewed for:

- presenter-vs-router boundary clarity
- whether current history loaders expose enough raw technical metric history
- whether the `Signal Summary` trimming is kept tight enough to remain in-scope
