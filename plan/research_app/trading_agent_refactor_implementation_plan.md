# Trading Agent Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the V2 relative-strength catalyst trading workflow in reviewable PR slices, starting with a verifiable MVP of universe -> point-in-time signal snapshots -> strategy scoring -> historical replay/outcome evaluation before adding paper trading, options, intraday refresh, reflection, learning adaptation, strategy evolution, and UI.

**Architecture:** Keep Python orchestration as the source of truth. LLM calls are bounded, Pydantic-validated, retried on schema failure, and downgraded to safe fallbacks when validation still fails. Each pipeline persists point-in-time snapshots with `event_time`, `published_at`, `ingested_at`, and `available_for_decision_at` so candidate selection, trade identity, confidence calibration, replay outcomes, risk decisions, paper stock/options orders, worst-case assignment exposure, portfolio state, prompt versions, LLM calls, reflection, and learning factors can be audited without lookahead.

**Tech Stack:** Python, SQLAlchemy, Alembic, Postgres JSONB, FastAPI/Jinja, APScheduler, pytest, existing market/news/global-context providers.

---

## Execution Rules

- Each PR slice stops after verification. Do not begin the next slice until the user has reviewed and merged.
- Use TDD for implementation code: write failing tests, run targeted tests, implement, rerun targeted tests, then run the broader relevant suite.
- After every completed implementation slice, update `plan/research_app/trading_agent_refactor_progress_tracker.md`.
- For major refactor slices, update `documents/repo_overview.md`. If the file is absent, create it with the current architecture summary.
- For Python commands, run `source ~/.venv/bin/activate` first.
- Any DB/API smoke test must be standalone and rate-limit conscious.
- Unit tests must use fake providers. Integration tests that touch external-provider behavior should use recorded `vcrpy` cassettes or equivalent fixtures. Live provider smoke tests are opt-in and must not block ordinary CI.
- Deployment changes must preserve Docker Compose and persistent disk Postgres requirements.

## PR Slice Overview

1. **PR 1a: Minimal Trading Foundation**
   Add only the minimum durable foundation: strategy definition schema, prompt registry/schema, portfolio-pool trade identity enums, and a versioned in-code seed catalog for the 15 broad tactical strategies, 4 eval-derived playbook strategies, and 5 initial strategy expression buckets from the design doc, including defined-risk option expressions. No universe, source ingestion, relationship graph, scheduler, API calls, or trading behavior yet.
2. **PR 1b: Portfolio Intents + Relationship Graph Schema**
   Add `portfolio_intents`, `ticker_relationships`, `peer_baskets`, and `theme_taxonomy` plus focused services/tests for core-holding eligibility and structured peer/theme read-through inputs. No signal pipeline or strategy scoring yet.
3. **PR 2: Provider Resilience + Three-Family Point-in-Time Signal MVP**
   Add provider adapter guardrails, fake providers, request budgeting/rate-limit/backoff/circuit-breaker metadata, user-editable liquidity/sector universe filters, manual ticker request ingestion, and deterministic pre-open signal snapshots across MVP technical, fundamental, and events/news signal families.
4. **PR 3: Strategy Matching + Historical Replay Outcome Evaluator**
   Match scanner and manual-request symbols to strategy definitions and persist ranked candidates with strategy horizon/evidence, source attribution, primary strategy selection, trade identity classification, catalyst-watch vs ordinary-watch distinction, confidence-calibration inputs, and deterministic replay/outcome evaluation against `SPY`, `QQQ`, sector/theme ETF, and decision-time peer baskets.
5. **PR 4: Position Sizing + Portfolio Risk Manager**
   Add deterministic sizing, risk appetite presets, generated risk configs, risk factor exposure calculation, unified margin-account buying-power caps, conservative broker-profile margin estimates, concentration caps, embedded bearish-evidence gating, and reduce/reject decisions.
6. **PR 5: Trading Decision Agent Guardrails**
   Add bounded trading agent output with Pydantic schema validation, retry, safe fallback, manual request mode gating, prompt/schema persistence, and no paper order side effects yet.
7. **PR 6: Paper Stock Broker + Portfolio State**
   Add paper stock orders/executions, positions, and unified simulated margin-account portfolio snapshots with margin model profile/source metadata.
8. **PR 7: Paper Options Strategy Layer + Assignment Risk**
   Add paper-only leg-based option strategy decisions, option legs, option orders/positions, open/close/roll/adjust/avoid-event actions, an initial whitelist of long call/put, credit spread, long straddle, and long strangle strategies, strategy-level option risk, conservative option margin requirements, and worst-case assigned-portfolio risk checks when assignment is possible.
9. **PR 8: Intraday Signal Refresh + News Alerts + Rebalance**
   Add hourly intraday signal refresh, normalized alerts, material signal-change detection, and risk-gated intraday rebalance decisions for stocks, paper option strategies, and hedge overlays.
10. **PR 9: Reflection + Learning Factors**
   Add post-close reflection with highest-quality model routing, Pydantic validation/fallback, learning factor lifecycle defaulting to candidate/observation, replay outcome consumption, benchmark/peer attribution, bullish/bearish calibration, paper options attribution, and strategy proposal hints.
11. **PR 10: Strategy Evolution + Dynamic Strategy Catalog**
   Convert repeated learning patterns into proposed strategies, shadow-test them, and promote/retire strategy definitions.
12. **PR 11: Today Dashboard UI**
   Add `/today`, pinned review, candidate, trade, options, risk exposure, reflection, and learning views.
13. **PR 12: Scheduler, Smoke Tests, Deploy Docs**
   Wire daily jobs, standalone smoke scripts, and deployment/runbook docs.

---

## PR 1a: Minimal Trading Foundation

**Goal:** Add the smallest durable strategy/prompt foundation without changing runtime behavior.

**Files:**
- Create: `src/db/models/trading.py`
- Modify: `src/db/models/__init__.py`
- Create: `alembic/versions/005_trading_minimal_foundation_tables.py`
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

### Task 1.4: Minimal ORM Models

- [ ] **Step 1: Write failing model tests**

Create `tests/db/test_trading_models.py` to instantiate only the PR 1a schema:

- `StrategyDefinition`
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
  - `validation_errors_json JSONB`
  - `fallback_action String(64)` nullable
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

Add a simple test in `tests/db/test_trading_models.py` or a new `tests/db/test_trading_migration.py` that reads `alembic/versions/005_trading_minimal_foundation_tables.py` and asserts table names exist. Keep it lightweight; this repo does not currently run migrations against Postgres in unit tests.

- [ ] **Step 2: Create migration**

Create `alembic/versions/005_trading_minimal_foundation_tables.py` with:

- `down_revision = "004"`
- create/drop only PR 1a tables: `strategy_definitions`, `llm_prompt_templates`, `llm_prompt_runs`, and `llm_usage_events`
- indexes for strategy id/version, prompt id/version, pipeline name, and status
- check constraints for strategy lifecycle status fields
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

- PR 1a status
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

Stop after PR 1a. Do not implement PR 1b until the user has reviewed and merged.

---

## PR 1b: Portfolio Intents + Relationship Graph Schema

**Goal:** Add core-holding intent configuration and structured peer/theme relationship data without touching signal generation or trading behavior.

**Files:**
- Modify: `src/db/models/trading.py`
- Modify: `src/db/models/__init__.py`
- Create: `alembic/versions/006_portfolio_intents_relationship_graph.py`
- Create: `src/trading/portfolio_intents.py`
- Create: `src/trading/relationships.py`
- Create: `tests/trading/test_portfolio_intents.py`
- Create: `tests/trading/test_relationships.py`
- Modify: `tests/db/test_trading_models.py`
- Modify: `plan/research_app/trading_agent_refactor_progress_tracker.md`

### Task 1b.1: Portfolio Intents

- [ ] **Step 1: Write failing portfolio intent tests**

Create `tests/trading/test_portfolio_intents.py` with assertions:

```python
from src.trading.portfolio_intents import PortfolioIntentConfig, is_core_holding_approved


def test_core_holding_requires_active_approved_intent():
    intent = PortfolioIntentConfig(
        ticker="GOOGL",
        intent_type="core_growth",
        target_weight=0.08,
        max_weight=0.12,
        lifecycle_status="active",
        add_rules=["add_on_pullback"],
        trim_rules=["trim_above_max_weight"],
        thesis_invalidators=["cloud_growth_breaks_down"],
        allowed_tactical_interactions=["pause_adds", "trim_for_risk"],
    )

    assert is_core_holding_approved("GOOGL", [intent]) is True
    assert is_core_holding_approved("NVDA", [intent]) is False
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_portfolio_intents.py -q
```

Expected: fail because `src.trading.portfolio_intents` does not exist.

- [ ] **Step 3: Implement portfolio intent helpers**

Create `src/trading/portfolio_intents.py` with a frozen dataclass `PortfolioIntentConfig` and pure helper functions for active ticker approval, max-weight lookup, and allowed tactical interactions. Keep it independent of database sessions so PR 1b unit tests remain fast.

- [ ] **Step 4: Verify tests pass**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_portfolio_intents.py -q
```

Expected: pass.

### Task 1b.2: Relationship Graph Helpers

- [ ] **Step 1: Write failing relationship tests**

Create `tests/trading/test_relationships.py` with assertions:

```python
from src.trading.relationships import (
    TickerRelationship,
    build_peer_basket_members,
    relationship_can_be_used_for,
)


def test_relationship_usage_is_explicit():
    rel = TickerRelationship(
        source_ticker="NVDA",
        target_ticker="MU",
        relationship_type="theme_leader",
        confidence=0.8,
        strength_score=0.7,
        allowed_uses=["readthrough", "peer_basket"],
    )

    assert relationship_can_be_used_for(rel, "readthrough") is True
    assert relationship_can_be_used_for(rel, "trade_approval") is False


def test_peer_basket_members_are_deterministic():
    relationships = [
        TickerRelationship("NVDA", "MU", "theme_leader", 0.8, 0.7, ["peer_basket"]),
        TickerRelationship("NVDA", "LITE", "theme_leader", 0.7, 0.6, ["peer_basket"]),
        TickerRelationship("TSLA", "MU", "customer", 0.5, 0.4, ["readthrough"]),
    ]

    assert build_peer_basket_members("NVDA", relationships) == ["LITE", "MU"]
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_relationships.py -q
```

Expected: fail because `src.trading.relationships` does not exist.

- [ ] **Step 3: Implement relationship helpers**

Create `src/trading/relationships.py` with frozen dataclasses for `TickerRelationship`, `PeerBasketDefinition`, and `ThemeTaxonomyNode`. Provide pure deterministic helpers for usage checks and peer basket construction. Do not let these helpers infer relationships from ticker names or LLM text.

- [ ] **Step 4: Verify tests pass**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_relationships.py -q
```

Expected: pass.

### Task 1b.3: ORM Models and Migration

- [ ] **Step 1: Extend model tests**

Update `tests/db/test_trading_models.py` to instantiate:

- `PortfolioIntent`
- `TickerRelationship`
- `PeerBasket`
- `ThemeTaxonomy`

- [ ] **Step 2: Run model tests to verify failure**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/db/test_trading_models.py -q
```

Expected: fail because the PR 1b ORM models do not exist yet.

- [ ] **Step 3: Add ORM models**

Modify `src/db/models/trading.py`:

- `PortfolioIntent`
  - `portfolio_intent_id UUID pk`
  - `ticker String(16) index`
  - `intent_type String(64)` with values such as `core_growth`, `core_index`, `core_theme`, `core_cash_like`
  - `target_weight Numeric`
  - `max_weight Numeric`
  - `add_rules_json JSONB`
  - `trim_rules_json JSONB`
  - `thesis_invalidators_json JSONB`
  - `allowed_tactical_interactions_json JSONB`
  - `lifecycle_status String(32)` with `active/paused/retired`
- `TickerRelationship`
  - `ticker_relationship_id UUID pk`
  - `source_ticker String(16) index`
  - `target_ticker String(16) index`
  - `relationship_type String(64)` with values such as `peer`, `customer`, `supplier`, `competitor`, `sector_leader`, `etf_component`, `theme_leader`, `theme_constituent`
  - `theme_id String(64)` nullable
  - `confidence Numeric`
  - `strength_score Numeric`
  - `valid_from DateTime`
  - `valid_until DateTime` nullable
  - `source_refs_json JSONB`
  - `allowed_uses_json JSONB`
- `PeerBasket`
  - `peer_basket_id UUID pk`
  - `basket_key String(128)`
  - `version String(32)`
  - `trade_date Date index`
  - `members_json JSONB`
  - `construction_method String(64)`
  - `source_refs_json JSONB`
- `ThemeTaxonomy`
  - `theme_id String(64) pk`
  - `display_name String(128)`
  - `parent_theme_id String(64)` nullable
  - `description Text` nullable
  - `lifecycle_status String(32)` with `active/retired`

- [ ] **Step 4: Create migration**

Create `alembic/versions/006_portfolio_intents_relationship_graph.py` with:

- `down_revision = "005"`
- create/drop PR 1b tables only
- indexes for source ticker, target ticker, ticker, theme id, trade date, and lifecycle status
- check constraints for portfolio intent lifecycle, relationship type, theme lifecycle, confidence range, and strength-score range

- [ ] **Step 5: Run targeted tests**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/trading/test_portfolio_intents.py tests/trading/test_relationships.py tests/db/test_trading_models.py -q
```

Expected: pass.

### Task 1b.4: Progress Tracker and Verification

- [ ] **Step 1: Update tracker**

Update `plan/research_app/trading_agent_refactor_progress_tracker.md` with PR 1b status, implemented files, test commands/results, and known gaps.

- [ ] **Step 2: Run broader relevant tests**

Run:

```bash
source ~/.venv/bin/activate
pytest tests/db tests/trading -q
```

Expected: pass.

- [ ] **Step 3: Stop for review**

Stop after PR 1b. Do not implement PR 2 until the user has reviewed and merged.

---

## PR 2: Provider Resilience + Three-Family Point-in-Time Signal MVP

**Goal:** Build a deterministic pre-market signal path that can be replayed without lookahead across three MVP signal families: technical, fundamental, and events/news. This PR includes provider guardrails, user-editable universe filters, active manual requests, point-in-time signal snapshots, portfolio-intent eligibility, and relationship-backed peer basket construction. No options, no LLM calls, no full transcript parsing, no deep SEC/insider interpretation, and no trading decisions yet.

**Files:**
- Create: `src/trading/manual_requests.py`
- Create: `src/trading/provider_resilience.py`
- Create: `src/trading/point_in_time.py`
- Create: `src/trading/universe.py`
- Create: `src/trading/signals.py`
- Create: `src/trading/signal_sources.py`
- Create: `src/trading/fundamental_signals.py`
- Create: `src/trading/event_news_signals.py`
- Create: `src/trading/pipeline.py`
- Create: `src/trading/repository.py`
- Modify: `src/trading/relationships.py`
- Modify: `src/trading/portfolio_intents.py`
- Modify: `src/db/models/trading.py`
- Create: `alembic/versions/007_universe_signal_mvp_tables.py`
- Modify: `src/tools/market_data/types.py` if the provider protocol needs universe support
- Modify: `src/tools/market_data/alpaca_provider.py` to add an asset/universe method if needed
- Test: `tests/trading/test_universe.py`
- Test: `tests/trading/test_provider_resilience.py`
- Test: `tests/trading/test_point_in_time.py`
- Test: `tests/trading/test_manual_requests.py`
- Test: `tests/trading/test_signals.py`
- Test: `tests/trading/test_signal_sources.py`
- Test: `tests/trading/test_fundamental_signals.py`
- Test: `tests/trading/test_event_news_signals.py`
- Test: `tests/trading/test_relative_strength.py`
- Test: `tests/trading/test_pipeline.py`
- Test: `tests/db/test_trading_models.py`

Implementation notes:

- Add a `UniverseProvider` interface with a test fake and an Alpaca implementation.
- Wrap live provider calls with `ProviderResiliencePolicy`: per-provider/per-endpoint rate limiter, batch fetch where available, exponential backoff with jitter, request budget, cache/freshness gate, circuit breaker, and degraded mode.
- Persist every live-provider attempt or cache decision through `ProviderRequestRun`.
- Unit tests must use fake providers. Provider integration tests should use `vcrpy` cassettes or equivalent recorded fixtures. Live provider smoke tests are opt-in only.
- Include a config fallback `TRADING_UNIVERSE_SYMBOLS` for local/dev tests.
- Implement active `UniverseFilterConfig` loading and updates with user-editable liquidity thresholds, sector/industry include/exclude lists, exchange/asset filters, and manual include/exclude ticker overrides.
- Default to common stocks with configurable minimum price and minimum average dollar volume filters; persist excluded symbols with reasons such as `below_min_price`, `below_min_dollar_volume`, `sector_excluded`, `not_common_stock`, or `manual_exclude`.
- Persist included and excluded symbols with exclusion reasons.
- Add `ManualTickerRequestService` for creating, dismissing, cancelling, and loading active manual requests.
- Merge active manual requests into the signal snapshot job even when the ticker did not pass the scanner ranking threshold.
- Manual requests stay active across trading days until dismissed by the user; update `last_evaluated_at` and latest result fields on each evaluation.
- Manual requests can bypass scanner selection threshold, but not ticker validation, market-data availability, liquidity rules, or later risk checks.
- Support `review_only` and `paper_trade_eligible` request modes.
- Use the PR 1b portfolio-intent helpers/service so `core_holding` eligibility later requires an approved active intent instead of LLM inference.
- Use the PR 1b relationship helpers/service and peer-basket builder for structured peer/theme relationships used by relative-strength and replay attribution.
- Add ORM models and migration for PR 2 operational state only:
  - `UniverseFilterConfig`
  - `UniverseSnapshot`
  - `UniverseSymbol`
  - `ManualTickerRequest`
  - `SourceIngestionRun`
  - `ProviderRequestRun`
  - `FundamentalSnapshot`
  - `EventNewsItem`
  - `SignalSnapshot`
- Create `alembic/versions/007_universe_signal_mvp_tables.py` with `down_revision = "006"`.
- `SignalSnapshot` must include `decision_time`, `available_for_decision_at`, `max_input_available_for_decision_at`, `source_record_refs_json`, `source_available_times_json`, `excluded_future_source_count`, and `point_in_time_passed`.
- `ProviderRequestRun` must include provider, endpoint/source family, cache hit/miss, request count, budget remaining, retry/backoff, latency, status, error code, and circuit state.
- `FundamentalSnapshot` stores latest point-in-time provider or existing normalized fundamental rows: ticker, period/as-of metadata, provider, source refs, `event_time`, `published_at`, `ingested_at`, `available_for_decision_at`, raw payload reference, and normalized metrics JSON.
- `EventNewsItem` stores headline/calendar/provider-event rows: ticker, optional source ticker, event type, direction/sentiment, importance, headline/summary, provider/source refs, dedupe key, `event_time`, `published_at`, `ingested_at`, `available_for_decision_at`, and raw payload reference.
- Build signal snapshots from existing daily bars/context and controlled provider/fake-provider source rows across all three MVP families:
  - `technical`: 1d/5d/10d/20d/60d returns, 20/50/200 SMA distance, trend slope, RSI 2/3/14, ATR%, realized volatility percentile, beta proxy vs `SPY`/`QQQ`, drawdown from recent high, distance from 52-week high, relative volume, volume acceleration, dollar volume, gap/premarket gap when available, and relative strength vs `SPY`, `QQQ`, sector/theme ETF, and peer basket.
  - `fundamental`: market-cap bucket, revenue-growth score, margin/profitability trend, quality/profitability score, valuation band or percentile, EV/sales or P/E percentile when available, FCF/profitability proxy when available, short-interest bucket when available, and explicit stale/missing flags.
  - `events_news`: earnings date distance, known event date, own earnings headline result when available, analyst upgrade/downgrade count, price-target revision score, guidance/news flag, customer/order/product/regulatory headline flags, high-signal news counts for 24h/7d, sentiment/direction, catalyst quality score, and direct negative catalyst type.
- Add source-ingestion run metadata for every scheduled or targeted refresh so freshness decisions are replayable.
- Add `SignalSourceRepository` or equivalent adapters that read normalized Postgres-backed sources or fake-provider fixtures for the PR 2 technical, fundamental, and events/news signal set. Deep insider/Form 4, full SEC parsing, full transcripts, options chains, and full macro/sector read-through are deferred until later source-specific PR work.
- Prefer normalized Postgres rows over ad hoc live provider calls. Provider calls are allowed only through controlled refresh/fallback adapters and must record attempted source, freshness, provider request metadata, and degraded-mode state.
- Store source provenance for each signal, including `source`, `source_table` or provider name, `event_time`, `published_at`, `ingested_at`, `available_for_decision_at`, and missing/stale/unavailable status.
- Store pre-open signal snapshots as the daily baseline with `snapshot_type = "pre_open"`, `decision_time`, `source_freshness_json`, `missing_signals_json`, `stale_signals_json`, `source_record_refs_json`, `source_available_times_json`, `max_input_available_for_decision_at`, `excluded_future_source_count`, and `point_in_time_passed`.
- Implement source freshness SLA config for each source family. Low-frequency fields can be carried forward when inside SLA; stale required fields must downgrade or block candidate outputs.
- Verify point-in-time behavior with tests that insert one available source row and one future source row, then assert the future row is excluded from the snapshot.
- Cover the point-in-time exclusion separately for technical market bars, `FundamentalSnapshot`, and `EventNewsItem` rows so each MVP signal family proves it cannot leak future data.
- Defer deep insider/Form 4, full SEC parsing, full earnings-call transcript interpretation, option-chain fields, and full macro/sector read-through to later slices; represent them as explicit missing fields in PR 2 snapshots.
- Add relative-strength fields vs `SPY`, `QQQ`, sector/theme ETF when configured, and peer basket when available.
- Add catalyst quality fields and direct-negative-catalyst fields only from structured event/news source rows; otherwise mark them missing without asking the LLM to infer values.
- Add option-chain placeholder fields as explicitly missing unless a provider exists.
- Store missing signals explicitly.
- Mark manual request results as `blocked_by_missing_data` when required market data cannot be fetched.
- Use no LLM calls.

Stop after PR 2 for review/merge.

---

## PR 3: Strategy Matching + Historical Replay Outcome Evaluator

**Goal:** Convert point-in-time signal snapshots into ranked strategy candidates with strategy-specific horizon/evidence/invalidators, trade identity classification, confidence-calibration inputs, and deterministic outcome evaluation before any paper trading behavior exists.

**Files:**
- Create: `src/trading/strategy_matching.py`
- Create: `src/trading/primary_strategy_selector.py`
- Create: `src/trading/trade_classifier.py`
- Create: `src/trading/confidence_calibration.py`
- Create: `src/trading/outcome_evaluator.py`
- Create: `src/trading/historical_replay.py`
- Modify: `src/trading/repository.py`
- Modify: `src/trading/pipeline.py`
- Modify: `src/db/models/trading.py`
- Create: `alembic/versions/008_strategy_matching_replay_tables.py`
- Test: `tests/trading/test_strategy_matching.py`
- Test: `tests/trading/test_primary_strategy_selector.py`
- Test: `tests/trading/test_trade_classifier.py`
- Test: `tests/trading/test_confidence_calibration.py`
- Test: `tests/trading/test_outcome_evaluator.py`
- Test: `tests/trading/test_historical_replay.py`
- Test: `tests/trading/test_candidate_repository.py`
- Test: `tests/db/test_trading_models.py`

Implementation notes:

- Load active `StrategyDefinition` rows.
- Add ORM models and migration for `StrategyRun`, `CandidateScore`, `TradeClassification`, `HistoricalReplayRun`, and `CandidateOutcomeEvaluation`.
- Create `alembic/versions/008_strategy_matching_replay_tables.py` with `down_revision = "007"`.
- Score only deterministic evidence available in point-in-time eligible `signals_json`.
- Persist one `CandidateScore` per `(ticker, strategy_id)` that passes basic eligibility.
- Persist `selection_source` as `scanner`, `manual_request`, or `watchlist_pin`, and link `manual_request_id` when applicable.
- Select one primary tactical strategy and one expression bucket per ticker/action before trade classification.
- Persist selected primary strategy context in `TradeClassification` and later `TradingDecision` context so attribution does not drift.
- Classify each candidate into portfolio-pool trade identities: `core_holding`, `tactical_stock_trade`, `tactical_option_trade`, or `watch_only`. `risk_hedge_overlay` is generated by `RiskManager`, not candidate scoring.
- Treat trade identity as a required field consumed by trading, sizing, risk, options, reflection, and UI; do not implement it as a separate strategy or standalone trade generator.
- Distinguish `catalyst_watch` from ordinary neutral/watch output as `watch_type` under `trade_identity = "watch_only"` when direction is uncertain but move potential is high.
- Compute confidence calibration inputs by strategy, expression bucket, trade identity, direction, catalyst type, benchmark/peer outperformance, and available historical outcomes from `candidate_outcome_evaluations`.
- Implement `HistoricalReplayRun` loading that reconstructs candidate/outcome sets from stored `decision_time` and `available_for_decision_at` metadata.
- Implement `OutcomeEvaluator` for trades, rejected candidates, `catalyst_watch`, ordinary `watch_only`, manual requests, and shadow strategy candidates.
- Scope replay v0 to the deterministic signal families actually produced by PR 2: technical, fundamental, and events/news MVP fields, plus universe/manual request metadata, strategy definition metadata, and explicit missing/stale fields.
- Replay v0 can evaluate technical strategies, valuation/fundamental-quality strategies that rely on PR 2 fundamental summaries, and headline/calendar/event-news strategies that rely on PR 2 structured event/news rows.
- Do not attempt deep earnings-transcript drift, full SEC/news article interpretation, insider/Form 4 strategies, full macro read-through, or options strategy replay in PR 3. Strategies that require those deferred source families must be marked `unsupported_missing_signal_family`, skipped, or downgraded to watch according to strategy rules.
- Do not backfill deferred source families from future/latest data just to make strategy replay look complete.
- Evaluate outcomes over each selected strategy's configured horizon and interim checkpoints.
- Compare against `SPY`, `QQQ`, sector/theme ETF when configured, decision-time peer basket, and decision-time opportunity set where available.
- Persist `CandidateOutcomeEvaluation` rows with horizon start/end, interim/final status, benchmark returns, peer basket id, candidate return, alpha, MFE/MAE, regime, sector/theme, catalyst type, confidence bucket, trade identity, and expression bucket.
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
- Create: `src/trading/risk_context.py`
- Create: `src/trading/position_sizing.py`
- Modify: `src/trading/repository.py`
- Test: `tests/trading/test_position_sizing.py`
- Test: `tests/trading/test_risk_context.py`
- Test: `tests/trading/test_risk_manager.py`

Implementation notes:

- Implement `RiskAppetiteProfile` with three presets: `conservative`, `balanced`, and `aggressive`; default to `balanced`.
- Implement deterministic `RiskConfigResolver` that converts the active risk appetite preset into a generated `RiskLimitConfig`. Persist both the user-facing preset and the generated config with resolver version for audit/replay.
- Define a pure `PortfolioContext` / `RiskContext` input object for PR 4 instead of reading paper portfolio tables directly. It should include account equity, cash balance, buying power, excess liquidity, current positions, existing exposure, current stock/option margin requirement, open strategy exposure, factor exposure, and current portfolio risk snapshots when available.
- Unit tests in PR 4 must feed fixture `PortfolioContext` objects so the risk manager can be implemented before paper portfolio state exists.
- PR 4 may read the latest persisted snapshot if one exists, but it must also work from an explicit fixture/context object. Do not couple PR 4 to `PaperBroker` or `PortfolioPipeline`.
- PR 6 owns wiring real paper positions and portfolio snapshots into `PortfolioContext`; that wiring should not require rewriting PR 4 risk logic.
- Keep detailed risk-limit numbers out of the default UI/operator config. Allow optional advanced overrides only as explicit metadata, not as the normal workflow.
- Calculate factor exposure by sector, strategy, horizon, direction, beta bucket, volatility bucket, liquidity bucket, event type, and macro sensitivity.
- Add unified margin-account risk fields and limits: account equity, cash balance, buying power, excess liquidity, stock margin requirement, option margin requirement, total margin requirement, buying-power effect, margin model profile/version, margin requirement source, estimated initial/maintenance requirement, and broker-reported requirement when imported.
- Add default conservative broker-profile margin settings: `estimated_fidelity_like_conservative_v1`, Reg T style stock initial requirement, house maintenance requirement assumptions, unknown-marginability fallback, concentration/volatility/liquidity add-ons, and conservative option margin rules.
- Enforce invariant hard safety rails across all presets: missing/stale signals, missing option risk metadata, unestimable margin, assignment over-concentration, macro-only bearish single-name shorts, and core-holding tactical exits must still reduce/reject/downgrade even under `aggressive`.
- Include explicit risk rules that prevent macro-only bearish evidence from creating high-confidence single-name shorts.
- Apply bearish evidence through existing sizing/reduce/reject paths, not through a standalone bearish trading module.
- Keep core-holding risk rules separate from short-term catalyst trade rules, and reject `core_holding` classifications without an active approved `portfolio_intent`.
- Implement reduce/reject behavior for concentration caps.
- Persist `position_sizing_decisions`, `portfolio_risk_snapshots`, and `risk_factor_exposures`.
- Keep this independent of LLM and paper broker.

Stop after PR 4 for review/merge.

---

## PR 5: Trading Decision Agent Guardrails

**Goal:** Add bounded trading-agent decisions after candidate scoring and risk context, with Pydantic validation, retry, safe fallback, and full prompt/schema persistence. No paper orders or portfolio mutation yet.

**Files:**
- Create: `src/agents/trading.py`
- Create: `src/agents/trading_schemas.py`
- Modify: `src/core/config.py`
- Modify: `src/trading/pipeline.py`
- Add ORM models/migration for `trading_decisions`
- Test: `tests/agents/test_trading_agent.py`
- Test: `tests/agents/test_trading_schemas.py`
- Test: `tests/trading/test_trading_decision_repository.py`

Implementation notes:

- Use `TRADING_MODEL_NAME` defaulting to `DEFAULT_FAST_MODEL_NAME`.
- Load trading prompts through `PromptRegistry`; no inline prompt strings.
- Define Pydantic schemas for every trading-agent output, including explicit `decision`, `trade_identity`, `strategy_id`, `expression_bucket_id`, `instrument_type`, confidence fields, thesis, invalidators, and fallback metadata.
- Validate every LLM response through Pydantic before persisting parsed decisions.
- Retry once with the validation error and compact repair prompt when parsing or validation fails.
- If retry fails, persist raw output, validation error, retry count, and fallback `no_trade` for new exposure or `hold` for existing positions.
- Persist `LlmPromptTemplate`, `LlmPromptRun`, and `LlmUsageEvent` records for every trading-agent call, including rendered prompt hash/redacted prompt, input context, raw output, parsed output, validation errors, fallback action, prompt/schema version, model, token usage, cost, latency, retries, and errors.
- Persist the full decision context snapshot, including trade identity, expression bucket, benchmark/peer context, historical replay outcome references, confidence basis, source availability metadata, `selection_source`, and `manual_request_id`.
- Enforce long-only common-stock decisions in V2. Bearish evidence may reduce/reject/downgrade, but direct short-stock decisions should be downgraded before later paper order creation.
- Enforce manual request mode: `review_only` can produce an actionable explanation but must never authorize a later paper order; `paper_trade_eligible` can proceed only after normal risk approval.
- Update linked manual request `result_status` to `actionable_trade`, `blocked_by_risk`, `no_trade`, `catalyst_watch`, or `ordinary_watch`.
- Do not create paper orders in PR 5. Persist proposed decisions and safe fallbacks only.

Stop after PR 5 for review/merge.

---

## PR 6: Paper Stock Broker + Portfolio State

**Goal:** Add paper common-stock order simulation and unified simulated margin-account portfolio state after guarded trading decisions and deterministic risk approval.

**Files:**
- Create: `src/trading/paper_stock_broker.py`
- Create: `src/trading/portfolio.py`
- Modify: `src/trading/repository.py`
- Modify: `src/trading/pipeline.py`
- Add ORM models/migration for `paper_orders`, `paper_executions`, `paper_positions`, `portfolio_snapshots`
- Test: `tests/trading/test_paper_stock_broker.py`
- Test: `tests/trading/test_portfolio.py`

Implementation notes:

- Consume only Pydantic-validated `TradingDecision` rows or safe fallbacks from PR 5.
- Map paper positions, cash, buying power, margin requirements, and latest portfolio snapshots into the PR 4 `PortfolioContext` / `RiskContext` contract before calling `RiskManager`.
- Risk manager remains the final gate before paper order creation.
- Enforce long-only common-stock paper orders in V2. Bearish evidence may reduce/reject/downgrade, but direct short-stock paper orders should be rejected before order creation.
- Model stocks and options in one simulated margin account. Stock fills must update cash balance, stock market value, account equity, stock margin requirement, total margin requirement, buying power, excess liquidity, margin model profile/version, and margin requirement source in `portfolio_snapshots`.
- Implement `estimated_fidelity_like_conservative_v1` as the default estimated model: long marginable stock uses a 50% initial requirement, maintenance uses at least a 30% base plus configured house/concentration/volatility/liquidity add-ons, and unknown/non-marginable/restricted/low-priced securities fall back to a 100% requirement. Do not claim exact Fidelity matching unless broker-observed values are imported.
- Reject or reduce stock orders when unified account buying power, total margin requirement, or excess-liquidity limits would be violated.
- Enforce manual request mode again at order creation: `review_only` cannot create a paper order even when an earlier decision was actionable.
- Paper broker must be idempotent for a trade date / ticker / strategy / action.

Stop after PR 6 for review/merge.

---

## PR 7: Paper Options Strategy Layer + Assignment Risk

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

Stop after PR 7 for review/merge.

---

## PR 8: Intraday Signal Refresh + News Alerts + Rebalance

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
- Validate intraday classification and rebalance JSON with Pydantic, retry once on validation failure, and fall back to `classification_failed` or `hold` unless deterministic hard-risk rails require reduce/exit.
- Normalize alert fields: ticker or source ticker, event type, sentiment, severity, source, published time, summary, strategy relevance, affected positions/candidates/themes, read-through relationship when applicable, and action-required flag.
- Severity levels are `critical`, `high`, `medium`, `low`.
- Critical/high alerts can propose `hold`, `reduce`, `exit`, `add`, `close_option_strategy`, `roll_option_strategy`, `adjust_option_strategy`, or `avoid_event_option` for whitelisted paper option strategies.
- `open_new` is disabled by default unless the ticker was already a morning candidate or manual override.
- Every proposed action must pass `PositionSizer`, `RiskManager`, and the relevant paper broker.
- Persist no-action and rejected signal/news triggers so post-close reflection can evaluate missed or noisy signals.

Stop after PR 8 for review/merge.

---

## PR 9: Reflection + Learning Factors

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
- Persist prompt run and usage records for reflection, including raw output, parsed output, Pydantic validation errors, retry count, and fallback status. Reflection failure must not mutate learning factors.
- Reflection input includes portfolio outcome, candidates, manual ticker requests, accepted/rejected trades, intraday news alerts, intraday rebalance decisions, risk snapshots, factor concentration, historical replay/outcome evaluator rows, benchmark/peer-basket returns, paper option decisions, worst-case assignment snapshots, and learning factors used.
- Attribute trades from `candidate_outcome_evaluations` against benchmarks and decision-time peer baskets over each selected strategy's configured holding horizon. Daily reflection should record interim mark-to-market for open trades and final horizon outcome when the trade closes or the intended horizon expires.
- Analyze bullish catalyst trades separately from bearish/risk-off calls.
- Evaluate confidence calibration by strategy, expression bucket, trade identity, direction, catalyst type, sector/theme, and market regime.
- Evaluate whether `catalyst_watch` would have been more useful than ordinary neutral/watch.
- Evaluate whether user-pinned tickers exposed scanner misses or mostly confirmed no-trade discipline.
- Learning factors start as `candidate`, `observation`, `shadow`, `active`, `suppressed`, or `retired`.
- New learning factors default to `candidate` or `observation`.
- Risk-tightening factors may become `active` automatically only when they reduce exposure, add required confirmation, block stale-data scenarios, lower confidence, or tighten exit rules.
- Any factor that increases score, expands eligibility, increases size, weakens hard safety rails, broadens universe filters, or increases risk budget must remain candidate/shadow/test and should become a strategy/config proposal if it needs behavior changes.
- Reflection may emit `strategy_proposal_hints`, but PR 9 should not add them to the strategy catalog directly.

Stop after PR 9 for review/merge.

---

## PR 10: Strategy Evolution + Dynamic Strategy Catalog

**Goal:** Let the system summarize repeated learning into new strategy proposals and add validated candidates to the strategy list without being limited to the initial seed strategies.

**Files:**
- Create: `src/trading/strategy_evolution.py`
- Modify: `src/trading/repository.py`
- Modify: `src/db/models/trading.py`
- Add Alembic migration for `strategy_proposals` and `strategy_evaluation_results`
- Test: `tests/trading/test_strategy_evolution.py`
- Test: `tests/trading/test_strategy_lifecycle.py`

Implementation notes:

- Consume reflection `strategy_proposal_hints`, candidate/observation learning factors, rejected candidate evidence, and historical replay/outcome performance summaries.
- Load strategy proposal synthesis prompts through `PromptRegistry` and persist prompt run/usage records.
- Validate proposal synthesis output with Pydantic, retry once on validation failure, and persist `proposal_failed` without creating definitions when validation still fails.
- Generate `StrategyProposal` records with proposed `strategy_id`, display name, thesis, required/optional signals, horizon, scoring rules, risk tags, invalidators, and evidence summary.
- Detect duplicates against existing strategy definitions by overlap in required signals, horizon, thesis, and risk tags.
- Create new `StrategyDefinition` rows only in `candidate` or `shadow` lifecycle status.
- Shadow strategies can be scored during scans but cannot create paper orders.
- Experimental strategies can create paper orders only with small capped budget and stricter risk limits.
- Persist every lifecycle transition and promotion/rejection reason.

Stop after PR 10 for review/merge.

---

## PR 11: Today Dashboard UI

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
- In `Candidates` or an admin subview, show approved `portfolio_intents` for core holdings and structured `ticker_relationships`/`peer_baskets`/`theme_taxonomy` used for read-through and attribution.
- In `Risk & Macro`, show the active risk appetite preset (`conservative`, `balanced`, or `aggressive`), generated risk config version, and binding constraints; hide detailed generated limits behind an advanced/debug view.
- In `Risk & Macro`, show a portfolio-aware upcoming event calendar: future macro events, Fed/rates events, own-company earnings, related-company earnings read-through, option-relevant events, and market-structure events that pass the display threshold.
- Each event row should show scheduled date/time, event type, global importance, portfolio risk level, affected ticker/position/option strategy, affected sector/theme, risk mechanism, lookahead reason, suggested action type, and source/provider.
- Do not show irrelevant low-importance events by default. The display window must be dynamic by holding period and event importance rather than a fixed "next N months" list.
- Add trade detail drill-down with point-in-time signal snapshots, source availability metadata, strategy scores, selected strategy, trade identity, LLM decision JSON, validation/fallback status, risk decision, order/fill state, exit plan, invalidators, replay outcome rows, and post-close outcome.
- Add a pinned-review form for ticker, reason, mode (`review_only` / `paper_trade_eligible`), and priority. Manual requests stay active until dismissed, so the UI should provide a dismiss action instead of default end-of-day expiry.
- Show pinned-review results with request status, result status, strategy match, trade identity, confidence basis, risk result, and linked trading decision if any.
- Show benchmark/peer outperformance and confidence basis for selected and rejected candidates.
- Show option strategy type, per-leg call/put side, buy/sell side, strike, expiry, DTE, Greeks, IV rank, bid/ask/mark, net debit/credit, max loss, breakevens, margin requirement, buying-power effect, earnings/event date, roll/close/adjust plan, and assignment plan when relevant.
- Show strategy proposals, shadow/experimental strategies, and promotion/retirement status.
- Show strategy performance by win rate, PnL, alpha vs benchmarks/decision-time peer basket over each strategy's configured horizon, drawdown, sample size, market regime, and bullish/bearish split from `candidate_outcome_evaluations`.
- Show LLM/API usage and estimated cost by pipeline, model, provider, run, token count, latency, retry/error state, validation/fallback state, prompt/schema version, provider request budget, cache hit/miss, degraded mode, and circuit-breaker state.
- Keep `/research` intact as audit UI.
- Avoid raw JSON as primary UX; use structured tables/cards.

Stop after PR 11 for review/merge.

---

## PR 12: Scheduler, Smoke Tests, Deploy Docs

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
- Add standalone smoke modes for provider guardrail fixture mode, universe/signal DB writes, historical replay fixture run, and paper-trade dry run.
- Add standalone smoke mode for active universe filter loading plus a fixture-backed manual ticker request in `review_only` mode that remains active until dismissed.
- Add standalone smoke mode for paper option decisions, option legs, option-risk snapshots, and assignment-risk snapshots using fixture data.
- Add standalone smoke mode for hourly intraday signal/news refresh using a fixed tiny ticker set or fixture mode.
- Add standalone smoke mode for strategy proposal creation from a fixed reflection fixture.
- Keep live provider/API smoke tests opt-in with tiny ticker sets and request budgets; ordinary CI should use fake providers and recorded cassettes only.
- Document Postgres persistent disk verification with `SHOW data_directory;`.
- Keep Docker Compose infrastructure.

Stop after PR 12 for review/merge.
