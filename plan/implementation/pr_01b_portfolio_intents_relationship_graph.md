# Implementation Module PR 1b: Portfolio Intents and Relationship Graph

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
- Modify: `plan/research_app/trading_agent_refactor/progress_tracker.md`

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

Update `plan/research_app/trading_agent_refactor/progress_tracker.md` with PR 1b status, implemented files, test commands/results, and known gaps.

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
