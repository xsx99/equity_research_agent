# PR 59 Today Trades Layout Overflow Fix

**Goal:** Fix the `/today?tab=trades` layout shown in the 2026-07-21 screenshot where the selected ticker detail cards overflow past the right edge of the Trades canvas.

**Design context:** This follows the existing Today UI direction in `plan/design/12_today_ui_quality_pass.md` and `plan/design/14_today_ui_information_design.md`: preserve the left ticker rail plus right detail panel workflow and make the rendered surface clean and scannable. No information architecture, data contract, or route behavior changes are in scope.

## Root Cause

The Trades workspace is a CSS grid with a left rail and right detail column, but the grid children kept the browser default `min-width:auto`. The detail panel contains wide nowrap tables, so its intrinsic width forced the right column wider than the containing Trades card. `.table-scroll` had horizontal overflow enabled, but the parent grid item could not shrink far enough for that scroll boundary to take effect.

## Implementation

- Add a CSS regression test for the containment contract in `tests/web/test_today_styles.py`.
- Let the Trades canvas, workspace grid, detail panel, subcards, tab panels, and `.table-scroll` shrink with `min-width:0`.
- Keep wide header tables scrollable inside `.table-scroll` with `max-width:100%`.
- Let Trade Plan text cells wrap while preserving nowrap numeric cells.

## Verification Plan

- RED: `source ~/.venv/bin/activate && pytest tests/web/test_today_styles.py -q`
- GREEN: `source ~/.venv/bin/activate && pytest tests/web/test_today.py tests/web/test_today_styles.py -q`
- Compile: `source ~/.venv/bin/activate && python -m compileall -q src`
- CSS hygiene: `git diff --check`
- Render check: run the app locally and capture `/today?tab=trades` in Chrome; confirm the selected detail panel stays inside the Trades canvas.
