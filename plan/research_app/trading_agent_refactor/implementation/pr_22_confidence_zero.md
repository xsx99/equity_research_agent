# Prompt 08 — Confidence shows 0.00 everywhere

You are editing the equity_research_agent repo. INVESTIGATE FIRST, then fix or report.

## Problem
Both the TRADES detail view and the candidate cards show `CONFIDENCE 0.00`
everywhere.

## Do this
1. Determine whether confidence is genuinely 0 in the underlying data, or present in
   the data but not wired through to the display.
   - Trace the confidence field from its source (the trading decision / candidate
     score record) through the loader in `src/web/routers/today.py`, the presenters
     (`today_workspace.py`, `today_candidates.py`), to the template
     `src/templates/today.html` (the `CONFIDENCE` metric).
2. If it's a wiring gap (value exists but is dropped/overwritten with 0), fix the
   path so the real confidence shows.
3. If confidence is genuinely 0 in the data, do NOT fake a value — instead write a
   short note stating that confidence is actually 0 upstream and where it should be
   produced, so it can be handled as a separate data issue.

## Acceptance criteria
- Either confidence displays the real value, or you have reported (in writing) that
  the value is genuinely 0 upstream with the exact file:line where it should be set.
- `pytest tests/web/ -q` passes.
