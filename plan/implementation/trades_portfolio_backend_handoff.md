# Backend Handoff — Trades & Portfolio data gaps

Context: the Today-page UI redesign (dark theme, Trades inner-tabs, History Highlights,
Recent News) is done at the **template + presenter** layer. The items below are the
**backend changes** the UI now needs (or that surfaced during investigation). Line numbers
are approximate — confirm before editing. LLM provider is **Google Gemini** (via Phidata),
not Anthropic.

---

## P1 — BUG (CONFIRMED, reconfirmed 2026-06-29): `entry_plan` / `exit_plan` never persisted (Trade Plan tab shows empty)

> The redesigned **Trade Plan tab** renders columns `Target Weight | Max Loss | Entry Plan |
> Exit Plan`. Entry/Exit are **always blank in the real app** because of this bug — the LLM
> produces them but they never reach the DB. Until this is fixed the Trade Plan tab shows only
> the two numeric columns. This is the highest-value fix for the Trades surface.

The trading agent's LLM output (`TradingDecisionOutput`) includes `entry_plan` and
`exit_plan` (strings), but they are **dropped on the way to the DB**, so the UI's Trade Plan
tab Entry/Exit fields are always empty in the real app.

- **Entry Plan** = how/when to enter the position (e.g. "Add on closing strength", "Scale in
  over 3 days", "Enter on pullback to the 20-day"). **Exit Plan** = the mechanical stop
  (price level / max-loss), e.g. "Stop out on a daily close below $452.91 (≈6% max loss)".
  These are distinct from the thesis (Evidence tab) and from invalidators — see P9.

- **Where it's lost:** `src/trading/workflows/trading_decision.py` (~lines 224–264) — the
  `metadata_json` dict built for `TradingDecisionRecord` does NOT include `entry_plan` /
  `exit_plan` (it includes `key_drivers`, `counterarguments`, `risk_checks`).
- **Where the UI reads them:** `src/web/presenters/today_workspace_detail.py` builds
  `trade_plan.entry_plan` / `trade_plan.exit_plan` from `metadata_json.get("entry_plan")` /
  `.get("exit_plan")`.
- **Fix:** add to the `metadata_json` dict:
  `"entry_plan": final_output.get("entry_plan")`, `"exit_plan": final_output.get("exit_plan")`.
- **Migration:** none — `TradingDecision.metadata_json` is JSONB.
- **Verify:** after a fresh decision run, Trade Plan tab shows Entry/Exit.

---

## P2 — VERIFY (maybe fix): bucket placement for filled/open positions

A filled / open position should appear in the **Open Positions** bucket, not **Action Now**.
This is `primary_state` / bucket classification in
`src/web/presenters/today_workspace.py` → `build_ticker_workspace` (~lines 65–102).
- **Action:** confirm against real data whether a filled long is classified
  `primary_state="open_position"`. (The mismatch was first seen in a UI mock, so this may be
  a mock artifact rather than a real bug.) Only adjust the classification if real data
  actually mis-buckets.

---

## P3 — Portfolio backend (needed for the Portfolio tab redesign)

### P3a — Expose dated chart series (for axis charts) — PARTIALLY DONE
`build_portfolio_analytics` now also returns `x_axis_ticks` (`[{x, time, anchor}]`, evenly
spaced) derived from the equity history's `time` field, and both charts render **date x-axis
labels** (UI done). Still **pre-rendered SVG** otherwise.
- **Remaining (optional, for richer charts):** expose the full dated series
  `series: [{date, equity, day_pnl}, ...]` + y-gridlines / y-axis value labels so the line/bar
  charts have a full axis grid (not just bottom date ticks).
- **Migration:** none.

### P3b — Enrich Open Positions rows
`src/web/routers/loaders/portfolio.py` → `_load_positions` (~lines 58–77) currently emits
`ticker, trade_identity(+label), strategy_id(+label), quantity, market_value, unrealized_pnl`.
The `PaperPosition` model has more.
- **Add:** `entry_price` (= `avg_cost`), `current_price` (= `market_price`),
  `held_days` (now − `opened_at`), `total_pnl_pct` (= `unrealized_pnl / (avg_cost*qty)`).
  `sleeve` can reuse `trade_identity_label`.
- **NOT derivable (omit):** `today_pnl` / `today_pnl_pct` — no prior-close price in the data.
- **Migration:** none.

### P3c — Realized trade stats — NEEDS NEW DATA (don't fabricate)
Win rate, profit factor, expectancy, best/worst **closed** trade, realized drawdown are
**not available**: closed positions (`_load_recent_closed_positions`) lack realized P&L /
entry / exit. Would require computing realized trade-level stats (entry vs exit fills) —
new aggregation + likely new persisted data. **Leave the UI cards out until this exists.**

### P3d — "Profitability Truth" row — NEEDS NEW DATA (don't fabricate)
Net account delta, open-position P&L %, capital-in-use, review-window P&L, window
expectancy, journal-vs-SQLite reconciliation — none of these exist. New computation /
reconciliation source required. **Leave out until backed.**

---

## P4 — Wire per-candidate Recent News (small)

The Candidates tab now has a **Recent News** tab per candidate, reading `row.news` (a list of
`{title, summary, time, source, sentiment, event_type}` like the trades news snippets). The
presenter doesn't populate it yet, so it shows "No recent news captured."
- `news_by_ticker` is **already loaded** in `load_today_dashboard` (`src/web/routers/today.py`,
  `_load_news_by_ticker(session)`) and fed to the trades workspace.
- Pass it into `build_today_candidates_view(...)` (`src/web/presenters/today_candidates.py`) and
  attach `row["news"] = news_by_ticker.get(ticker, [])` to each `decision_readout` / `rows` item
  (snippet shape already matches what the template expects — see
  `today_workspace_detail._build_snippets`: title/summary/time/source/sentiment/event_type).
- **Migration:** none.

---

## P5 — Surface the trading-agent LLM thesis on Candidates (presenter join) — ✅ DONE

Implemented: `load_today_dashboard` builds `thesis_history_by_ticker` (ticker → newest-first
`[(decision_time, thesis)]`) from `trade_rows` and passes it to `build_today_candidates_view`,
which time-matches each candidate/evaluation to the agent thesis at-or-before its decision_time
(`_thesis_at`). The UI prefers `row.thesis` / `evaluation.thesis`, falling back to the rule-based
text. (Below is the original analysis for reference.)


The Candidates row "Primary Reason" and History both currently show **rule-based / derived**
text, NOT the LLM thesis:
- `CandidateScore.selection_reason` is a **deterministic strategy-matching string** (see
  `src/trading/strategies/matching.py` — e.g. "deterministic PR02 signals matched strategy",
  "macro regime blocks this strategy"). It is NOT LLM-written.
- `operator_summary` is a `_sentence_join(...)` derived display string
  (`src/web/routers/loaders/candidates.py`), also not LLM.
- The **LLM thesis is produced by the trading agent and lives on `TradingDecision.thesis`**
  (the step that runs after a candidate is selected). Candidates are `CandidateScore` rows and
  don't currently join to their `TradingDecision`.

**Fix:** in `build_today_candidates_view` (`src/web/presenters/today_candidates.py`), join each
candidate (by ticker / decision_id) to its latest `TradingDecision` and surface `thesis` as the
candidate's reason — both for the row's Primary Reason column and for each `evaluations[]` entry
(add `evaluation.thesis`). `trade_rows` / `_load_trade_detail` are already available in
`load_today_dashboard` to build a `ticker → thesis` (or `decision_id → thesis`) map to pass in.
Until then the UI shows the rule-based `selection_reason` (row) and derived `operator_summary`
(history), which read as status text rather than reasoning.
- **Migration:** none (data exists on `TradingDecision`).

---

## P6 — Selected-ticker header: discrete avg fill price (header "Fill" column)

The redesigned Trades hero is now a key/value table (Strategy, Confidence, Approved Weight,
Expression, Horizon, Position, Opened, **Fill**). The **Fill** cell shows the average fill
price, but there is no discrete field for it — the template currently shows
`position_execution.summary` only when it contains a `$` (a heuristic), so in the real app the
Fill cell is usually hidden.
- **Where:** `position.summary` comes from the positions loader and defaults to a generic
  string like `"Open position, risk within limits"` (see `header_system.py:156`,
  `today_overview.py:313`) — no price.
- **Fix:** expose a discrete `avg_fill_price` (and optionally `filled_qty`) on the position
  payload consumed by `today_workspace_detail._build_*` so the header can render
  `Fill  $521.58 avg`. `PaperPosition.avg_cost` already holds the fill price.
- **UI binding:** add `fill_price` to `position_execution` in
  `src/web/presenters/today_workspace_detail.py` and have the template show that field instead
  of the `$`-in-summary heuristic.
- **Migration:** none.

---

## P7 — Risk Manager: structured per-rule checks + specific reason/lookahead copy

The Risk tab now renders **per-rule approvals** (`✓ Sector concentration 9% vs 15% cap`) when
the risk summary carries a structured `rule_checks` list; otherwise it falls back to plain
`applied_rules` chips (current real-data behavior, which is just rule *names*).
- **Add** `rule_checks: [{label, observed, cap, passed}, ...]` to the risk summary the risk
  manager emits (and surface it in `today_workspace_detail.py` `risk_summary`). Then the UI
  shows the approval *against each rule* with a pass/fail verdict instead of opaque rule ids.
- **Also:** `risk.reason` and `risk.lookahead_risk_source` should be **specific**, not generic.
  Good: `"Sector concentration at 9% vs the 15% cap; sized to 7% of book. Okay to proceed."`,
  `"Earnings on 06/26/2026 (9 sessions out) — kept to a probe ahead of the print."`
  Bad (current): `"Within exposure and event limits."`, `"Earnings in 9 sessions"`.
- **Migration:** none (JSON payload).

---

## P8 — History tab: per-decision `confidence`

The Trades **History** tab is now a table: `Time | Phase | Decision | Strategy | Conf |
Reasoning`. `Strategy` and `Conf` come from each timeline decision.
- **Done (presenter):** `today_workspace_timeline.py` `_history_trade_decision_view` now adds
  `confidence` (from the decision row's `confidence`). `strategy_label` was already present.
- **Backend action:** none if `TradingDecision.confidence` is populated per decision (it is for
  the latest decision; confirm historical decision rows also carry it). If older rows lack
  `confidence`, the Conf column shows `—` for them — acceptable.

---

## P9 — Semantic separation: `invalidators` vs `exit_plan`

The Evidence tab shows **Invalidators — what breaks the thesis** and the Trade Plan tab shows
**Exit Plan**. These must be populated with *different kinds* of content:
- **`invalidators`** = qualitative / thesis-breaking conditions, e.g. "Earnings miss with
  guidance cut". **Do NOT** put price-level stops here.
- **`exit_plan`** = the mechanical stop (price / max-loss), e.g. "Stop out on a daily close
  below $452.91 (≈6% max loss)".
- **Where:** `invalidators` come from `_decision_invalidators`; `exit_plan` is the P1 field.
  Ensure the trading agent's output keeps price stops in `exit_plan` and reserves
  `invalidators` for thesis-level conditions — they were mixed in early mock data.
- **Migration:** none.

---

## P10 — Portfolio tables: column enrichment (UI done) + option per-position P&L (NEEDS BACKEND)

The Portfolio tab tables were enriched. **Loader plumbing already done this session** (pure
exposure of existing columns, in `src/web/routers/loaders/portfolio.py`):
- **Stock Positions** (`_load_positions`): added `avg_cost` → table now shows
  `Qty | Entry | Market Value | Unrealized P&L` (Entry = avg_cost; Unrealized P&L already existed).
- **Option Positions** (`_load_option_positions`): added `quantity`, `expiry_label`,
  `buying_power_effect` → table shows `Contracts | Expiry | BP Effect | Max Loss`.
- **Hedge Overlays** (`_load_hedge_overlays`): added `action_label`, `hedge_cost`, `created_at`
  → table shows `Action | Strategy Type | Hedge Cost | Protected Notional | Added`.

**STILL NEEDS BACKEND — per-position option P&L:** options have no Unrealized P&L / Market Value
because `PaperOptionPosition` has **no `market_value` / `unrealized_pnl` / cost-basis column**
(only quantity/expiry/max_loss/margin/buying_power_effect/assignment_notional). The loader's old
`market_value` getattr was always `None`. Two related pieces exist but are unusable per-position:
- `portfolio_snapshots.option_market_value` is an **account-level aggregate**, not per position.
- Live option marks ARE computed during intraday refresh (`_option_mark_price` in
  `src/trading/runtime/intraday_refresh_helpers.py`) but never written back onto the position.
- **Fix:** add `market_value` (+ `unrealized_pnl`) to `PaperOptionPosition`; have the intraday
  refresh / valuation persist the mark per position; cost basis = premium paid (≈ `max_loss` for
  long-premium strategies, or from `metadata_json.legs`). Then `unrealized_pnl = market_value −
  premium_paid` and the Option Positions table can show P&L like stocks. **Migration: yes** (new
  columns). This is P3-class work (deferred), recorded here so it isn't lost.

### Stock daily P&L / total_pnl_pct (still deferred, P3b)
`avg_cost` is now exposed, but per-position **daily P&L** is still not derivable (no prior-close),
and `total_pnl_pct` is not computed. Left out per the P3 deferral.

---

## P11 — Portfolio analytics cards: Sharpe (done), strategy effectiveness (done), benchmark-relative (NEEDS BACKEND)

Five metric cards were added to the Portfolio analytics row.

**Done this session (backed by existing data):**
- **Sharpe Ratio** — computed in `today_portfolio_analytics.build_portfolio_analytics` from daily
  equity returns: annualized `mean/std × √252`, risk-free = 0. Exposed as `metrics.sharpe_ratio`.
  (If a non-zero rf or a different annualization factor is wanted, adjust there.)
- **Most / Least Effective Strategy** — computed in `today.py` (`load_today_dashboard`) by ranking
  `_load_strategy_performance` rows by `total_pnl` (= cumulative alpha); injected as
  `portfolio["strategy_effectiveness"] = {most, least}`. Shows strategy label + win_rate + alpha.

**STILL NEEDS BACKEND — benchmark-relative returns (placeholder cards in UI):**
`Total Return vs Benchmark` and `Daily Return vs Benchmark` render as `—` / "awaiting benchmark
feed". There is **no account-level benchmark series** anywhere — only per-ticker `rs_vs_spy_1d`
and per-eval `alpha`. To back these:
- Fetch a benchmark (e.g. SPY) price/return series **aligned to the portfolio equity history
  dates** (`_load_portfolio_history`).
- Compute `total_return − benchmark_total_return` and `daily_return − benchmark_daily_return`,
  expose as `metrics.total_return_vs_benchmark` / `metrics.daily_return_vs_benchmark`.
- UI is ready: drop the placeholder cards' bodies onto those fields. **Migration:** likely a
  benchmark-series table or a cached fetch. P3-class work (deferred), kept as placeholders per
  user request.

---

## P12 — Risk & Macro tab: macro news feed + richer earnings calendar (NEEDS BACKEND)

The Risk & Macro tab was reworked (command center, "Macro Read" callout, deduped earnings vs
risk actions, denser calendars). Two pieces need backend data:

- **Macro News feed** — the UI has a `Macro News` section (ticker-recent-news style: title /
  source / time / sentiment / summary) that renders only when `risk_macro["macro_news"]` is
  populated. There is currently **no macro-level news source** (`NewsAlert` is ticker-scoped).
  Add a macro/market news feed (or filter market-wide items) and expose as
  `risk_macro["macro_news"] = [{title, summary, time, source, sentiment}, ...]`.
- **Richer event/earnings calendar** — the calendars were restyled to the dense reference
  layout (Economic Calendar = `dot · time · name · impact` rows; Upcoming Earnings = compact
  tile grid). The following reference fields are **NOT in the data** and were left out:
  - **Feed status badge** (`LIVE` / `PARTIAL`) per calendar.
  - **Refresh telemetry**: "Last updated HH:MM ET", "Cache · N rows · checked HH:MM", and the
    descriptive line ("High-impact in next 7d: 1 …", "Inside 2d buy-veto window: CNXC, RDUS …").
  - **Per-earnings chips**: `D0` (days-to-report), `GATE` (gate status), `PM`/`AM` (session),
    consensus EPS / `$price`, `expected_move`.
  - To back these, extend the event payload (`build_today_risk_macro_payload` / its loader) with
    `feed_status`, `last_updated_at`, `checked_at`, `cache_row_count`, and per-earnings
    `days_to_report`, `gate_status`, `session`, `consensus_eps`, `expected_move`. UI currently
    shows count + high-impact count + colored importance badges/dots from the available fields.
- **Migration:** macro_news likely a feed/table; earnings enrichment depends on the data source.
- **Filter added (done):** `local_time(..., 'month_day_time')` → `MM-DD HH:MM` in
  `src/web/filters.py` for the compact calendar timestamps.

---

## P13 — Learning-factor "Today's Effect" copy must match what is actually applied

The System tab's Learning Factors table now shows a **Today's Effect** column + a `TODAY` flag
for active factors (replacing the old separate "Today Weight Inputs" table). The effect string
comes from `_effect_summary(effect_tags)` in `today_learning_strategies.py` — a humanized render
of `effect_tags`. **This can misrepresent reality**: `build_learning_adjustments`
(`src/trading/learning/apply.py`) only implements two concrete adjustments:
- **scope = `strategy`** (with `strategy_id`): `increase_score` → that strategy's match score
  `× 1.10` (capped 1.25), applied in `StrategyMatcher._apply_learning_factor_modifier`
  (`matching.py`).
- **scope = `risk` / `portfolio`**: risk-tightening tags → risk-budget `× 0.85`;
  `increase_risk_budget` → `× 1.10`, applied in `preopen_risk.py` (book-wide risk dial).

There is **no per-sector / per-name weight tilt** (e.g. "tech weight −10%") in the apply logic, so
an `effect_tags` value implying one would display an effect the engine never applies.
- **Fix:** make the UI effect copy derive from the **actually-applied** adjustment — e.g. expose
  per-factor `applied_effect` from `build_learning_adjustments` (`strategy score ×1.10` /
  `risk budget ×0.85`) and show that, instead of free-text `effect_tags`. Alternatively, constrain
  `effect_tags` to the set the engine honors and map them 1:1. Until then, treat the Effect column
  as indicative, not literal.
- **Note:** Learning Factor ≠ Strategy. A Strategy is a trading playbook (matches candidates, makes
  trades, owns win-rate/P&L); a Learning Factor is a learned multiplier/dial layered on top — it
  either scales one strategy's score (scope=strategy) or the whole book's risk budget
  (scope=risk/portfolio). It never defines or replaces a strategy.

---

## Frontend follow-ups (UI consistency sweep — NOT backend)

A cross-tab consistency pass was done on the Today redesign. Clean: no undefined CSS vars,
heading levels consistent (`h2` surface / `h3` panel / `h4` news headline only), body type
unified to `--fs-base` / `--text-dim` / `--text`, and all tables now share the `.dtable` header
chrome (`.compact-table` was aligned to it). Two **low-priority** items left, deliberately not
changed (cosmetic, churn/risk not worth it mid-redesign):
- **Hardcoded px font-sizes** in the base/legacy component layer of `style.css` (10/11/12/13px,
  etc.). The values match the token scale (`--fs-2xs…--fs-md`) but aren't written as
  `var(--fs-*)`. A full tokenization pass would be purely mechanical; do it as its own change.
- **Three tile families** coexist: header `.kpi-card` (gradient-accent), `.cmd-tile` (centered,
  Risk & Macro command center), `.summary-tile` (label/value, Portfolio/System vitals). They
  serve different roles; unifying to one tile component is a larger redesign, not urgent.

---

## Notes
- Candidate sub-scores (technical/fundamental/sentiment/rs_rank) are also missing; the
  Candidates UI uses `candidate_score` + signal bullets + risk tags instead.
- No dedicated news-summary LLM agent exists; `NewsAlert` / `EventNewsItem` already carry
  `headline, summary, published_at, source, sentiment` (+ event_type/importance) and the UI
  now surfaces them. An LLM news-rewrite agent would be a separate, larger piece.
