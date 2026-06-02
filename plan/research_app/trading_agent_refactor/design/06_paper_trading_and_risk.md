# Design Module 06: Paper Trading and Risk

## 10. Paper Trading and Risk

### Alpaca-Backed Unified Paper Margin Account

V2 should represent one paper margin-account view shared by stock trades, option trades, hedge overlays, and assignment scenarios. For PR 6 common-stock trading, Alpaca paper trading is the execution and account-state source of truth. Local `paper_orders`, `paper_executions`, `paper_positions`, and `portfolio_snapshots` are audit/replay mirrors of broker order status, fills, account fields, and open stock positions rather than an independent stock fill simulator.

There should not be a separate stock cash account and option margin account. Every proposed order must be evaluated against the same account-level buying power and margin constraints. In PR 6, the stock portion of that account comes from Alpaca `/v2/account` and `/v2/positions` sync. PR 7 option simulation must overlay option buying-power effects and assignment scenarios onto this same local account view, or explicitly revise this design if option execution also becomes broker-backed.

The account snapshot should persist:

- `cash_balance`
- `account_equity`
- `net_liquidation_value`
- `buying_power`
- `excess_liquidity`
- `stock_market_value`
- `option_market_value`
- `stock_margin_requirement`
- `option_margin_requirement`
- `total_margin_requirement`
- `initial_margin_requirement` and `maintenance_margin_requirement` when available or approximated
- `margin_model_profile`, `margin_model_version`, and `margin_requirement_source`
- `day_pnl`, `realized_pnl`, and `unrealized_pnl`

When broker-reported margin fields are unavailable, or when replay/local simulation/option overlays need an estimate, the estimated margin model should be more realistic than a flat toy model while still being explicit that it is an estimate. The conservative fallback is `estimated_fidelity_like_conservative_v1`: a broker-profile model inspired by public Reg T, exchange, and Fidelity-style house/RBR concepts. It must not claim to exactly reproduce Fidelity's internal margin engine unless broker-observed margin requirements are imported and stored.

Supported margin model profiles:

- `alpaca_paper_account`: broker-sourced paper account fields for stock cash, equity, buying power, stock market value, and broker-reported margin fields.
- `reg_t_base_conservative_v1`: simple Reg T style fallback.
- `estimated_fidelity_like_conservative_v1`: offline/replay fallback model with Reg T initial requirements, broker-house maintenance assumptions, option-spread treatment, and conservative add-ons.
- `broker_observed_margin_v1`: optional future mode that uses imported broker-reported requirements or broker-calculator outputs as the authoritative requirement, while still storing the simulated estimate for comparison.

Every margin computation or broker sync should persist `margin_model_profile`, `margin_model_version`, `margin_requirement_source`, and whether the requirement is estimated, broker-reported, broker-observed, or manually overridden. For Alpaca-backed stock snapshots, use `margin_model_profile = "alpaca_paper_account"` and `margin_requirement_source = "broker_reported"` when the value came from the paper account payload. If broker-reported values are unavailable or a replay run has no broker payload, the system should use the conservative estimate and label it as such.

Default estimated rules:

- Long marginable US stock starts with a Reg T style 50% initial requirement. Maintenance uses the maximum of the configured base maintenance requirement and any security, house, concentration, volatility, liquidity, leveraged-ETF, or unknown-marginability add-on. The default base maintenance requirement should be at least 30% for fully marginable diversified common stock.
- Unknown, non-marginable, very low-priced, highly volatile, hard-to-borrow, concentrated, or manually restricted securities should fall back to a 100% requirement unless a stricter override is configured.
- Short stock is disabled in V2 by default. If enabled later, it must use stricter initial and maintenance requirements, locate/borrow assumptions, and conservative house add-ons.
- Long options consume full premium paid plus fees as buying-power effect.
- Defined-risk credit spreads consume max loss when max loss is known; if a configured broker profile requires a higher value, use the higher value.
- Long straddles and long strangles consume full net premium paid plus fees as buying-power effect.
- Standalone naked short options, short straddles, short strangles, standalone short puts, covered calls, collars, debit spreads, and custom multi-leg structures are outside the initial V2 option whitelist. They should be rejected or downgraded unless explicitly enabled in a later design revision.
- If naked or undefined-risk structures are enabled later, they must use conservative uncovered-option formulas and may be blocked entirely when inputs are missing. The model must not treat short-option premium as sufficient collateral.
- Multi-leg option strategies must persist a deterministic `strategy_pairing_method`. If legs cannot be paired unambiguously into a defined-risk structure, margin should fall back to the more conservative naked-leg estimate or the trade should be rejected.
- Assignment-capable strategies must pass both current margin/buying-power checks and a worst-case assigned portfolio check at strike-level stock exposure.
- If required data is missing, stale, or internally inconsistent, the risk manager should use the more conservative requirement, reduce size, or reject the paper order.

This keeps paper risk close enough to real margin-account behavior for planning, while preserving a clear audit trail between estimated requirements and any future broker-observed values.

### Paper Broker Rules

- Default stock execution model: submit approved `market` / `day` stock orders to Alpaca paper trading and poll broker order state by deterministic `client_order_id`.
- Local stock guardrails still run before the broker call: V2 common-stock paper orders are long-only for new exposure, `review_only` manual requests cannot create orders, unsupported actions are rejected, and non-positive quantities are rejected.
- Local `paper_orders` must persist the deterministic client order id, broker order id when returned, status, rejection reason, linked trading/risk decision ids, ticker, strategy, action, trade date, quantity, and submitted/fill timestamps.
- Local `paper_executions` must be created only from broker-reported filled order state, including broker order id, filled quantity, filled average price, execution time, and net cash effect for audit.
- After each stock fill, the workflow must sync Alpaca account and open positions, then persist `paper_positions` and `portfolio_snapshots` from broker payloads.
- Stock slippage, commission, price availability, and fill rejection are broker-reported in the Alpaca-backed path. Offline replay/local simulation may retain estimated slippage/commission models, but those estimates must not be mixed into live Alpaca paper snapshots as authoritative fills.
- Stock and option paper paths can share order-state semantics, but option fills remain simulated and must use explicit option-chain data or fixture data until an option broker path is designed.
- Option fill rejection if strike, expiry, bid/ask/mark, delta, IV rank/percentile, or earnings date data required by the strategy is missing.
- All fills are persisted; order state transitions are auditable and reconcileable by broker/client order id.

### Position Management

Position sizing is deterministic and happens after the trading agent proposes a trade. The trading agent may suggest `target_weight`, but `PositionSizer` owns the final size. The sizing algorithm should combine:

- strategy candidate score
- trading decision confidence
- strategy-level risk budget
- macro risk budget multiplier
- ticker volatility / ATR%
- liquidity and dollar-volume capacity
- unified margin-account equity, buying power, margin used, and gross/net exposure
- current exposure to the same risk factors
- active learning factors that tighten sizing rules

Initial sizing rule:

```text
base_weight = strategy_budget * candidate_score * confidence * macro_risk_budget_multiplier
vol_adjusted_weight = base_weight * target_volatility / ticker_realized_volatility
liquidity_capped_weight = min(vol_adjusted_weight, max_liquidity_participation_weight)
final_weight = min(liquidity_capped_weight, remaining_factor_budget, single_name_limit)
```

The exact formula can evolve, but every sizing decision must persist inputs, caps applied, and final size. If a trade is reduced because of risk, the UI should show the binding constraint.

### Option Strategy Risk and Assignment Risk

For every paper option strategy, risk must be evaluated at the strategy level and at the leg level. The risk manager should calculate:

- per-leg option exposure: call/put, side, quantity, strike, expiry, DTE, Greeks, mark, and event-through-expiry status
- strategy-level exposure: net debit/credit, max loss, max profit when definable, breakevens, margin requirement, buying-power effect, net Greeks, and liquidity/width quality
- portfolio-level option exposure: aggregate delta/gamma/theta/vega, protected exposure, hedge cost, margin usage, buying-power usage, and concentration by ticker/theme/expiry/event

For assignment-capable paper strategies, risk must also be evaluated as if assignment can happen. The risk manager should calculate both:

- current portfolio exposure: stock positions plus marked option positions
- worst-case assigned portfolio: current stock positions plus assignment-capable short option legs converted into the resulting stock exposure at their strikes

The worst-case assigned portfolio is the primary control for assignment-capable credit spreads and any future strategy with short option legs that can create stock exposure. Standalone short puts are not part of the initial V2 option whitelist. A trade is rejected, reduced, or adjusted if simultaneous assignment would create unacceptable concentration, even if current stock exposure looks safe.

Required assignment metrics:

- assignment notional by ticker
- margin requirement and buying-power effect by strategy and total portfolio
- breakeven exposure by ticker
- sector/theme/industry exposure after assignment
- high-beta AI/semis/space exposure after assignment
- expression bucket exposure after assignment
- correlation-cluster exposure after assignment
- earnings-through-expiry flag and event-risk exposure

Example assignment question the risk manager must answer:

```text
If every assignment-capable short option leg is assigned at strike, does the portfolio become an over-concentrated high-beta AI/semiconductor/space book?
```

If yes, the system can propose `avoid_event_option`, `close_option_strategy`, `roll_option_strategy`, `adjust_option_strategy` to a lower-risk whitelisted structure, reduce new common-stock exposure, or reject new option strategies.

### Portfolio Risk Factor Model

`RiskManager` should maintain a portfolio risk snapshot before order staging, after order staging, and after fills. The purpose is to avoid a portfolio that looks diversified by ticker count but is concentrated in the same underlying risk.

Risk factors to track:

| Factor Type | Exposure Examples | Why It Matters |
| --- | --- | --- |
| Single name | ticker weight, beta-adjusted ticker weight | Prevent one position dominating PnL. |
| Sector / industry | GICS sector, industry group, theme cluster | Avoid all trades being the same sector bet. |
| Strategy | gap, breakout, earnings drift, squeeze, mean reversion | Avoid one strategy regime dominating the book. |
| Horizon bucket | intraday, 1-3d, 1-2w, 2w-3m | Avoid liquidity/risk mismatch across holding periods. |
| Direction | long, short, gross, net | Control net market exposure and leverage. |
| Market beta | SPY beta, high-beta basket proxy | Avoid hidden market beta concentration. |
| Volatility | high ATR%, realized vol percentile | Avoid all positions being high-vol names. |
| Liquidity | dollar volume bucket, spread proxy | Avoid crowding into hard-to-exit positions. |
| Momentum / reversal | high momentum, oversold, squeeze pressure | Avoid correlated factor trades across names. |
| Event/catalyst | earnings, analyst revision, regulatory, M&A, macro event | Avoid too many event-risk trades on the same day. |
| Macro sensitivity | rates-sensitive, oil-sensitive, USD-sensitive, credit-sensitive | Keep macro factor exposure aligned with macro regime. |
| Correlation cluster | rolling return correlation or sector/theme cluster | Catch hidden concentration across related tickers. |
| Option strategy | per-leg Greeks, net Greeks, max loss, max profit, breakevens, margin requirement, buying-power effect, spread width, expiry/event exposure | Understand option risk beyond the underlying stock position. |
| Option assignment | assignment-capable short-leg notional, breakeven exposure, margin requirement, buying-power effect | Avoid hidden stock exposure that appears only after assignment. |
| Hedge overlay | hedge notional, hedge delta, hedge cost, protected exposure | Track whether paper option hedges reduce the intended risk without becoming a hidden speculative position. |

Factor exposures should be approximate in V2. A robust simple model is better than a fragile complex one: start with sector/industry, strategy, horizon, direction, beta proxy, volatility bucket, liquidity bucket, and event type, then add rolling-correlation clusters once enough market data is available.

### Risk Appetite Presets

The operator-facing risk configuration should be intentionally small. In V2, all trading is paper-only, so there is no need to expose fields such as `allowed_paper_only`. The primary user setting should be:

```json
{
  "risk_appetite": "balanced"
}
```

Supported presets:

| Preset | Intended behavior |
| --- | --- |
| `conservative` | Smaller paper position sizes, lower margin usage, stricter assignment exposure, stricter theme/sector concentration, more frequent downgrade to watch, and preference for defined-risk option structures. |
| `balanced` | Default profile. Allows normal paper position sizes and moderate margin usage while still enforcing all hard safety rails. |
| `aggressive` | Larger paper position sizes, wider concentration and margin budgets, and more willingness to use option expressions when data is complete. It still cannot bypass hard safety rails. |

`RiskConfigResolver` owns the conversion from `risk_appetite` to an effective generated `RiskLimitConfig`. The resolver must be deterministic and versioned. Inputs should include:

- selected `risk_appetite`
- account equity, buying power, margin usage, and excess liquidity
- current portfolio composition and trade identities
- macro regime and macro budget multiplier
- strategy horizon and expression bucket
- option assignment exposure and Greeks
- event risk and source freshness state

The generated config is persisted for audit/debug/replay, but it is not the primary user-facing object. The UI should show the active preset and a short explanation of binding constraints. Full generated limits can live behind an advanced/debug view.

### Hard Safety Rails

Hard safety rails do not change across `conservative`, `balanced`, and `aggressive`:

- Missing, stale, or internally inconsistent signal snapshots block trading or downgrade to watch.
- Missing option-chain, leg pricing, Greeks, margin, buying-power, event, or assignment metadata blocks option trades or downgrades to watch.
- If margin requirement cannot be estimated, use the conservative fallback, reduce size, or reject.
- Worst-case assignment cannot create an over-concentrated portfolio by ticker, sector/theme, expression bucket, or correlation cluster.
- Macro-only bearish evidence cannot create a high-confidence single-name short or bearish trade.
- Core holdings cannot be sold solely because of a short-term tactical signal.
- Risk hedge overlays remain paper-only `RiskManager` actions and are excluded from tactical strategy win-rate attribution.
- No averaging down in V2 unless explicitly added later.

### Generated Risk Limits and Actions

The effective generated risk config should cover these categories without exposing dozens of knobs in the default UI:

- max position weight per ticker
- max daily new positions
- gross/net/beta-adjusted exposure
- macro budget multiplier
- strategy, horizon, event, sector, industry, theme, and correlation-cluster caps
- high-volatility and low-liquidity caps
- unified margin-account buying power, total margin requirement, and excess-liquidity caps
- stock margin and option margin/buying-power usage caps
- option max loss, net debit/credit, assignment notional, and portfolio Greeks caps
- event-through-expiry restrictions for option strategies
- paper hedge overlay eligibility and budget caps

Risk actions should distinguish soft warnings from hard blocks:

- Soft warning: allow order but mark the portfolio as near limit.
- Size reduction: reduce order until exposure fits the remaining factor budget.
- Hard reject: no order is created.
- Forced reduce/exit: only for existing positions that violate hard limits after market movement or stale risk data.
- Paper hedge overlay: open, close, or adjust a simulated option hedge when portfolio-level risk should be reduced without changing the underlying tactical/core position. This is a risk action, not a trading strategy signal.

Example high-level config:

```json
{
  "risk_appetite": "conservative",
  "profile_version": "v1"
}
```

Example generated config snapshot:

```json
{
  "risk_appetite": "conservative",
  "resolver_version": "risk_config_resolver_v1",
  "margin_model_profile": "estimated_fidelity_like_conservative_v1",
  "risk_tiers": {
    "position_size": "small",
    "margin_usage": "low",
    "theme_concentration": "strict",
    "assignment_exposure": "strict",
    "option_expression": "defined_risk_preferred"
  },
  "binding_limits": [
    "missing_data",
    "margin_usage",
    "assignment_exposure",
    "theme_concentration"
  ]
}
```

The risk manager must persist both accepted and rejected decisions. Rejected trades are important training data for reflection because the system should learn whether risk constraints protected the portfolio or blocked good opportunities.
