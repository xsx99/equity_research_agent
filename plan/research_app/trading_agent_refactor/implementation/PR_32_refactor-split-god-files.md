# Refactor Handoff: Split the God Files (>300-line modules)

> **Audience:** an implementing coding agent that CAN push to this repo.
> **Author:** analysis agent (code-only environment, cannot run the app/tests or push).
> **Goal:** bring oversized modules toward the team's "≤300 lines per file" guideline by
> splitting them along existing seams. **Pure structural refactor — no behavior change.**
> **Hard rule:** move code **verbatim**. No logic edits, no signature changes, no reordering of
> business logic. Every public name keeps its import path (re-export where needed). If a real
> behavior change looks unavoidable, **stop and flag it in the PR description** instead of proceeding.
>
> **Verified at HEAD `1c01346` ("clean up code").** All line numbers below were accurate at that
> commit — **re-verify each boundary before editing** (re-run the analysis snippets provided).

---

## Why these are safe to split

Every file below is the same shape: **a small public surface (a class or a couple of functions)
plus a long tail of module-level helpers.** Because the helpers are module-level (`def _x(...)`,
no `self`), moving them to a sibling module and importing them back is mechanical and low-risk —
the same technique that the repository mixin split (`refactor-dead-tables-and-repository-split.md`
Part B) used successfully.

The analysis agent already ran a dependency check on PRs A–D (which helpers the public surface
calls back, whether moved helpers call back into the original → **circular-import risk**, and which
external files import the moved symbols). Results are embedded per PR.

---

## Files over 300 lines (verdict per file)

```
LINES  FILE                                              VERDICT
2242   src/db/models/trading.py                          SPLIT  → PR D (package)
2095   src/web/routers/today.py                          SPLIT  → PR C
1584   src/trading/workflows/trading_decision.py         SPLIT  → PR A
1563   src/trading/workflows/paper_execution.py          SPLIT  → PR B
1318   src/web/presenters/today_workspace.py             SPLIT  → PR E
 791   src/trading/runtime/smoke_fixture_modes.py        defer  (test/smoke fixtures, cohesive)
 750   src/trading/signals/source_ingestion.py           optional (later)
 721   src/trading/repositories/_base.py                 LEAVE  (intentional shared-import hub from the mixin split)
 672   src/trading/strategies/matching.py                optional (later)
 630   src/trading/runtime/preopen_risk.py               optional (later)
 623   src/providers/news_data/helpers.py                optional (later)
 609   src/trading/strategies/catalog.py                 LEAVE  (cohesive data catalog; splitting hurts readability)
 558   src/trading/intraday/rebalance.py                 optional (later)
 536   src/providers/market_data/alpaca_provider.py      LEAVE  (single provider class)
 513   src/trading/risk/manager.py                       optional (later)
 ...   (~22 more files in the 300–500 band)              LEAVE for now
```

> **Scope decision:** The 300-line rule is a *guideline*. This handoff targets the **5 true God
> files** (1300–2300 lines) — that is where the cost actually concentrates. Files in the 300–500
> band are mostly single cohesive units (one provider class, one data catalog); splitting them
> yields little and risks churn. Do PRs A–E first. A follow-up pass on the 500–800 band can come
> later if the team still wants strict ≤300 everywhere — see "Known residual" at the end.

**Do each PR independently and in this order (A→E). A–C are the safest; D is the riskiest.**

---

## Re-verification snippet (run before each PR)

Use these helper scripts to re-confirm boundaries on the current HEAD. Save them once:

```python
# /tmp/analyze.py  — names moved, names to import back, circular-call check
import ast, re, sys
path, split = sys.argv[1], int(sys.argv[2])
src = open(path).read(); lines = src.splitlines(); tree = ast.parse(src)
moved, stay = {}, {}
for n in tree.body:
    if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
        (moved if n.lineno>=split else stay)[n.name]=(n.lineno,n.end_lineno)
stay_src="\n".join(lines[:split-1]); moved_src="\n".join(lines[split-1:])
print("MOVED:",len(moved)); print(sorted(moved))
print("IMPORT BACK (moved names used in stay region):",
      sorted(n for n in moved if re.search(r'\b'+n+r'\b',stay_src)))
print("CIRCULAR (stay funcs called from moved region — must be empty):",
      sorted(n for n in stay if re.search(r'\b'+n+r'\b',moved_src)))
```

```python
# /tmp/imports.py — which module imports the moved block needs
import ast, re, sys
path, split = sys.argv[1], int(sys.argv[2])
src=open(path).read(); lines=src.splitlines(); tree=ast.parse(src)
imp={}
for n in tree.body:
    if isinstance(n,ast.Import):
        for a in n.names: imp[a.asname or a.name.split(".")[0]]=ast.get_source_segment(src,n)
    elif isinstance(n,ast.ImportFrom):
        for a in n.names: imp[a.asname or a.name]=f"from {n.module} import {a.name}"
moved="\n".join(lines[split-1:])
for k,v in imp.items():
    if re.search(r'\b'+re.escape(k)+r'\b',moved): print(f"{k:42s} {v}")
```

Then the **mechanical procedure** for A/B/C/E (function-tail extraction):

1. Create the new sibling module: docstring, `from __future__ import annotations`, the imports its
   block needs (from `/tmp/imports.py`), then the moved function bodies **verbatim**.
2. In the original: delete the moved block; add `from <new module> import (<the IMPORT-BACK names>)`
   in the import section so the public surface still resolves the helpers.
3. Fix any **external** files that imported a moved symbol (listed per PR) to point at the new module.
4. Verify (per-PR commands below). The public API of the original module must be unchanged.

---

# PR A — `trading_decision.py` (1584 → ~616 + ~999)

**Split line:** `610` (first helper `_render_news_source_text`). The class
`TradingDecisionPipeline` and the two dataclasses (lines 1–607) **stay**.

**New module:** `src/trading/workflows/option_strategy_builder.py`

**Move (36 module-level helpers, verbatim):** everything from line 610 to EOF —
`_render_news_source_text`, `_classification_instrument_type`, `_resolve_expression_fallback_plan`,
`_decision_action_for_expression`, the full `_build_option_strategy_payload(s)` family,
`_choose_option_strategy_type`, `_expression_*` policy helpers, `_option_*` (days/profit/leg/chain/
roll/close/assignment) helpers, `_select_option_chain_legs`, `_flatten_option_chain_contracts`,
`_serialize_option_strategy_payload`, `_news_evidence_limit`, `_evidence_priority`,
`_round_nested_floats`, etc. **Circular check: 0 (none of these call back into the class). ✅**

**New module imports** (verbatim from the original; do **not** import `field` — it's a loop var):
```python
import os
import uuid
from datetime import datetime, timedelta
from typing import Any
from src.trading.options.strategy import (
    OptionLegDefinition, OptionStrategyDecisionInput, OptionStrategyDecisionRecord, OptionsStrategyLayer,
)
from src.trading.signals import SignalSnapshotResult
from src.trading.signals.sources import EventNewsItemRecord, SourceRecord
from src.trading.strategies.classifier import TradeClassificationRecord
from src.trading.strategies.matching import CandidateScoreRecord, StrategyDefinitionRecord
```

**Import back into `trading_decision.py` (7 — referenced by the pipeline class):**
```python
from src.trading.workflows.option_strategy_builder import (
    _build_option_strategy_payloads, _classification_instrument_type, _evidence_priority,
    _news_evidence_limit, _render_news_source_text, _resolve_expression_fallback_plan,
    _round_nested_floats,
)
```
Do **not** remove any imports from `trading_decision.py` — all of them are still used by the class.

**⚠ External call site to fix — REQUIRED:** `src/trading/runtime/preopen_risk.py` (~line 510) does a
local import:
```python
from src.trading.workflows.trading_decision import (_build_option_strategy_payload, _decision_action_for_expression)
```
Both names move to the new module. **Repoint it:**
```python
from src.trading.workflows.option_strategy_builder import (_build_option_strategy_payload, _decision_action_for_expression)
```

**No other file** imports a moved private symbol (all other `trading_decision` importers use the
public `TradingDecisionRecord` / `TradingDecisionPipeline` / `TradingDecisionPipelineResult`, which stay).

---

# PR B — `paper_execution.py` (1563 → ~733 + ~869)

**Split line:** `722` (first helper `_hedge_trading_decision_from_generated_action`). The class
`PaperExecutionWorkflow` (1–719) **stays**.

**New module:** `src/trading/workflows/paper_execution_options.py`

**Move (23 helpers, verbatim):** the `_hedge_*` decision/action builders,
`_generated_hedge_option_strategy_payload`, `_matching_open_option_position`, the
`_build/_open/_close_option_order_request` family, `_paper_option_*_legs_*`, `_broker_leg_refs_*`,
`_option_contract_symbol_from_payload`, `_risk_hedge_option_strategy_type`,
`_materialized_option_positions`, the `_build_execution_fallback_*` family,
`_option_decision_from_trading_decision`, `_fallback_option_strategy_payload`,
`_remaining_fallback_expression_bucket_ids`. **Circular check: 0. ✅**

**New module imports:**
```python
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from src.trading.brokers.paper_option import (PaperOptionOrderLeg, PaperOptionOrderRequest, PaperOptionPosition)
from src.trading.options.strategy import OptionStrategyDecisionRecord
from src.trading.risk import (OptionLegRiskInput, OptionRiskInput, RiskDecisionRecord, TradeRiskRequest)
from src.trading.workflows.trading_decision import TradingDecisionRecord
```

**Import back into `paper_execution.py` (12 — referenced by the workflow class):**
```python
from src.trading.workflows.paper_execution_options import (
    _build_execution_fallback_option_risk_input, _build_execution_fallback_option_trade_risk_request,
    _build_execution_fallback_trade_risk_request, _build_option_order_request,
    _fallback_option_strategy_payload, _hedge_risk_decision_from_generated_action,
    _hedge_trading_decision_from_generated_action, _matching_open_option_position,
    _materialized_option_positions, _option_decision_from_trading_decision,
    _remaining_fallback_expression_bucket_ids, _risk_hedge_option_strategy_type,
)
```

**External call sites:** none — no other file imports a moved private symbol. ✅

---

# PR C — `today.py` router (2095 → ~450 + ~1756)

**Split line:** `413` (first helper `_build_header`). The router stays: `init`, the 4 `@router`
handlers, the orchestrator `load_today_dashboard`, and `create_manual_request` /
`dismiss_manual_request` / `update_universe_filter` (lines 1–412).

**New module:** `src/web/routers/today_loaders.py`

**Move (76 helpers, verbatim):** all `_load_*`, `_build_*`, `_serialize_*`, `_normalize_*`, plus the
small math/format utils (`_safe_*`, `_to_float`, `_to_decimal`, `_is_number`, `_format_*`,
`_split_csv`, `_sentence_join`, `_group_latest_by_ticker`, `_risk_*`, `_timeline_summary_from_signal`,
`_technical_history_items`, `_signal_summary_items`, etc.) — everything from line 413 to EOF.
**Circular check: 0. ✅**

**⚠ Module global to relocate:** `_TAB_LABELS` (defined lines 78–84) is used by **both** a stayed
function (`load_today_dashboard`, ~line 351) **and** a moved one (`_normalize_tab`, ~line 1448).
**Move the `_TAB_LABELS` definition into `today_loaders.py`** and import it back into `today.py`
(keeps the dependency one-directional: router → loaders, never the reverse, so no import cycle).

**New module imports** (subset actually used by the moved block — verbatim forms):
```python
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from sqlalchemy.orm import Session as SQLAlchemySession
from src.db.models.trading import (  # only the models the helpers touch:
    CandidateOutcomeEvaluation, CandidateScore, DailyReflection, EventNewsItem, IntradaySignalSnapshot,
    LearningFactor, LlmUsageEvent, NewsAlert, PaperOrder, PaperOptionOrder, PaperOptionPosition,
    PaperPosition, PeerBasket, PortfolioIntent, PortfolioRiskSnapshot, PortfolioSnapshot, RiskDecision,
    RiskFactorExposure, RiskHedgeDecision, SignalSnapshot, StrategyDefinition, StrategyEvaluationResult,
    StrategyProposal, ThemeTaxonomy, TickerRelationship, TradingDecision, UniverseFilterConfig,
)
from src.trading.repositories.sqlalchemy import SqlAlchemyTradingRepository
from src.web.presenters.signal_evidence import signal_groups
from src.web.presenters.today_copy import (
    candidate_result_label, generic_status_label, intent_type_label, live_status_label,
    macro_regime_label, manual_request_mode_label, manual_request_status_label,
    option_strategy_type_label, risk_appetite_label, runtime_mode_label, scope_label,
    strategy_label, trade_identity_label,
)
from src.web.presenters.today_portfolio_analytics import build_portfolio_analytics
from src.web.presenters.today_risk_macro import build_today_risk_macro_payload
```

**Import back into `today.py` (45 helpers + `_TAB_LABELS`)** — the orchestrator/handlers reference
exactly these 45 moved functions. Re-run `/tmp/analyze.py src/web/routers/today.py 413` to regenerate
the exact list, then `from src.web.routers.today_loaders import (...)` them, plus `_TAB_LABELS`.

**⚠ Tests import private helpers from the router (REQUIRED — all must keep resolving):**
`tests/web/test_today.py` does `from src.web.routers.today import _build_header`,
`_load_signal_history_by_ticker`, `_load_trade_detail`, `_load_candidate_rows`, `_load_manual_requests`,
`_load_recent_closed_positions`, `_load_fundamentals_by_ticker`, `_load_news_by_ticker`,
`_load_strategy_performance` (plus public `load_today_dashboard`, `create_manual_request`,
`dismiss_manual_request`). **All 9 private names are in the 45-name import-back set**, so the router
re-exports them and the tests keep working **unchanged** — do not skip any of the 45.

Sanity gate (must print `NONE`):
```python
# after the split, confirm every moved name referenced in today.py is imported back or still defined
```
(use the verify logic the analysis agent ran; the expected output is "MISSING: NONE", "test privates: NONE").

---

# PR D — `db/models/trading.py` → package (RISKIEST — do last, review hard)

**Why riskier:** SQLAlchemy mapper config errors surface only at import/runtime, not at parse time.
But the analysis is favorable:

**Verified facts (HEAD 1c01346):**
- 79 classes = **26 `ChoiceEnum` enums** (lines 26–185) + **53 `Base` models** (lines 188–2242).
- **0 module-level helper functions / assignments** (besides the enums).
- `Base` and `ChoiceEnum` are **imported** (`from .base import Base, ChoiceEnum`) — not defined here.
- **Every `relationship(...)` uses a string target; every `ForeignKey(...)` uses a `"table.col"`
  string.** (verified: `grep -nE "relationship\(\s*[A-Z]"` and `ForeignKey\(\s*[A-Z]` → no hits.)
- **No model references a sibling model class by a bare Python name** (verified via AST `Name`-node
  scan — all model→model links are inside relationship strings, resolved by the registry).
- 25 of 53 models reference enums by bare name; enums depend only on `ChoiceEnum`.

**Consequence:** a domain partition needs **no cross-model imports** — each model module needs only
`from .base import Base`, the sqlalchemy types, and the enums it uses. This is the key safety property.

**Target layout** — convert the module into a package (preserve the import path
`from src.db.models.trading import X`):
```
src/db/models/trading/
    __init__.py          # re-exports EVERYTHING (see below) — keeps the public surface byte-identical
    enums.py             # all 26 ChoiceEnum classes (depend only on .base.ChoiceEnum)
    strategy.py          # StrategyDefinition, StrategyProposal, StrategyEvaluationResult, StrategyRun,
                         #   CandidateScore, WatchCandidate, TradeClassification
    llm.py               # LlmPromptTemplate, LlmPromptRun, LlmUsageEvent
    signals.py           # SignalSnapshot, EventNewsItem, SocialMacroItem, FundamentalSnapshot,
                         #   SourceIngestionRun, ProviderRequestRun
    macro_calendar.py    # MacroSnapshot, CalendarEvent, PortfolioEventRiskAssessment
    risk.py              # PositionSizingDecision, PortfolioRiskSnapshot, PortfolioRiskIntent,
                         #   RiskFactorExposure, RiskDecision, OptionRiskSnapshot, RiskHedgeDecision
    execution.py         # TradingDecision, PaperOrder, PaperExecution, PaperPosition, PortfolioSnapshot,
                         #   OptionStrategyDecision, OptionStrategyLeg, PaperOption{Order,Execution,Position}
    intraday.py          # IntradaySignalScan, IntradaySignalSnapshot, NewsAlert, IntradayRebalanceDecision
    reflection.py        # HistoricalReplayRun, CandidateOutcomeEvaluation, DailyReflection, LearningFactor
    universe.py          # PortfolioIntent, TickerRelationship, PeerBasket, ThemeTaxonomy,
                         #   UniverseFilterConfig, UniverseSnapshot, UniverseSymbol, ManualTickerRequest,
                         #   TradingRuntimeRun
```
(Grouping is **not sacred** — keep relationship-string targets within the same `Base` registry, which
they already are. Any partition works as long as `__init__.py` imports all submodules.)

**Each model submodule header (copy verbatim, prune unused later):**
```python
"""<domain> ORM models."""
import uuid
from sqlalchemy import (Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index,
                        Integer, Numeric, String, Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from src.db.models.trading.base import Base    # NOTE: see migration step below for .base location
from src.db.models.trading.enums import *       # enums are cheap; import-* avoids per-model pruning
```

> **`.base` path caveat:** the current file imports `from .base import Base, ChoiceEnum` where `.base`
> is `src/db/models/base.py`. After converting `trading.py` → `trading/` package, a submodule's
> `.base` would resolve to `src/db/models/trading/base.py` (wrong). Use the **absolute** path
> `from src.db.models.base import Base, ChoiceEnum` in `enums.py` and every submodule. Do **not**
> create a `trading/base.py`.

**`trading/__init__.py` — preserve the exact public surface.** The simplest correct approach:
```python
from src.db.models.trading.enums import *      # all 26 enums
from src.db.models.trading.strategy import *
from src.db.models.trading.llm import *
from src.db.models.trading.signals import *
from src.db.models.trading.macro_calendar import *
from src.db.models.trading.risk import *
from src.db.models.trading.execution import *
from src.db.models.trading.intraday import *
from src.db.models.trading.reflection import *
from src.db.models.trading.universe import *
```
Importing all submodules here guarantees every mapped class is registered before first use (critical
for string-relationship resolution). **Then verify the public surface is unchanged** (snippet below).

**Critical verifications for PR D (run all):**
```bash
# 1. Public surface of the package == old module's surface (MUST be empty diff):
#    capture BEFORE on main:  python -c "import src.db.models.trading as m; print('\n'.join(sorted(d for d in dir(m) if not d.startswith('_'))))" > /tmp/before.txt
#    capture AFTER on branch: same command > /tmp/after.txt ; diff /tmp/before.txt /tmp/after.txt
# 2. Mappers configure (catches broken string relationships across modules):
python -c "import src.db.models; from sqlalchemy.orm import configure_mappers; configure_mappers(); print('mappers OK')"
# 3. The package re-exports everything src/db/models/__init__.py pulls (that list is the contract):
python -c "import src.db.models"   # will ImportError if any name in models/__init__.py is missing
# 4. Alembic still sees all tables / metadata is complete:
python -c "from src.db.models.base import Base; print(len(Base.metadata.tables), 'tables')"   # compare to pre-split count
# 5. Model tests:
pytest tests/db/test_trading_models.py -q
```
> `src/db/models/__init__.py` imports ~80 names from `src.db.models.trading` and re-exports them via
> `__all__` — that file is the public contract. It needs **no change** if `trading/__init__.py`
> re-exports the same names. Confirm with verification #3.

> Migrations under `alembic/versions/*` reference tables by **string name** only (not by importing
> these classes), so they are unaffected. Double-check with
> `grep -rl "from src.db.models.trading import" alembic` (expect none).

---

# PR E — `today_workspace.py` presenter (1318 → ~3 modules)

**Public surface:** exactly **one** exported function — `build_ticker_workspace` (line 38). The only
importers are `src/web/routers/today.py` and `tests/web/test_today_workspace.py`, both importing just
`build_ticker_workspace`. This gives maximum freedom; only that name must keep its path.

**Suggested split** (group the ~60 private helpers + module globals by concern):
```
src/web/presenters/today_workspace.py            # keeps build_ticker_workspace + item bucketing
                                                 #   (_build_ticker_items, _group_rows_by_ticker,
                                                 #    _item_priority, _attention_flags, _card_*, ...)
src/web/presenters/today_workspace_detail.py     # _build_detail, _build_signal_summary,
                                                 #   _build_technical_charts, _build_snippets,
                                                 #   _build_event_news_summary, news/recency helpers,
                                                 #   _TECHNICAL_CHART_SPECS, _SIGNAL_GROUP_ORDER, _NEWS_* consts
src/web/presenters/today_workspace_timeline.py   # _build_timeline, _build_signal_timeline_events,
                                                 #   _history_card_*, _timeline_* , _build_lifecycle,
                                                 #   _build_decision_list, _build_risk_history
src/web/presenters/today_workspace_format.py     # leaf utils: _format_*, _parse_timestamp,
                                                 #   _normalize_datetime, _sort_key*, _empty_*,
                                                 #   _humanize_label, _with_terminal_period, _truncate_*
```
**Procedure:** same as A/B/C. Run `/tmp/analyze.py` to find the import-back set and **check the
circular column** — these helper groups call each other more than the workflow files do, so you may
need a small shared `today_workspace_format.py` that the other two import from (one-directional:
detail/timeline → format, never the reverse). If `/tmp/analyze.py` shows a back-call from format into
detail/timeline, move that function down into `format` too. Keep the dependency graph a DAG.

Move module-level constants (`_ACTIONABLE_DECISIONS`, `_ACTIONABLE_ORDER_STATUSES`, `_EMPTY_MARKER`,
`_NO_MATERIAL_TICKER_NEWS`, `_NEWS_SUMMARY_MAX_CHARS`, `_TECHNICAL_CHART_SPECS`, `_SIGNAL_GROUP_ORDER`)
into whichever module uses them; import back if `build_ticker_workspace` also uses them.

**Verify:** `python -c "from src.web.presenters.today_workspace import build_ticker_workspace"` and
`pytest tests/web/test_today_workspace.py -q`.

---

## Global verification (after each PR, and again at the end)

```bash
# byte-compile everything (cheap structural gate):
python -m compileall -q src

# import smoke for the touched entrypoints:
python -c "import src.web.routers.today, src.trading.workflows.trading_decision, src.trading.workflows.paper_execution, src.web.presenters.today_workspace, src.db.models"

# full suite (the real gate — author cannot run it):
pytest -q
```

For the function-tail PRs (A/B/C/E), the **public surface must be byte-for-byte identical**. Capture
`dir(module)` before and after and diff, exactly as the repository-split PR did.

---

## Known residual (be honest in the PR descriptions)

The extracted helper modules are **still over 300 lines** — this halves the God files but does not by
itself satisfy strict ≤300:
- `option_strategy_builder.py` ≈ **999** lines (36 cohesive option helpers).
- `paper_execution_options.py` ≈ **869** lines.
- `today_loaders.py` ≈ **1756** lines (76 loaders — by far the biggest residual).

These are cohesive, so a second pass is optional. If strict ≤300 is required, the natural second-pass
cuts are: split `today_loaders.py` by dashboard section (portfolio / trades / candidates / risk-macro /
strategy-learning / ticker-detail loaders), and split `option_strategy_builder.py` into
`option_policy.py` (the `_expression_*` policy helpers) + `option_chain.py` (chain/leg selection) +
the orchestration core. **Do this only after A–E land and tests are green** — chaining two structural
refactors before verifying the first multiplies risk. State the residual line counts in each PR so
reviewers know ≤300 is not yet met.

## Out of scope (do NOT do here)
- Any logic/timezone/query fixes (see `docs/future-work.md`) — verbatim moves only.
- Touching the 300–500-line band files marked LEAVE.
- The `historical_replay_runs` table (kept intentionally; replay to be wired up later).
