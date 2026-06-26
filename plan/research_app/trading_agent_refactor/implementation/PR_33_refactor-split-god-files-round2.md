# Refactor Handoff (Round 2): The Residuals + the Front-End God Files

> **Audience:** an implementing coding agent that CAN push to this repo.
> **Author:** analysis agent (code-only environment — cannot run the app/tests or push).
> **Prereq:** Round 1 (`docs/refactor-split-god-files.md`, PRs A–E) is **already landed** in commit
> `26819d0 "split god files"`. This document covers the two things Round 1 did **not**:
>   1. the **biggest residual** it created — `today_loaders.py` (1750 lines), and
>   2. the **front-end god files** it never touched — `style.css` (1736), `today.html` (1494),
>      `research_detail.html` (429). Round 1 was scoped to `.py` verbatim moves only.
> **Goal:** same as Round 1 — structural split along existing seams, **no behavior change**, every
> public name keeps its import/template path. If a real behavior change looks unavoidable, **stop and
> flag it** instead of proceeding.
>
> **Verified at HEAD `26819d0`.** Re-verify every line number and boundary before editing — re-run the
> snippets below; the files churn.

---

## Where things stand after Round 1

```
LINES  FILE                                              ROUND-1 STATUS        THIS DOC
1750   src/web/routers/today_loaders.py                  created by PR C       → PART 1 (split)
1736   src/static/style.css                              never touched         → PART 3 (low prio)
1494   src/templates/today.html                          never touched         → PART 2 (split)
 995   src/trading/workflows/option_strategy_builder.py  created by PR A       → optional, see Round 1 §residual
 865   src/trading/workflows/paper_execution_options.py  created by PR B       → optional, see Round 1 §residual
 429   src/templates/research_detail.html                never touched         → PART 2 (optional)
```

PRs A–E all executed: `db/models/trading.py` → package (11 submodules), `today.py` 2095→513,
`trading_decision.py` 1584→617, `paper_execution.py` 1563→733, `today_workspace.py` 1318→3 modules.
The 300–500 band files Round 1 marked **LEAVE** stay out of scope here too.

**Recommended order:** PART 1 first (highest value, contained), then PART 2 (`today.html`, clean Jinja
seam), then PART 3 (`style.css`, lowest value / highest cascade-risk — do only if strict ≤300 is a
hard requirement). Each part is independent; do not chain before verifying the previous one.

---

# PART 1 — `today_loaders.py` (1750 → ~9 section modules)

**Public surface:** 76 module-level functions + one constant `_TAB_LABELS` (line 60). The **only**
importer is `src/web/routers/today.py`, which imports back exactly **46 names** (45 helpers +
`_TAB_LABELS`) — see the `from src.web.routers.today_loaders import (...)` block at the top of
`today.py`. Tests import private helpers from `today.py` (the router re-exports), **not** from
`today_loaders.py` directly — confirmed: `grep -rn "from src.web.routers.today_loaders import" tests/`
returns only `tests/test_app.py:35` (which imports `_TAB_LABELS, _build_header, _load_trade_detail`).

### ⚠️ CRITICAL SEAM — the `_router_loader_proxy` monkeypatch bridge (read before touching anything)

`today.py` (lines ~127–187) runs a loop that does, for each of the 45 re-exported helper names:

```python
def _router_loader_proxy(name):
    def _proxy(*args, **kwargs):
        return getattr(sys.modules[__name__], name)(*args, **kwargs)   # __name__ == today.py
    return _proxy

for _loader_name in (... 45 names ...):
    setattr(_today_loaders, _loader_name, _router_loader_proxy(_loader_name))
_today_loaders.SqlAlchemyTradingRepository = _router_loader_proxy("SqlAlchemyTradingRepository")
```

**What it does:** it overwrites each name *inside the `today_loaders` module namespace* with a proxy
that re-dispatches through `today.py`'s namespace. This is a **test seam**: it lets a test
`monkeypatch.setattr("src.web.routers.today._load_positions", fake)` take effect even for calls made
**between loaders** (loader A calling loader B resolves B via `today.py`, so the patch propagates).

**Why it matters for the split:** once you move `_load_positions` et al. into section submodules,
calls *between* helpers in different submodules must still hit the proxy. Two safe options — pick **A**:

- **Option A (recommended — keep the bridge centralized in `today.py`):** Leave the proxy loop in
  `today.py` but change its target. Each section submodule must import its sibling helpers **from
  `today_loaders` (the re-export hub), not from each other directly**, so that `setattr` on the hub is
  what every cross-module call sees. Concretely: keep `today_loaders.py` as a thin **re-export hub**
  (`from .today_loaders_portfolio import *`, etc., for all sections), and have the proxy loop continue
  to `setattr` on `_today_loaders`. Any helper that calls a sibling must reference it via the
  `today_loaders` module object, not a direct cross-submodule import — otherwise the monkeypatch won't
  reach it. **This preserves the existing seam with zero test changes.**
- **Option B (riskier):** push the proxy loop down per-submodule. Rejected — multiplies the seam across
  9 files and is easy to get subtly wrong (a missed name silently breaks one test's patching).

> **Net effect of Option A:** `today_loaders.py` shrinks from 1750 to a ~60-line hub (imports +
> `_TAB_LABELS` + `__all__`). The 76 functions live in section modules. The proxy loop in `today.py`
> is **unchanged**. Tests are **unchanged**.

### Re-verify the partition before splitting

```bash
# regenerate the exact function list + line ranges:
grep -nE "^(def |async def )" src/web/routers/today_loaders.py
# confirm cross-helper call graph (which helpers call which) so you keep callers+callees consistent:
python /tmp/analyze.py src/web/routers/today_loaders.py <split>   # the script from Round 1
# confirm nothing else imports from today_loaders directly:
grep -rn "today_loaders" src tests   # expect only today.py + tests/test_app.py
```

### Proposed partition (76 funcs → 9 modules by dashboard section)

Boundaries follow the dashboard's own sections. Leaf math/format utils go in a shared `_format` module
that every other section imports (one-directional: sections → format, never reverse — keep it a DAG).

```
src/web/routers/today_loaders.py                 # HUB ~60 lines: re-export *, _TAB_LABELS, __all__
src/web/routers/loaders/_format.py               # leaf utils, NO domain imports:
                                                 #   _to_float _safe_float _safe_diff _safe_pct _safe_sum
                                                 #   _exposure_ratio _to_decimal _split_csv _sentence_join
                                                 #   _is_number _format_pct _format_decimal
                                                 #   _group_latest_by_ticker _normalize_order_status
src/web/routers/loaders/header_system.py         # _build_header _build_job_timeline
                                                 #   _build_system_view _load_llm_usage
                                                 #   _build_overview_command_center  (see DEAD-CODE note)
                                                 #   _normalize_tab _normalize_detail_tab
                                                 #   _normalize_detail_item_index _select_detail_item
                                                 #   _detail_tab_items   (+ define _TAB_LABELS here, hub re-exports)
src/web/routers/loaders/portfolio.py             # _build_portfolio_view _load_positions
                                                 #   _load_recent_closed_positions _load_option_positions
                                                 #   _load_hedge_overlays _load_portfolio_history
                                                 #   _load_portfolio_intents _load_risk_exposures
src/web/routers/loaders/trades.py                # _load_trade_rows _serialize_trade_row
                                                 #   _ensure_trade_rows_include_ticker _load_order_status
                                                 #   _load_trade_detail _latest_trade_decision_id_for_ticker
                                                 #   _merge_audit_detail_into_workspace_detail
                                                 #   _audit_trade_summary
src/web/routers/loaders/candidates.py            # _attach_candidate_summary _build_candidates_summary
                                                 #   _load_candidate_rows _load_manual_requests
                                                 #   _candidate_result_status _candidate_trade_identity
src/web/routers/loaders/risk_macro.py            # _load_latest_macro_snapshot_for_today
                                                 #   _load_latest_preopen_runtime_run_for_today
                                                 #   _load_today_risk_macro _load_live_alerts
                                                 #   _load_material_changes _load_risk_by_ticker
                                                 #   _risk_decision_lookahead_source _risk_applied_rules
                                                 #   _risk_decision_binding_constraint
                                                 #   _load_material_signal_change_tickers
src/web/routers/loaders/universe_learning.py     # _load_relationships _load_peer_baskets _load_themes
                                                 #   _serialize_universe_filter _serialize_reflection
                                                 #   _load_learning_factors _load_strategy_performance
                                                 #   _load_strategy_proposals _load_strategy_definitions
                                                 #   _load_strategy_evaluation_results
src/web/routers/loaders/ticker_detail.py         # _load_signal_history_by_ticker _load_news_by_ticker
                                                 #   _load_fundamentals_by_ticker _timeline_summary_from_signal
                                                 #   _technical_history_items _signal_summary_items
                                                 #   _price_technical_summary _relative_strength_summary
                                                 #   _fundamental_snippets_from_metrics _append_news_snippet
```

> Largest resulting module ≈ ticker_detail / risk_macro at ~250–300 lines — under the guideline. The
> hub stays ~60. Grouping is **not sacred**; the only hard rules are (1) `_format` has no domain
> imports and everyone else may import it, (2) cross-section helper calls go **through the hub** (the
> monkeypatch seam), and (3) the dependency graph stays a DAG.

### Mechanical procedure

1. Create `src/web/routers/loaders/__init__.py` (empty) + the 8 section modules. Each gets
   `from __future__ import annotations`, only the imports its block needs (use `/tmp/imports.py` from
   Round 1 on each line range), then the function bodies **verbatim**.
2. For cross-section calls, import the sibling **from the hub**: inside a section module write
   `from src.web.routers import today_loaders` and call `today_loaders._load_X(...)` — NOT a direct
   `from .portfolio import _load_X`. (This is what keeps the proxy seam working — see CRITICAL SEAM.)
3. Rewrite `today_loaders.py` as the hub: `from src.web.routers.loaders.header_system import *`
   (and the other 7), define/relocate `_TAB_LABELS`, and set `__all__` to the 46 names `today.py`
   imports. **Leave the proxy loop in `today.py` unchanged.**
4. Verify (below). `today.py` and all tests must be untouched.

### Verification

```bash
python -m compileall -q src
python -c "import src.web.routers.today"                       # import smoke
python -c "from src.web.routers.today_loaders import _TAB_LABELS, _build_header, _load_trade_detail"  # tests/test_app.py:35 contract
# public surface of the hub must equal the 46 re-exported names:
python -c "import src.web.routers.today_loaders as m; print(len([n for n in dir(m) if not n.startswith('__')]))"
pytest tests/web/test_today.py tests/test_app.py -q            # the seam-sensitive tests (monkeypatch propagation)
pytest -q                                                       # full gate (author cannot run)
```

> **The monkeypatch tests are the real gate.** `tests/web/test_today.py` patches
> `src.web.routers.today._load_*` and asserts the dashboard uses the fake. If step 2 was done with a
> direct cross-submodule import instead of going through the hub, those tests fail — that failure is
> the signal you broke the seam, not a flaky test.

### 🏷 DEAD-CODE note (flag, do NOT silently delete in this verbatim refactor)

`_build_overview_command_center` exists and `today.py` still builds an `overview` payload, but
`_TAB_LABELS` has **no `"overview"` entry**, so `selected_tab` can never equal `"overview"` — the
`{% elif selected_tab == "overview" %}` branch in `today.html` (lines ~525–724, ~200 lines) is
**unreachable**. This matches the note in `docs/ui-redesign-plan.md` ("没有 Overview tab… 死分支").
Carry `_build_overview_command_center` over verbatim with the others. **Do not delete the dead tab
branch as part of this structural PR** — raise it as a separate follow-up so a reviewer can confirm
`overview` isn't consumed elsewhere (it currently is still passed to the template context and may feed
the header). Mention the line count in the PR description.

---

# PART 2 — Templates: `today.html` (1494) and `research_detail.html` (429)

Jinja has a clean, zero-risk seam that the Python files don't: **`{% include %}`**. Splitting a
template into per-section partials changes **no rendered output** as long as the partials inherit the
same context (Jinja `include` shares the parent context by default).

## `today.html` → per-tab partials

The tab branches are already cleanly delimited (re-verify line numbers — they move):

```
LINES (at 26819d0)   BRANCH
  1–65               header + global tab nav            → stays in today.html
  66–524             {% if selected_tab == "trades" %}  → today/_tab_trades.html      (~459)
 525–724             {% elif ... == "overview" %}        → DEAD branch (see PART 1 note)
 725–933             {% elif ... == "portfolio" %}       → today/_tab_portfolio.html   (~209)
 934–1094            {% elif ... == "risk-macro" %}      → today/_tab_risk_macro.html  (~161)
1095–1331            {% elif ... == "candidates" %}      → today/_tab_candidates.html  (~237)
1332–1494            {% elif ... == "system" %}          → today/_tab_system.html      (~163)
```

**Procedure:**
1. Create `src/templates/today/` and move each branch body **verbatim** into a partial. (Keep the
   `{% if %}/{% elif %}` chain in `today.html`; only the body inside each branch moves.)
2. In `today.html`, replace each branch body with `{% include "today/_tab_trades.html" %}` etc. Jinja
   passes the full parent context to includes automatically, so the partials see the same variables
   (`portfolio`, `risk_macro`, `candidates`, etc.) — no parameter threading needed.
3. **Dead `overview` branch:** keep it (move to `today/_tab_overview.html` and include it) to stay
   verbatim, OR flag for deletion in the PR — same call as the PART 1 dead-code note. Do not silently
   drop it.

**This is the safest split in either round** — no Python, no imports, no name resolution. Output is
byte-identical if context propagation is left at Jinja's default.

**Verification:**
```bash
python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('src/templates')).get_template('today.html')"  # parse/compile all includes
pytest tests/web/test_today.py tests/web/test_today_workspace.py -q   # these assert on rendered HTML
```
The web tests render the template against fixtures and assert on `data-testid`/text — they are the gate
that the includes produce identical markup. If any partial references a variable the parent didn't pass
(shouldn't happen with default context sharing), these catch it.

## `research_detail.html` (429) — optional, lower value

Single `{% block content %}` with a `detail.*` context. Natural partials: the run-metadata card, the
decision card (thesis / key drivers / counterarguments), and the per-section output lists. Same
`{% include %}` procedure. Only importer/renderer is `src/web/routers/research.py`; tests in
`tests/research/` and `tests/web/`. **Do this only if you want strict ≤300 on templates too** — at 429
it's barely over and cohesive. Verify with `pytest tests/research -q` + the research web tests.

---

# PART 3 — `style.css` (1736) — LOWEST priority, do only if strict ≤300 is mandated

**Be honest in the PR: splitting CSS here is low value and carries cascade risk the `.py`/template
splits don't.** Reasons:

- CSS has **no import system**. Splitting means either (a) multiple `<link>` tags in `base.html`
  (load order = cascade order — getting it wrong silently changes specificity/overrides), or (b)
  introducing a build step (SASS/PostCSS `@import` + bundling) — a new toolchain this repo doesn't have.
- The file is referenced **once** (`base.html:7`) and shared by all 4 templates (`watchlist`,
  `research`, `today`, `research_detail` all `extends base.html`). A split must keep the **same
  cascade** for every page.
- The largest region — `/* Today dashboard visual refresh scaffold */` (lines ~499–1639, ~1140 lines)
  — has **almost no internal section comments**, so there are no clean seams to cut along. You'd be
  inventing boundaries, which is exactly where cascade-order regressions hide.

**If you must split** (multi-`<link>` approach, no build step):
1. Cut along the existing top-level comment banners, preserving source order:
   `Layout / Cards / Stats row / Tables / Badges / Forms / Flash / Admin / Detail page / Tabs /
   Sections` → `base.css`; the big `Today dashboard …` block → `today.css`; `Compact risk manager
   subcard` (1639+) → append to `today.css`.
2. In `base.html`, emit the links **in the same order** the rules appear today:
   `<link rel="stylesheet" href="/static/base.css"><link rel="stylesheet" href="/static/today.css">`.
   Order is load-bearing — equal-specificity rules resolve by source order, and today's file relies on
   that. Do **not** reorder.
3. There is **no automated test** for visual CSS. Verification is manual: render every page
   (`/today` all 5 tabs, `/research`, a `research_detail`, `/watchlist`) before and after and diff
   screenshots. **Flag in the PR that this was visually spot-checked, not test-covered** — per the repo
   memory the author cannot run the app, so this verification must be done by the implementer.

**Recommendation:** unless the ≤300 guideline is being enforced strictly on CSS, **leave `style.css`
as-is** and note it as accepted residual. The cost/benefit is the worst of any file in either round.

---

## Global verification (after each PART, and again at the end)

```bash
python -m compileall -q src
python -c "import src.web.routers.today, src.web.routers.research"
python -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('src/templates')); [e.get_template(t) for t in ('today.html','research_detail.html','base.html')]"
pytest -q   # the real gate — author cannot run it
```

## Out of scope (do NOT do here)
- Any logic/query/timezone fixes (see `docs/future-work.md`) — verbatim moves only.
- Deleting the dead `overview` tab branch / `_build_overview_command_center` — flag separately.
- The 300–500-line `.py` band Round 1 marked **LEAVE**, and the `option_strategy_builder.py` /
  `paper_execution_options.py` residuals (covered by Round 1 §"Known residual" if ever pursued).
- The `historical_replay_runs` table (kept intentionally; replay wired up later).
```
