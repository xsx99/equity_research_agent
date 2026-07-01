# Handoff — Today dashboard real-data bugs (surfaced by the deployed app)

Context: the Today redesign (dark theme, KPI cards, Trades inner-tabs, attention feed) is
committed at HEAD and renders correctly against a **mock fixture**. When run against the
**real DB + Gemini output**, the deployed app surfaced the issues below. Each was confirmed in
code (file:line). Line numbers are approximate — reconfirm before editing. None of these are
mock/preview artifacts; they only appear with real data, which is why the unit tests and the
fixture-based preview did not catch them.

**Investigation only → implementation handoff.** Fixes proposed; not applied.

---

## P0 — DEPLOY/CSS STALENESS (explains "why the deployed UI looks nothing like the redesign")

**Symptom (deployed app):** light/white theme, header KPI values render as a **vertical stack
of plain text** (no cards), even though the page markup is clearly the NEW redesigned templates
(Overview attention feed, Trades EVIDENCE/RISK/TRADE PLAN sub-tabs, System events/exposure, etc.).

**Root cause (confirmed):** the deployed app is serving a **stale `/static/style.css`** — an old,
light-themed stylesheet that predates the redesign and lacks the `.kpi-cards` / `.kpi-card` rules.
The HTML (dynamic, regenerated each request) is current; the static CSS is not.
- Committed `src/static/style.css` is a **dark theme**: `:root { --bg:#0a0e14; --text:#e6edf3; … }`
  (`style.css:10-28`), and defines `.kpi-cards { display:grid; … }` + `.kpi-card { … }`
  (`style.css:1166-1175`). `style.css` is clean at HEAD (last touched by `e6ef172 UI refactor`).
- `src/templates/today.html:21-52` renders the header as `.kpi-cards` → six `.kpi-card`
  articles. With the current CSS these are a horizontal card grid; with an OLD CSS that has no
  such rules, the `<article>`/`<div>` collapse to stacked block text — exactly the deployed look.
- `src/templates/base.html:7` links the stylesheet with **no cache-busting**:
  `<link rel="stylesheet" href="/static/style.css">`. A browser/CDN holds the old file.

**This is a deployment/caching problem, not a bug in the redesign code.**

**Fix:**
1. Cache-bust the stylesheet link — e.g. `href="/static/style.css?v={{ asset_version }}"` (build
   hash or mtime), so a new deploy invalidates the cached CSS.
2. Confirm the deploy pipeline actually ships the current `src/static/style.css` (static assets
   copied/rebuilt, not left from a prior image).
3. Hard-refresh (Cmd+Shift+R) once to verify.

**How to confirm which CSS is live:** open `<deployed-host>/static/style.css` and search for
`--bg: #0a0e14` or `.kpi-card`. Present → CSS is current (look elsewhere). Absent / light tokens →
stale CSS confirmed.

---

## B1 — Risk & Macro: massive duplication (earnings + OTHER RISK ACTIONS)

**Symptom:** "Upcoming Earnings" lists the same earnings twice (GOOGL "within 22 day(s)" AND
"…28 day(s)"); "OTHER RISK ACTIONS" repeats the same NVDA `Monitor` headline 15+ times (identical
title, all "company_specific … 0 day(s)").

**Root cause (confirmed):** the loaders are append-only point-in-time audit stores; the presenter
emits the accumulated set with **no dedup**.
- `src/web/presenters/today_risk_macro.py:84-89` builds `events` and `risk_sources` with no
  collapse by natural key.
- Source rows from `src/trading/repositories/mixins/macro_calendar.py:147-166` and `:92-106` load
  **every** row with `available_for_decision_at <= decision_time` — multiple preopen/intraday runs
  accumulate duplicates (each re-derived earnings date is a new `event_key`).
- Template amplifies it: `src/templates/today/_tab_risk_macro.html:138-140` loops all matching
  `risk_sources` per earnings tile, and `:37` builds `other.rows` from all non-earnings
  risk_sources → every duplicate becomes a row.

**Fix (minimal):** dedupe in `build_today_risk_macro_payload` before emitting.
- `events`: key by `event_key` (`earnings:{TICKER}:{date}`) or `(event_type, ticker, scheduled_at)`,
  keep newest.
- `risk_sources`: key by `(ticker, risk_source, event_type)` (or `+recommended_action`), keep the
  latest `available_for_decision_at`.

**Confidence:** confirmed in code.

---

## B2 — Risk & Macro: Economic Calendar column empty

**Symptom:** the left "Economic Calendar" column renders empty; only the right "Upcoming Earnings"
column is populated.

**Root cause (confirmed):** no economic/macro calendar data is produced in the live preopen path
— this is **missing data, not a wiring bug**.
- Template buckets a row as earnings if `"earn" in event_kind`, else into the economic column
  (`src/templates/today/_tab_risk_macro.html:24-34`).
- Economic rows require `event_type="macro"` events, only created when `macro_events=(...)` is
  passed to `CalendarEventPipeline.build_events` (`src/trading/events/calendar.py:111-129`).
- The preopen builder `src/trading/runtime/preopen_risk.py:286-306` passes only earnings args;
  `macro_events` defaults to `()`. So persisted `CalendarEvent` rows are only earnings — never macro.

**Fix:** (a) real fix (deferred): feed a macro/economic calendar source into
`_build_preopen_calendar_events` so `macro_events` is populated. (b) UI honesty now: reword the
empty-state at `_tab_risk_macro.html:121` so it reads "no economic-calendar feed wired yet" rather
than implying data loss. Recommend (b) now, track (a).

**Confidence:** confirmed in code (empty by absence of source, not a key/filter mismatch).

---

## B3 — News mis-attribution across tickers (MU+NVDA same headline; APP "World Cup")

**Symptom:** Overview "Needs Attention" shows MU and NVDA with the SAME headline ("Micron Stock
Redefined Its Future…"), and APP shows an irrelevant "Iran heads home … World Cup" headline.

**Root cause (confirmed):** this is **readthrough/sympathy news by design**, but the loader drops
the subject column so it looks like mis-attribution.
- `src/web/routers/loaders/ticker_detail.py:90-119` keys news by the attribution column `row.ticker`
  and passes only headline/summary/source/event_type — it ignores `NewsAlert.source_ticker` /
  `readthrough_source_ticker` (`src/db/models/trading/intraday.py:87,99`) and
  `EventNewsItem.source_ticker` / `explicit_ticker_mention_flag` (`src/db/models/trading/signals.py:130,172`).
- A row `ticker=NVDA, source_ticker=MU` is NVDA's *readthrough* of Micron news → the same Micron
  headline correctly attaches to both, but with no "about MU" indicator it reads as a bug.

**Fix (presentation-layer):** carry `source_ticker` (+ `readthrough_source_ticker` /
`explicit_ticker_mention_flag`) into the snippet dict in `_append_news_snippet`, then in the news
templates tag items as "readthrough from {source_ticker}" when `source_ticker` != grouping ticker.
Optionally de-emphasize/exclude readthrough items from the Overview attention feed.

**Confidence:** confirmed in code (dropped column); which exact headline maps to which ticker is
runtime data, but the mechanism is the root cause.

---

## B4 — Candidates: Outcome "Actionable Trade" contradicts the no-trade thesis

**Symptom:** APP/CRDO/MRVL/NOK rows show Outcome = "Actionable Trade" while their LLM thesis says
"not actionable / decision to not trade / hold / no clean entry".

**Root cause (confirmed):** the Outcome label comes from the **classifier** stage (pre-decision),
not the actual trading-decision result.
- `src/trading/strategies/classifier.py:53` hardcodes `result_status="actionable_trade"` for any
  candidate that cleared classification (only means "eligible for an expression bucket").
- `src/web/routers/loaders/candidates.py:151-156` (`_candidate_result_status`) returns that
  classification status first; fed to `current_outcome_label` (line 88).
- `src/web/presenters/today_copy.py:151-152` + `_humanize_id` (`:257-266`): `"actionable_trade"`
  isn't in `_CANDIDATE_RESULT_LABELS`, so it humanizes to "Actionable Trade".
- Carried through `today_candidates.py:158` and rendered at `_tab_candidates.html:6`, while
  `thesis` (`today_candidates.py:162`, from the trading decision) says the opposite.

**Fix (minimal):** in `_candidate_result_status`, prefer the latest *trading-decision* outcome for
the ticker over the classifier's `result_status` — map no-trade/hold/exit-none to
`no_trade`/`ordinary_watch`. The candidate row already gets per-ticker thesis history
(`thesis_history_by_ticker`); thread the decision status the same way. (Adding "actionable_trade"
to `_CANDIDATE_RESULT_LABELS` is a band-aid; sourcing the outcome from the decision is the real fix.)

**Confidence:** confirmed in code (label provenance); whether every named row has a no-trade
decision is runtime data, but the mechanism is confirmed.

---

## B5 — Portfolio: Sharpe Ratio unstable (4.42)

**Root cause (confirmed):** minimum-sample guard is only `len(daily_returns) >= 2` with full √252
annualization and no small-n suppression.
- `src/web/presenters/today_portfolio_analytics.py:76-87`: smallest n that emits a number is **2
  daily returns (3 equity snapshots)**; 2-sample std is meaningless and ×√252 explodes the ratio.
- Template renders it unconditionally when non-null (`src/templates/today/_tab_portfolio.html:62`).

**Fix (minimal):** require `len(daily_returns) >= 20` (≈1 month) before emitting `sharpe_ratio`;
below that leave `None` (template already shows "—"). Optionally emit a `sharpe_low_sample` flag so
the UI can show "n too small" instead of a misleading value.

**Confidence:** confirmed in code.

---

## B6 — System tab: raw number leak (`50157.226068 exposure`)

**Root cause (confirmed):** `src/templates/today/_tab_system.html:28` interpolates the raw float
with no number filter:
```jinja
{{ system.exposure_summary.total_exposure if system.exposure_summary.total_exposure is not none else "—" }} exposure
```
`total_exposure` is a raw `float` from `_safe_sum(exposures, "exposure")`
(`src/web/routers/loaders/header_system.py:123` → `_format.py:42-51`).

**Fix (minimal):** format at the template (codebase convention = presenters return raw numerics,
templates format; both filters already registered in `src/web/filters.py:91-92`):
```jinja
{{ fmt_currency(system.exposure_summary.total_exposure) if … else "—" }}
```
Use `fmt_currency` (this is a raw dollar sum across `RiskFactorExposure.gross_exposure`, not a
sub-1 ratio). Do not pre-format in the presenter — `exposure_summary` is consumed as raw numbers
elsewhere.

**Confidence:** confirmed in code.

---

## Cross-cutting note
B1 and B3 share a root theme: the loaders are **append-only, point-in-time audit stores**, and the
presenters/templates render the accumulated set verbatim. B1 needs dedup-by-natural-key; B3 needs a
subject-vs-attribution distinction. Both are presentation-layer fixes, not data corruption.

## Suggested order
1. **P0 deploy/CSS** — without it, none of the redesign is visible regardless of the rest.
2. **B6, B5** — one-line / small, high signal-to-noise.
3. **B1, B4** — dedup + correct outcome provenance; medium.
4. **B3** — readthrough attribution (presentation + small loader change).
5. **B2** — UI copy now; real macro feed deferred.
