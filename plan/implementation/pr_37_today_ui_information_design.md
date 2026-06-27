# PR 37 `/today` UI Information Design — Implementation Plan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. ALSO REQUIRED: invoke the `ui-development` skill before touching any `.html`, `style.css`, or presenter — it carries the pre-ship checklist this plan depends on. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn `plan/design/14_today_ui_information_design.md` (a written spec with a 20-item prioritized backlog, but no actionable handoff) into file-level implementation slices, and execute them. The north star (design 14 §6.5): `/today` is an **observation / audit** surface — its job is to make a human *understand and trust* the automation's decisions, not operate it. So the claim↔evidence binding (IP-2), the single "today health bar" (IP-9/IP-10), and the conclusion→why→evidence hierarchy (IP-1/§3) are the priorities; the only manual write action ("add ticker candidate") must stay singular and obvious.

**Architecture:** Server-rendered Jinja (`src/templates/today/`), single stylesheet `src/static/style.css`, data shaped by `src/web/presenters/*`, formatting in `src/web/filters.py`, copy/label maps in `src/web/presenters/today_copy.py`. No JS framework. Each slice is independently reviewable and stops for review before the next (per README Execution Rules + design 14 §0.5 "don't do one big change + push"). Presenter logic (dedup, formatting, chart math, label maps) is unit-testable without a browser; visual/hover changes must be verified by real render + screenshot (handed off — no local app env; see `no-app-env-access` memory).

**Tech Stack:** Python, Jinja2, inline SVG, vanilla JS (no framework), pytest for presenter/filter units.

---

## Required Pre-Read

1. `documents/general_instructions.md`
2. `plan/design/14_today_ui_information_design.md` — **the spec this plan executes** (read fully)
3. `plan/design/09_ui_error_testing_delivery.md` §13 — the original audit-trail design design 14 deviates from
4. The `ui-development` skill (pre-ship checklist)
5. `plan/implementation/pr_28_ui-redesign-plan.md`, `pr_29_today_ui_quality_pass.md`, `pr_30_today_candidate_trade_semantic_split.md` — prior UI passes
6. `plan/progress_tracker.md` — **Recent** section only
7. `plan/review_backlog.md` — item #5

## Scope decision: slice it, don't big-bang

Design 14 §7 lists 20 fixes (P0→P3). This plan groups them into **5 reviewable slices**. Implement and ship them in order; each stops for human review + render verification before the next. Do NOT collapse them into one PR.

- **Slice A (P0 information):** claim↔evidence transitional merge + dedup + Overview tab + attention-feed CSS.
- **Slice B (P0/P1 — the health bar & navigation scent):** the single "today health bar" (depends on PR 35's reason codes + PR 36) + per-tab attention counts + as-of/live-stale.
- **Slice C (P1 machine-value correctness):** label maps, `pct_unsigned`, `fmt_currency` negative sign, double-eyebrow, focus styles.
- **Slice D (P1 charts):** PnL per-day hover + Y-axis annotation + confidence/weight magnitude bars.
- **Slice E (P2/P3 visual system):** flat grey-blue token convergence, tabular-nums right-align, colorblind-safe direction marks. (Largest; may itself be sub-sliced.)

`config_json` validation, God-file/repository splits, and the timezone/whole-table query work are **not** UI and are out of scope here (design 14 §9 explicitly excludes them — they are PR 35/36 and separate refactors).

## Guardrails (from `ui-development` skill + design 14 §8)

- Verify by **real render** (or hand off a screenshot) — never claim a visual/hover change is done from reading the diff. Charts and hover MUST be browser-verified.
- Every machine value goes through a filter: datetime→`local_time`/`<time>`; numbers→`fmt_*`/`pct`; enums/ids→a `*_label` humanizer or hidden.
- Every new CSS class has a matching rule. No new hardcoded colors once tokens exist (Slice E) — use tokens.
- One fact rendered once (IP-3). No duplicate aliases across cards.
- Presenter changes ship with presenter unit tests (dedup, label mapping, chart math, format).
- Anchors used as cards get `text-decoration:none` + `:focus-visible`.
- Do not add operate-style affordances (approve/override/order buttons) — observation surface only (memory: `ui-is-observation-surface`).

## File Map (by slice — confirm exact line numbers before editing; design 14 cites them but re-verify)

- `src/web/presenters/today_workspace_detail.py` — dedup `edge`==`bull_points`; build merged rationale+evidence (Slice A)
- `src/templates/today/_tab_trades.html` — merge Bull-Bear + Signal Groups card; remove double eyebrow; confidence bar (A/C/D)
- `src/web/today.py` (or wherever the tab-label registry lives — design 14 §0 cites `_TAB_LABELS`; `grep -rn "_tab_overview\|tab" src/web/` to locate) — re-attach Overview tab (A)
- `src/templates/today/_tab_overview.html` — revive as a real tab (A)
- `src/static/style.css` — attention-feed variants, focus styles, tokens, tabular-nums (A/C/E)
- `src/web/presenters/today_copy.py` — fill empty label maps `event_type_label`/`risk_source_label`/`scope_label`/`generic_status_label` (currently `_mapped_or_humanized(value, {})`, lines ~215-235) (C)
- `src/web/filters.py` — `fmt_currency` negative-sign fix (line ~23); add `pct_unsigned` / `fmt_pct(signed=False)` (C)
- `src/web/presenters/today_portfolio_analytics.py` — emit per-point chart data `[{x,y,date,equity,day_pnl,pnl_pct}]` + min/max/baseline for axis (D)
- `src/templates/today/_tab_portfolio.html` + a small inline `<script>` (base.html style) — hover tooltip + crosshair + Y-axis labels (D)
- `src/web/presenters/today_overview.py` / header presenter — health bar payload + per-tab attention counts + as-of/stale (B)
- `tests/web/test_today*.py`, `tests/web/test_filters*.py`, presenter tests — per slice
- `plan/progress_tracker.md`, `plan/review_backlog.md`

## Slice A — P0 information (claim↔evidence transitional + dedup + Overview + attention CSS)

Maps design 14 backlog #1, #2, #4, #5.

- [ ] A1 (dedup, IP-3): In `today_workspace_detail.py` the `trade_plan.edge` and `bull_bear.bull_points` are the SAME `tuple(key_drivers)` (design 14 §IP-3 cites lines 127/132). Remove the `edge` alias from the presenter and delete the "Edge" segment from the Trade Plan card. Add a presenter unit test asserting `edge` is not duplicated.
- [ ] A2 (transitional claim↔evidence, IP-2): Merge the Bull-Bear card (`_tab_trades.html:280-321`) and the Signal Groups card (`:323-355`) into ONE "Rationale & Evidence" card — claims on top, evidence grouped by Technical/Fundamental/News below, in the same card. This is the **template-only transitional** step (the full driver→signal data linkage is A5, deferred). Do not fabricate links; just co-locate.
- [ ] A3 (Overview tab, #5): Re-add `overview` to the tab-label registry so the dead branch (`today.html:69` per design 14 §0) becomes reachable and `_tab_overview.html` renders as a real tab. Verify the tab renders (handoff screenshot).
- [ ] A4 (attention-feed CSS, #4): `_tab_portfolio.html:149/170/191` use `attention-feed-row-review/-alert/-signal` but `style.css` has only the base class. Either add visually-distinct rules for the three variants or remove the unused classes. Pick one; if adding, give review/alert/signal distinct left-border colors (pos/neg/neutral semantics).
- [ ] A5 (terminal claim↔evidence — DATA work, deferred note): The full IP-2 (each driver carries the `signal_key`s it references; presenter assembles `rationale:[{claim,direction,conviction,evidence:[{label,value,source,as_of}]}]`) requires a decision-chain data change. Do NOT do it in this slice — write a one-paragraph follow-up note in the tracker describing the data contract so a later slice picks it up.
- [ ] A6: Presenter unit tests for dedup + merged-card data shape. Render-verify (handoff).

## Slice B — the today health bar + navigation scent (IP-9/IP-10)

Maps design 14 backlog #15, #16 and the §9 "#1/#2 observability — UI half is free" insight. **Depends on PR 35** (reason-coded skipped execution records) and **PR 36** (reflection ran/skipped) landing first, or being stubbed behind a presenter that tolerates missing fields.

- [ ] B1: Define the health-bar presenter payload: `orders_submitted: int`, `orders_skipped: int`, `skip_reasons: dict[str,int]`, `orders_failed: int`, `reflection_ran: bool`, plus an overall `as_of` timestamp and a `live|stale` flag (stale when intraday data older than a threshold). Source `orders_*`/`skip_reasons` from PR 35's extended execution report; `reflection_ran` from the reflection runtime report (PR 36).
- [ ] B2: Render a single health bar in the header / Overview that reads e.g. `Orders: 3 submitted · 2 skipped (1 not_authorized, 1 risk_rejected) · Reflection: ran · as of 16:21 ET (live)`. Skipped/failed counts must be visible so "0 orders" can never silently read as success.
- [ ] B3 (IP-10, #15): Attach attention counts to tab labels using existing `header.open_alert_count` etc. — `Candidates (3)`, `Risk & Macro ⚠`. Locate the tab-label render (`today.html:61` per design 14) and thread counts in.
- [ ] B4 (IP-9, #16): Page-level as-of timestamp + live/stale state in the header; stale intraday data visually flagged.
- [ ] B5: Presenter unit tests for the health-bar math + stale threshold. Render-verify (handoff).

## Slice C — machine-value correctness

Maps design 14 backlog #8, #9, #10, #13, #14, and §6 violations.

- [ ] C1 (#14, `fmt_currency` negative sign): `filters.py:23` `fmt_currency(-8000.32)` → `$-8,000.32` (wrong). Fix to `-$8,000.32` (sign before `$`). Add filter unit tests for negative, zero, None, large values.
- [ ] C2 (#9, `pct` over-signs exposures): `filters.py:11` `pct` always emits `+`. Exposures / margin-util are not P&L — a leading `+` misreads as "+31% change". Add `pct_unsigned` (or `fmt_pct(value, signed=False)`) and switch Net/Gross Exposure + Margin Util KPIs to it. Keep `pct` (signed) for P&L. Unit-test both.
- [ ] C3 (#8/#12, empty label maps): Fill the empty `{}` maps in `today_copy.py` — `event_type_label`, `risk_source_label`, `scope_label`, `generic_status_label` (lines ~215-235) — with mappings for the leaking slugs design 14 §0.5 caught: `own_event`, `macro_high_overlay`, `single_name_limit`, `event_window_check`, `risk_config_resolver_v1`, `earnings_drift_v1`, `semis_readthrough_v1`, `market_bars`. For ID-like values (`*_v1`, `strategy_id`) humanize or hide rather than show the raw slug. Add them to `_INLINE_LABELS` if used inline. Unit-test the mappings.
- [ ] C4 (#8/#12 template sites): Fix the template leaks: `_tab_risk_macro.html:19` (`"%.2f%%"|format` → `pct`/`pct_unsigned`), `_tab_system.html:55/71` (raw `strategy_id` → `strategy_label`), `_tab_overview.html:169` / `_tab_risk_macro.html:141` (raw `severity` enum → a label).
- [ ] C5 (#10, double eyebrow): `_tab_trades.html:96-97` stacks "Trade Decision" + "Latest Conclusion". Keep one.
- [ ] C6 (#13, focus styles): Add `:focus-visible` focus rings to card-anchors (`.ticker-card`, `.attention-feed-row`, `.detail-list-item`) and tabs; new text colors must pass WCAG AA.
- [ ] C7: Filter + label unit tests; render-verify (handoff).

## Slice D — chart interactivity & magnitude

Maps design 14 backlog #3, #6, #11 and §4.

- [ ] D1 (#3, PnL hover): In `today_portfolio_analytics.py`, emit per-point data `points:[{x,y,date,equity,day_pnl,pnl_pct}]` alongside the existing geometry. Keep the degenerate-data guards (single point, all-equal, all-zero, None — never divide by a zero range); existing `test_today_portfolio_analytics.py` must still pass.
- [ ] D2: Add a vanilla inline `<script>` (mimic `base.html` style, no framework) in `_tab_portfolio.html`: on SVG `mousemove`, find nearest point by x, show tooltip (date + equity + day P&L + %) + vertical crosshair. Keep `.equity-line` `fill:none`.
- [ ] D3 (#11, axis): Presenter emits min/max/baseline; SVG gets Y-axis labels so magnitude is readable, not just shape.
- [ ] D4 (#6, magnitude bars): Confidence/weight in the trades hero get a `▮▮▮▮▯`-style bar next to the number; pos/neg coloring.
- [ ] D5: Presenter math unit tests; **browser-verify hover** (handoff screenshot — design 14 §4: "charts are the first thing to verify by real render").

## Slice E — visual system convergence (P2/P3)

Maps design 14 backlog #17, #18, #19 and §5. Largest; sub-slice if needed (tokens → shadows → radii → colors, "one class at a time", never all at once).

- [ ] E1: Add the `:root` token block from design 14 §5 to the top of `style.css` (currently 0 CSS vars, 141 hardcoded colors, 10 radii values). New code references tokens only.
- [ ] E2 (#17): Right-align numeric table columns + `font-variant-numeric: tabular-nums`.
- [ ] E3 (#18): Add direction marks/arrows to pos/neg values (not color-only) for colorblind safety.
- [ ] E4 (#19): Migrate warm-gold/heavy-shadow/oversized-radius surfaces to flat grey-blue, in batches (shadows first, then radii, then colors). Each batch is its own review.
- [ ] E5: Render-verify each batch (handoff).

## Out of scope / deferred (note in tracker, don't lose)

- Full IP-2 driver→signal data linkage (Slice A5) — needs decision-chain data contract.
- Invalidator "tripped?" status (design 14 #20) — needs new gate/veto logic; independent future work.
- LLM prompt logging keep-or-cut decision (design 14 §9) — product call, not this plan.

## Per-slice exit + final wrap

- [ ] After EACH slice: run the touched presenter/filter unit tests, hand off a render screenshot, prepend a dated `plan/progress_tracker.md` **Recent** entry, and stop for review.
- [ ] After Slice E: in `plan/review_backlog.md` mark #5 resolved (note any deferred sub-items A5/#20).

## Done when

- The Trades detail reads conclusion→why→evidence with claims and evidence co-located (transitional merge shipped; data linkage noted as follow-up).
- A single today health bar surfaces submitted/skipped(reason)/failed + reflection-ran + as-of/live-stale, so silent skips are visible.
- No raw slugs/enums leak; `fmt_currency` negatives and exposure percentages render correctly.
- PnL chart is per-day hoverable with axis magnitude; confidence shows a magnitude bar.
- (Slice E) visual system converged to flat grey-blue tokens.
- Each slice was render-verified and reviewed before the next; tracker + backlog updated.
