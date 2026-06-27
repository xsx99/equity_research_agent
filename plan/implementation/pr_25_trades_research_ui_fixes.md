# Prompt 11 — Trades/Research UI & data fixes (6 issues)

You are editing the `equity_research_agent` repo. Implement the 6 independent fixes
below. Make ONLY the changes described. After each fix, run the matching tests.

> **Before you start — read this.**
> - Each section is self-contained; you may do them in any order.
> - For every code change I quote a **FIND** block (the current/buggy code) and a
>   **REPLACE** block (the target code). Locate the FIND block by searching for it,
>   then replace it exactly. Line numbers are approximate hints only — trust the
>   quoted code, not the numbers.
> - **Some of these fixes may already be present in the working tree.** If a FIND
>   block doesn't match because the code already looks like the REPLACE block, that
>   fix is already done — verify it matches and move on. Do NOT duplicate it.
> - Do not refactor unrelated code. Do not change DB schema. Keep the style of the
>   surrounding code.
> - Project note: you run tests with `pytest`. The app itself is not run locally.

---

## Fix 1 — Open positions disappear from the "Open Positions" bucket

### Goal
The Portfolio view lists a position as open, but that same ticker is missing from the
TRADES tab "Open Positions" bucket. They must be consistent: if a ticker has an open
position, it shows in Open Positions.

### Verified facts
- The TRADES workspace buckets tickers in `build_ticker_workspace` in
  `src/web/presenters/today_workspace.py` (around lines 77-93).
- The bug: the `elif` chain checks "is this ticker in recently-closed positions"
  BEFORE "is this ticker in open positions". So a ticker that closed an earlier trade
  today and then re-opened (it appears in BOTH `closed_positions_by_ticker` and
  `positions_by_ticker`) gets dropped into the `closed_today` bucket and never reaches
  `open_positions`. The Portfolio view reads open positions directly, so the two
  surfaces disagree.

### Change
In `src/web/presenters/today_workspace.py`, swap the order so open positions win.

**FIND:**
```python
        if _is_action_now(item):
            item["primary_state"] = "action_now"
            buckets["action_now"].append(item)
        elif ticker in normalized_closed_positions:
            item["primary_state"] = "closed"
            buckets["closed_today"].append(item)
        elif ticker in normalized_positions:
            item["primary_state"] = "open_position"
            buckets["open_positions"].append(item)
```

**REPLACE:**
```python
        if _is_action_now(item):
            item["primary_state"] = "action_now"
            buckets["action_now"].append(item)
        elif ticker in normalized_positions:
            # An open position always wins over a historical closed one for the
            # same ticker (e.g. a prior trade closed earlier, then re-entered).
            # Otherwise the position shows in the portfolio but vanishes from the
            # Open Positions bucket here.
            item["primary_state"] = "open_position"
            buckets["open_positions"].append(item)
        elif ticker in normalized_closed_positions:
            item["primary_state"] = "closed"
            buckets["closed_today"].append(item)
```

### Test
Add to `tests/web/test_today_workspace.py` a test where one ticker is in BOTH
`positions_by_ticker={"NVDA": {"status": "open"}}` and
`closed_positions_by_ticker={"NVDA": {...}}`, and assert NVDA lands in
`buckets["open_positions"]` (not `closed_today`) with `primary_state == "open_position"`.
A ticker that is ONLY closed must still land in `closed_today`.

Run: `pytest tests/web/test_today_workspace.py -q`

### Acceptance
- A ticker that is currently open appears in Open Positions even if it also has a
  recent closed position for the same ticker.
- Existing closed-only behavior is unchanged.

---

## Fix 2 — Trade-decision thesis on the TRADES tab reads poorly

### Goal
The thesis shown on the TRADES tab reads worse than the RESEARCH page thesis. Raise
the trade-decision thesis to the same writing bar.

### Verified facts
- The TRADES tab shows `TradingDecision.thesis` (`src/db/models/trading.py`), produced
  by the trading decision agent using prompt
  `src/agents/prompts/trading/trading_decision_v1.yaml`.
- The RESEARCH thesis (`ResearchOutput.thesis_summary`) reads better because its prompt
  `src/agents/prompts/research/research_v1.yaml` has a strong strategist persona and an
  explicit "short plain-English summary" instruction with top-down→bottom-up structure.
- `trading_decision_v1.yaml` only says `` `thesis` must always be a non-empty string ``
  (one of the hard rules) and gives NO guidance on quality, length, or structure — so
  output is terse and mechanical.
- This is a PROMPT-only change. Do NOT change the output schema, the JSON keys, or the
  decision logic. Effect appears on the next trading run; there is nothing to render
  differently.

### Change
In `src/agents/prompts/trading/trading_decision_v1.yaml`, insert a new
"Thesis writing rules:" block immediately BEFORE the existing
"Field interpretation rules:" line.

**FIND:**
```yaml
  Field interpretation rules:

  - `key_drivers` must contain the strongest provided evidence supporting the selected decision.
```

**REPLACE:**
```yaml
  Thesis writing rules:

  - `thesis` is the human-readable narrative an operator reads first. Write it to the same bar as a sharp sell-side strategist note: clear, specific, and evidence-bound.
  - Write 2 to 4 plain-English sentences. Do not return a single terse fragment, a restatement of field names, or boilerplate.
  - Sentence 1: state the directional decision and the chosen strategy / expression in plain language (e.g., "Enter a tactical long via the momentum-breakout expression").
  - Then connect the decision to the 1 or 2 strongest concrete datapoints from `signal_snapshot` that actually drive it (name the metric, trend, catalyst, or news item, not the raw field key).
  - When macro / regime context is a dominant factor, state how it aligns with or pressures the setup, mirroring the top-down logic the research view uses.
  - Close with the single most important risk or invalidation condition in one clause, so the reader knows what would break the thesis.
  - Keep it self-contained and readable on its own; do not rely on `key_drivers`/`counterarguments` to make the thesis make sense. Never invent facts that are not in the input.

  Field interpretation rules:

  - `key_drivers` must contain the strongest provided evidence supporting the selected decision.
```

### Test
There is no rendering change. If a prompt-loading/snapshot test exists
(`grep -rl trading_decision tests/`), update its expected text. Otherwise just confirm
the YAML still parses: `python -c "import yaml; yaml.safe_load(open('src/agents/prompts/trading/trading_decision_v1.yaml'))"`.

### Acceptance
- The prompt contains explicit thesis-quality guidance.
- Schema/keys/decision rules are unchanged; YAML still loads.

---

## Fix 3a — Past events show in "Event Risk"; only upcoming events should show

### Goal
The Risk & Macro → Event Risk section shows past events (e.g. a US CPI print that
already happened). It must only show events whose scheduled time is in the future.

### Verified facts
- Events are rendered from `payload["events"]`, built in
  `src/web/presenters/today_risk_macro.py` in `build_today_risk_macro_payload`
  (the `"events": tuple(_event_row(event) for event in calendar_events if _default_visible_event(event)),`
  line, ~line 83).
- `_default_visible_event` (~line 180) only checks a metadata visibility flag — there is
  NO date filtering anywhere in the presenter. Each event has an `event_time`
  (`datetime`) attribute (see `_event_row` reading `getattr(event, "event_time", None)`).
- The presenter is called from `_load_today_risk_macro` in `src/web/routers/today.py`
  (~lines 751-785). That function has access to `latest_risk.decision_time`, which is the
  natural "as of" reference time for the snapshot.
- The presenter has `from datetime import date, datetime, timezone` already imported.

### Change 3a.1 — router passes an `as_of` reference
In `src/web/routers/today.py`, function `_load_today_risk_macro`: hoist the
`decision_time` out of the `if isinstance(session, SQLAlchemySession):` block so it is
always defined, and pass it to the presenter.

**FIND:**
```python
    exposures = _load_risk_exposures(session)
    latest_intent = None
    risk_macro_context: dict[str, object] = {"macro_snapshot": latest_macro_snapshot}
    if isinstance(session, SQLAlchemySession):
        repository = SqlAlchemyTradingRepository(session)
        trade_date = (
            latest_risk.decision_time.date()
            if latest_risk is not None
            else None
        )
        decision_time = latest_risk.decision_time if latest_risk is not None else None
```

**REPLACE:**
```python
    exposures = _load_risk_exposures(session)
    latest_intent = None
    risk_macro_context: dict[str, object] = {"macro_snapshot": latest_macro_snapshot}
    decision_time = latest_risk.decision_time if latest_risk is not None else None
    if isinstance(session, SQLAlchemySession):
        repository = SqlAlchemyTradingRepository(session)
        trade_date = (
            latest_risk.decision_time.date()
            if latest_risk is not None
            else None
        )
```

Then, in the same function, the `return build_today_risk_macro_payload(...)` call.

**FIND:**
```python
    return build_today_risk_macro_payload(
        latest_risk=latest_risk,
        latest_intent=latest_intent,
        risk_macro_context=risk_macro_context,
        exposures=exposures,
    )
```

**REPLACE:**
```python
    return build_today_risk_macro_payload(
        latest_risk=latest_risk,
        latest_intent=latest_intent,
        risk_macro_context=risk_macro_context,
        exposures=exposures,
        as_of=decision_time,
    )
```

### Change 3a.2 — presenter accepts `as_of` and filters past events
In `src/web/presenters/today_risk_macro.py`:

**(a) Add the `as_of` parameter.** FIND:
```python
def build_today_risk_macro_payload(
    *,
    latest_risk: object | None,
    latest_intent: object | None,
    risk_macro_context: dict[str, object] | None,
    exposures: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
```
REPLACE:
```python
def build_today_risk_macro_payload(
    *,
    latest_risk: object | None,
    latest_intent: object | None,
    risk_macro_context: dict[str, object] | None,
    exposures: tuple[dict[str, Any], ...],
    as_of: datetime | None = None,
) -> dict[str, Any]:
```

**(b) Apply the filter.** FIND:
```python
        "events": tuple(_event_row(event) for event in calendar_events if _default_visible_event(event)),
```
REPLACE:
```python
        "events": tuple(
            _event_row(event)
            for event in calendar_events
            if _default_visible_event(event) and _is_upcoming_event(event, as_of)
        ),
```

**(c) Add the helper** right after the `_default_visible_event` function:
```python
def _is_upcoming_event(event: object, as_of: datetime | None) -> bool:
    """Hide events whose scheduled time is already in the past.

    The risk surface is forward-looking: a CPI print or earnings date that has
    already happened should not be presented as a pending catalyst. We compare
    against ``as_of`` (the decision-snapshot time) when available, otherwise the
    event date alone cannot be classified and we keep it visible.
    """
    if as_of is None:
        return True
    event_time = getattr(event, "event_time", None)
    if not isinstance(event_time, (datetime, date)):
        return True
    cutoff: date | datetime = as_of
    if isinstance(event_time, datetime):
        reference = as_of
        if event_time.tzinfo is None and as_of.tzinfo is not None:
            reference = as_of.replace(tzinfo=None)
        elif event_time.tzinfo is not None and as_of.tzinfo is None:
            reference = as_of.replace(tzinfo=timezone.utc)
        return event_time >= reference
    # ``event_time`` is a plain date: keep it if it is on or after the as-of day.
    if isinstance(cutoff, datetime):
        cutoff = cutoff.date()
    return event_time >= cutoff
```

> Note: `as_of=None` keeps all events (back-compatible). Use `>=` so an event exactly
> at `as_of` still shows. `date` and `timezone` are already imported in this file.

### Test
In `tests/web/test_today_risk_macro.py`, add a test that builds the payload with
`as_of=<a known time>` and two events: one with `event_time` in the past and one in the
future. Assert only the future event is in `payload["events"]`. Confirm existing tests
(which call the presenter WITHOUT `as_of`) still pass unchanged.

Run: `pytest tests/web/test_today_risk_macro.py -q`

### Acceptance
- With a known `as_of`, past events are hidden; events at-or-after `as_of` show.
- Calling the presenter without `as_of` shows all events (unchanged behavior).

---

## Fix 3b — Upcoming earnings (e.g. MU) missing from Event Risk (INVESTIGATION + smoke test)

### Goal
A real upcoming earnings date (e.g. MU next week) does not appear in Event Risk.
Determine and document the real cause; do NOT guess-edit logic.

### Verified facts (the earnings pipeline)
- Earnings calendar events are created ONLY inside the pre-open risk run, in
  `_build_preopen_calendar_events` in `src/trading/runtime/preopen_risk.py` (~line 286).
  It loops over **candidates** and calls
  `CalendarEventPipeline.build_events(..., earnings_in_days=_earnings_in_days(snapshot), earnings_date=_earnings_date(snapshot))`.
- `_earnings_in_days` / `_earnings_date` (same file, ~lines 336-367) read the candidate's
  signal snapshot JSON: `events_news.earnings_in_days`, `events_news.known_event_date`,
  `fundamental.earnings_date`, `fundamental.known_event_date`.
- `CalendarEventPipeline.build_events` (`src/trading/events/calendar.py`, ~lines 87-110)
  only emits an earnings event when one of those fields is present.
- The signal value ultimately comes from Finnhub:
  `AlpacaMarketDataProvider._fetch_earnings_in_days_from_finnhub`
  (`src/providers/market_data/alpaca_provider.py`, ~line 409). It returns
  `{"earnings_in_days": None, "earnings_date": None}` immediately if
  `self.finnhub_api_key` is falsy, and otherwise queries a `today → today+45d` window.

### Therefore an earnings event is missing if ANY of these is true
1. `FINNHUB_API_KEY` is not configured in the runtime environment → Finnhub is never
   queried → no earnings field → no event. (Most likely cause.)
2. The ticker (MU) was not among the scored **candidates** in the pre-open run that
   produced the on-screen events → no event is built for it even if data exists.
3. The earnings date is outside the `today → +45d` window, or Finnhub returned no row.

### Tasks
1. **Do NOT change pipeline logic blindly.** First confirm which cause applies.
2. **Add a standalone smoke test** so the user can diagnose without running the app:
   create `scripts/run_trading_earnings_calendar_smoke.py` that:
   - Reads `FINNHUB_API_KEY` from env; if missing, prints a clear message and exits
     non-zero ("FINNHUB_API_KEY not set — earnings events cannot be generated").
   - Instantiates the provider and calls the Finnhub earnings fetch for a ticker passed
     as `argv[1]` (default `MU`), printing the returned `earnings_in_days` /
     `earnings_date`.
   - Must be runnable stand-alone and hit Finnhub only once (respect rate limits), per
     `documents/general_instructions.md`.
3. In the smoke test's module docstring, document the 3 failure causes above and how to
   tell them apart (no key → cause 1; key set but `None` returned → cause 3 or symbol
   issue; data present but not on the page → cause 2, ticker not a candidate).

> Related existing work: `plan/coding_agent_prompts/05_fix_earnings_date.md` already
> covers threading the REAL earnings date through the pipeline. If that fix is not yet
> applied, apply it too — it is complementary to this diagnosis.

### Acceptance
- A standalone script exists that, given a ticker, reports whether Finnhub returns an
  earnings date — making the root cause obvious.
- No production pipeline behavior changed without evidence of the actual cause.

---

## Fix 4 — Candidate decisions show only signals, no thesis

### Goal
On the CANDIDATES tab, each decision card should clearly show the decision thesis, not
just signals. The data already exists but is visually buried.

### Verified facts
- The presenter `_group_candidate_rows` in
  `src/web/presenters/today_candidates.py` already attaches `selection_reason`
  (the candidate's rationale) to each row — no presenter change needed.
- In the template `src/templates/today.html`, the candidate card renders
  `row.selection_reason` INSIDE the "Signals Used" section, so it looks like a signal
  note rather than a thesis.

### Change
In `src/templates/today.html`, in the candidate decision card, pull `selection_reason`
out into its own labeled "Decision Thesis" block ABOVE the "Signals Used" list.

**FIND:**
```html
            <div>
              <span class="metric-label">Signals Used</span>
              {% if row.selection_reason %}
              <div class="detail-muted">{{ row.selection_reason }}</div>
              {% endif %}
              <ul class="history-card-listing">
```

**REPLACE:**
```html
            {% if row.selection_reason %}
            <div>
              <span class="metric-label">Decision Thesis</span>
              <p class="hero-summary">{{ row.selection_reason }}</p>
            </div>
            {% endif %}
            <div>
              <span class="metric-label">Signals Used</span>
              <ul class="history-card-listing">
```

### Test
Existing `tests/web/test_today_candidates.py` already asserts `selection_reason` is on
the row — keep it passing. (Template-only change.) Run:
`pytest tests/web/test_today_candidates.py -q`

### Acceptance
- Each candidate card shows a distinct "Decision Thesis" block (when a reason exists),
  separate from the signals list.

---

## Fix 6 — Risk Manager Summary card: make it compact + show its reasoning

### Goal
On the TRADES tab the "Risk Manager Summary" is usually just "approve" but takes a big
block. Make it compact, and surface the risk manager's reasoning when present.

### Verified facts
- The risk manager is a DETERMINISTIC rule engine — there is no LLM "thesis". Its
  reasoning lives in `RiskDecision.reason_code`, `RiskDecision.applied_rules_json`,
  `lookahead_risk_source`, and `generated_hedge_action_json`
  (`src/db/models/trading.py`, `RiskDecision`).
- The presenter `build_ticker_workspace`'s detail builder in
  `src/web/presenters/today_workspace.py` constructs `latest_risk_summary` with
  `status`, `status_label`, `reason`, `lookahead_risk_source`, `hedge_overlay_reason`.
  `applied_rules` is NOT currently included.
- In `src/web/routers/today.py`: the per-ticker risk payload (the `grouped[ticker] = {...}`
  dict, ~line 1610) and the audit `risk_decision` dict (~line 1064) and the risk_summary
  merge (~line 1500) do NOT carry `applied_rules`.
- The template `src/templates/today.html` (~lines 213-222) renders a `support-kv-list`
  with Status plus a muted reason paragraph — verbose even when nothing to say.
- `_EMPTY_MARKER = "No material update"` in `today_workspace.py`.

### Change 6.1 — surface `applied_rules` from the DB (router)
In `src/web/routers/today.py`:

**(a)** Add a normalizer helper. Place it right before `_risk_decision_binding_constraint`:
```python
def _risk_applied_rules(value: Any) -> tuple[str, ...]:
    """Normalize ``applied_rules_json`` into readable rule labels.

    The risk manager is deterministic, so its "reasoning" is the set of rules it
    evaluated. Entries may be plain strings or dicts carrying a rule id / reason.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    labels: list[str] = []
    for item in value:
        if isinstance(item, dict):
            label = str(
                item.get("label")
                or item.get("rule")
                or item.get("rule_id")
                or item.get("name")
                or item.get("reason_code")
                or ""
            ).strip()
        else:
            label = str(item or "").strip()
        if label and label not in labels:
            labels.append(label)
    return tuple(labels)
```

**(b)** In the audit `risk_decision` dict, add `applied_rules`. FIND:
```python
        risk_decision = {
            "status": row.risk_decision.status,
            "reason_code": row.risk_decision.reason_code,
            "generated_hedge_action": getattr(row.risk_decision, "generated_hedge_action_json", None),
            "lookahead_risk_source": _risk_decision_lookahead_source(row.risk_decision),
        }
```
REPLACE:
```python
        risk_decision = {
            "status": row.risk_decision.status,
            "reason_code": row.risk_decision.reason_code,
            "generated_hedge_action": getattr(row.risk_decision, "generated_hedge_action_json", None),
            "lookahead_risk_source": _risk_decision_lookahead_source(row.risk_decision),
            "applied_rules": _risk_applied_rules(getattr(row.risk_decision, "applied_rules_json", None)),
        }
```

**(c)** In the risk_summary merge block, add applied_rules. FIND:
```python
    if not risk_summary.get("hedge_overlay_reason") and isinstance(audit_detail.get("risk_decision"), dict):
        generated_hedge_action = audit_detail["risk_decision"].get("generated_hedge_action")
        if isinstance(generated_hedge_action, dict):
            risk_summary["hedge_overlay_reason"] = generated_hedge_action.get("reason_code")
```
REPLACE:
```python
    if not risk_summary.get("hedge_overlay_reason") and isinstance(audit_detail.get("risk_decision"), dict):
        generated_hedge_action = audit_detail["risk_decision"].get("generated_hedge_action")
        if isinstance(generated_hedge_action, dict):
            risk_summary["hedge_overlay_reason"] = generated_hedge_action.get("reason_code")
    if not risk_summary.get("applied_rules") and isinstance(audit_detail.get("risk_decision"), dict):
        risk_summary["applied_rules"] = audit_detail["risk_decision"].get("applied_rules") or ()
```

**(d)** In the per-ticker grouped risk dict, add applied_rules. FIND:
```python
        grouped[ticker] = {
            "status": row.status,
            "reason": row.reason_code,
            "lookahead_risk_source": lookahead_risk_source,
            "generated_hedge_action": generated_hedge_action,
            "history": [
```
REPLACE:
```python
        grouped[ticker] = {
            "status": row.status,
            "reason": row.reason_code,
            "lookahead_risk_source": lookahead_risk_source,
            "generated_hedge_action": generated_hedge_action,
            "applied_rules": _risk_applied_rules(getattr(row, "applied_rules_json", None)),
            "history": [
```

### Change 6.2 — presenter exposes `applied_rules`
In `src/web/presenters/today_workspace.py`, the `latest_risk_summary` dict. FIND:
```python
    latest_risk_summary = {
        "status": risk.get("status") or _EMPTY_MARKER,
        "status_label": risk_status_label(risk.get("status")) or _EMPTY_MARKER,
        "reason": risk_reason_label(risk.get("reason")) or operator_text(risk.get("reason")) or _EMPTY_MARKER,
        "lookahead_risk_source": risk.get("lookahead_risk_source"),
        "hedge_overlay_reason": _hedge_overlay_reason(risk.get("generated_hedge_action")),
    }
```
REPLACE:
```python
    latest_risk_summary = {
        "status": risk.get("status") or _EMPTY_MARKER,
        "status_label": risk_status_label(risk.get("status")) or _EMPTY_MARKER,
        "reason": risk_reason_label(risk.get("reason")) or operator_text(risk.get("reason")) or _EMPTY_MARKER,
        "lookahead_risk_source": risk.get("lookahead_risk_source"),
        "hedge_overlay_reason": _hedge_overlay_reason(risk.get("generated_hedge_action")),
        "applied_rules": tuple(risk.get("applied_rules") or ()),
    }
```

### Change 6.3 — compact template card
In `src/templates/today.html`, replace the Risk Manager Summary card. FIND:
```html
              <section class="card subcard">
                <h4>Risk Manager Summary</h4>
                <div class="support-kv-list">
                  <div class="support-kv-row">
                    <span class="metric-label">Status</span>
                    <strong>{{ detail.latest_conclusion.risk_summary.status_label or "Unavailable" }}</strong>
                  </div>
                </div>
                <div class="detail-muted">{{ detail.latest_conclusion.risk_summary.reason or detail.latest_conclusion.risk_summary.summary or "No material update." }}</div>
              </section>
```
REPLACE:
```html
              {% set risk = detail.latest_conclusion.risk_summary %}
              <section class="card subcard risk-manager-subcard">
                <div class="risk-manager-head">
                  <h4>Risk Manager</h4>
                  {% set risk_status = risk.status_label if risk.status_label and risk.status_label != "No material update" else "Unavailable" %}
                  <span class="detail-chip risk-status-chip risk-status-{{ (risk.status or 'unknown') | lower }}">{{ risk_status }}</span>
                </div>
                {% set has_risk_detail = (risk.reason and risk.reason != "No material update") or risk.lookahead_risk_source or risk.hedge_overlay_reason or risk.applied_rules %}
                {% if has_risk_detail %}
                {% if risk.reason and risk.reason != "No material update" %}
                <p class="detail-muted">{{ risk.reason }}</p>
                {% endif %}
                {% if risk.lookahead_risk_source %}
                <p class="detail-muted"><span class="metric-label">Lookahead risk</span> {{ risk.lookahead_risk_source }}</p>
                {% endif %}
                {% if risk.hedge_overlay_reason %}
                <p class="detail-muted"><span class="metric-label">Hedge overlay</span> {{ risk.hedge_overlay_reason }}</p>
                {% endif %}
                {% if risk.applied_rules %}
                <details class="risk-applied-rules">
                  <summary>Applied rules ({{ risk.applied_rules | length }})</summary>
                  <ul class="output-list">
                    {% for rule in risk.applied_rules %}<li>{{ rule }}</li>{% endfor %}
                  </ul>
                </details>
                {% endif %}
                {% else %}
                <p class="detail-muted quiet-empty">No additional risk notes.</p>
                {% endif %}
              </section>
```

> The `{% set risk = ... %}` is scoped to the ticker-detail branch and does not collide
> with the `risk_macro` variable used in the separate Risk tab branch.

### Change 6.4 — styles
Append to the END of `src/static/style.css` (outside any media query):
```css
/* Compact risk manager subcard */
.risk-manager-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.risk-manager-head h4 {
  margin: 0;
}
.risk-status-chip {
  text-transform: capitalize;
}
.risk-status-approved,
.risk-status-approve {
  background: #e3f4e8;
  color: #1f6b3a;
}
.risk-status-rejected,
.risk-status-blocked,
.risk-status-reject {
  background: #fbe6e6;
  color: #9b2c2c;
}
.risk-applied-rules {
  margin-top: 0.4rem;
}
.risk-applied-rules summary {
  cursor: pointer;
  font-size: 12px;
  color: #37506e;
}
.risk-applied-rules .output-list {
  margin-top: 0.35rem;
}
```

### Test
Run `pytest tests/web/test_today_workspace.py -q` (and any router test that builds the
risk summary). The new `applied_rules` key must default to `()` when absent.

### Acceptance
- When the risk decision is a plain approve with no extra detail, the card is just a
  title + a status chip (no big empty block).
- When `reason` / `lookahead_risk_source` / `hedge_overlay_reason` / `applied_rules`
  exist, they are shown (applied rules inside a collapsible `<details>`).

---

## Final check
Run the full web test module set:
```
pytest tests/web/test_today_workspace.py tests/web/test_today_risk_macro.py tests/web/test_today_candidates.py -q
```
All must pass. Do not commit unless every acceptance criterion above is met.
