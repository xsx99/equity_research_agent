# Implementation Module PR 11: Today Dashboard UI

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

