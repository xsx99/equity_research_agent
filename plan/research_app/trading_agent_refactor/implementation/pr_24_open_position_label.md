# Prompt 10 — "Open Position" must not be labeled "no_trade"

You are editing the equity_research_agent repo. Make ONLY the change described.

## Problem
On the TRADES workspace, AAPL appears in the "Open Positions" bucket but its item
label is `no_trade`. The label reflects the latest decision verb instead of the
position's lifecycle state, which is confusing.

## Do this
- Find where the workspace bucket items get their label
  (`src/web/presenters/today_workspace.py`, and the bucket rendering in
  `src/templates/today.html` — the "Open Positions" / "Closed Today" / "Watch"
  lists).
- For items in the Open Positions bucket, the per-item label should reflect the
  position lifecycle state (e.g. "Open"), not the latest decision verb (`no_trade`).
  The latest decision can still be shown as secondary detail, but the primary label
  must be consistent with the bucket.

## Acceptance criteria
- An open position in the Open Positions bucket is labeled as open, even when its
  latest decision was "No Trade".
- The bucket label and the per-item label are consistent.
- `pytest tests/web/ -q` passes.
