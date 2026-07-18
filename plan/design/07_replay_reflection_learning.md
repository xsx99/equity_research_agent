# Design Module 07: Replay, Reflection, and Learning

## 11. Historical Replay, Reflection, and Learning Loop

### Historical Replay and Outcome Evaluator

Reflection should not be the first component to judge whether a strategy worked. Before reflection runs, `HistoricalReplayOutcomeEvaluator` must compute deterministic outcomes from point-in-time snapshots:

- every selected trade
- every rejected candidate that reached candidate scoring
- every `catalyst_watch` and ordinary `watch_only` item
- active and shadow strategy candidates
- manual ticker requests

The evaluator measures each item over the selected strategy's configured horizon and any interim checkpoints. It compares absolute return and risk-adjusted return against:

- `SPY`
- `QQQ`
- configured sector ETF
- configured theme ETF
- decision-time peer basket
- decision-time opportunity set when available

It should persist interim marks for open trades and final outcome rows only when the trade closes or the configured horizon expires. The evaluator must use only data that was available at each decision time for candidate reconstruction, and only subsequent market data for outcome measurement. It must not use future knowledge to change the original candidate set, peer basket, strategy assignment, confidence bucket, or trade identity.

Outcome records should include:

- `strategy_id` and version
- `trade_identity`
- `expression_bucket_id`
- `decision_time`
- `horizon_start_at` and `horizon_end_at`
- benchmark returns
- peer basket return and basket membership snapshot id
- candidate/trade return
- alpha vs each comparator
- MFE/MAE
- drawdown and volatility where available
- regime, sector/theme, catalyst type, and confidence bucket
- whether the row is interim or final

Reflection and strategy evolution consume these outcome rows rather than recomputing attribution ad hoc.

Replay v0 scope is intentionally narrower than the final strategy catalog, but it should cover the three MVP signal families: technical, fundamental, and events/news. The first replay evaluator should evaluate strategies whose required inputs are present in the deterministic signal surface implemented at that time: market bars, liquidity, benchmark/sector/theme/peer-basket relative strength, valuation/fundamental summary fields, headline/calendar/provider-event fields, universe/manual request metadata, strategy definition metadata, and explicit missing/stale fields. Full transcript-driven earnings drift, deep SEC/insider interpretation, option-chain strategy replay, and full macro/sector read-through remain unavailable until those source families are implemented as point-in-time snapshots. Strategies that require unavailable families must be marked `unsupported_missing_signal_family`, skipped, or downgraded according to strategy rules; replay must not backfill them from latest/future source tables.

### Reflection Input and Output

Reflection runs after the portfolio is marked to close and after historical replay/outcome evaluation has produced the relevant interim or final outcome rows. It receives:

- morning macro snapshot
- strategy candidates and scores
- trading decisions and rejected decisions
- intraday news alerts and rebalance decisions
- paper orders/executions
- end-of-day PnL, benchmark return, sector return
- peer-basket returns and relevant ETF returns, e.g. `QQQ`, `SMH`, `SOXX`
- paper option positions, option strategy lifecycle actions, leg-level risk snapshots, hedge overlay decisions, and worst-case assignment snapshots when relevant
- historical replay/outcome evaluator rows for selected trades, rejected candidates, watch items, and shadow strategies
- per-trade MFE/MAE if available
- invalidators and whether they triggered
- prior learning factors used

Reflection should evaluate the portfolio, not just individual research calls. The main questions are:

- Did bullish catalyst trades outperform the relevant ETF and peer basket over their intended strategy horizon, or only ride a sector tailwind?
- Did bearish or risk-off reasoning actually add value, or did it incorrectly suppress strong-trend names?
- Were high-confidence calls calibrated by historical pattern quality, or did narrative completeness inflate confidence?
- Did `neutral/watch` hide a catalyst-watch opportunity with large move potential?
- Did option trades have acceptable max loss, Greeks, event risk, liquidity, and assignment risk where relevant?
- Did risk hedge overlays reduce portfolio risk enough to justify hedge cost?
- Did the selected strategies perform as expected for their horizons?
- Did risk constraints prevent losses or block profitable opportunities?
- Were skipped candidates better than selected trades?
- Did intraday news alerts trigger useful rebalances, or did the system overreact/underreact?
- Did macro regime constraints help or hurt?
- Was the portfolio too concentrated in any sector, strategy, horizon, beta, volatility, liquidity, event, macro, or correlation factor?
- Did factor concentration explain more PnL than ticker selection?
- Did active learning factors improve decisions, overfit, or become stale?
- Are there repeated profitable or avoided-loss patterns that deserve a new trading strategy rather than another one-off learning factor?

The reflection output is structured:

```json
{
  "trade_date": "2026-05-28",
  "portfolio_summary": {
    "realized_pnl": 123.45,
    "unrealized_pnl": -12.34,
    "benchmark_return": 0.004
  },
  "what_worked": ["Avoided high beta longs during elevated volatility."],
  "what_failed": ["Chased opening gap without enough volume confirmation."],
  "attribution": [
    {
      "strategy_id": "gap_reversal_v1",
      "result": "negative",
      "root_cause": "entry_too_early",
      "evidence": ["MAE exceeded planned risk before signal confirmation"]
    }
  ],
  "learning_factors": [
    {
      "type": "candidate_filter",
      "scope": "strategy",
      "strategy_id": "gap_reversal_v1",
      "condition": "opening_gap_pct > 0.04 and relative_volume < 1.5",
      "recommendation": "downgrade candidate unless volume confirms in first 30 minutes",
      "confidence": 0.66,
      "activation_policy": "auto_context"
    }
  ]
}
```

Reflection may also emit `strategy_proposal_hints`: partial observations that are not yet complete strategy definitions. `StrategyEvolutionPipeline` owns converting those hints into concrete strategy proposals so reflection stays focused on evidence and attribution.

### Horizon-Aware Strategy Evolution Evidence

Reflection receives both same-day outcome rows and bounded prior context: prior candidate outcome evaluations plus prior daily reflection summaries over the configured lookback. Same-day rows remain useful for operator review, but durable claims must distinguish `single_day_noise`, `interim_horizon_mark`, `final_horizon_evidence`, and repeated patterns. Interim outcome rows can monitor open horizons; they do not prove an edge.

Strategy evolution consumes a trailing evidence window rather than only the current reflection day. LLM proposals must cite concrete `supporting_outcome_ids`, but those citations are advisory input to deterministic Python gates. A proposal is accepted only when cited final outcome rows meet the minimum evidence policy: enough final rows, distinct trade dates, distinct tickers, positive win rate, and positive mean alpha. Missing ids, interim-only evidence, or same-day-only support are persisted as `insufficient_evidence_rejected` with `metadata_json.evidence_gate` explaining the failed gate.

Lifecycle promotion reuses the same multi-day evidence policy for `shadow -> experimental` and `experimental -> active`, with the stricter active-promotion mean-alpha threshold preserved. New strategy definitions still start at `candidate` or `shadow`; the LLM never creates active or experimental strategies directly.

The next trading run adapts only to learning factors that are active under the lifecycle policy below. Adaptation means:

- candidate scores can be adjusted only by active, validated strategy-scoped learning factors
- trading prompt context may include candidate/observation lessons as soft context, but the prompt must label them as not behavior-changing
- risk manager can automatically apply learning factors that tighten constraints, lower size, add blocked conditions, or increase required confirmation
- learning factors that raise score, expand eligibility, increase size, loosen risk, or promote a new setup must remain candidate/shadow/test until outcome evidence supports promotion
- every applied learning factor is persisted through `learning_factor_applications`
- later reflections evaluate whether the learning factor helped, hurt, overfit, or should be retired

### Learning Factor Lifecycle

| Status | Meaning |
| --- | --- |
| `candidate` | Newly generated by reflection; may appear as soft context, but does not change scoring, sizing, or risk approval |
| `observation` | Informational lesson shown in UI or prompt context for analyst review; no behavioral effect |
| `shadow` | Evaluated against historical/live paper outcomes without changing orders or sizes |
| `active` | Allowed to affect candidate scoring, trading prompt context, or risk rules under its approved scope |
| `suppressed` | Stored but not injected |
| `retired` | No longer relevant |

Initial policy:

- New learning factors default to `candidate` or `observation`, not `active`.
- Risk-tightening factors may become `active` automatically when they only reduce exposure, add required confirmation, block stale-data scenarios, lower confidence, or tighten exit rules.
- Any learning factor that increases score, expands eligibility, increases position size, weakens hard safety rails, broadens universe rules, or increases strategy/risk budget must go through shadow/test evidence and explicit promotion.
- If reflection suggests a looser risk rule, broader universe rule, larger strategy budget, or new alpha pattern, the change should become a strategy/config proposal rather than an automatically active learning factor.
- Every trading decision stores which learning factors were injected so impact can be evaluated later.
