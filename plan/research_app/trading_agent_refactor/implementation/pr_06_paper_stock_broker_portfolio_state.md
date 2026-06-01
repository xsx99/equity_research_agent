# Implementation Module PR 6: Paper Stock Broker and Portfolio State

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

