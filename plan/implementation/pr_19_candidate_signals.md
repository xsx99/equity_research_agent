# Prompt 04 — Show which signals drove each candidate's trade decision

You are editing the equity_research_agent repo. Make ONLY the changes described. Run
the matching tests.

## Goal
On the CANDIDATES tab, each decision card shows PRIMARY REASON / CURRENT OUTCOME /
TRADE IDENTITY / STRATEGY LENS / DUPLICATE ROWS, but never the actual signals
(technical/fundamental/news) behind the decision. Surface those signals on each
candidate card, the same way the TRADES tab shows a "Signal Summary".

## Context (verified facts) — the data exists but is dropped before the UI
- Model `CandidateScore` (`src/db/models/trading.py:1156-1209`) stores:
  - `core_signal_evidence_json` (line 1188) — technical/fundamental/news evidence
  - `selection_reason` (line 1196) — why this candidate was selected
  - `risk_tags_json` (1192), `invalidators_json` (1191),
    `missing_required_signals_json` (1189)
- Loader `_load_candidate_rows(...)` in `src/web/routers/today.py` (~lines 1087-1120)
  extracts only labels/IDs — it does NOT read `core_signal_evidence_json` or
  `selection_reason`.
- Presenter `_group_candidate_rows(...)` in
  `src/web/presenters/today_candidates.py` (lines 38-75) therefore has no signal data.
- Card template `src/templates/today.html:930-951` has no signal section.
- For reference, the TRADES-tab Signal Summary formatting lives in
  `src/web/presenters/today_workspace.py` — reuse its phrasing/format so the two tabs
  read consistently (e.g. "Technical: 20d return -1.44%, relative volume 0.78",
  "Fundamental: quality 0.98, revenue growth 0.65, margin trend 0.93").

## Changes
1. **Loader** (`src/web/routers/today.py`, `_load_candidate_rows`): for each
   `CandidateScore` row, also read `row.core_signal_evidence_json`,
   `row.selection_reason`, `row.risk_tags_json`, `row.invalidators_json`,
   `row.missing_required_signals_json`. Add them to the per-row dict.
2. **Presenter** (`src/web/presenters/today_candidates.py`): add a helper
   `_signal_bullets(evidence: dict) -> tuple[str, ...]` that turns
   `core_signal_evidence_json` into human-readable bullets grouped like the TRADES
   tab (Technical / Fundamental / News). In `_group_candidate_rows`, attach to each
   row: `signal_bullets` (from the primary candidate's evidence), `selection_reason`,
   and optionally `risk_tags` / `invalidators` as short bullets. If evidence is
   empty, set `signal_bullets` to a single string
   `"No signal snapshot recorded for this candidate."` — never leave it blank.
3. **Template** (`src/templates/today.html`): after the `candidate-decision-grid`
   block (after line 951, before the "Strategy alternatives" `<details>` at line 952),
   add a "Signals Used" section: render `row.selection_reason` as a short line, then
   `row.signal_bullets` as a `<ul>`. Match the existing `history-card-listing` /
   `metric-label` styling so it looks native.

## Acceptance criteria
- Every candidate decision card shows the concrete signals behind the decision, or
  the explicit "No signal snapshot recorded" fallback — never an empty section.
- The bullets read like the TRADES-tab Signal Summary (same phrasing/format).
- Add a test asserting `signal_bullets` is populated from
  `core_signal_evidence_json`. `pytest tests/web/ -q` passes.
