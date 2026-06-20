# Prompt 01 — Remove the JSON "audit trail" from the Today UI

You are editing the equity_research_agent repo (FastAPI + Jinja templates). Make
ONLY the changes described. Do not refactor unrelated code. Run the matching tests
when done.

## Goal
Remove every trace of a raw-JSON / raw-ID "audit trail" from the Today UI. The user
does not want JSON or machine IDs shown anywhere; the UI must be human-readable only.

## Context (verified facts)
- `src/web/routers/today.py:1466-1467` attaches raw payloads to the trade-detail
  tabs:
  ```python
  tabs["raw_json"] = audit_detail
  risk_tab["raw_json"] = audit_detail.get("risk_decision")
  ```
  No template renders `raw_json` today — it's dead plumbing from a previous plan.
  Remove it so it can never be surfaced.
- `src/templates/today.html:966-974` renders a candidate "Advanced" block that
  prints raw internal IDs (`Source ID`, `Outcome ID`, `Trade Identity ID`,
  `Strategy ID`). That is a raw audit trail and must be removed.

## Changes
1. In `src/web/routers/today.py`, delete the two lines that assign `tabs["raw_json"]`
   and `risk_tab["raw_json"]` (around line 1466-1467). Then `grep -rn "raw_json" src/`
   and remove any remaining references in routers/presenters/templates.
2. In `src/templates/today.html`, delete the candidate "Advanced" internal-IDs block
   at lines 966-974 — the `<details><summary>Advanced</summary> ... Strategy ID ...</details>`
   block that prints the four `... ID:` rows. KEEP the "Strategy alternatives"
   `<details>` block just above it (lines ~952-964); that one is human-readable.

## Acceptance criteria
- `grep -rn "raw_json" src/` returns zero matches.
- The CANDIDATES tab no longer shows any `... ID: <value>` rows.
- All tests in `tests/web/` pass: `pytest tests/web/ -q`.
