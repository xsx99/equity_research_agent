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
   Add ORM/Alembic foundation tables, universe filter config schema, manual ticker request schema, prompt registry schema, portfolio-pool trade identity enums, and a versioned in-code seed catalog for the 15 broad tactical strategies, 4 eval-derived playbook strategies, and 5 initial strategy expression buckets from the design doc, including defined-risk option expressions. No scheduler, API calls, or trading behavior yet.
2. **PR 2: Universe Scan + Signal Snapshots**
   Add user-editable liquidity/sector universe filters, universe provider/pipeline, manual ticker request ingestion, normalized future event calendar ingestion/risk scoring, and deterministic signal snapshot persistence from market bars plus Postgres-backed insider, SEC, news, fundamentals, event/calendar, options, macro/sector/theme read-through, and existing research context sources.
3. **PR 3: Strategy Matching + Candidate Scoring**
   Match scanner and manual-request symbols to strategy definitions and persist ranked candidates with strategy horizon/evidence, source attribution, primary strategy selection, trade identity classification, catalyst-watch vs ordinary-watch distinction, and confidence-calibration inputs.
4. **PR 4: Position Sizing + Portfolio Risk Manager**
   Add deterministic sizing, risk appetite presets, generated risk configs, risk factor exposure calculation, unified margin-account buying-power caps, conservative broker-profile margin estimates, concentration caps, embedded bearish-evidence gating, and reduce/reject decisions.
5. **PR 5: Trading Decisions + Paper Stock Broker + Portfolio State**
   Add bounded trading agent output, manual request mode gating, paper stock orders/executions, positions, and unified simulated margin-account portfolio snapshots with margin model profile/source metadata.
6. **PR 6: Paper Options Strategy Layer + Assignment Risk**
   Add paper-only leg-based option strategy decisions, option legs, option orders/positions, open/close/roll/adjust/avoid-event actions, an initial whitelist of long call/put, credit spread, long straddle, and long strangle strategies, strategy-level option risk, conservative option margin requirements, and worst-case assigned-portfolio risk checks when assignment is possible.
7. **PR 7: Intraday Signal Refresh + News Alerts + Rebalance**
   Add hourly intraday signal refresh, normalized alerts, material signal-change detection, and risk-gated intraday rebalance decisions for stocks, paper option strategies, and hedge overlays.
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
    strategy_layer_ids = {
        item.strategy_id for item in INITIAL_STRATEGY_CATALOG
        if item.strategy_layer == "tactical_pattern"
    }
    expression_bucket_ids = {
        item.strategy_id for item in INITIAL_STRATEGY_CATALOG
        if item.strategy_layer == "expression_bucket"
    }
    assert len(strategy_ids) == 24
    assert len(strategy_layer_ids) == 19
    assert len(expression_bucket_ids) == 5
    assert "catalyst_breakout_v1" in strategy_ids
    assert "gap_and_go_v1" in strategy_ids
    assert "short_squeeze_breakout_v1" in strategy_ids
    assert "strong_theme_catalyst_continuation_v1" in strategy_layer_ids
    assert "strong_theme_no_clear_near_term_entry_v1" in strategy_layer_ids
    assert "valuation_repair_quality_software_v1" in strategy_layer_ids
    assert "core_accumulation_on_pullback_v1" in strategy_layer_ids
    assert "long_stock" in expression_bucket_ids
    assert "defined_risk_directional_option" in expression_bucket_ids
    assert "defined_risk_income_spread" in expression_bucket_ids
    assert "volatility_event_option" in expression_bucket_ids
    assert "core_stock_accumulation" in expression_bucket_ids
    assert "strong_theme_catalyst_long_stock" not in strategy_ids
    assert "strong_theme_no_clear_near_term_sell_put" not in strategy_ids
    assert "valuation_repair_quality_software_sell_put" not in strategy_ids


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
- Include all 15 broad tactical strategies, the 4 eval-derived playbook strategies, and the 5 initial strategy expression buckets from the design doc, including `defined_risk_directional_option` and `defined_risk_income_spread`.
- Provide `get_initial_strategy_definitions() -> list[dict[str, object]]`.
- Keep thresholds in `config_json` and avoid provider-specific code.
- Include `strategy_layer`, `allowed_trade_identities`, `allowed_instruments`, `allowed_option_strategy_types`, `required_option_leg_fields`, and option policy fields where relevant.

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
    assert "tactical_stock_trade" in TRADE_IDENTITIES
    assert "tactical_option_trade" in TRADE_IDENTITIES
    assert "risk_hedge_overlay" in TRADE_IDENTITIES
    assert "watch_only" in TRADE_IDENTITIES


def test_core_holding_is_separate_from_short_term_pool():
    policy = get_trade_identity_policy("core_holding")
    assert policy.instrument == "stock"
    assert policy.portfolio_pool == "core"
    assert policy.can_be_sold_by_short_term_signal is False


def test_tactical_option_trade_requires_leg_based_risk():
    policy = get_trade_identity_policy("tactical_option_trade")
    assert policy.instrument == "paper_option_strategy"
    assert policy.requires_option_legs is True
    assert policy.requires_max_loss is True
    assert policy.requires_assignment_plan_when_short_options is True


def test_risk_hedge_overlay_is_risk_manager_owned():
    policy = get_trade_identity_policy("risk_hedge_overlay")
    assert policy.instrument == "paper_option_hedge"
    assert policy.portfolio_pool == "risk_hedge"
    assert policy.generated_by == "risk_manager"
    assert policy.counts_toward_strategy_win_rate is False
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
- identities: `core_holding`, `tactical_stock_trade`, `tactical_option_trade`, `risk_hedge_overlay`, `watch_only`
- fields for instrument, portfolio pool, default horizon, sizing policy, exit policy, option-leg requirements, max-loss requirements, assignment requirements when short options are present, hedge ownership, whether the identity counts toward strategy win rate, and whether short-term signals can sell the position

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
- `SourceIngestionRun`
- `MacroSnapshot`
- `MacroReadthroughEvent`
- `CalendarEvent`
- `PortfolioEventRiskAssessment`
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
        allowed_common_stock_direction="long_only",
        config_json={"required_signals": ["opening_gap_pct"]},
        lifecycle_status="active",
        source="seed",
        is_active=True,
    )
    assert row.strategy_id == "gap_and_go_v1"
    assert row.lifecycle_status == "active"
    assert row.allowed_common_stock_direction == "long_only"
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

- `UniverseFilterConfig`
  - `universe_filter_config_id UUID pk`
  - `name String(128)`
  - `version String(32)`
  - `min_price Numeric` nullable
  - `min_avg_dollar_volume Numeric` nullable
  - `included_sectors_json JSONB` nullable
  - `excluded_sectors_json JSONB` nullable
  - `included_industries_json JSONB` nullable
  - `excluded_industries_json JSONB` nullable
  - `included_exchanges_json JSONB` nullable
  - `asset_types_json JSONB` defaulting to common stock
  - `manual_include_tickers_json JSONB` nullable
  - `manual_exclude_tickers_json JSONB` nullable
  - `is_active Bool`
- `UniverseSnapshot`
  - `snapshot_id UUID pk`
  - `trade_date Date index`
  - `universe_filter_config_id fk universe_filter_configs`
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
- `SourceIngestionRun`
  - `source_ingestion_run_id UUID pk`
  - `source_family String(64)` with values such as `market_data`, `news`, `sec_filings`, `insider_form4`, `fundamentals`, `earnings_calendar`, `option_chain`, `macro_calendar`
  - `run_type String(32)` with values such as `scheduled_pre_open`, `scheduled_post_close`, `intraday_inline`, `intraday_targeted`, `manual_smoke`
  - `scope_json JSONB`
  - `provider String(64)` nullable
  - `coverage_json JSONB`
  - `as_of DateTime`
  - `started_at DateTime`
  - `completed_at DateTime` nullable
  - `status`
  - `error_message Text`
- `MacroSnapshot`
  - `macro_snapshot_id UUID pk`
  - `trade_date Date index`
  - `as_of DateTime`
  - `regime_json JSONB`
  - `indicators_json JSONB`
  - `status`
- `MacroReadthroughEvent`
  - `readthrough_event_id UUID pk`
  - `macro_snapshot_id fk macro_snapshots` nullable
  - `trade_date Date index`
  - `source_ticker String(16) index`
  - `source_event_type String(64)` with values such as `earnings_release`, `earnings_transcript`, `guidance`, `customer_commentary`
  - `readthrough_scope String(64)` with values such as `sector`, `theme`, `peer_group`, `supply_chain`, `customer_chain`
  - `readthrough_direction String(16)` with values `positive/negative/mixed/neutral`
  - `strength_score Numeric`
  - `mechanisms_json JSONB`
  - `affected_themes_json JSONB`
  - `relationship_types_json JSONB`
  - `source_refs_json JSONB`
  - `valid_until DateTime`
  - `requires_target_confirmation Bool`
- `CalendarEvent`
  - `calendar_event_id UUID pk`
  - `source_provider String(64)`
  - `source_url Text` nullable
  - `event_type String(64)` with values such as `macro_release`, `fed_event`, `treasury_auction`, `own_earnings`, `related_company_earnings`, `market_structure`, `option_expiry`
  - `event_name String(255)`
  - `scheduled_at DateTime index`
  - `timezone String(64)`
  - `global_importance String(16)` with `critical/high/medium/low`
  - `source_ticker String(16)` nullable
  - `affected_tickers_json JSONB`
  - `affected_sectors_json JSONB`
  - `affected_themes_json JSONB`
  - `raw_payload_json JSONB`
  - `dedupe_key String(255)` unique
- `PortfolioEventRiskAssessment`
  - `event_risk_assessment_id UUID pk`
  - `calendar_event_id fk calendar_events`
  - `trade_date Date index`
  - `portfolio_snapshot_id UUID` nullable
  - `portfolio_risk_level String(16)` with `critical/high/medium/low/none`
  - `relevance_score Numeric`
  - `affected_positions_json JSONB`
  - `affected_candidates_json JSONB`
  - `affected_option_strategies_json JSONB`
  - `risk_mechanisms_json JSONB`
  - `lookahead_reason Text`
  - `suggested_action_type String(64)` nullable
  - `is_displayed Bool`
- `SignalSnapshot`
  - `signal_snapshot_id UUID pk`
  - `universe_snapshot_id fk`
  - `ticker String(16)`
  - `trade_date Date index`
  - `snapshot_type String(32)` with values such as `pre_open`
  - `signals_json JSONB`
  - `missing_signals_json JSONB`
  - `stale_signals_json JSONB`
  - `source_freshness_json JSONB`
  - `status`
- `StrategyDefinition`
  - `strategy_definition_id UUID pk`
  - `strategy_id String(64)`
  - `version String(16)`
  - `display_name String(128)`
  - `strategy_layer String(32)` with values such as `tactical_pattern`, `expression_bucket`
  - `typical_horizon String(32)`
  - `allowed_common_stock_direction String(16)` defaulting to `long_only`
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
  - `last_evaluated_at DateTime` nullable
  - `dismissed_at DateTime` nullable
  - `status String(32)` with values `active/running/failed/dismissed/cancelled`
  - `result_status String(32)` nullable with values `actionable_trade/catalyst_watch/ordinary_watch/no_trade/blocked_by_risk/blocked_by_missing_data`
  - `result_decision_id UUID` nullable
  - `source_context_json JSONB`
  - `error_message Text`
- `TradeClassification`
  - `trade_classification_id UUID pk`
  - `candidate_id fk candidate_scores` nullable for current-position classifications
  - `ticker String(16)`
  - `trade_date Date index`
  - `trade_identity String(64)` with `core_holding/tactical_stock_trade/tactical_option_trade/risk_hedge_overlay/watch_only`
  - `expression_bucket_id String(64)` nullable
  - `watch_type String(32)` nullable with `catalyst_watch/ordinary_watch`
  - `instrument_type String(32)`
  - `portfolio_pool String(32)`
  - `horizon_policy String(64)`
  - `exit_policy_json JSONB`
  - `classification_reason Text`
- `RiskAppetiteProfile`
  - `risk_appetite_profile_id UUID pk`
  - `risk_appetite String(32)` with `conservative/balanced/aggressive`
  - `profile_version String(32)`
  - optional `advanced_overrides_json JSONB`
  - `is_active Boolean`
- `RiskLimitConfig`
  - generated versioned JSON config, source `risk_appetite_profile_id`, resolver version, and `is_active`
- `PortfolioRiskSnapshot`
  - portfolio-level exposure JSON before/after decisions/fills, including active risk appetite, generated risk config id/version, unified margin-account equity, buying power, excess liquidity, stock/option margin requirements, total margin requirement, margin model profile/version, margin requirement source, estimated initial/maintenance requirements, and broker-reported requirements when available
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
- check constraints for manual ticker request mode/status/result status fields, including `active/running/failed/dismissed/cancelled`
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

**Goal:** Build a deterministic pre-market universe using user-editable liquidity and sector filters, normalized future event calendar, portfolio event-risk scoring, and full signal snapshot pipeline with benchmark/peer relative-strength inputs plus Postgres-backed insider, SEC, news, fundamentals, event/calendar, options, macro/sector/theme read-through, and existing research context signals. No strategy matching or trading decisions yet.

**Files:**
- Create: `src/trading/manual_requests.py`
- Create: `src/trading/universe.py`
- Create: `src/trading/signals.py`
- Create: `src/trading/signal_sources.py`
- Create: `src/trading/event_calendar.py`
- Create: `src/trading/pipeline.py`
- Create: `src/trading/repository.py`
- Modify: `src/tools/market_data/types.py` if the provider protocol needs universe support
- Modify: `src/tools/market_data/alpaca_provider.py` to add an asset/universe method if needed
- Test: `tests/trading/test_universe.py`
- Test: `tests/trading/test_manual_requests.py`
- Test: `tests/trading/test_signals.py`
- Test: `tests/trading/test_signal_sources.py`
- Test: `tests/trading/test_event_calendar.py`
- Test: `tests/trading/test_relative_strength.py`
- Test: `tests/trading/test_pipeline.py`

Implementation notes:

- Add a `UniverseProvider` interface with a test fake and an Alpaca implementation.
- Include a config fallback `TRADING_UNIVERSE_SYMBOLS` for local/dev tests.
- Implement active `UniverseFilterConfig` loading and updates with user-editable liquidity thresholds, sector/industry include/exclude lists, exchange/asset filters, and manual include/exclude ticker overrides.
- Default to common stocks with configurable minimum price and minimum average dollar volume filters; persist excluded symbols with reasons such as `below_min_price`, `below_min_dollar_volume`, `sector_excluded`, `not_common_stock`, or `manual_exclude`.
- Persist included and excluded symbols with exclusion reasons.
- Add `ManualTickerRequestService` for creating, dismissing, cancelling, and loading active manual requests.
- Merge active manual requests into the signal snapshot job even when the ticker did not pass the scanner ranking threshold.
- Manual requests stay active across trading days until dismissed by the user; update `last_evaluated_at` and latest result fields on each evaluation.
- Manual requests can bypass scanner selection threshold, but not ticker validation, market-data availability, liquidity rules, or later risk checks.
- Support `review_only` and `paper_trade_eligible` request modes.
- Build signal snapshots from existing daily bars/context where possible.
- Add source-ingestion run metadata for every scheduled or targeted refresh so freshness decisions are replayable.
- Add `SignalSourceRepository` or equivalent adapters that read normalized Postgres-backed sources for insider transactions/Form 4/SEC filings, news and analyst events, fundamentals/valuation, earnings/event calendar, option-chain snapshots, macro/sector/theme read-through events, and existing research/global-context artifacts.
- Add an `EventCalendarService` that normalizes future macro/economic/Fed events and earnings calendar rows from configured providers into `calendar_events`.
- Add a deterministic `PortfolioEventRiskScorer` that maps events to current positions, core holdings, top candidates, active manual requests, paper option expiries, sectors/themes, and strategy holding periods.
- Hide low-importance events by default when `PortfolioEventRiskScorer` finds no relevant portfolio/candidate/theme exposure; persist them only for audit if ingested.
- Implement dynamic event lookahead: intraday/1-3 day trades show same-day plus next 5 trading days; tactical stock trades show relevant events through intended horizon; option trades show events through expiry plus buffer; core holdings show high/critical macro and own/major-peer earnings 3-6 months out.
- Prefer normalized Postgres rows over ad hoc live provider calls. Provider calls are allowed only through controlled refresh/fallback adapters and must record attempted source and freshness.
- Store source provenance for each signal, including `source`, `source_table` or provider name, `as_of` / `published_at` / `filing_date` where relevant, and missing/stale status.
- Store pre-open signal snapshots as the daily baseline with `snapshot_type = "pre_open"`, `source_freshness_json`, `missing_signals_json`, and `stale_signals_json`.
- Implement source freshness SLA config for each source family. Low-frequency fields can be carried forward when inside SLA; stale required fields must downgrade or block candidate outputs.
- Add derived insider/SEC signals such as net buy value, cluster buy count, officer/director buy flags, sale concentration, and recent filing freshness.
- Add derived news/fundamental signals such as high-signal news count, analyst revision score, guidance/customer/regulatory flags, valuation percentile, margin trend, quality score, and market-cap/liquidity quality.
- Add own-company earnings signals when the reporting ticker equals the snapshot ticker: earnings event type, reported time, EPS/revenue surprise, guidance revision, segment growth, margin change, transcript availability/sentiment/key topics, and post-earnings analyst revisions. These may populate target-company catalyst fields when evidence supports it.
- Add macro/sector/theme read-through fields from peer, customer, supplier, competitor, or sector-leader earnings. These fields are exposure context, not target-company catalyst fields, and must not populate `fresh_catalyst_type` or `direct_negative_catalyst_type` for the target ticker by themselves.
- Model the read-through schema with source ticker, affected theme/scope, relationship type, direction, strength, mechanism, source release/transcript provenance, validity window, and target confirmation requirement.
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
- Select one primary tactical strategy and one expression bucket per ticker/action before trade classification.
- Persist selected primary strategy context in `TradeClassification` and later `TradingDecision` context so attribution does not drift.
- Classify each candidate into portfolio-pool trade identities: `core_holding`, `tactical_stock_trade`, `tactical_option_trade`, or `watch_only`. `risk_hedge_overlay` is generated by `RiskManager`, not candidate scoring.
- Treat trade identity as a required field consumed by trading, sizing, risk, options, reflection, and UI; do not implement it as a separate strategy or standalone trade generator.
- Distinguish `catalyst_watch` from ordinary neutral/watch output as `watch_type` under `trade_identity = "watch_only"` when direction is uncertain but move potential is high.
- Compute confidence calibration inputs by strategy, expression bucket, trade identity, direction, catalyst type, benchmark/peer outperformance, and available historical outcomes.
- Downgrade macro-only bearish candidates to risk warnings or no-trade; do not create single-name bearish candidates from macro alone.
- Apply bearish evidence as an embedded gating rule in candidate scoring and confidence calibration; do not create a separate bearish signal function that bypasses the normal strategy/risk flow.
- Preserve rejected candidates with `rejection_reason` when they are useful for later reflection.
- Update manual request `result_status` to `catalyst_watch`, `ordinary_watch`, `no_trade`, or `blocked_by_missing_data` when no trading decision will be requested.
- Do not call `TradingPipeline` yet.

Stop after PR 3 for review/merge.

---

## PR 4: Position Sizing + Portfolio Risk Manager

**Goal:** Add deterministic sizing, simple risk appetite presets, generated effective risk configs, portfolio factor concentration controls, and embedded bearish-evidence gating.

**Files:**
- Create: `src/trading/risk.py`
- Create: `src/trading/risk_config.py`
- Create: `src/trading/position_sizing.py`
- Modify: `src/trading/repository.py`
- Test: `tests/trading/test_position_sizing.py`
- Test: `tests/trading/test_risk_manager.py`

Implementation notes:

- Implement `RiskAppetiteProfile` with three presets: `conservative`, `balanced`, and `aggressive`; default to `balanced`.
- Implement deterministic `RiskConfigResolver` that converts the active risk appetite preset into a generated `RiskLimitConfig`. Persist both the user-facing preset and the generated config with resolver version for audit/replay.
- Keep detailed risk-limit numbers out of the default UI/operator config. Allow optional advanced overrides only as explicit metadata, not as the normal workflow.
- Calculate factor exposure by sector, strategy, horizon, direction, beta bucket, volatility bucket, liquidity bucket, event type, and macro sensitivity.
- Add unified margin-account risk fields and limits: account equity, cash balance, buying power, excess liquidity, stock margin requirement, option margin requirement, total margin requirement, buying-power effect, margin model profile/version, margin requirement source, estimated initial/maintenance requirement, and broker-reported requirement when imported.
- Add default conservative broker-profile margin settings: `estimated_fidelity_like_conservative_v1`, Reg T style stock initial requirement, house maintenance requirement assumptions, unknown-marginability fallback, concentration/volatility/liquidity add-ons, and conservative option margin rules.
- Enforce invariant hard safety rails across all presets: missing/stale signals, missing option risk metadata, unestimable margin, assignment over-concentration, macro-only bearish single-name shorts, and core-holding tactical exits must still reduce/reject/downgrade even under `aggressive`.
- Include explicit risk rules that prevent macro-only bearish evidence from creating high-confidence single-name shorts.
- Apply bearish evidence through existing sizing/reduce/reject paths, not through a standalone bearish trading module.
- Keep core-holding risk rules separate from short-term catalyst trade rules.
- Implement reduce/reject behavior for concentration caps.
- Persist `position_sizing_decisions`, `portfolio_risk_snapshots`, and `risk_factor_exposures`.
- Keep this independent of LLM and paper broker.

Stop after PR 4 for review/merge.

---

## PR 5: Trading Decisions + Paper Stock Broker + Portfolio State

**Goal:** Add paper common-stock trading behavior and the unified simulated margin account after candidate scoring and risk approval.

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
- Persist the full decision context snapshot, including trade identity, expression bucket, benchmark/peer context, confidence basis, `selection_source`, and `manual_request_id`.
- Enforce long-only common-stock paper orders in V2. Bearish evidence may reduce/reject/downgrade, but direct short-stock paper orders should be rejected before paper order creation.
- Model stocks and options in one simulated margin account. Stock fills must update cash balance, stock market value, account equity, stock margin requirement, total margin requirement, buying power, excess liquidity, margin model profile/version, and margin requirement source in `portfolio_snapshots`.
- Implement `estimated_fidelity_like_conservative_v1` as the default estimated model: long marginable stock uses a 50% initial requirement, maintenance uses at least a 30% base plus configured house/concentration/volatility/liquidity add-ons, and unknown/non-marginable/restricted/low-priced securities fall back to a 100% requirement. Do not claim exact Fidelity matching unless broker-observed values are imported.
- Reject or reduce stock orders when unified account buying power, total margin requirement, or excess-liquidity limits would be violated.
- Enforce manual request mode: `review_only` can produce an actionable explanation but must not create a paper order; `paper_trade_eligible` can create a paper order only after normal risk approval.
- Update linked manual request `result_status` to `actionable_trade`, `blocked_by_risk`, `no_trade`, `catalyst_watch`, or `ordinary_watch`.
- Risk manager is the final gate before paper order creation.
- Paper broker must be idempotent for a trade date / ticker / strategy / action.

Stop after PR 5 for review/merge.

---

## PR 6: Paper Options Strategy Layer + Assignment Risk

**Goal:** Add paper/simulation-only leg-based option strategy decisions, single-leg and multi-leg option positions, strategy-level option risk, and worst-case assigned-portfolio risk management when assignment is possible.

**Files:**
- Create: `src/trading/options_strategy.py`
- Create: `src/trading/option_risk.py`
- Create: `src/trading/paper_option_broker.py`
- Modify: `src/trading/repository.py`
- Modify: `src/trading/portfolio.py`
- Modify: `src/trading/risk.py`
- Modify: `src/agents/trading_schemas.py`
- Add ORM models/migration for `option_strategy_decisions`, `option_strategy_legs`, `risk_hedge_decisions`, `paper_option_orders`, `paper_option_positions`, `option_risk_snapshots`
- Test: `tests/trading/test_options_strategy.py`
- Test: `tests/trading/test_option_risk.py`
- Test: `tests/trading/test_paper_option_broker.py`
- Test: `tests/trading/test_option_repository.py`

Implementation notes:

- Support generic option actions: `open_option_strategy`, `close_option_strategy`, `roll_option_strategy`, `adjust_option_strategy`, and `avoid_event_option`.
- Support only the initial V2 option strategy whitelist: `long_call`, `long_put`, `put_credit_spread`, `call_credit_spread`, `long_straddle`, and `long_strangle`.
- Reject or downgrade any non-whitelisted `option_strategy_type`, including standalone `short_put`, `covered_call`, `collar`, debit spreads, naked short options, short straddles, short strangles, and custom multi-leg structures.
- Require every option plan to include `option_strategy_type`, legs with call/put side, buy/sell side, quantity, strike, expiry, DTE, Greeks, IV rank/percentile, bid/ask/mid/chosen price, net debit/credit, max loss, max profit when definable, breakevens, margin requirement, buying-power effect, margin model profile/version/source, deterministic `strategy_pairing_method` for multi-leg strategies, event-through-expiry flags, roll/close/adjust conditions, and assignment plan when short options are present.
- Reject or downgrade to watch when required option chain, leg pricing, Greeks, max-loss, margin, buying-power, event, or assignment metadata is missing.
- Calculate strategy-level option risk and current portfolio exposure for all option strategies.
- Calculate worst-case assigned exposure where assignment-capable short option legs convert into stock exposure at strike.
- Apply option risk caps by max loss, margin requirement, buying-power effect, Greeks, ticker, sector/theme, expression bucket, high-beta AI/semis/space cluster, correlation cluster, and assignment-capable notional.
- Apply option margin requirements and buying-power effects to the same simulated margin account used by paper stock positions; do not maintain a separate option buying-power pool.
- Implement option margin with conservative broker-profile behavior for the whitelist: long calls, long puts, long straddles, and long strangles consume full net premium plus fees; defined-risk credit spreads consume max loss or the broker-profile requirement if higher; structures outside the whitelist are blocked before margin approval.
- Persist broker-observed margin fields separately if a future broker feed or calculator import exists; until then, mark all requirements as `simulated_formula` and use the conservative estimate.
- Keep the options layer paper/simulation-only; no real broker integration.
- Support paper-only risk hedge overlay orders generated by `RiskManager` with `trade_identity = "risk_hedge_overlay"`. Persist them separately from tactical option trades and exclude them from strategy win-rate attribution.
- Persist option decisions and rejected plans because reflection needs to evaluate missed option trades, avoided max-loss risk, hedge effectiveness, and avoided assignment risk.

Stop after PR 6 for review/merge.

---

## PR 7: Intraday Signal Refresh + News Alerts + Rebalance

**Goal:** Refresh intraday signals and news hourly during regular trading hours using the pre-open baseline snapshot, source freshness gates, and targeted source refreshes, then trigger risk-gated intraday rebalance actions for material signal changes or high-impact positive/negative events.

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
- Refresh intraday price/volume/liquidity signals, VWAP/opening-range/gap signals, relative strength vs benchmarks/peers, option marks, per-leg Greeks, max-loss/margin/buying-power changes, assignment-risk deltas when relevant, news/event signals, target-company earnings release/transcript/guidance updates, peer/sector-leader earnings read-through updates, and freshness checks for low-frequency insider/SEC/fundamental/event sources.
- Persist intraday signal snapshots with deltas vs the morning snapshot and previous hourly snapshot.
- Define material-change thresholds that can trigger rebalance even without a new headline.
- Load the pre-open baseline `signal_snapshot_id` and previous hourly snapshot for every ticker in the intraday scope.
- Before building each intraday snapshot, compute a freshness plan by source family and ticker/event scope. Run inline required refreshes for price/volume, intraday relative strength, scoped news/events, and open option marks; run targeted refreshes for SEC filings, own earnings transcripts, or peer read-through only when relevant.
- Do not rerun the full universe scan or full source-ingestion set during hourly refresh. Carry forward low-frequency baseline fields when they remain inside freshness SLA and mark them as `carried_forward_from_baseline`.
- Persist intraday snapshot fields for `baseline_signal_snapshot_id`, `previous_intraday_snapshot_id`, `refreshed_signals_json`, `carried_forward_signals_json`, `delta_vs_baseline_json`, `delta_vs_previous_json`, and `source_freshness_json`.
- Block or downgrade actions when required source freshness is insufficient: no new add when high-frequency price/news is stale, no option open/roll when option data is stale/missing, and no high-confidence bearish action when direct-negative-catalyst checks are missing.
- Use deterministic dedupe keys so repeated headlines do not trigger repeated rebalances.
- Load intraday classification/rebalance prompts through `PromptRegistry` and persist prompt run/usage records for every LLM call.
- Normalize alert fields: ticker or source ticker, event type, sentiment, severity, source, published time, summary, strategy relevance, affected positions/candidates/themes, read-through relationship when applicable, and action-required flag.
- Severity levels are `critical`, `high`, `medium`, `low`.
- Critical/high alerts can propose `hold`, `reduce`, `exit`, `add`, `close_option_strategy`, `roll_option_strategy`, `adjust_option_strategy`, or `avoid_event_option` for whitelisted paper option strategies.
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
- Attribute trades against benchmarks and decision-time peer baskets over each selected strategy's configured holding horizon. Daily reflection should record interim mark-to-market for open trades and final horizon outcome when the trade closes or the intended horizon expires.
- Analyze bullish catalyst trades separately from bearish/risk-off calls.
- Evaluate confidence calibration by strategy, expression bucket, trade identity, direction, catalyst type, sector/theme, and market regime.
- Evaluate whether `catalyst_watch` would have been more useful than ordinary neutral/watch.
- Evaluate whether user-pinned tickers exposed scanner misses or mostly confirmed no-trade discipline.
- Learning factors start as `candidate`, `active`, `suppressed`, or `retired`.
- New learning factors default to `active` immediately so the next trading run can adapt; any reflection output that would weaken hard safety rails, widen universe filters, or increase risk budgets must become a strategy/config proposal instead of an automatically active learning factor.
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
- Show live alerts, material signal changes, positions, trades, trade identity, expression bucket, paper options, hedge overlays, candidates, risk exposure, post-close reflection, learning factors, and macro regime.
- In `Candidates`, show and edit the active universe filter: min price, min average dollar volume, included/excluded sectors or industries, exchange/asset eligibility, and manual include/exclude ticker overrides.
- In `Risk & Macro`, show the active risk appetite preset (`conservative`, `balanced`, or `aggressive`), generated risk config version, and binding constraints; hide detailed generated limits behind an advanced/debug view.
- In `Risk & Macro`, show a portfolio-aware upcoming event calendar: future macro events, Fed/rates events, own-company earnings, related-company earnings read-through, option-relevant events, and market-structure events that pass the display threshold.
- Each event row should show scheduled date/time, event type, global importance, portfolio risk level, affected ticker/position/option strategy, affected sector/theme, risk mechanism, lookahead reason, suggested action type, and source/provider.
- Do not show irrelevant low-importance events by default. The display window must be dynamic by holding period and event importance rather than a fixed "next N months" list.
- Add trade detail drill-down with signal snapshots, strategy scores, selected strategy, trade identity, LLM decision JSON, risk decision, order/fill state, exit plan, invalidators, and post-close outcome.
- Add a pinned-review form for ticker, reason, mode (`review_only` / `paper_trade_eligible`), and priority. Manual requests stay active until dismissed, so the UI should provide a dismiss action instead of default end-of-day expiry.
- Show pinned-review results with request status, result status, strategy match, trade identity, confidence basis, risk result, and linked trading decision if any.
- Show benchmark/peer outperformance and confidence basis for selected and rejected candidates.
- Show option strategy type, per-leg call/put side, buy/sell side, strike, expiry, DTE, Greeks, IV rank, bid/ask/mark, net debit/credit, max loss, breakevens, margin requirement, buying-power effect, earnings/event date, roll/close/adjust plan, and assignment plan when relevant.
- Show strategy proposals, shadow/experimental strategies, and promotion/retirement status.
- Show strategy performance by win rate, PnL, alpha vs benchmarks/decision-time peer basket over each strategy's configured horizon, drawdown, sample size, market regime, and bullish/bearish split.
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
- Add standalone smoke mode for active universe filter loading plus a fixture-backed manual ticker request in `review_only` mode that remains active until dismissed.
- Add standalone smoke mode for paper option decisions, option legs, option-risk snapshots, and assignment-risk snapshots using fixture data.
- Add standalone smoke mode for hourly intraday signal/news refresh using a fixed tiny ticker set or fixture mode.
- Add standalone smoke mode for strategy proposal creation from a fixed reflection fixture.
- Document Postgres persistent disk verification with `SHOW data_directory;`.
- Keep Docker Compose infrastructure.

Stop after PR 11 for review/merge.
