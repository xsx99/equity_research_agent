# Plan: `/today` dashboard UI redesign — implementation (PR-A / PR-B / PR-C)

**Audience:** coding agent working on the personal repo (`github.com/xsx99/equity_research_agent`).
**Why this doc exists:** PR-A and PR-B were already implemented on a company laptop that is blocked from
pushing to the personal remote. This plan lets you reproduce that work exactly (via a patch) and then
continue with PR-C and beyond.

**Base commit:** everything here is written against `5e902b4` (main, "Merge PR #19"). Confirm you're on it:
```
git rev-parse HEAD          # should be 5e902b453c41ca206beac9f91b7a6e3c120e8d31, or rebase onto it
```

**Audience for the UI itself:** the single operator (finance- and system-literate). Keep professional
terminology; reorganize by workflow; cut redundancy; do NOT add beginner copy. The dashboard's spine is
**portfolio & P&L**. The app theme is **light/warm** (see `src/static/style.css`); do not introduce a dark
theme.

Files in play: `src/web/routers/today.py`, `src/templates/today.html`, `src/static/style.css`.

---

## PR-A + PR-B — already implemented (reproduce via patch)

The fastest path is to apply the bundled patch, which contains the exact PR-A + PR-B code changes and
applies cleanly on `5e902b4`:

```
git checkout -b today-ui-redesign 5e902b4
git apply plan/research_app/today_ui_pr_ab.patch
git add src/ && git commit -m "Redesign /today dashboard: money-first header, portfolio home, 5-tab IA"
```

Verify after applying (no app/DB needed):
```
python -m py_compile src/web/routers/today.py        # must succeed
# template structure: no unbalanced/`double-else` blocks (see verification script at the bottom)
```

If the patch does NOT apply (repo drifted from `5e902b4`), reproduce the changes manually using the
specs below — they fully describe what the patch does.

### PR-A — money-first header + default tab + copy cleanup

**A1. `src/web/routers/today.py` — extend `_build_header(...)`.** The returned dict already had
`nav/day_pnl/buying_power/gross_exposure`. Add account state + P&L pulled from the latest
`portfolio_snapshots` row (`latest_portfolio`) and exposure from `latest_risk`:
- `account_equity` ← `latest_portfolio.account_equity`
- `cash_balance` ← `latest_portfolio.cash_balance`
- `day_pnl_pct` ← `_safe_pct(day_pnl, _safe_diff(account_equity, day_pnl))`  *(ratio, e.g. 0.0097)*
- `realized_pnl`, `unrealized_pnl`, `stock_market_value`, `option_market_value` ← same snapshot
- `net_exposure` ← `latest_risk.net_exposure`
- `margin_util_pct` ← `_safe_pct(latest_portfolio.total_margin_requirement, account_equity)`

Add two module-level helpers (guard `None`/zero, return `float | None`):
```python
def _safe_diff(a, b):  # a - b as float, else None
def _safe_pct(numerator, denominator):  # numerator/denominator ratio, guard None/0
```
Column names verified against `src/db/models/trading.py` (`PortfolioSnapshot`, `PortfolioRiskSnapshot`).

**A2. Default landing tab → `portfolio`.**
- Handler default: `def today_dashboard(... tab: str = "portfolio" ...)`.
- `_normalize_tab` fallback returns `"portfolio"` (not `"overview"`).

**A3. Header template (`today.html`).** Replace the two `operator-strip-group` blocks + the
"Trading Workstation / Today Dashboard / Operator workstation…" title block with:
- `<h1>Today</h1>` + a muted sub-line `{{ header.trade_date }} · {{ header.market_phase }}`.
- A `.kpi-bar` row, money first: **Account Equity · Day P&L ($ + `pct(header.day_pnl_pct)`) · Unrealized
  P&L · Net/Gross Exp. · Buying Power**. Tone Day/Unrealized P&L with `kpi-pos`/`kpi-neg` based on sign.
- A `.kpi-context` line: Macro Regime · Risk Appetite · Margin Util. · Pre-open Job · Open Alerts.
- Use existing globals `fmt_currency`, `pct` (`pct` multiplies a ratio by 100 and adds sign).

**A4. Copy cleanup.** Remove every visible `<p class="eyebrow">Focused Surface</p>` (was on each tab
heading) and the "Trading Workstation"/"Operator workstation for V2 trading artifacts" strings. Keep CSS
class names; only change human-readable text.

**A5. `style.css`** — append `.kpi-bar/.kpi/.kpi-label/.kpi-value(.kpi-value-lg)/.kpi-sub/.kpi-pos/.kpi-neg/
.kpi-context` in the existing light/warm palette (P&L green `#1a7f37`, red `#b42318`).

### PR-B — portfolio home + 7→5 tabs + System tab

**B1. Tabs 7 → 5.** `_TAB_LABELS` in `today.py`:
```python
("portfolio","Portfolio"), ("trades","Trades"), ("candidates","Candidates"),
("risk-macro","Risk & Macro"), ("system","System"),
```
Dropped: `overview`, `learning-strategies`, `ops-cost`. (`_normalize_tab` coerces unknown/legacy tab ids
→ `portfolio`, so old bookmarks still resolve.)

**B2. Tab nav (`today.html`).** In the `{% for tab in tabs %}` loop, push System right and mute it:
```html
{% if tab.id == "system" %}<span class="today-global-tab-spacer"></span>{% endif %}
<a class="today-global-tab {% if tab.id == 'system' %}today-global-tab-muted{% endif %} {% if selected_tab == tab.id %}active{% endif %}" href="/today?tab={{ tab.id }}">{{ tab.label }}</a>
```
CSS: `.today-global-tab-spacer{flex:1 1 auto}` and a muted `.today-global-tab-muted` variant.

**B3. Portfolio = home surface.** Delete the standalone `{% elif selected_tab == "overview" %}` branch.
Make the `portfolio` branch lead with a **P&L/exposure summary card** (reuse `header.*`: equity, day/
realized/unrealized P&L with `kpi-pos/kpi-neg` tone, gross/net exp., cash/buying power) using the existing
`surface-summary-row`/`summary-tile` markup, then the existing Stock/Option/Hedge tables, then a
**"Needs attention"** section (`.needs-attention-grid`) rebuilt from the still-always-computed `overview`
payload: `overview.live_alerts`, `overview.material_changes`, `overview.command_center.needs_review`.
Dropped Overview widgets (operator_strip, metric_cards, current_summary, redundant "Open Positions" list)
are intentionally removed — they duplicate the new header / position tables.

**B4. System tab (de-emphasized).** Merge the old `learning-strategies` and `ops-cost` branches into a
single `{% else %}` branch titled **System**, containing: System Issues
(`overview.command_center.system_issues`), Reflection/Performance Snapshot, Strategy Proposals, Strategy
Performance, Learning Factors, LLM Usage Ledger, Provider Usage. All three payloads (`overview`,
`learning_strategies`, `ops_cost`) are returned unconditionally by `load_today_dashboard`, so they're
available regardless of selected tab. **Watch for the classic bug:** there must be exactly **one**
`{% else %}` at the tab-ladder level — when merging, do not leave the old ops-cost `{% else %}` in place.

**B5. `style.css`** — append `.today-global-tab-spacer`, `.today-global-tab-muted(.active)`,
`.portfolio-pnl-row .summary-tile strong.kpi-pos/.kpi-neg`, `.needs-attention-grid`.

**PR-B invariant — do NOT touch the Trades per-ticker detail panel.** Signal Summary
(`data-testid="signal-summary"`), Event / News Summary, Risk Manager Summary, Lifecycle, Latest
Conclusion, and the timeline sub-tab must remain byte-for-byte intact.

---

## PR-C — polish (NOT yet done — implement this)

Goal: tighten readability now that IA is settled. Presentation-only; no new queries.

**C1. Per-table "so what" aggregate lines.** Above each `compact-table`, render a one-line summary computed
in the presenter from rows already loaded (no new DB calls):
- Stock Positions: `<n> positions · $<Σ market_value> market value · <Σ unrealized P&L, toned>`.
- Option Positions: `<n> strategies · $<Σ market_value> · max loss $<Σ max_loss>`.
- Candidates: `<n> scored · <n actionable> actionable · <n watch> watch · <n blocked> blocked`.
- Risk factor exposures / LLM usage: count + key total.
- Implement small helpers in `src/web/routers/today.py` (or a presenter) that sum Decimal fields safely
  (reuse `_safe_*` patterns; guard `None`). Add the rendered strings into the `portfolio`/`candidates`/
  `system` payloads or compute inline in the template with a `{% set %}` over the row list.

**C2. Finish System-tab de-emphasis styling.** Confirm the muted tab reads as clearly secondary (color,
weight, right-aligned via the spacer). No KPIs from System should appear in the header KPI bar.

**C3. Needs-attention polish.** If all three needs-attention groups are empty, collapse the section to a
single quiet "Nothing needs attention" line instead of three empty sub-blocks. Make each row link to the
relevant tab/ticker (e.g. an alert row → `/today?tab=trades&ticker=<t>`).

**C4. Empty-state pass.** With an empty DB the header KPIs render `—`; verify every new block degrades to a
quiet empty state rather than a broken layout.

### PR-C acceptance
- Each position/candidate table shows a correct aggregate line; numbers tie out to the table rows.
- System tab is visibly de-emphasized; header shows no ops metrics.
- Empty-DB render is clean (`—` / quiet empties, no exceptions).
- Trades detail panel still intact (see invariant above).

---

## Future (optional, post-PR-C)
- **Conversion-funnel panel** on System or a new view: learning_factors created → applied → strategy
  proposals → new definitions → promoted. Read-only over existing tables.
- Wire research `watchlists` → trading universe with `selection_source="watchlist_pin"` (separate effort;
  see `wire_live_pipelines.md` if/when restored).

## Verification (no app/DB required)
```
python -m py_compile src/web/routers/today.py
```
Template structure lint (catches unbalanced blocks AND double-`else`/`elif-after-else`):
```python
import re
src=open('src/templates/today.html').read()
stack=[]; ok=True
for t in re.findall(r'{%-?\s*(\w+)', src):
    if t in ('if','for','with','call','macro','block'): stack.append({'k':t,'else':False})
    elif t=='elif':
        if not stack or stack[-1]['k']!='if' or stack[-1]['else']: ok=False; break
    elif t=='else':
        if not stack or stack[-1]['k'] not in ('if','for') or stack[-1]['else']: ok=False; break
        stack[-1]['else']=True
    elif t in ('endif','endfor','endwith','endcall','endmacro','endblock'):
        if not stack: ok=False; break
        stack.pop()
print('STRUCTURE OK' if ok and not stack else 'STRUCTURE FAIL')
```
Then run the app the normal way (`docker compose up --build` → http://localhost:8000/today). With an empty
DB, KPIs show `—`; populate `portfolio_snapshots` to see real P&L.

## Guardrails
- Light/warm theme only; reuse existing CSS class names, add new ones additively.
- Keep routes/query params (`tab`, `ticker`, `detail_tab`, `/today/manual-requests` POST) working.
- Do not modify `/research` or `/watchlist`.
- Presentation only — no schema or pipeline changes.
