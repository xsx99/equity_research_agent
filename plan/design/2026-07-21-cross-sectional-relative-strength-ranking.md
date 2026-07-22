# Cross-Sectional Relative-Strength Universe Ranking

Date: 2026-07-21
Status: Approved in conversation; pending written-spec review

## Summary

Replace the current absolute-threshold relative-strength scoring formula with a
point-in-time, cross-sectional universe-ranking stage. The new stage runs after
the existing price and liquidity filters and before expensive per-ticker research.
It ranks the full eligible universe, persists the complete cohort for audit and
replay, and sends a configurable Top-N shortlist plus forced tickers into the
existing signal, strategy, risk, decision, and execution pipelines.

This is an upstream research-prioritization rank. It does not replace
strategy-specific `candidate_scores`, trade classification, or the risk gate.

## User Decisions

- The immediate goal is to decide which stocks in the full market deserve deeper
  research.
- The first slice is relative strength, not a simultaneous implementation of
  fundamental, technical, valuation, and catalyst pillars.
- The current relative-strength scoring formula will be fully replaced for new
  production runs. It will not remain as a runtime fallback or shadow selector.
- Historical rows remain unchanged for audit.
- The shortlist size is configurable and defaults to Top 100.
- Manual requests, watchlist pins, open positions, and explicit manual includes
  remain in the research set even when they fall outside Top 100. Their true rank
  and forced-inclusion reason remain visible.

## Current-State Problems

The current `_score_relative_strength()` implementation in
`src/trading/strategies/matching.py` is not a cross-sectional rank. It assigns a
0-1 score from fixed thresholds:

- 35% from one-day return relative to SPY;
- 25% from one-day return relative to QQQ;
- 20% from absolute 20-day return;
- 10% from relative volume;
- 10% from a binary dollar-volume threshold.

This has several structural problems:

- one-day relative performance supplies 60% of the score;
- SPY and QQQ comparisons are correlated and double-count broad-market strength;
- the stock is never compared with the same-day opportunity set;
- absolute 20-day return is used instead of benchmark or peer alpha;
- sector, industry, theme, and configured peer baskets are absent;
- one-day price concentration, volatility, and drawdown have no penalty;
- the same absolute formula is reused by multiple strategy families;
- the universe is fully researched before a true opportunity rank exists.

The design documents already call for decision-time peer baskets,
`rs_vs_sector_20d`, `rs_vs_peer_basket_20d`, `sector_rank_percentile`, and
`peer_rank_percentile`. This design implements that direction without collapsing
strategy matching into one universal alpha score.

## Goals

- Rank every eligible full-universe stock within one frozen decision-time cohort.
- Prefer persistent benchmark and peer outperformance over a single large daily
  move.
- Normalize comparable features cross-sectionally rather than with arbitrary
  fixed caps.
- Produce an auditable score, rank, confidence, and contributor breakdown.
- Reduce expensive fundamental, news, event, insider, and option refreshes to the
  shortlist and forced tickers.
- Make every new score reproducible from persisted decision-time raw metrics,
  cohort metadata, model version, and configuration.
- Provide one canonical relative-strength signal to all strategy scorers that use
  relative strength.

## Non-Goals

- Building the full four-pillar stock model in this slice.
- Adding balance-sheet or accounting/regulatory eligibility data that is not
  currently available for the full universe at low cost.
- Replacing `candidate_scores` or choosing a trade directly from the universe
  rank.
- Changing trade classification, position sizing, or risk approval rules.
- Re-optimizing weights on the complete historical sample.
- Rewriting historical candidate rows with the new model.
- Fetching per-ticker sector or fundamental context from an external provider just
  to construct the rank.

## Architecture

The live pre-open flow becomes:

```text
Alpaca active US-equity universe
  -> existing price/liquidity/asset hard filters
  -> UniverseRankingPipeline
       -> batch-load adjusted daily OHLCV for the eligible cohort
       -> build point-in-time raw rank metrics
       -> resolve comparable peer cohorts
       -> calculate cross-sectional percentiles
       -> calculate penalties, confidence, score, and deterministic rank
       -> persist the complete ranking run and all ranking rows
  -> Top-N shortlist + forced tickers
  -> existing full SignalPipeline for the research set
  -> existing StrategyPipeline
  -> existing Risk / Decision / Execution pipelines
```

`UniverseRankingPipeline` is a separate component with one responsibility: turn
an eligible point-in-time universe plus low-cost market data into a persisted
research-priority cohort. It does not fetch news, fundamentals, option chains, or
LLM output.

The first implementation may issue a second bounded batch-bars request after the
existing liquidity enrichment request. It must not issue one bars request per
ticker. Sharing a single 65-session batch between universe liquidity enrichment
and ranking is an allowed follow-up optimization, but is not required to couple
the two components in the initial implementation.

## Eligibility

The existing `UniverseFilterConfig` remains the owner of asset-type, price,
average-dollar-volume, exchange, sector/industry allow/deny, and manual exclusion
rules.

The ranking stage adds only rank-data eligibility:

- at least 61 valid adjusted daily closes so 60-day returns can be calculated;
- sufficient volume history for the relative-volume component;
- a valid broad-market benchmark series for the same horizons;
- no duplicate symbol in the frozen cohort;
- all data used has `available_for_decision_at <= decision_time`.

Rows failing ranking eligibility are persisted with `status = insufficient_data`
and explicit missing fields. They do not enter the automatic Top-N shortlist.
Forced tickers may still enter deeper research, but their ranking status and
missing-data state must not be presented as a valid score.

Balance-sheet, accounting, and regulatory hard flags are deferred until a
full-universe, point-in-time, low-cost source exists. Direct negative company
catalysts continue to block or downgrade candidates in the existing strategy and
risk layers.

## Ranking Inputs

For each eligible ticker, calculate and persist the following raw metrics from the
same adjusted daily-bar cutoff:

- `return_1d`, `return_5d`, `return_20d`, and `return_60d`;
- `alpha_vs_spy_5d`, `alpha_vs_spy_20d`, and `alpha_vs_spy_60d`;
- the corresponding sector/industry/peer relative returns when a valid cohort is
  available;
- `relative_volume_20d`;
- realized-volatility metric over the configured window;
- drawdown from the recent high;
- one-day return concentration relative to the 20-day move;
- bar count, last bar date, and market-data provenance.

SPY is the single broad-market benchmark in the weighted score. QQQ relative
returns may remain in technical evidence for display and diagnostics, but SPY and
QQQ must not both contribute independent weights to the canonical score. A mapped
sector ETF or configured peer basket supplies the more specific comparison.

## Comparable Cohorts

The cohort resolver uses the most specific point-in-time grouping that has enough
members:

```text
configured peer basket
  -> industry
  -> sector
  -> similar-liquidity cohort
  -> entire eligible universe
```

The minimum cohort size is configurable and defaults to 10. Peer, industry, and
sector metadata must come from already-persisted point-in-time records or existing
relationship configuration; the ranker must not make N external company-profile
requests. Similar-liquidity cohorts are deterministic buckets derived from the
eligible cohort's average dollar volume.

Each ranking row records the selected cohort type, cohort identifier, cohort size,
and any fallback chain used. A fallback is valid ranking behavior, not missing
data, but it lowers confidence when it is materially less comparable than the
preferred cohort.

## Cross-Sectional Normalization

Each continuous component is converted into a deterministic percentile within
its resolved cohort. Ties use average-rank percentiles. Missing values remain
missing; they are never imputed to zero. Symbol is the final deterministic
tie-breaker for output rank.

Percentiles are preferred over raw z-scores in v1 because they are bounded,
interpretable, robust to extreme returns, and easy to reproduce. Raw metrics remain
persisted so a future model version can use median/MAD robust z-scores without
changing the v1 contract.

## Relative-Strength Score V1

The initial version is `cross_sectional_rs_v1`. All weights and penalty thresholds
are stored in versioned configuration rather than hidden constants.

Positive components:

```text
0.30 * peer_or_fallback_20d_percentile
+ 0.20 * sector_or_fallback_20d_percentile
+ 0.15 * market_20d_alpha_percentile
+ 0.15 * relative_strength_60d_persistence
+ 0.10 * multi_horizon_direction_agreement
+ 0.10 * relative_volume_percentile
```

Definitions:

- `peer_or_fallback_20d_percentile` ranks 20-day performance in the most specific
  valid comparable cohort.
- `sector_or_fallback_20d_percentile` ranks 20-day performance in the sector or
  next valid fallback cohort.
- `market_20d_alpha_percentile` ranks 20-day SPY alpha across the eligible market.
- `relative_strength_60d_persistence` is the comparable-cohort percentile of
  60-day benchmark/peer outperformance.
- `multi_horizon_direction_agreement` is the fraction of 5-day, 20-day, and 60-day
  broad-benchmark alpha values that are positive.
- `relative_volume_percentile` ranks current relative volume in the comparable
  cohort; it confirms a move but cannot dominate it.

Penalties:

```text
one_day_concentration_penalty: 0.00 to 0.10
volatility_drawdown_penalty:   0.00 to 0.10
```

The one-day penalty increases when an outsized fraction of the positive 20-day
move came from the latest day. It is zero when the 20-day move is non-positive or
when concentration is below the configured threshold; it must handle near-zero
denominators without division instability.

The volatility/drawdown penalty combines cross-sectional realized-volatility and
drawdown severity percentiles. It must not independently reject a stock; it only
prevents unstable price action from looking like persistent relative strength.

The final score is:

```text
relative_strength_score = clamp(
    weighted_positive_components
    - one_day_concentration_penalty
    - volatility_drawdown_penalty,
    0.0,
    1.0,
)
```

The weights are an explicit v1 prior, not an optimized claim. They remain frozen
until walk-forward evidence supports a new version.

## Confidence

`data_confidence` is separate from `relative_strength_score`. It is derived from:

- required history completeness;
- component availability;
- source freshness;
- cohort specificity and size;
- benchmark and peer coverage.

Confidence does not boost score. A high score with weak confidence remains visible
for forced/manual review but is not eligible for automatic Top-N selection below
the configurable minimum confidence threshold.

The output also records top positive and negative contributors as structured
component/value/contribution rows. These are deterministic explanations, not LLM
summaries.

## Ranking And Shortlist Selection

Eligible rows are ordered by:

1. `relative_strength_score` descending;
2. `data_confidence` descending;
3. average dollar volume descending;
4. ticker ascending.

Each row receives `overall_rank` and `overall_percentile`. The automatic research
set consists of the configured Top-N rows meeting the confidence threshold. The
default N is 100.

Forced tickers are appended after automatic selection and deduplicated. Their
ranking rows retain their original rank and carry one or more inclusion reasons:
`manual_request`, `watchlist_pin`, `open_position`, or `manual_include`.

The full universe snapshot is persisted before narrowing. The narrowed research
set is a separate result, so the UI and runtime cannot mistake "not shortlisted"
for "not in the tradable universe."

## Persistence Contract

Add two persisted concepts.

### `universe_ranking_runs`

- `ranking_run_id`
- `universe_snapshot_id`
- `decision_time`
- `model_version`
- `config_json`
- `input_count`
- `eligible_count`
- `shortlist_count`
- `status`: `running`, `succeeded`, `degraded`, or `failed`
- source/provenance and error metadata
- timestamps

### `universe_rankings`

- `universe_ranking_id`
- `ranking_run_id`
- `ticker`
- `status`: `ranked` or `insufficient_data`
- `overall_rank` and `overall_percentile`
- `relative_strength_score`
- `data_confidence`
- `peer_group_type`, `peer_group_id`, and `peer_group_size`
- `is_automatic_shortlist`
- `forced_inclusion_reasons_json`
- `raw_metrics_json`
- `normalized_metrics_json`
- `positive_contributors_json`
- `negative_contributors_json`
- `missing_inputs_json`
- source-reference and availability metadata

Enforce one row per `(ranking_run_id, ticker)` and index run/rank, ticker/time, and
shortlist status. Scores and percentiles are constrained to 0-1 when non-null.

Historical candidate rows and strategy runs are not backfilled. New
`candidate_scores` reference the ranking run and/or ranking row through explicit
IDs in their persisted context so the research-priority decision can be traced to
the later strategy decision.

## Signal And Strategy Integration

For shortlisted and forced tickers, the ranking overlay is merged into the
canonical technical signal family before strategy matching. New fields include:

- `relative_strength_score`
- `relative_strength_rank`
- `relative_strength_percentile`
- `relative_strength_data_confidence`
- peer/sector/market component percentiles
- multi-horizon agreement
- one-day concentration penalty
- volatility/drawdown penalty
- ranking model and run IDs

The raw one-day `rs_vs_spy_1d` and `rs_vs_qqq_1d` fields may remain for diagnostics
and UI evidence. They are no longer used directly by candidate-scoring formulas.

All candidate scorers that currently consume one-day relative strength must use
the canonical rank signal instead:

- `relative_strength_rotation_v1` and `base_breakout_v1` use the canonical score as
  their primary relative-strength input;
- catalyst scoring uses it as bounded confirmation instead of `max(one-day SPY,
  one-day QQQ)`;
- insider accumulation and valuation-repair scoring use it in their existing
  bounded confirmation slots;
- no candidate scorer may silently reconstruct the removed legacy formula.

For strategies where relative strength is required, a missing or invalid ranking
overlay yields an explicit missing required signal and prevents actionability. For
strategies where it is optional, the component contributes nothing and the
missing state remains visible in evidence.

Candidate score semantics remain strategy-specific. The universe rank indicates
research priority; it is not copied wholesale into every candidate score.

## Failure And Degraded Modes

- If the batch-bars rank input cannot be loaded, mark the ranking run `failed`.
  Do not fall back to the old formula. Automatic scanner shortlisting stops for
  that run; forced tickers may continue through non-ranking-dependent research and
  existing-position risk monitoring.
- If only some tickers lack sufficient history, persist them as
  `insufficient_data` and rank the remaining eligible cohort.
- If a preferred peer cohort is missing or too small, use the documented fallback
  chain and lower confidence.
- If the broad-market benchmark is missing, the run is degraded or failed
  according to the configured minimum viable component set; it must not fabricate
  alpha.
- If persistence fails, do not pass an unpersisted ranking into strategy scoring.
- Provider request failures and coverage are recorded through the existing
  resilience/telemetry conventions.

## Replay And Validation

The ranker is deterministic and point-in-time. Replay consumes the persisted raw
metrics and cohort configuration from the original ranking run or reconstructs a
cohort only from data that was available at that historical decision time.

Before production replacement, run walk-forward validation with chronologically
separated train/calibration and evaluation windows. Do not tune and report on the
same complete history. Compare at least:

- future 5-day, 20-day, and 60-day return;
- alpha versus SPY, relevant sector benchmark, and decision-time peer basket;
- hit rate and mean alpha by score decile;
- monotonicity across rank deciles;
- turnover and cohort stability;
- drawdown and volatility of the selected cohort;
- performance with and without each penalty;
- the historical legacy formula as an offline benchmark only.

The v1 weights are frozen in production. Evidence for a weight change creates a
new model version rather than mutating historical interpretation.

## Testing Strategy

### Unit tests

- return, alpha, relative-volume, volatility, drawdown, and one-day-concentration
  calculations;
- percentile ranking with ties and deterministic ordering;
- peer/industry/sector/liquidity/universe fallback behavior;
- minimum cohort size;
- confidence calculation and missing-component behavior;
- penalty bounds and final score clamp;
- Top-N plus forced-ticker deduplication.

### Pipeline tests

- full universe remains persisted while only the research set reaches expensive
  signal ingestion;
- batch bars are requested in bounded chunks, not per ticker;
- rank rows are persisted before downstream consumption;
- failed ranking has no legacy-formula fallback;
- ranking fields are merged into signal snapshots;
- all existing candidate scorers stop using one-day RS directly.

### Repository and migration tests

- constraints, indexes, relationships, JSON payloads, and upsert behavior;
- one row per run/ticker;
- run-to-universe and candidate-to-ranking traceability.

### Replay tests

- no future bars or revised cohort membership enter a historical rank;
- stored model version/config reproduces the same score and order;
- outcome evaluation computes rank-decile and benchmark/peer attribution.

### Live smoke test

Add a standalone, rate-limited smoke script that ranks a small explicit ticker
set, reports raw metrics, normalized components, score, confidence, and order, and
does not invoke news, fundamentals, options, LLMs, database writes unless an
explicit persistence flag is supplied.

## Delivery Sequence

Implementation planning should split delivery into independently verifiable
steps:

1. Pure ranking records, metric calculation, normalization, scoring, and tests.
2. Persistence models, migration, repository methods, and tests.
3. Bounded batch input loader and live universe-ranking workflow.
4. Pre-open orchestration and Top-N/forced-ticker research-set narrowing.
5. Signal overlay and complete removal of legacy one-day RS use from candidate
   scoring.
6. Replay/outcome comparison and offline walk-forward validation.
7. Standalone smoke test, operational observability, documentation, and tracker
   updates.

## Acceptance Criteria

- A live pre-open run persists one complete ranking cohort for the eligible full
  universe.
- Only Top-N eligible ranked tickers plus forced tickers enter expensive research.
- Every ranked row exposes score, rank, confidence, peer context, raw/normalized
  metrics, and structured contributors.
- New candidate scoring contains no direct use of one-day SPY/QQQ relative return.
- No runtime path falls back to the removed legacy relative-strength formula.
- Ranking-dependent candidates are explicitly blocked when required ranking data
  is unavailable.
- Historical ranking replay is point-in-time and reproducible by model version.
- Walk-forward evaluation reports rank-decile alpha and compares the legacy
  formula offline without using the full sample for weight optimization.
- Focused and broader relevant unit/integration suites pass, compile checks pass,
  `git diff --check` passes, and the project progress tracker is updated when the
  implementation is complete.
