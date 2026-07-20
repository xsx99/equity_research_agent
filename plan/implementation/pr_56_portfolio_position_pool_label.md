# PR 56 — Portfolio Position Pool Label

## Goal
Show whether each Portfolio position belongs to the core pool or satellite pool.

## Design
- Use the existing persisted `trade_identity` on stock and option position rows.
- Map `core_holding` to `Core`.
- Map `tactical_stock_trade` and `tactical_option_trade` to `Satellite`.
- Keep the existing `Identity` column for the more specific trade identity.
- Render a new `Pool` column in Stock Positions and Option Positions.

## Tasks
- [x] Add loader regression coverage for stock-position pool labels, including `core_holding`.
- [x] Add Portfolio template regression coverage for the `Pool` column.
- [x] Add pool fields in the Portfolio loader.
- [x] Render `Pool` in stock and option position tables.
- [x] Run web tests and rendered Portfolio-page verification.

## Verification
- RED: `source ~/.venv/bin/activate && pytest tests/web/test_today_portfolio_loader.py::test_load_positions_exposes_enriched_stock_position_fields tests/web/test_today_portfolio_loader.py::test_load_positions_labels_core_holding_pool tests/web/test_today.py::TestTodayDashboard::test_portfolio_tab_renders_summary_first_structure -q` failed before implementation on missing loader keys and missing `Pool` header.
- GREEN: same focused command passed with `3 passed`.
- `source ~/.venv/bin/activate && pytest tests/web -q` passed with `174 passed`.
- `source ~/.venv/bin/activate && python -m compileall -q src` passed.
- `git diff --check` passed.
- Render verification loaded `http://127.0.0.1:8000/today?tab=portfolio` and captured `/private/tmp/portfolio_pool_render.png`; live stock rows rendered `Pool = Satellite`.
