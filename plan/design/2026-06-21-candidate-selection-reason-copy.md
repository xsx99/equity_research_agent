# Candidate Selection Reason Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the opaque candidate-scan `selection_reason` copy `deterministic PR02 signals matched strategy` with operator-facing strategy-and-signal wording on `/today` `Candidates`, without changing backend matching or persistence semantics.

**Architecture:** Keep `CandidateScore.selection_reason` as the persisted audit field. Detect the generic internal match string only at the Today presenter boundary, synthesize a display-only summary from the candidate’s `strategy_label` plus the strongest items in `core_signal_evidence`, and continue showing explicit backend reasons such as negative catalysts or macro blocks unchanged. Reuse the existing signal-formatting/copy conventions so the one-line summary and the bullets stay aligned instead of inventing a second vocabulary.

**Tech Stack:** Python, pytest, FastAPI/Jinja, existing `/today` presenters and copy helpers.

---

## Required Pre-Read

- `documents/general_instructions.md`
- `plan/research_app/trading_agent_refactor/implementation/pr_19_candidate_signals.md`
- `plan/research_app/trading_agent_refactor/design/09_ui_error_testing_delivery.md`
- `src/web/presenters/today_candidates.py`
- `src/web/presenters/today_copy.py`
- `tests/web/test_today_candidates.py`
- `tests/web/test_today.py`

## Scope And Non-Goals

- In scope:
  - Humanize the one-line `selection_reason` shown above candidate signal bullets.
  - Keep the detailed `signal_bullets`, `risk_tags`, and `invalidators` sections intact.
  - Preserve already-specific reasons like `direct company-level negative catalyst blocks bullish candidate`.
- Out of scope:
  - Changing `src/trading/strategies/matching.py` persisted strings.
  - Schema or repository changes.
  - Reworking candidate ranking, evidence scoring, or template layout beyond rendering the new display string.

## File Map

- `src/web/presenters/today_candidates.py`
  - Own the display-only rewrite from raw `selection_reason` to an operator-facing summary.
  - Derive a short ordered list of signal fragments from existing evidence keys.
- `src/web/presenters/today_copy.py`
  - Add any shared copy helpers/constants only if they reduce duplication cleanly.
  - Keep internal/smoke filtering and operator text cleanup as the source of truth.
- `src/templates/today.html`
  - Likely no structural change; continue rendering `row.selection_reason`.
  - Only touch this file if presenter output changes require a copy-label tweak.
- `tests/web/test_today_candidates.py`
  - Lock the presenter contract for generic-match replacement, specific-reason pass-through, and no-evidence fallback.
- `tests/web/test_today.py`
  - Lock the rendered HTML so the internal string never appears on the Candidates tab.
- `tests/web/test_today_copy.py`
  - Add coverage only if a new shared copy helper lands in `today_copy.py`.
- `plan/research_app/trading_agent_refactor/progress_tracker.md`
  - Update only after implementation is actually completed and verified; do not touch it during plan-only work.

## Display Contract

When the primary candidate row carries the exact generic internal reason:

```python
"deterministic PR02 signals matched strategy"
```

the presenter should replace it with operator-facing text shaped like:

```python
"Matched Gap continuation on signals: positive sentiment, 2 high-signal items / 24h, 20d return 8.26%, relative volume 0.78."
```

Rules:

- Start with `Matched <strategy label>`.
- Follow with `on signals: ...` when at least one evidence fragment can be summarized.
- Prefer 2 to 4 high-signal fragments so the line stays scannable.
- Use existing human-readable phrasing already used by `_signal_bullets(...)` where practical.
- If the generic reason is present but evidence is empty, fall back to `Matched <strategy label> using available signals.`.
- If the strategy label is unavailable, fall back to `Matched strategy using available signals.`.
- If the raw `selection_reason` is anything else, keep it after normal operator-text cleanup.

### Task 1: Lock The Presenter Contract With Failing Tests

**Files:**
- Modify: `tests/web/test_today_candidates.py`
- Modify: `tests/web/test_today.py`

- [ ] **Step 1: Add a failing presenter test for generic-match replacement**

```python
def test_build_today_candidates_view_humanizes_generic_match_reason():
    payload = build_today_candidates_view(
        rows=(
            {
                "ticker": "AAPL",
                "strategy_label": "Gap continuation",
                "selection_reason": "deterministic PR02 signals matched strategy",
                "core_signal_evidence": {
                    "events_news.sentiment_direction": "positive",
                    "events_news.high_signal_news_count_24h": 2,
                    "technical.return_20d": 0.0826,
                    "technical.relative_volume": 0.78,
                },
                ...
            },
        ),
        ...
    )

    assert payload["decision_readout"][0]["selection_reason"] == (
        "Matched Gap continuation on signals: positive sentiment, "
        "2 high-signal items / 24h, 20d return 8.26%, relative volume 0.78."
    )
```

- [ ] **Step 2: Add a failing presenter test for explicit-reason pass-through**

```python
def test_build_today_candidates_view_preserves_specific_selection_reason():
    ...
    assert row["selection_reason"] == "direct company-level negative catalyst blocks bullish candidate"
```

- [ ] **Step 3: Add a failing presenter test for empty-evidence fallback**

```python
def test_build_today_candidates_view_falls_back_when_generic_reason_has_no_evidence():
    ...
    assert row["selection_reason"] == "Matched Gap continuation using available signals."
```

- [ ] **Step 4: Add a failing route/render test that the raw internal string never appears**

```python
def test_today_candidates_tab_hides_internal_generic_selection_reason(client):
    response = client.get("/today?tab=candidates")
    assert "deterministic PR02 signals matched strategy" not in response.text
    assert "Matched Gap continuation on signals:" in response.text
```

- [ ] **Step 5: Run the targeted tests to verify they fail**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_candidates.py tests/web/test_today.py -q -k 'selection_reason or humanizes_generic_match_reason or hides_internal_generic_selection_reason'`

Expected: FAIL because the presenter still returns the stored generic string unchanged.

### Task 2: Implement Display-Only Selection-Reason Synthesis

**Files:**
- Modify: `src/web/presenters/today_candidates.py`
- Modify: `src/web/presenters/today_copy.py`
- Modify: `tests/web/test_today_copy.py`

- [ ] **Step 1: Introduce a single generic-match sentinel constant**

```python
_GENERIC_MATCH_REASON = "deterministic PR02 signals matched strategy"
```

- [ ] **Step 2: Add a pure helper that rewrites only the generic reason**

```python
def _selection_reason(row: dict[str, Any]) -> str | None:
    cleaned = _clean_copy(row.get("selection_reason"))
    if cleaned != _GENERIC_MATCH_REASON:
        return cleaned

    strategy = _display_strategy_label(row)
    fragments = _selection_reason_fragments(row.get("core_signal_evidence"))
    if fragments and strategy and strategy != "Unavailable":
        return f"Matched {strategy} on signals: {', '.join(fragments)}."
    if strategy and strategy != "Unavailable":
        return f"Matched {strategy} using available signals."
    return "Matched strategy using available signals."
```

- [ ] **Step 3: Build a short ordered fragment extractor from existing evidence keys**

```python
def _selection_reason_fragments(evidence: dict[str, Any] | Any) -> tuple[str, ...]:
    flattened = _flatten_evidence(evidence)
    fragments = (
        _news_reason_fragments(flattened)
        + _technical_reason_fragments(flattened)
        + _fundamental_reason_fragments(flattened)
    )
    return tuple(fragment for fragment in fragments if fragment)[:4]
```

Candidate fragment priority:

- News/events first:
  - `sentiment positive`
  - `2 high-signal items / 24h`
  - `catalyst quality 0.82`
- Technical second:
  - `20d return 8.26%`
  - `relative volume 0.78`
  - `RS vs SPY 2.70%`
- Fundamental third:
  - `quality 0.98`
  - `revenue growth 0.65`
  - `margin trend 0.93`
- Ignore low-value noise if a fragment would repeat what the bullet list already states verbosely or produce awkward raw IDs.

- [ ] **Step 4: Keep formatting vocabulary aligned with existing bullets**

```python
def _percent_fragment(label: str, value: float | None) -> str | None:
    if value is None:
        return None
    return f"{label} {value:.2%}"
```

Do not invent terms like `PR02`, `deterministic`, `events_news`, or raw field IDs in operator-facing copy.

- [ ] **Step 5: Add copy-helper tests only if shared helpers move into `today_copy.py`**

```python
def test_operator_text_does_not_rewrite_specific_selection_reason():
    ...
```

If all new logic stays local to `today_candidates.py`, skip `today_copy.py` changes and skip this test file.

- [ ] **Step 6: Run targeted presenter/copy tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_candidates.py tests/web/test_today_copy.py -q -k 'selection_reason or humanizes_generic_match_reason'`

Expected: PASS for the new presenter-copy contract.

### Task 3: Wire The Grouped Candidate View And Verify Full Rendering

**Files:**
- Modify: `src/web/presenters/today_candidates.py`
- Modify: `src/templates/today.html`
- Modify: `tests/web/test_today.py`

- [ ] **Step 1: Replace the grouped-row assignment to use the synthesized display string**

```python
"selection_reason": _selection_reason(primary),
```

Do not change:

- `signal_bullets`
- `risk_tags`
- `invalidators`
- `strategy alternatives`

- [ ] **Step 2: Leave the template structure alone unless copy wrap/readability requires a tiny tweak**

Preferred outcome:

```jinja2
{% if row.selection_reason %}
<div class="detail-muted">{{ row.selection_reason }}</div>
{% endif %}
```

No new template branches should be needed if the presenter contract stays stable.

- [ ] **Step 3: Run the focused web tests**

Run: `source ~/.venv/bin/activate && pytest tests/web/test_today_candidates.py tests/web/test_today.py -q`

Expected: PASS

- [ ] **Step 4: Run the broader web regression suite**

Run: `source ~/.venv/bin/activate && pytest tests/web/ -q`

Expected: PASS with no raw `deterministic PR02 signals matched strategy` string in rendered output.

- [ ] **Step 5: Do a final grep to confirm the internal string is no longer surfaced by the web layer**

Run: `rg -n "deterministic PR02 signals matched strategy" src/web tests/web`

Expected: zero presenter/template assertions rendering the raw phrase; any remaining hit should be limited to backend matching or tests that intentionally assert replacement behavior.

## Implementation Notes

- Keep this as a display-layer cleanup, not a backend contract rewrite.
- Avoid mutating `rows` upstream in `today.py`; the rewrite belongs in the presenter next to other operator-facing copy decisions.
- Favor tiny pure helpers over expanding `_group_candidate_rows(...)` inline again.
- Reuse existing `_flatten_evidence(...)` and signal-format helpers where possible so summary and bullets do not drift.
- Preserve smoke filtering behavior from `today_copy.is_internal_smoke_text(...)`.
- If the best implementation ends up needing one tiny helper in `today_copy.py`, keep it generic and reusable; do not move candidate-specific orchestration into that file.

## Completion Checklist

- [ ] Generic internal selection reason never appears in the Candidates UI.
- [ ] Specific backend reasons still render unchanged.
- [ ] The new one-line summary names the matched strategy and concrete signals.
- [ ] Existing `signal_bullets` remain present as the detailed breakdown.
- [ ] `source ~/.venv/bin/activate && pytest tests/web/test_today_candidates.py tests/web/test_today.py -q` passes.
- [ ] `source ~/.venv/bin/activate && pytest tests/web/ -q` passes.
- [ ] After implementation only: update `plan/research_app/trading_agent_refactor/progress_tracker.md` with verification evidence.
