# Design: `/today` UI quality pass

**Date:** 2026-06-23  
**Scope owner:** Codex session in auto mode  
**Depends on:** [11_today_ui_implementation_plan.md](./11_today_ui_implementation_plan.md), [pr_28_ui-redesign-plan.md](../implementation/pr_28_ui-redesign-plan.md)

## Why this follow-up exists

The PR 28 redesign fixed the `/today` information architecture, but the current UI still has
high-visibility quality problems in the rendered surface:

- the Portfolio analytics block is visually broken because the equity line and daily P&L bars
  compete inside one SVG, and dense bar widths collapse into a black mass;
- the Candidates tab still exposes machine-oriented artifacts such as duplicate-row counts,
  repeated audit rows, raw timestamps, and multiple adjacent fields that restate the same thing;
- some list surfaces read as unreviewed data dumps rather than operator-facing briefing surfaces;
- the Trades tab workflow is correct, but a few detail fields still leak raw/internal copy or use
  more density than the surrounding layout can support.

This pass is intentionally narrower than the redesign itself. The goal is not a new IA. The goal
is to make the existing IA render cleanly, scan quickly, and avoid leaking machine values.

## User-approved direction

- Overall visual direction: **Calm Briefing Surface**
- `Trades` workflow: **keep the current left ticker rail + right detail panel**
- First priority: **chart and list quality**

That means this pass should improve readability, hierarchy, and render correctness without turning
the page into a different product.

## Goals

1. Fix the Portfolio analytics section so charts are legible and mathematically stable.
2. Make candidate and risk lists read like an operator briefing rather than an audit export.
3. Remove or collapse raw/internal/machine-facing values that should never be first-class UI copy.
4. Preserve the existing `/today` routes, tab model, and Trades operator workflow.
5. Keep the light/warm visual language already established in `style.css`.

## Non-goals

- No new tabs or route/query-param changes.
- No frontend framework or client-side state system.
- No database/schema changes.
- No changes to trading logic, risk decisions, or data collection pipelines except presenter-level
  shaping needed for display quality.
- No redesign of `/research` or `/watchlist`.

## Surface-by-surface design

### 1. Portfolio: split analytics into two clean charts

The analytics block should stop trying to tell two stories in one SVG.

**Decision**
- Render **Account Equity** as a dedicated line chart card.
- Render **Daily P&L** as a separate bar chart card with its own baseline and bar geometry.
- Keep the metrics, but tighten them into a lighter companion block under/alongside the charts.

**Implementation implications**
- `build_portfolio_analytics(...)` should return separate payloads for equity and bars instead of a
  single mixed `equity_points + daily_bars` surface.
- Bar width must scale with series length instead of using a minimum width that guarantees overlap at
  high point counts.
- Degenerate cases must stay safe: one point, all-equal equity, zero-only daily P&L, and empty bars.

### 2. Candidates: collapse duplicates into human review history

The Candidates tab currently mixes review content with backend audit density.

**Decision**
- Treat rows grouped by ticker as one candidate briefing card.
- Deduplicate repeated evaluations that only restate the same outcome/summary pair.
- Replace the machine-facing `Duplicate Rows` field with a human-facing `Evaluation History` summary.
- Show timeline timestamps with the existing local-time filter instead of raw ISO strings.

### 3. Trades: preserve workflow, reduce detail noise

The Trades tab already has the right interaction model. This pass should not replace it.

**Decision**
- Keep the left-side rail and right-side detail canvas exactly as the working model.
- Use the calm-briefing tone inside the existing structure: stronger spacing, fewer duplicate labels,
  quieter empty copy, and humanized supporting text.
- Hide any remaining raw/internal/smoke-style identifiers from hero and plan blocks.

### 4. Risk & Macro and attention feeds: briefing rows, not loose dumps

These surfaces should read like a summary page an operator scans in seconds.

**Decision**
- Normalize event, risk-source, and attention rows into consistent cards/rows with the same shared
  visual language already used elsewhere on `/today`.
- Keep counts and badges, but pair them with readable one-line summaries and quiet empty states.

## Data-to-display rules for this pass

- All displayed times must go through existing local-time formatting in the template.
- Raw internal IDs, smoke labels, and backend-only duplicate counters should not render as primary UI.
- If the presenter already has a cleaned label helper, use it instead of formatting ad hoc in Jinja.
- When the UI needs to collapse repeated rows, do it in the presenter and test it there.

## Acceptance criteria

- Portfolio charts are legible at both short and long history windows.
- Candidate cards no longer expose duplicate-machine-row language or repeated identical timeline rows.
- Trades keeps the current operator workflow while reading cleaner.
- Risk and attention lists visually match the rest of the dashboard instead of looking like raw HTML.
- Empty states remain quiet and stable across all touched tabs.
