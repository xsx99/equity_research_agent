# Plan: Wire the four live trading pipelines end-to-end

**Audience:** coding agent. **Status:** ready to implement. **Do not change behavior beyond what each task specifies.**

## Background / what is already true (verified)

The trading V2 modules, persistence, and scheduler jobs are built. The *only* things preventing the
daily/manual/intraday/post-close chains from running "for real" are a small set of wiring gaps:

1. Every live runner already accepts an execution policy, but the scheduler entry point drops it.
   - `src/trading/runtime/preopen.py::run_live_preopen_once(*, execute_paper_orders=False, execute_paper_option_orders=False, ...)` ✅ accepts policy
   - `src/trading/runtime/intraday_refresh.py::run_live_intraday_refresh_once(*, execute_paper_orders=False, execute_paper_option_orders=False, ...)` ✅ accepts policy
   - `src/trading/runtime/manual_review.py::run_live_manual_review_once(*, execute_paper_orders=False, ...)` ✅ accepts policy (no option flag)
   - `src/trading/runtime/facade.py::run_job_phase(phase)` ❌ takes no policy and calls the handler with `()`
   - The 5 jobs call `run_job_phase("preopen")` etc. ❌ with no policy
   - `LivePreopenRuntime._run_execution` already does the right thing: returns dry-run report when
     `execute_paper_orders` is false, else calls `PaperExecutionWorkflow.run(...)`.
2. Cold start crashes: `SqlAlchemyTradingRepository.load_active_universe_filter_config()`
   (`src/trading/repositories/sqlalchemy.py:132`) raises `RuntimeError("active_universe_filter_config_not_found")`
   at line 139 when `universe_filter_configs` has no active row. Nothing seeds it (only the
   `universe_signal_db_write` smoke fixture inserts one). `seed_initial_strategy_definitions` IS called at
   `src/trading/runtime/preopen_dependencies.py:129`, but there is no equivalent universe seed.
3. Reflection produces `learning_factors` and persists them, but no preopen/risk code ever reads them, so
   the "auto-reflect → influence tomorrow" loop is open. (`save_learning_factor` exists at
   `repositories/sqlalchemy.py:576`; there is **no** `load_active_learning_factors` method yet.)
4. The research watchlist (`watchlists` table) is disconnected from the trading universe. The
   `selection_source="watchlist_pin"` enum value is defined but never assigned anywhere.

**Product decisions already made (do not re-ask):**
- Paper-order execution should be **ON by default** (`TRADING_EXECUTE_PAPER_ORDERS` default `true`), but
  must stay configurable so it can be switched back to dry-run.
- Option-order execution stays **OFF by default**.
- Strategy evolution stays **fully automatic** — no human approval gate.

---

## P0 — Make the execution chain actually trade (single PR)

### Task P0.1 — Add execution-policy config
File: `src/core/config.py` (near the existing `TRADING_*` block around line 51-56).

Add:
```python
def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "y")

TRADING_EXECUTE_PAPER_ORDERS = _env_bool("TRADING_EXECUTE_PAPER_ORDERS", True)
TRADING_EXECUTE_PAPER_OPTION_ORDERS = _env_bool("TRADING_EXECUTE_PAPER_OPTION_ORDERS", False)
```
If a `_env_bool` style helper already exists in the file, reuse it instead of redefining.

### Task P0.2 — Thread policy through the facade + dispatch
File: `src/trading/runtime/facade.py`
- Change `run_job_phase` to accept and forward an execution policy:
```python
def run_job_phase(
    phase: str,
    *,
    execute_paper_orders: bool | None = None,
    execute_paper_option_orders: bool | None = None,
) -> dict[str, Any]:
    """Run one scheduler-facing trading phase."""
    return dispatch.get_job_phase_handler(phase)(
        execute_paper_orders=execute_paper_orders,
        execute_paper_option_orders=execute_paper_option_orders,
    )
```

File: `src/trading/runtime/dispatch.py`
- `get_job_phase_handler` returns a zero-arg `RuntimeHandler` today. The post-close handlers
  (`reflection`, `strategy_evolution`) do **not** accept execution kwargs; `manual_review` accepts only
  `execute_paper_orders`. So filter kwargs by the handler's real signature instead of passing blindly.
- Replace the direct call path so `run_job_phase` can hand kwargs to dispatch and dispatch drops the ones a
  handler doesn't support. Recommended implementation:
```python
import inspect

def get_job_phase_handler(phase: str) -> RuntimeHandler:
    try:
        handler = JOB_PHASE_HANDLERS[phase]
    except KeyError as exc:
        raise ValueError(f"unsupported_trading_job_phase:{phase}") from exc

    params = inspect.signature(handler).parameters

    def _invoke(**policy: Any) -> dict[str, Any]:
        # only forward kwargs the handler actually accepts, and only when not None
        kwargs = {k: v for k, v in policy.items() if k in params and v is not None}
        return handler(**kwargs)

    return _invoke
```
- Keep `RuntimeHandler` type as `Callable[..., dict[str, Any]]`.

### Task P0.3 — Have the jobs pass the configured policy
Files:
- `src/scheduler/jobs/trading_preopen_job.py`
- `src/scheduler/jobs/intraday_signal_refresh_job.py`
- `src/scheduler/jobs/manual_ticker_review_job.py`

In each `run()`, replace `run_job_phase("<phase>")` with:
```python
from src.core import config as app_config
...
result = run_job_phase(
    "<phase>",
    execute_paper_orders=app_config.TRADING_EXECUTE_PAPER_ORDERS,
    execute_paper_option_orders=app_config.TRADING_EXECUTE_PAPER_OPTION_ORDERS,
)
```
- `manual_ticker_review_job` may pass only `execute_paper_orders` (the handler ignores the option flag, but
  the dispatch filter in P0.2 also makes passing both harmless — either is fine; prefer passing both for
  uniformity since dispatch filters).
- **Do NOT** modify `trading_reflection_job.py` or `strategy_evolution_job.py` — leave them as
  `run_job_phase("reflection")` / `run_job_phase("strategy_evolution")` (no execution policy).

### Task P0.4 — Seed a default universe filter config (cold-start fix)
File: `src/trading/runtime/support.py` — add alongside `seed_initial_strategy_definitions`:
```python
def seed_default_universe_filter_config(session: Any) -> None:
    """Insert a permissive active universe filter profile when none exists."""
    from src.db.models.trading import UniverseFilterConfig as UniverseFilterConfigModel
    existing = (
        session.query(UniverseFilterConfigModel)
        .filter(UniverseFilterConfigModel.is_active.is_(True))
        .first()
    )
    if existing is not None:
        return
    session.add(
        UniverseFilterConfigModel(
            profile_name="default",
            version=1,
            is_active=True,
            min_price=5,
            min_avg_dollar_volume=10_000_000,
            included_sectors_json=[],
            excluded_sectors_json=[],
            included_industries_json=[],
            excluded_industries_json=[],
            exchanges_json=[],
            asset_types_json=[],
            manual_include_json=[],
            manual_exclude_json=[],
        )
    )
    session.flush()
```
- Column names/types verified against `src/db/models/trading.py:576` (`UniverseFilterConfig`).
- Pick conservative thresholds; `min_price` and `min_avg_dollar_volume` are `nullable=False` so they must
  be set. Empty `*_json` lists = no sector/industry/exchange restriction.

File: `src/trading/runtime/preopen_dependencies.py` (~line 128-129) — call it right where the strategy
catalog is seeded, so all phases that build preopen deps (preopen, manual_review, intraday all reuse this)
get the bootstrap:
```python
trading_repository = SqlAlchemyTradingRepository(session)
seed_initial_strategy_definitions(trading_repository)
seed_default_universe_filter_config(session)   # <-- add
```
- Import `seed_default_universe_filter_config` from `src.trading.runtime.support` next to the existing
  `seed_initial_strategy_definitions` import (line 13).

### P0 acceptance criteria
- On a fresh database, `run_job_phase("preopen", execute_paper_orders=False)` runs without raising
  `active_universe_filter_config_not_found`.
- With `TRADING_EXECUTE_PAPER_ORDERS=true`, running the preopen / intraday / manual phases submits paper
  orders to Alpaca paper and writes rows to `paper_orders`, `paper_executions`, `portfolio_snapshots`; the
  runtime report `execution.mode == "execute"`.
- With `TRADING_EXECUTE_PAPER_ORDERS=false`, no orders are submitted and `execution.mode == "dry_run"`,
  while decision/candidate/risk rows are still persisted (unchanged from today).
- `reflection` and `strategy_evolution` phases behave exactly as before.

### P0 tests
- Add a dispatch unit test: `run_job_phase("reflection", execute_paper_orders=True)` must NOT raise and must
  call the reflection handler with no execution kwargs (assert via a stub handler / signature filtering).
- Add a job test asserting each of the 3 trading jobs forwards `app_config.TRADING_EXECUTE_PAPER_ORDERS`
  (monkeypatch `run_job_phase` and assert kwargs).
- Add a `seed_default_universe_filter_config` test: empty DB → one active row; idempotent on second call.

---

## P1 — Close the reflection feedback loop (single PR)

Goal: yesterday's `learning_factors` actually influence today's matching / sizing — not just sit in the DB
as audit rows.

**Verified `effect_tags` vocabulary** (from `src/trading/post_close/reflection.py:13-28`, exhaustive today):
- `_RISK_TIGHTENING_EFFECT_TAGS = {reduce_exposure, require_confirmation, block_stale_data, lower_confidence, tighten_exit_rules}`
- `_EXPANSIONARY_EFFECT_TAGS = {increase_score, expand_eligibility, increase_size, weaken_safety_rails, broaden_universe, increase_risk_budget}`

**Verified `LearningFactorRecord`** (`reflection.py:90-110`) fields the application layer can use:
`factor_key, trade_date, factor_type, scope, status, strategy_id, condition, recommendation, confidence,
activation_policy, effect_tags: tuple[str, ...], source_daily_reflection_id, metadata_json`.
- `scope` values seen: `strategy | portfolio | trade | watchlist | risk` (per `LearningFactor` ORM CHECK).
- `status` lifecycle: `candidate | observation | shadow | active | suppressed | retired`.

### Task P1.1 — Repository: load active learning factors
File: `src/trading/repositories/sqlalchemy.py`
- There is **no** load method today — only `save_learning_factor` (line 576) and the
  `_learning_factor_record(row)` mapper (line 2310). Add a loader that reuses the mapper:
```python
def load_active_learning_factors(self) -> list[LearningFactorRecord]:
    rows = (
        self.session.query(LearningFactor)
        .filter(LearningFactor.status.in_(("active", "shadow")))
        .all()
    )
    return [_learning_factor_record(row) for row in rows]
```
- `LearningFactor` ORM is already imported in this module (used by `save_learning_factor`). Confirm import of
  `LearningFactorRecord` (it is the return type of the existing mapper, so already imported).
- Semantics to preserve downstream: `active` → apply effect; `shadow` → load but **do not apply** (observe
  + log only). The application layer (P1.2), not this method, enforces that split.

### Task P1.2 — Learning-factor application layer
New file: `src/trading/learning/apply.py`
- Pure, dependency-free. Define:
```python
@dataclass(frozen=True)
class LearningAdjustments:
    # multiplicative score deltas keyed by strategy_id (applied in the matcher)
    strategy_score_multiplier: dict[str, float]   # default 1.0
    # global multiplier applied to macro_risk_budget_multiplier before RiskConfigResolver.resolve()
    risk_budget_multiplier: float                 # default 1.0
    applied_factor_keys: tuple[str, ...]
    shadow_factor_keys: tuple[str, ...]           # loaded but not applied (logged)

def build_learning_adjustments(factors: Iterable[LearningFactorRecord]) -> LearningAdjustments: ...
```
- Mapping rules (conservative; unknown tags = no-op):
  - Only factors with `status == "active"` contribute; `status == "shadow"` go to `shadow_factor_keys` only.
  - `scope == "strategy"` + `strategy_id` set:
    - `increase_score` → `strategy_score_multiplier[sid] *= 1.10` (cap product at 1.25)
    - (no explicit `decrease_score` tag exists; treat risk-tightening factors as portfolio-level below)
  - `scope in {"risk","portfolio"}`:
    - any tag in `_RISK_TIGHTENING_EFFECT_TAGS` (e.g. `reduce_exposure`) → `risk_budget_multiplier *= 0.85`
    - `increase_risk_budget` → `risk_budget_multiplier *= 1.10`
  - Clamp `risk_budget_multiplier` to `[0.5, 1.25]` (downstream resolver re-clamps to `[0.25, 1.25]`).
  - Do NOT implement `broaden_universe`/`expand_eligibility`/`weaken_safety_rails` effects in this PR — log
    them as recognized-but-not-applied so we don't silently relax safety rails. Note this in `log()`/comments.

### Task P1.3 — Inject adjustments (matcher + risk)
**3a. Build adjustments in preopen deps.** File: `src/trading/runtime/preopen_dependencies.py` (~line 128, right
after `trading_repository`/seeds):
```python
from src.trading.learning.apply import build_learning_adjustments
...
learning_adjustments = build_learning_adjustments(
    trading_repository.load_active_learning_factors()
)
```

**3b. Matcher score injection.** File: `src/trading/strategies/matching.py`
- `StrategyMatcher` is constructed arg-less today. Add an optional ctor param:
```python
def __init__(self, *, learning_adjustments: "LearningAdjustments | None" = None) -> None:
    self._learning_adjustments = learning_adjustments
```
- Scores are already post-processed at lines **153-154** via `_apply_insider_modifier(score, snapshot)` and
  `_apply_social_macro_modifier(score, snapshot)` (each returns `_clamp(score + delta)`). Add one more line
  immediately after:
```python
score = self._apply_learning_factor_modifier(score, definition)
```
  with a method mirroring `_apply_insider_modifier` (matching.py:630):
```python
def _apply_learning_factor_modifier(self, score: float, definition: StrategyDefinitionRecord) -> float:
    adj = self._learning_adjustments
    if adj is None:
        return score
    mult = adj.strategy_score_multiplier.get(definition.strategy_id, 1.0)
    return _clamp(score * mult)
```
- Wire it through `StrategyPipeline`. File: `src/trading/workflows/strategy_scoring.py` — the pipeline already
  accepts `matcher: StrategyMatcher | None`. In `preopen_dependencies.py` pass the configured matcher:
```python
strategy_pipeline=StrategyPipeline(
    repository=trading_repository,
    manual_request_service=manual_request_service,
    matcher=StrategyMatcher(learning_adjustments=learning_adjustments),
),
```

**3c. Risk budget injection.** File: `src/trading/runtime/preopen_risk.py` — at line **67** the resolver is
called with `macro_risk_budget_multiplier=float(getattr(macro_snapshot, "risk_budget_multiplier", 1.0) or 1.0)`.
Multiply that value by `learning_adjustments.risk_budget_multiplier` before passing in. `_LiveRiskWorkflow`
must receive the adjustments — add an optional ctor field and set it where `_LiveRiskWorkflow(...)` is built
in `preopen_dependencies.py`. `RiskConfigResolver.resolve` already re-clamps to `[0.25, 1.25]`
(`risk/config.py:92`), so this is safe.
- (Out of scope this PR: the two `resolve()` calls in `workflows/paper_execution.py:444,467` for
  execution-time re-sizing — leave unchanged; note the asymmetry in the PR description.)

- Keep every injection optional/defaulted (`None`/`1.0`) so existing tests and smoke fixtures that don't pass
  adjustments are byte-for-byte unaffected.

### Task P1.4 — Audit lineage (proposals/definitions only)
- **Already done for learning factors:** `LearningFactorRecord.source_daily_reflection_id` exists
  (`reflection.py:108`) and maps to `LearningFactor.daily_reflection_id` FK (saved at
  `repositories/sqlalchemy.py:584`). No change needed there.
- **Gap is on proposals/definitions:** `StrategyProposalRecord` (`strategy_evolution.py:44-60`) has
  `prompt_run_id` but **no** reflection link; the `StrategyProposal` ORM (`db/models/trading.py`) likewise has
  `prompt_run_id` but no `daily_reflection_id`. Add a nullable `source_daily_reflection_id` /
  `daily_reflection_id` FK to `strategy_proposals` (and optionally `strategy_definitions`) via an Alembic
  migration, thread it through `StrategyProposalRecord` + `save_strategy_proposal`
  (`repositories/sqlalchemy.py:377`), and populate it at the proposal-creation sites in
  `strategy_evolution.py` (lines 153, 183, 252) from `request.daily_reflections`. Keep nullable for backfill.

### P1 acceptance criteria
- Insert an `active` `scope="strategy"` learning factor with `increase_score` for a known `strategy_id`; next
  preopen run's `candidate_score` for that strategy is measurably higher (unit test with a stubbed snapshot).
- Insert an `active` `scope="risk"` factor with `reduce_exposure`; next preopen run's `final_weight` is
  measurably lower (the resolved `macro_risk_budget_multiplier` drops ~15%).
- A `shadow` factor appears in `shadow_factor_keys` / logs but changes no scores or weights.
- New `strategy_proposals` rows created by evolution carry `source_daily_reflection_id`.
- Existing preopen/intraday/manual smoke fixtures and tests still pass unchanged.

---

## P1 (parallel) — Connect research watchlist → trading universe (small change)

### Task P1.5
**Source (verified):** `src/research/repositories/research_repository.py:35` —
`get_active_tickers(session) -> list[str]` returns active `watchlists.ticker` values
(`src/db/models/watch_list.py::Watchlist`, columns `ticker`, `is_active`).

Two implementation levels — pick based on how much you want the `watchlist_pin` tag:

- **(a) Simple — scanned as ordinary universe members.** In `preopen_dependencies.py`, load
  `get_active_tickers(session)` and merge them into the loaded `UniverseFilterConfig.manual_include` before
  passing config to the scan. They get scored but tagged `selection_source="scanner"`. Lowest effort; does
  NOT light up the `watchlist_pin` enum.
- **(b) Full — tagged `watchlist_pin`.** Thread a new pinned-ticker source through the same path that
  `manual_requests` already use: `universe_scan_pipeline.run(config, decision_time, manual_requests=...)` →
  `SignalPipeline.build_pre_open_snapshots` → `build_signal_snapshot(..., selection_source=...)`
  (`src/trading/signals/snapshots.py:40`). Add a `watchlist_pins` channel that sets
  `selection_source="watchlist_pin"` (the value already exists in the `candidate_scores` CHECK constraint at
  `db/models/trading.py` but is never assigned). More plumbing, but gives correct provenance + lets the UI
  distinguish research-watchlist-driven candidates.

Recommendation: ship **(a)** in this PR to connect the two systems quickly; do **(b)** only if provenance
tagging matters for the `/today` UI.

### Acceptance
- A ticker added under `/watchlist` appears in the next preopen `strategy_runs` / `candidate_scores`
  (as `scanner` for option (a), or `watchlist_pin` for option (b)).

---

## P2 (optional) — Observability of the loop

- Add a `/today` panel showing the conversion funnel: learning_factors created → applied today →
  strategy_proposals → new strategy_definitions → promoted (shadow→experimental→active), plus which learning
  factors influenced today's weights. No new pipeline logic; read-only presenters over existing tables.

---

## Suggested PR sequence
1. **PR-A (P0):** config flag + facade/dispatch threading + 3 jobs + universe seed + tests.
   Ship, then **observe 1-2 trading days** of real paper orders before P1.
2. **PR-B (P1):** learning-factor load + application layer + injection + audit FK + tests.
3. **PR-C (P1 parallel):** watchlist → universe.
4. **PR-D (P2):** observability panel.

## Guardrails for the implementer
- Do not change cron schedules or the post-close jobs' behavior.
- Keep `execute_paper_orders` plumbing additive: every runner already defaults to dry-run, so the only new
  default-on behavior comes from `TRADING_EXECUTE_PAPER_ORDERS=true` in P0.1.
- Preserve idempotency: paper orders already use `client_order_id`; do not weaken that.
- All new code paths must be exercised by tests; reuse existing smoke fixtures where possible.
