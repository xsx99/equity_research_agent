# Prompt 07 — Portfolio "Strategy" column shows "None"

You are editing the equity_research_agent repo. Make ONLY the change described.

## Problem
On the PORTFOLIO tab, the AAPL and NVDA stock positions show `Strategy: None`, even
though they have a "Tactical Stock Trade" identity.

## Do this
- Find where the stock-positions table is built for the PORTFOLIO tab (start in
  `src/web/presenters/today_overview.py` and the portfolio/positions loader in
  `src/web/routers/today.py`; the template is the "STOCK POSITIONS" table in
  `src/templates/today.html`).
- Determine why the strategy field is `None`: is the position not linked to a
  strategy in the data, or is the link present but not read into the presenter?
  - If the link exists, map it through so the real strategy/identity shows.
  - If genuinely unknown, display `—` instead of the literal `None`.

## Acceptance criteria
- Stock positions show their real strategy, or `—` when truly unknown — never the
  literal string `None`.
- `pytest tests/web/ -q` passes.
