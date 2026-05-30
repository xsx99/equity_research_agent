# Trading Agent Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the V2 relative-strength catalyst trading workflow in reviewable PR slices: pre-market universe scan, signal snapshots, trade identity classification, strategy matching, risk-aware paper stock/options simulation, post-close reflection, learning adaptation, self-discovered strategy evolution, and UI.

**Architecture:** Keep Python orchestration as the source of truth. LLM calls are bounded: Gemini Flash for trading/research summaries, highest-quality configured model for reflection. Each pipeline persists replayable snapshots so candidate selection, trade identity, confidence calibration, risk decisions, paper stock/options orders, worst-case assignment exposure, portfolio state, prompt versions, LLM calls, reflection, and learning factors can be audited.

**Tech Stack:** Python, SQLAlchemy, Alembic, Postgres JSONB, FastAPI/Jinja, APScheduler, pytest, existing market/news/global-context providers.

---

## Execution Rules

- Each PR slice stops after verification. Do not begin the next slice until the user has reviewed and merged.
- Use TDD for implementation code: write failing tests, run targeted tests, implement, rerun targeted tests, then run the broader relevant suite.
- After every completed implementation slice, update `plan/research_app/trading_agent_refactor_progress_tracker.md`.
- For major refactor slices, update `documents/repo_overview.md`. If the file is absent, create it with the current architecture summary.
- For Python commands, run `source ~/.venv/bin/activate` first.
- Any DB/API smoke test must be standalone and rate-limit conscious.
- Deployment changes must preserve Docker Compose and persistent disk Postgres requirements.

## PR Slice Overview

1. **PR 1: Trading Foundation Schema + Strategy Catalog**
   Add ORM/Alembic foundation tables, manual ticker request schema, prompt registry schema, trade identity enums, and a versioned in-code seed catalog for the 15 tactical strategies plus 4 portfolio/option strategy buckets from the design doc. No scheduler, API calls, or trading behavior yet.
2. **PR 2: Universe Scan + Signal Snapshots**
   Add universe provider/pipeline, manual ticker request ingestion, and deterministic signal snapshot persistence from market bars plus Postgres-backed insider, SEC, news, fundamentals, event/calendar, options, and existing research context sources.
3. **PR 3: Strategy Matching + Candidate Scoring**
   Match scanner and manual-request symbols to strategy definitions and persist ranked candidates with strategy horizon/evidence, source attribution, primary strategy selection, trade identity classification, catalyst-watch vs ordinary-watch distinction, and confidence-calibration inputs.
4. **PR 4: Position Sizing + Portfolio Risk Manager**
   Add deterministic sizing, risk factor exposure calculation, concentration caps, bearish-signal gating, and reduce/reject decisions.
5. **PR 5: Trading Decisions + Paper Stock Broker + Portfolio State**
   Add bounded trading agent output, manual request mode gating, paper stock orders/executions, positions, and portfolio snapshots.
6. **PR 6: Paper Options Strategy Layer + Assignment Risk**
   Add paper-only short-put decisions, option orders/positions, sell/close/roll/avoid/assignment-plan actions, and worst-case assigned-portfolio risk checks.
7. **PR 7: Intraday Signal Refresh + News Alerts + Rebalance**
   Add hourly intraday signal refresh, normalized alerts, material signal-change detection, and risk-gated intraday rebalance decisions for stocks and paper short puts.
8. **PR 8: Reflection + Learning Factors**
   Add post-close reflection with highest-quality model routing, learning factor lifecycle, benchmark/peer attribution, bullish/bearish calibration, paper options attribution, and strategy proposal hints.
9. **PR 9: Strategy Evolution + Dynamic Strategy Catalog**
   Convert repeated learning patterns into proposed strategies, shadow-test them, and promote/retire strategy definitions.
10. **PR 10: Today Dashboard UI**
   Add `/today`, pinned review, candidate, trade, options, risk exposure, reflection, and learning views.
11. **PR 11: Scheduler, Smoke Tests, Deploy Docs**
   Wire daily jobs, standalone smoke scripts, and deployment/runbook docs.

---

## PR 1: Trading Foundation Schema + Strategy Catalog

**Goal:** Add the durable database and strategy-definition foundation without changing runtime behavior.

**Files:**
- Create: `src/db/models/trading.py`
- Modify: `src/db/models/__init__.py`
- Create: `alembic/versions/005_trading_foundation_tables.py`
- Create: `src/agents/prompt_registry.py`
- Create: `src/agents/prompts/README.md`
- Create: `src/trading/__init__.py`
- Create: `src/trading/trade_taxonomy.py`
- Create: `src/trading/strategy_catalog.py`
- Create: `tests/agents/test_prompt_registry.py`
- Create: `tests/trading/test_strategy_catalog.py`
- Create: `tests/trading/test_trade_taxonomy.py`
- Create: `tests/db/test_trading_models.py`
- Modify: `plan/research_app/trading_agent_refactor_progress_tracker.md`

### Task 1.1: Strategy Catalog

- [ ] **Step 1: Write failing catalog tests**

Create `tests/trading/test_strategy_catalog.py` with assertions:

```python
from src.trading.strategy_catalog import INITIAL_STRATEGY_CATALOG, get_initial_strategy_definitions


def test_initial_catalog_contains_expected_strategies():
    strategy_ids = {item.strategy_id for item in INITIAL_STRATEGY_CATALOG}
    assert len(strategy_ids) == 19
    assert "catalyst_breakout_v1" in strategy_ids
    assert "gap_and_go_v1" in strategy_ids
    assert "short_squeeze_breakout_v1" in strategy_ids
    assert "strong_theme_catalyst_long_stock" in strategy_ids
    assert "strong_theme_no_clear_near_term_sell_put" in strategy_ids
    assert "valuation_repair_quality_software_sell_put" in strategy_ids
    assert "core_accumulation_on_pullback" in strategy_ids


def test_strategy_definitions_have_required_fields():
    for item in INITIAL_STRATEGY_CATALOG:
        assert item.display_name
        if item.strategy_layer == "tactical_pattern":
            assert item.strategy_id.endswith("_v1")
        assert item.typical_horizon
        assert item.core_thesis
        assert item.required_signals
        assert item.risk_tags
        assert item.invalidators
        assert item.strategy_layer in {"tactical_pattern", "expression_bucket"}


def test_seed_rows_are_json_serializable():
    rows = get_initial_strategy_definitions()
    assert rows
    assert all("strategy_id" in row for row in rows)
    assert all(row["version"] == "v1" for row in rows)
    assert all(row["lifecycle_status"] == "active" for row in rows)
    assert all(row["source"] == "seed" for row in rows)
    assert all(isinstance(row["config_json"], dict) for row in rows)
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_strategy_catalog.py -q
```

Expected: fail because `src.trading.strategy_catalog` does not exist.

- [ ] **Step 3: Implement the catalog**

Create `src/trading/strategy_catalog.py`:

- Use a frozen dataclass `StrategyCatalogItem`.
- Include all 15 tactical strategies and the 4 portfolio/option strategy buckets from the design doc.
- Provide `get_initial_strategy_definitions() -> list[dict[str, object]]`.
- Keep thresholds in `config_json` and avoid provider-specific code.
- Include `strategy_layer`, `allowed_trade_identities`, `allowed_instruments`, and option policy fields where relevant.

- [ ] **Step 4: Verify catalog tests pass**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_strategy_catalog.py -q
```

Expected: pass.

### Task 1.2: Trade Taxonomy

- [ ] **Step 1: Write failing taxonomy tests**

Create `tests/trading/test_trade_taxonomy.py` with assertions:

```python
from src.trading.trade_taxonomy import TRADE_IDENTITIES, get_trade_identity_policy


def test_trade_identities_include_required_pools():
    assert "core_holding" in TRADE_IDENTITIES
    assert "catalyst_common_stock" in TRADE_IDENTITIES
    assert "strong_theme_sell_put" in TRADE_IDENTITIES
    assert "valuation_repair_sell_put" in TRADE_IDENTITIES
    assert "catalyst_watch" in TRADE_IDENTITIES
    assert "ordinary_watch" in TRADE_IDENTITIES


def test_core_holding_is_separate_from_short_term_pool():
    policy = get_trade_identity_policy("core_holding")
    assert policy.instrument == "stock"
    assert policy.portfolio_pool == "core"
    assert policy.can_be_sold_by_short_term_signal is False


def test_sell_put_identities_require_assignment_plan():
    for identity in ["strong_theme_sell_put", "valuation_repair_sell_put"]:
        policy = get_trade_identity_policy(identity)
        assert policy.instrument == "cash_secured_short_put"
        assert policy.requires_assignment_plan is True
        assert policy.requires_worst_case_assignment_check is True
```

- [ ] **Step 2: Run the failing taxonomy test**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_trade_taxonomy.py -q
```

Expected: fail because `src.trading.trade_taxonomy` does not exist.

- [ ] **Step 3: Implement the taxonomy**

Create `src/trading/trade_taxonomy.py` with:

- frozen dataclass `TradeIdentityPolicy`
- identities: `core_holding`, `catalyst_common_stock`, `strong_theme_sell_put`, `valuation_repair_sell_put`, `catalyst_watch`, `ordinary_watch`
- fields for instrument, portfolio pool, default horizon, sizing policy, exit policy, assignment requirements, and whether short-term signals can sell the position

- [ ] **Step 4: Verify taxonomy tests pass**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_trade_taxonomy.py -q
```

Expected: pass.

### Task 1.3: Prompt Registry Foundation

- [ ] **Step 1: Write failing prompt registry tests**

Create `tests/agents/test_prompt_registry.py` with assertions:

```python
from src.agents.prompt_registry import PromptRegistry


def test_prompt_registry_requires_versioned_prompt_metadata(tmp_path):
    prompt_dir = tmp_path / "prompts" / "trading"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "trading_decision_v1.yaml"
    prompt_file.write_text(
        "prompt_id: trading_decision\n"
        "prompt_version: v1\n"
        "pipeline_name: trading\n"
        "output_schema_id: trading_decision\n"
        "output_schema_version: v1\n"
        "template: 'Ticker: {{ ticker }}'\n",
        encoding="utf-8",
    )

    registry = PromptRegistry(root=tmp_path / "prompts")
    template = registry.load("trading_decision", "v1")

    assert template.prompt_id == "trading_decision"
    assert template.prompt_version == "v1"
    assert template.output_schema_version == "v1"
    assert template.template_hash


def test_prompt_registry_renders_and_hashes_prompt(tmp_path):
    prompt_dir = tmp_path / "prompts" / "trading"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "trading_decision_v1.yaml"
    prompt_file.write_text(
        "prompt_id: trading_decision\n"
        "prompt_version: v1\n"
        "pipeline_name: trading\n"
        "output_schema_id: trading_decision\n"
        "output_schema_version: v1\n"
        "template: 'Ticker: {{ ticker }}'\n",
        encoding="utf-8",
    )

    registry = PromptRegistry(root=tmp_path / "prompts")
    rendered = registry.render("trading_decision", "v1", {"ticker": "NVDA"})

    assert rendered.text == "Ticker: NVDA"
    assert rendered.rendered_prompt_hash
```

- [ ] **Step 2: Run the failing prompt registry tests**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/agents/test_prompt_registry.py -q
```

Expected: fail because `src.agents.prompt_registry` does not exist.

- [ ] **Step 3: Implement prompt registry foundation**

Create `src/agents/prompt_registry.py` and `src/agents/prompts/README.md`:

- Load prompt templates only from version-controlled prompt files under `src/agents/prompts/`.
- Require `prompt_id`, `prompt_version`, `pipeline_name`, `output_schema_id`, `output_schema_version`, and `template`.
- Render templates deterministically.
- Compute `template_hash` and `rendered_prompt_hash`.
- Leave DB persistence of runs to repository/model code, but expose metadata needed for `LlmPromptTemplate`, `LlmPromptRun`, and `LlmUsageEvent`.

- [ ] **Step 4: Verify prompt registry tests pass**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/agents/test_prompt_registry.py -q
```

Expected: pass.

### Task 1.4: ORM Models

- [ ] **Step 1: Write failing model tests**

Create `tests/db/test_trading_models.py` to instantiate:

- `UniverseSnapshot`
- `UniverseSymbol`
- `ManualTickerRequest`
- `MacroSnapshot`
- `SignalSnapshot`
- `StrategyDefinition`
- `StrategyRun`
- `CandidateScore`
- `RiskLimitConfig`
- `PortfolioRiskSnapshot`
- `RiskFactorExposure`
- `StrategyProposal`
- `StrategyEvaluationResult`
- `TradeClassification`
- `LlmPromptTemplate`
- `LlmPromptRun`
- `LlmUsageEvent`

Assertions:

```python
def test_strategy_definition_defaults():
    row = StrategyDefinition(
        strategy_id="gap_and_go_v1",
        version="v1",
        display_name="Gap-and-Go",
        strategy_layer="tactical_pattern",
        typical_horizon="intraday-3d",
        config_json={"required_signals": ["opening_gap_pct"]},
        lifecycle_status="active",
        source="seed",
        is_active=True,
    )
    assert row.strategy_id == "gap_and_go_v1"
    assert row.lifecycle_status == "active"
    assert row.source == "seed"
    assert row.is_active is True
```

Also assert enum `.choices()` for new status enums.

- [ ] **Step 2: Run the failing model tests**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/db/test_trading_models.py -q
```

Expected: fail because `src.db.models.trading` does not exist.

- [ ] **Step 3: Implement `src/db/models/trading.py`**

Create focused SQLAlchemy models:

- `UniverseSnapshot`
  - `snapshot_id UUID pk`
  - `trade_date Date index`
  - `source String(64)`
  - `filters_json JSONB`
  - `status queued/running/succeeded/failed`
  - timestamps and `error_message`
- `UniverseSymbol`
  - `id UUID pk`
  - `snapshot_id fk universe_snapshots`
  - `ticker String(16)`
  - `name`, `exchange`, `asset_type`
  - `is_included Bool`
  - `exclusion_reason`
  - `metadata_json JSONB`
- `MacroSnapshot`
  - `macro_snapshot_id UUID pk`
  - `trade_date Date index`
  - `as_of DateTime`
  - `regime_json JSONB`
  - `indicators_json JSONB`
  - `status`
- `SignalSnapshot`
  - `signal_snapshot_id UUID pk`
  - `universe_snapshot_id fk`
  - `ticker String(16)`
  - `trade_date Date index`
  - `signals_json JSONB`
  - `missing_signals_json JSONB`
  - `status`
- `StrategyDefinition`
  - `strategy_definition_id UUID pk`
  - `strategy_id String(64)`
  - `version String(16)`
  - `display_name String(128)`
  - `strategy_layer String(32)` with values such as `tactical_pattern`, `expression_bucket`
  - `typical_horizon String(32)`
  - `config_json JSONB`
  - `lifecycle_status String(16)` with `candidate/shadow/experimental/active/retired`
  - `source String(32)` with values such as `seed`, `reflection_learning`, `manual`
  - `parent_strategy_id String(64)` nullable for revisions/derived strategies
  - `evidence_json JSONB`
  - `is_active Bool`
  - unique `(strategy_id, version)`
- `StrategyRun`
  - `strategy_run_id UUID pk`
  - `trade_date Date index`
  - `universe_snapshot_id`, `macro_snapshot_id`
  - `status`, timestamps, `error_message`
- `CandidateScore`
  - `candidate_id UUID pk`
  - `strategy_run_id fk`
  - `signal_snapshot_id fk`
  - `ticker`
  - `strategy_id`, `strategy_version`
  - `candidate_score Numeric`
  - `typical_horizon`
  - `evidence_json`, `invalidators_json`, `risk_tags_json`
  - `macro_compatibility`
  - `selection_source String(32)` with values such as `scanner`, `manual_request`, `watchlist_pin`
  - `manual_request_id fk manual_ticker_requests` nullable
  - `selection_reason`, `rejection_reason`
- `ManualTickerRequest`
  - `manual_request_id UUID pk`
  - `ticker String(16) index`
  - `trade_date Date index`
  - `submitted_at DateTime`
  - `reason Text`
  - `priority String(16)` with values such as `normal`, `high`
  - `mode String(32)` with values `review_only`, `paper_trade_eligible`
  - `expires_at DateTime`
  - `status String(32)` with values `pending/running/completed/failed/expired/cancelled`
  - `result_status String(32)` nullable with values `actionable_trade/catalyst_watch/ordinary_watch/no_trade/blocked_by_risk/blocked_by_missing_data`
  - `result_decision_id UUID` nullable
  - `source_context_json JSONB`
  - `error_message Text`
- `TradeClassification`
  - `trade_classification_id UUID pk`
  - `candidate_id fk candidate_scores` nullable for current-position classifications
  - `ticker String(16)`
  - `trade_date Date index`
  - `trade_identity String(64)` with `core_holding/catalyst_common_stock/strong_theme_sell_put/valuation_repair_sell_put/catalyst_watch/ordinary_watch`
  - `strategy_bucket_id String(64)` nullable
  - `instrument_type String(32)`
  - `portfolio_pool String(32)`
  - `horizon_policy String(64)`
  - `exit_policy_json JSONB`
  - `classification_reason Text`
- `RiskLimitConfig`
  - versioned JSON config and `is_active`
- `PortfolioRiskSnapshot`
  - portfolio-level exposure JSON before/after decisions/fills
- `RiskFactorExposure`
  - normalized exposure rows by `factor_type`, `factor_name`, `exposure_value`
- `StrategyProposal`
  - `strategy_proposal_id UUID pk`
  - `proposed_strategy_id String(64)`
  - `display_name String(128)`
  - `proposed_config_json JSONB`
  - `source String(32)`
  - `source_reflection_ids_json JSONB`
  - `evidence_summary Text`
  - `status candidate/shadow/experimental/active/rejected/retired`
  - `duplicate_of_strategy_id String(64)` nullable
  - `rejection_reason Text`
- `StrategyEvaluationResult`
  - `strategy_evaluation_id UUID pk`
  - `strategy_id`, `strategy_version`
  - `evaluation_date Date`
  - `mode shadow/experimental/active`
  - `metrics_json JSONB`
  - `promotion_decision`
  - `decision_reason`
- `LlmPromptTemplate`
  - `prompt_template_id UUID pk`
  - `prompt_id String(128)`
  - `prompt_version String(32)`
  - `pipeline_name String(64)`
  - `template_path String(255)`
  - `template_hash String(128)`
  - `git_commit String(64)` nullable
  - `output_schema_id String(128)`
  - `output_schema_version String(32)`
  - `lifecycle_status active/retired`
  - unique `(prompt_id, prompt_version)`
- `LlmPromptRun`
  - `prompt_run_id UUID pk`
  - `prompt_template_id fk llm_prompt_templates`
  - `pipeline_name String(64)`
  - `pipeline_run_id UUID` nullable
  - `rendered_prompt_hash String(128)`
  - `rendered_prompt_redacted Text` nullable
  - `input_context_json JSONB`
  - `raw_output_text Text`
  - `parsed_output_json JSONB`
  - `parse_status succeeded/failed`
  - `error_message Text`
- `LlmUsageEvent`
  - `llm_usage_event_id UUID pk`
  - `prompt_run_id fk llm_prompt_runs`
  - `provider String(64)`
  - `model String(128)`
  - `prompt_tokens Integer`
  - `completion_tokens Integer`
  - `total_tokens Integer`
  - `estimated_cost Numeric`
  - `latency_ms Integer`
  - `retry_count Integer`
  - `status succeeded/failed`

- [ ] **Step 4: Export models**

Modify `src/db/models/__init__.py` to export the new models/enums.

- [ ] **Step 5: Verify model tests pass**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/db/test_trading_models.py -q
```

Expected: pass.

### Task 1.5: Alembic Migration

- [ ] **Step 1: Write migration shape test**

Add a simple test in `tests/db/test_trading_models.py` or a new `tests/db/test_trading_migration.py` that reads `alembic/versions/005_trading_foundation_tables.py` and asserts table names exist. Keep it lightweight; this repo does not currently run migrations against Postgres in unit tests.

- [ ] **Step 2: Create migration**

Create `alembic/versions/005_trading_foundation_tables.py` with:

- `down_revision = "004"`
- create/drop all PR 1 foundation tables
- indexes for date, ticker, strategy, status
- check constraints for status fields and `candidate_score between 0 and 1`
- check constraints for strategy lifecycle status fields
- check constraints for manual ticker request mode/status/result status fields
- check constraints for trade identity fields
- check constraints for prompt lifecycle, parse status, and usage status fields

- [ ] **Step 3: Run targeted tests**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/agents/test_prompt_registry.py tests/trading/test_strategy_catalog.py tests/trading/test_trade_taxonomy.py tests/db/test_trading_models.py -q
```

Expected: pass.

### Task 1.6: Progress Tracker and Verification

- [ ] **Step 1: Update tracker**

Update `plan/research_app/trading_agent_refactor_progress_tracker.md` with:

- PR 1 status
- implemented files
- test commands and results
- any known gaps

- [ ] **Step 2: Run broader relevant tests**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/agents/test_prompt_registry.py tests/db tests/trading -q
```

Expected: pass.

- [ ] **Step 3: Stop for review**

Stop after PR 1. Do not implement PR 2 until the user has reviewed and merged.

---

## PR 2: Universe Scan + Signal Snapshots

**Goal:** Build a deterministic pre-market universe and full signal snapshot pipeline with benchmark/peer relative-strength inputs plus Postgres-backed insider, SEC, news, fundamentals, event/calendar, options, and existing research context signals. No strategy matching or trading decisions yet.

**Files:**
- Create: `src/trading/manual_requests.py`
- Create: `src/trading/universe.py`
- Create: `src/trading/signals.py`
- Create: `src/trading/signal_sources.py`
- Create: `src/trading/pipeline.py`
- Create: `src/trading/repository.py`
- Modify: `src/tools/market_data/types.py` if the provider protocol needs universe support
- Modify: `src/tools/market_data/alpaca_provider.py` to add an asset/universe method if needed
- Test: `tests/trading/test_universe.py`
- Test: `tests/trading/test_manual_requests.py`
- Test: `tests/trading/test_signals.py`
- Test: `tests/trading/test_signal_sources.py`
- Test: `tests/trading/test_relative_strength.py`
- Test: `tests/trading/test_pipeline.py`

Implementation notes:

- Add a `UniverseProvider` interface with a test fake and an Alpaca implementation.
- Include a config fallback `TRADING_UNIVERSE_SYMBOLS` for local/dev tests.
- Persist included and excluded symbols with exclusion reasons.
- Add `ManualTickerRequestService` for creating, expiring, cancelling, and loading active manual requests.
- Merge active manual requests into the signal snapshot job even when the ticker did not pass the scanner ranking threshold.
- Manual requests can bypass scanner selection threshold, but not ticker validation, market-data availability, liquidity rules, or later risk checks.
- Support `review_only` and `paper_trade_eligible` request modes.
- Build signal snapshots from existing daily bars/context where possible.
- Add `SignalSourceRepository` or equivalent adapters that read normalized Postgres-backed sources for insider transactions/Form 4/SEC filings, news and analyst events, fundamentals/valuation, earnings/event calendar, option-chain snapshots, and existing research/global-context artifacts.
- Prefer normalized Postgres rows over ad hoc live provider calls. Provider calls are allowed only through controlled refresh/fallback adapters and must record attempted source and freshness.
- Store source provenance for each signal, including `source`, `source_table` or provider name, `as_of` / `published_at` / `filing_date` where relevant, and missing/stale status.
- Add derived insider/SEC signals such as net buy value, cluster buy count, officer/director buy flags, sale concentration, and recent filing freshness.
- Add derived news/fundamental signals such as high-signal news count, analyst revision score, guidance/customer/regulatory flags, valuation percentile, margin trend, quality score, and market-cap/liquidity quality.
- Add relative-strength fields vs `SPY`, `QQQ`, sector/theme ETF when configured, and peer basket when available.
- Add catalyst quality fields and direct-negative-catalyst fields without asking the LLM to infer missing values.
- Add option-chain placeholder fields as explicitly missing unless a provider exists.
- Store missing signals explicitly.
- Mark manual request results as `blocked_by_missing_data` when required market data cannot be fetched.
- Use no LLM calls.

Stop after PR 2 for review/merge.

---

## PR 3: Strategy Matching + Candidate Scoring

**Goal:** Convert signal snapshots into ranked strategy candidates with strategy-specific horizon/evidence/invalidators, trade identity classification, and confidence-calibration inputs.

**Files:**
- Create: `src/trading/strategy_matching.py`
- Create: `src/trading/primary_strategy_selector.py`
- Create: `src/trading/trade_classifier.py`
- Create: `src/trading/confidence_calibration.py`
- Modify: `src/trading/repository.py`
- Modify: `src/trading/pipeline.py`
- Test: `tests/trading/test_strategy_matching.py`
- Test: `tests/trading/test_primary_strategy_selector.py`
- Test: `tests/trading/test_trade_classifier.py`
- Test: `tests/trading/test_confidence_calibration.py`
- Test: `tests/trading/test_candidate_repository.py`

Implementation notes:

- Load active `StrategyDefinition` rows.
- Score only deterministic evidence available in `signals_json`.
- Persist one `CandidateScore` per `(ticker, strategy_id)` that passes basic eligibility.
- Persist `selection_source` as `scanner`, `manual_request`, or `watchlist_pin`, and link `manual_request_id` when applicable.
- Select one primary tactical strategy and one strategy bucket per ticker/action before trade classification.
- Persist selected primary strategy context in `TradeClassification` and later `TradingDecision` context so attribution does not drift.
- Classify each candidate into `core_holding`, `catalyst_common_stock`, `strong_theme_sell_put`, `valuation_repair_sell_put`, `catalyst_watch`, or `ordinary_watch`.
- Distinguish `catalyst_watch` from ordinary neutral/watch output when direction is uncertain but move potential is high.
- Compute confidence calibration inputs by strategy bucket, direction, catalyst type, benchmark/peer outperformance, and available historical outcomes.
- Downgrade macro-only bearish candidates to risk warnings or no-trade; do not create single-name bearish candidates from macro alone.
- Preserve rejected candidates with `rejection_reason` when they are useful for later reflection.
- Update manual request `result_status` to `catalyst_watch`, `ordinary_watch`, `no_trade`, or `blocked_by_missing_data` when no trading decision will be requested.
- Do not call `TradingPipeline` yet.

Stop after PR 3 for review/merge.

---

## PR 4: Position Sizing + Portfolio Risk Manager

**Goal:** Add deterministic sizing, portfolio factor concentration controls, and bearish-signal gating.

**Files:**
- Create: `src/trading/risk.py`
- Create: `src/trading/position_sizing.py`
- Modify: `src/trading/repository.py`
- Test: `tests/trading/test_position_sizing.py`
- Test: `tests/trading/test_risk_manager.py`

Implementation notes:

- Implement `RiskLimitConfig` loader with default config.
- Calculate factor exposure by sector, strategy, horizon, direction, beta bucket, volatility bucket, liquidity bucket, event type, and macro sensitivity.
- Include explicit risk rules that prevent macro-only bearish evidence from creating high-confidence single-name shorts.
- Keep core-holding risk rules separate from short-term catalyst trade rules.
- Implement reduce/reject behavior for concentration caps.
- Persist `position_sizing_decisions`, `portfolio_risk_snapshots`, and `risk_factor_exposures`.
- Keep this independent of LLM and paper broker.

Stop after PR 4 for review/merge.

---

## PR 5: Trading Decisions + Paper Stock Broker + Portfolio State

**Goal:** Add paper common-stock trading behavior after candidate scoring and risk approval.

**Files:**
- Create: `src/agents/trading.py`
- Create: `src/agents/trading_schemas.py`
- Create: `src/trading/paper_stock_broker.py`
- Create: `src/trading/portfolio.py`
- Modify: `src/core/config.py`
- Modify: `src/trading/pipeline.py`
- Add ORM models/migration for `trading_decisions`, `paper_orders`, `paper_executions`, `paper_positions`, `portfolio_snapshots`
- Test: `tests/agents/test_trading_agent.py`
- Test: `tests/trading/test_paper_stock_broker.py`
- Test: `tests/trading/test_portfolio.py`

Implementation notes:

- Use `TRADING_MODEL_NAME` defaulting to `DEFAULT_FAST_MODEL_NAME`.
- Load trading prompts through `PromptRegistry`; no inline prompt strings.
- Persist `LlmPromptTemplate`, `LlmPromptRun`, and `LlmUsageEvent` records for every trading-agent call, including rendered prompt hash/redacted prompt, input context, raw output, parsed output, prompt/schema version, model, token usage, cost, latency, retries, and errors.
- Persist the full decision context snapshot, including trade identity, strategy bucket, benchmark/peer context, confidence basis, `selection_source`, and `manual_request_id`.
- Enforce manual request mode: `review_only` can produce an actionable explanation but must not create a paper order; `paper_trade_eligible` can create a paper order only after normal risk approval.
- Update linked manual request `result_status` to `actionable_trade`, `blocked_by_risk`, `no_trade`, `catalyst_watch`, or `ordinary_watch`.
- Risk manager is the final gate before paper order creation.
- Paper broker must be idempotent for a trade date / ticker / strategy / action.

Stop after PR 5 for review/merge.

---

## PR 6: Paper Options Strategy Layer + Assignment Risk

**Goal:** Add paper/simulation-only short-put strategy decisions and worst-case assigned-portfolio risk management.

**Files:**
- Create: `src/trading/options_strategy.py`
- Create: `src/trading/option_risk.py`
- Create: `src/trading/paper_option_broker.py`
- Modify: `src/trading/repository.py`
- Modify: `src/trading/portfolio.py`
- Modify: `src/trading/risk.py`
- Modify: `src/agents/trading_schemas.py`
- Add ORM models/migration for `option_strategy_decisions`, `paper_option_orders`, `paper_option_positions`, `option_risk_snapshots`
- Test: `tests/trading/test_options_strategy.py`
- Test: `tests/trading/test_option_risk.py`
- Test: `tests/trading/test_paper_option_broker.py`
- Test: `tests/trading/test_option_repository.py`

Implementation notes:

- Support `sell_put`, `close_put`, `roll_put`, `avoid_earnings_put`, and `put_assignment_plan`.
- Require every short-put plan to include strike, expiry, DTE, delta, IV rank/percentile, premium, breakeven, assignment notional, cash-secured amount, underlying exposure, earnings date, roll/close conditions, and assignment plan.
- Reject or downgrade to watch when required option metadata is missing.
- Calculate current portfolio exposure and worst-case assigned exposure where all paper short puts convert to long stock at strike.
- Apply assignment caps by ticker, sector/theme, strategy bucket, high-beta AI/semis/space cluster, correlation cluster, and available cash-secured commitment.
- Keep the options layer paper/simulation-only; no real broker integration.
- Persist option decisions and rejected plans because reflection needs to evaluate missed premium vs avoided assignment risk.

Stop after PR 6 for review/merge.

---

## PR 7: Intraday Signal Refresh + News Alerts + Rebalance

**Goal:** Refresh intraday signals and news hourly during regular trading hours, then trigger risk-gated intraday rebalance actions for material signal changes or high-impact positive/negative events.

**Files:**
- Create: `src/trading/intraday_signals.py`
- Create: `src/trading/news_alerts.py`
- Create: `src/trading/intraday_rebalance.py`
- Modify: `src/trading/repository.py`
- Modify: `src/agents/trading_schemas.py` if rebalance decisions share trading-agent schema
- Modify: `src/core/config.py`
- Add ORM models/migration for `intraday_signal_scans`, `intraday_signal_snapshots`, `news_alerts`, `intraday_rebalance_decisions`
- Test: `tests/trading/test_intraday_signals.py`
- Test: `tests/trading/test_news_alerts.py`
- Test: `tests/trading/test_intraday_rebalance.py`
- Test: `tests/trading/test_news_alert_repository.py`

Implementation notes:

- Scan scope starts with open stock positions, paper option positions, same-day trades, staged orders, top morning candidates, active manual/pinned review tickers, and high-impact market/sector news.
- Refresh intraday price/volume/liquidity signals, VWAP/opening-range/gap signals, relative strength vs benchmarks/peers, option marks/assignment-risk deltas, news/event signals, and freshness checks for low-frequency insider/SEC/fundamental/event sources.
- Persist intraday signal snapshots with deltas vs the morning snapshot and previous hourly snapshot.
- Define material-change thresholds that can trigger rebalance even without a new headline.
- Use deterministic dedupe keys so repeated headlines do not trigger repeated rebalances.
- Load intraday classification/rebalance prompts through `PromptRegistry` and persist prompt run/usage records for every LLM call.
- Normalize alert fields: ticker, event type, sentiment, severity, source, published time, summary, strategy relevance, affected positions/candidates, and action-required flag.
- Severity levels are `critical`, `high`, `medium`, `low`.
- Critical/high alerts can propose `hold`, `reduce`, `exit`, `add`, `close_put`, `roll_put`, or `avoid_earnings_put`.
- `open_new` is disabled by default unless the ticker was already a morning candidate or manual override.
- Every proposed action must pass `PositionSizer`, `RiskManager`, and the relevant paper broker.
- Persist no-action and rejected signal/news triggers so post-close reflection can evaluate missed or noisy signals.

Stop after PR 7 for review/merge.

---

## PR 8: Reflection + Learning Factors

**Goal:** Add post-close reflection using the highest-quality configured model and persist learning factors plus strategy proposal hints.

**Files:**
- Create: `src/agents/reflection.py`
- Create: `src/agents/reflection_schemas.py`
- Create: `src/trading/reflection_pipeline.py`
- Modify: `src/core/config.py`
- Add ORM models/migration for `daily_reflections`, `learning_factors`, `learning_factor_applications`
- Test: `tests/agents/test_reflection_agent.py`
- Test: `tests/trading/test_reflection_pipeline.py`
- Test: `tests/trading/test_learning_factors.py`

Implementation notes:

- Add `REFLECTION_MODEL_NAME`; production should warn if absent.
- Load reflection prompts through `PromptRegistry`; no inline prompt strings.
- Persist prompt run and usage records for reflection, including raw output and parsed output. Reflection failure must not mutate learning factors.
- Reflection input includes portfolio outcome, candidates, manual ticker requests, accepted/rejected trades, intraday news alerts, intraday rebalance decisions, risk snapshots, factor concentration, benchmark/peer-basket returns, paper option decisions, worst-case assignment snapshots, and learning factors used.
- Analyze bullish catalyst trades separately from bearish/risk-off calls.
- Evaluate confidence calibration by strategy bucket, direction, catalyst type, sector/theme, and market regime.
- Evaluate whether `catalyst_watch` would have been more useful than ordinary neutral/watch.
- Evaluate whether user-pinned tickers exposed scanner misses or mostly confirmed no-trade discipline.
- Learning factors start as `candidate`, `active`, `suppressed`, or `retired`.
- Only tightening risk or context reminders can auto-activate initially.
- Reflection may emit `strategy_proposal_hints`, but PR 8 should not add them to the strategy catalog directly.

Stop after PR 8 for review/merge.

---

## PR 9: Strategy Evolution + Dynamic Strategy Catalog

**Goal:** Let the system summarize repeated learning into new strategy proposals and add validated candidates to the strategy list without being limited to the initial seed strategies.

**Files:**
- Create: `src/trading/strategy_evolution.py`
- Modify: `src/trading/repository.py`
- Modify: `src/db/models/trading.py` if `StrategyProposal` / `StrategyEvaluationResult` were not added in PR 1
- Add Alembic migration if proposal/evaluation tables are added here
- Test: `tests/trading/test_strategy_evolution.py`
- Test: `tests/trading/test_strategy_lifecycle.py`

Implementation notes:

- Consume reflection `strategy_proposal_hints`, learning factors, rejected candidate evidence, and strategy performance summaries.
- Load strategy proposal synthesis prompts through `PromptRegistry` and persist prompt run/usage records.
- Generate `StrategyProposal` records with proposed `strategy_id`, display name, thesis, required/optional signals, horizon, scoring rules, risk tags, invalidators, and evidence summary.
- Detect duplicates against existing strategy definitions by overlap in required signals, horizon, thesis, and risk tags.
- Create new `StrategyDefinition` rows only in `candidate` or `shadow` lifecycle status.
- Shadow strategies can be scored during scans but cannot create paper orders.
- Experimental strategies can create paper orders only with small capped budget and stricter risk limits.
- Persist every lifecycle transition and promotion/rejection reason.

Stop after PR 9 for review/merge.

---

## PR 10: Today Dashboard UI

**Goal:** Add operator-facing V2 tabbed trading workstation.

**Files:**
- Create: `src/web/routers/today.py`
- Create: `src/templates/today.html`
- Modify: `src/app.py`
- Modify: `src/templates/base.html`
- Modify: `src/static/style.css`
- Test: `tests/test_app.py` or `tests/web/test_today.py`

Implementation notes:

- Build `/today` as tabs: `Overview`, `Portfolio`, `Trades`, `Risk & Macro`, `Candidates`, `Learning & Strategies`, and `Ops & Cost`.
- Show live alerts, material signal changes, positions, trades, trade identity, strategy bucket, paper options, candidates, risk exposure, post-close reflection, learning factors, and macro regime.
- Add trade detail drill-down with signal snapshots, strategy scores, selected strategy, trade identity, LLM decision JSON, risk decision, order/fill state, exit plan, invalidators, and post-close outcome.
- Add a pinned-review form for ticker, reason, mode (`review_only` / `paper_trade_eligible`), priority, and expiry.
- Show pinned-review results with request status, result status, strategy match, trade identity, confidence basis, risk result, and linked trading decision if any.
- Show benchmark/peer outperformance and confidence basis for selected and rejected candidates.
- Show short-put strike, expiry, DTE, delta, IV rank, premium, breakeven, assignment notional, cash-secured amount, earnings date, roll/close plan, and assignment plan.
- Show strategy proposals, shadow/experimental strategies, and promotion/retirement status.
- Show strategy performance by win rate, PnL, alpha vs benchmarks/peer basket, drawdown, sample size, market regime, and bullish/bearish split.
- Show LLM/API usage and estimated cost by pipeline, model, provider, run, token count, latency, retry/error state, and prompt/schema version.
- Keep `/research` intact as audit UI.
- Avoid raw JSON as primary UX; use structured tables/cards.

Stop after PR 10 for review/merge.

---

## PR 11: Scheduler, Smoke Tests, Deploy Docs

**Goal:** Wire the daily workflow into scheduler and operational docs.

**Files:**
- Create: `src/scheduler/jobs/trading_preopen_job.py`
- Create: `src/scheduler/jobs/manual_ticker_review_job.py`
- Create: `src/scheduler/jobs/intraday_signal_refresh_job.py`
- Create: `src/scheduler/jobs/trading_reflection_job.py`
- Create: `src/scheduler/jobs/strategy_evolution_job.py`
- Modify: `src/scheduler/service.py` or `scripts/run_scheduler_service.py`
- Create: `scripts/run_trading_once.py`
- Create: `scripts/run_trading_smoke_test.py`
- Modify: `documents/research_app_runbook.md`
- Modify: `documents/research_app_deploy.md`
- Modify: `documents/repo_overview.md`
- Test: `tests/test_scheduler_jobs.py`
- Test: `tests/scripts/test_run_trading_smoke_test.py`

Implementation notes:

- Keep schedule in `America/New_York`.
- Add standalone smoke modes for universe/signal DB writes and paper-trade dry run.
- Add standalone smoke mode for a fixture-backed manual ticker request in `review_only` mode.
- Add standalone smoke mode for paper option decisions and assignment-risk snapshots using fixture data.
- Add standalone smoke mode for hourly intraday signal/news refresh using a fixed tiny ticker set or fixture mode.
- Add standalone smoke mode for strategy proposal creation from a fixed reflection fixture.
- Document Postgres persistent disk verification with `SHOW data_directory;`.
- Keep Docker Compose infrastructure.

Stop after PR 11 for review/merge.
