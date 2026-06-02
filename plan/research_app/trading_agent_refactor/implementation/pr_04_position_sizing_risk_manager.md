# Implementation Module PR 4: Position Sizing and Risk Manager

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
- PR 4 may read the latest persisted snapshot if one exists, but it must also work from an explicit fixture/context object. Do not couple PR 4 to `PaperStockBroker`, option paper broker, or `PortfolioPipeline`.
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
