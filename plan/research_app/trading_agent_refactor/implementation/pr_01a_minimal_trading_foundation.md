# Implementation Module PR 1a: Minimal Trading Foundation

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
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

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

Update `plan/research_app/trading_agent_refactor/progress_tracker.md` with:

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
