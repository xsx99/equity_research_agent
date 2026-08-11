# Strategy Learning Loop Recovery Design

**Date:** 2026-08-11
**Status:** Approved for implementation planning
**Supersedes for production:** the candidate-reconstruction trigger proposed by
`plan/implementation/pr_38_historical_replay_wiring.md`

## 1. Problem

The System tab currently makes it appear that strategies disappeared, but three
separate failures are combined in that presentation:

1. `strategy_proposals` still contains historical rows, but the UI only loads the
   latest ten calendar days. When no new proposal is created, the panel becomes an
   unexplained zero.
2. Strategy performance is derived entirely from
   `candidate_outcome_evaluations`, and the production database has no outcome
   rows. `historical_replay_runs` is also empty because the existing replay runner
   is only reachable through a fixture smoke path.
3. The 60-day strategy-evolution loader serializes every rejected candidate into
   the LLM prompt. A reconstructed 2026-07-30 request contained 7,691 rejected
   candidates and rendered to 4,152,584 characters, after which OpenRouter
   returned HTTP 400. The failure occurred before prompt-run or proposal
   persistence.

The strategy catalog itself is not empty. The repair must restore the continuous
outcome-to-learning loop and make the UI explain its state; merely widening the
proposal lookback would mask the fault.

## 2. Goals

- Evaluate the candidates that were actually persisted at each historical
  decision time, without reconstructing them from current strategy definitions.
- Produce deterministic interim and final outcome rows for selected, rejected,
  watch, manual, active, and shadow candidates.
- Backfill the most recent 60 calendar days and then evaluate newly matured
  candidates every trading day.
- Run outcome evaluation before reflection and strategy evolution.
- Bound strategy-evolution inputs before prompt rendering and never send an
  over-budget request.
- Separate research edge from real paper-trade performance in the System UI.
- Always show current strategy definitions and explain why no recent proposal was
  created.
- Persist success, degraded, skipped, and failed post-close runtime states.

## 3. Non-Goals

- Reconstructing past candidates with strategies or lifecycle states that did not
  exist at the original decision time.
- Building a fully event-sourced strategy-definition history in this recovery.
- Treating replay alpha as dollar P&L.
- Enabling live brokerage, non-paper execution, or new trading authority.
- Replacing the existing offline `HistoricalReplayRunner`; it remains useful for
  controlled research fixtures and future point-in-time reconstruction work.
- Backfilling more than 60 calendar days in the first production run.

## 4. Chosen Architecture

Production learning will use a new `OutcomeEvaluationPipeline` over persisted
`candidate_scores`. It will not call `StrategyMatcher` for historical dates.

The existing `HistoricalReplayRunner` has a different responsibility: reconstruct
a candidate cohort from decision-time signal snapshots. Using it for daily
production maturation would load current active strategy definitions, create new
strategy runs and candidate scores, and risk strategy-version lookahead. It remains
an offline/research path.

Both paths may persist `historical_replay_runs`, distinguished by
`metadata_json.mode`:

- `persisted_candidate_maturation`: production outcome evaluation.
- `candidate_reconstruction`: offline historical replay.

This reuses the existing outcome-run lineage without inventing a second run table.

One run row represents one exact
`(source_decision_time, snapshot_type, evaluation_as_of_session, mode)` tuple, not
an entire calendar day. Its id is a stable UUIDv5 derived from that tuple. A source
date containing pre-open, manual, and intraday decisions therefore produces
separate lineage rows. The outer backfill transaction boundary remains the source
decision date and may contain several such run rows.

Existing status constraints are retained rather than widened:

- `historical_replay_runs.status`: `running`, `succeeded`, or `failed`.
- A partially complete provider result is stored as `status=succeeded` with
  `metadata_json.result_status=degraded` and explicit missing/error counts.
- `trading_runtime_runs.status`: `passed`, `failed`, or `skipped`.
- A degraded scheduler invocation is stored as `status=passed` with
  `metadata_json.result_status=degraded`. The UI maps this combination to the
  user-facing label `Degraded`.

### 4.1 Component Boundaries

`OutcomeHorizonPolicy`

- Pure Python mapping from a canonical `typical_horizon` to interim and final XNYS
  session offsets.
- Rejects unknown values with `unsupported_horizon`; it never guesses.
- Supplies the longest evidence-retention requirement.

`OutcomeCandidateRepository`

- Loads persisted candidates with due interim or final checkpoints.
- Performs due/previously-evaluated filtering in SQL.
- Loads the original classification/watch context needed for attribution.
- Groups lineage by exact decision time and linked signal-snapshot type.
- Upserts outcome and run records with database-enforced idempotency.

`OutcomePriceLoader`

- Uses the existing Alpaca provider and provider-resilience conventions.
- Builds one deterministic symbol union from the candidate, `QQQ`, `SPY`, the
  candidate's persisted sector/theme ETF keys, persisted peer-basket members, and
  persisted opportunity-set members, then batch-loads split-adjusted bars over
  explicit date ranges.
- Loads comparator identities, members, and optional decision-time weights from
  persisted candidate context through `OutcomeCandidateRepository`; it never
  resolves current taxonomy membership inside the price loader.
- Uses an injected XNYS calendar so tests remain offline and deterministic.
- Returns structured missing-symbol and provider-error details rather than
  fabricating price points.

`OutcomeEvaluationPipeline`

- Processes one original decision date per transaction.
- Computes price boundaries, returns, alpha, MFE, and MAE.
- Writes only complete, auditable interim/final rows.
- Returns a normalized runtime report with counts and reason codes.

`OutcomeBackfillCommand`

- Exposes `--start-date`, `--end-date`, `--resume`, and `--dry-run`.
- Defaults to no mutation unless an explicit date range is supplied.
- Processes dates independently so one failed date does not roll back others.

`StrategyEvolutionEvidenceBuilder`

- Converts database-scale evidence into bounded aggregate groups and representative
  outcome rows.
- Owns all input caps and the final rendered-prompt budget.
- Does not make lifecycle decisions; the existing deterministic evidence gate
  remains authoritative.

`ExecutionLedgerReducer`

- Pure read-model code that constructs completed stock and option trade cycles from
  persisted orders and fills.
- Excludes open or unpairable cycles from performance statistics and reports their
  counts.

## 5. Horizon Policy

All offsets are XNYS trading sessions, not calendar days. The lower end of a range
is the interim checkpoint and the upper end is the final checkpoint.

| Canonical horizon | Interim session | Final session |
| --- | ---: | ---: |
| `intraday-2d` | 1 | 2 |
| `intraday-3d` | 1 | 3 |
| `1d-2w` | 1 | 10 |
| `2d-3w` | 2 | 15 |
| `2d-4w` | 2 | 20 |
| `3d-4w` | 3 | 20 |
| `1-6w` | 5 | 30 |
| `1-8w` | 5 | 40 |
| `2-8w` | 10 | 40 |
| `2w-8w` | 10 | 40 |
| `2w-3m` | 10 | 63 |
| `1-3m` | 21 | 63 |
| `2-12w` | 10 | 60 |
| `intraday-3m` | 1 | 63 |
| `intraday-4w` | 1 | 20 |
| `multi-month+` | 63 | 126 |

New strategy proposals must use one of these canonical values. Existing unknown
values are skipped and surfaced; they are not coerced.

### 5.1 Price Boundaries

- A pre-open candidate starts at the regular-session open for its decision
  session.
- An intraday candidate starts at the first minute bar at or after decision time.
- A checkpoint ends at the regular-session close for the corresponding session.
- Candidate and benchmark calculations use identical boundaries.
- Daily/intraday OHLC data supplies MFE and MAE through interval highs and lows.
- Prices are split-adjusted. The run records provider, feed, adjustment, and bar
  resolution in metadata.

An outcome is complete only when the candidate and primary benchmark have valid
start/end prices. Missing price data leaves the checkpoint pending for retry and is
reported on the run; it does not create a final row with null alpha.

### 5.2 Direction, Watch, and Finalization Semantics

The evaluator records the raw underlying return in
`metadata_json.underlying_return` and uses `candidate_return` as the
direction-adjusted thesis return:

- `bullish` or `long`: `candidate_return = underlying_return`.
- `bearish`, `short`, or the exact canonical value `risk_off`:
  `candidate_return = -underlying_return`.
- `neutral`: `candidate_return = underlying_return`, `alpha = null`, and
  `metadata_json.directional_edge_eligible=false`.
- Any other or missing legacy direction, including existing `risk_warning` rows,
  is recorded as `unsupported_direction` and is never inferred from thesis text,
  status, or rejection reason. Once candidate prices are available, the checkpoint
  receives one idempotent observational interim/final row with null alpha,
  `directional_edge_eligible=false`, and
  `metadata_json.evaluation_disposition=unsupported_direction`; it is then
  terminal rather than retried every day.

For bullish/long candidates, comparator alpha is candidate underlying return minus
comparator return. For bearish/short/risk-off candidates it is comparator return
minus candidate underlying return. A directional win means primary alpha is
strictly positive. Neutral outcomes and rows with null primary alpha are excluded
from win-rate, proposal, and lifecycle-promotion evidence; they remain visible as
watch/opportunity observations.

Candidate status and selection path do not change this math. A rejected bullish
candidate, for example, can record missed positive edge, while a bearish blocked
candidate can record whether the avoided-loss thesis was correct.

Direction-adjusted excursion metrics use every aligned bar from the start boundary
through the checkpoint. Let `s` be `+1` for bullish/long and `-1` for
bearish/short/risk_off, and let each bar's raw excursion return be measured from
the candidate start price. Then:

- `max_favorable_excursion = max(s × raw_path_return)`
- `max_adverse_excursion = min(s × raw_path_return)`

Raw high/low excursion returns remain in metadata for audit. Neutral rows retain
raw MFE/MAE observations but are not directional evidence.

Risk-adjusted comparator performance is the annualized information ratio of
aligned session active returns: `mean(s × (asset_return - comparator_return)) /
sample_stddev(...) × sqrt(252)`, using the `n-1` denominator. It is null with fewer
than two aligned observations or zero standard deviation and is stored per comparator in
`metadata_json.comparator_information_ratios`. It is diagnostic/UI evidence only;
the current promotion gate continues to use final alpha and win rate.

Finalization follows the existing replay/learning contract:

- A selected trade-path candidate finalizes at the earlier of a complete position
  close or its canonical final session. Partial reductions do not finalize it.
- Its actual close timestamp and close fill determine the early endpoint, and
  `metadata_json.finalization_reason=trade_closed`.
- A selected trade still open at the horizon finalizes at horizon close with
  `finalization_reason=horizon_expired`.
- Rejected, watch, manual-review-only, and non-traded shadow candidates finalize
  only at their canonical final session.
- Interim rows never become final in place; a distinct final row is inserted at
  the applicable endpoint.

`Strategy Edge` consumes these candidate outcomes. `Traded Performance` separately
uses the complete execution ledger, so actual fill P&L is never inferred from an
underlying candidate return.

Selection status does not disqualify a directional research outcome: bullish or
bearish `watch_only`, rejected, manual-review, and shadow rows may support proposal
and shadow-to-experimental gates. Neutral rows never satisfy a promotion gate.
Experimental-to-active promotion is stricter: its cited final outcomes must be
linked to selected trade paths that produced paper fills, preserving the existing
requirement for paper-trade evidence.

### 5.3 Comparator Contract

Comparator identities must come from the candidate's persisted decision-time
benchmark/peer/source context. The evaluator must not query a latest relationship
or taxonomy table to reconstruct an old comparator.

- `benchmark_returns_json` stores all available comparator returns keyed by stable
  identifiers: `SPY`, `QQQ`, configured sector/theme ETFs, and a persisted
  decision-time opportunity-set key when available.
- `peer_basket_id` and `peer_basket_return` retain the decision-time peer-basket
  lineage.
- `metadata_json.comparator_alphas` stores the direction-adjusted alpha for every
  available comparator, including `peer:<peer_basket_id>`.
- `metadata_json.primary_comparator_key` identifies the comparator used for the
  scalar `alpha` column. It is the candidate's persisted primary benchmark, with
  deterministic fallback to `QQQ` and then `SPY` only when the persisted primary
  key is absent.
- Candidate price plus the primary comparator are required for a directional final
  row. Missing either leaves it pending. Missing optional sector/theme/peer/
  opportunity comparators does not block finalization, but the run records the
  missing comparator keys and the UI exposes comparator coverage.
- A composite peer or opportunity-set return uses persisted decision-time weights
  when present. If no weights were persisted, it uses deterministic equal weights
  across the persisted members. Every persisted member must have valid aligned
  boundary prices; otherwise that optional comparator is marked missing rather
  than silently reweighting the surviving members.

## 6. Idempotency and Transactions

Add a uniqueness constraint over:

```text
(candidate_score_id, evaluation_status, horizon_end_at)
```

Production maturation outcomes always have a non-null `candidate_score_id`.
Offline replay remains compatible because each reconstructed candidate receives a
new candidate id.

- Re-running a completed date skips existing checkpoints.
- One decision date is one transaction.
- A 60-day backfill commits successful dates independently.
- A failed batch is rolled back, then its failed runtime/run state is persisted in
  a fresh transaction.
- A degraded batch commits complete outcomes and records missing symbols and retry
  reasons.
- Existing successful outcomes are never replaced by a later provider response.

Long-horizon candidates may receive an interim row during the initial backfill and
a final row in a later daily run.

The stable run UUIDv5 makes retry lineage idempotent. If every due checkpoint for a
run already exists, the invocation reports it as already evaluated instead of
creating a second run record.

## 7. Schedule and Data Flow

The weekday post-close order in `America/New_York` becomes:

1. `16:10` — outcome evaluation of every due persisted candidate.
2. `16:20` — reflection consumes newly available interim/final outcomes.
3. `16:50` — strategy evolution consumes bounded multi-day final evidence.

The outcome job queries due checkpoints across prior decision dates, rather than
only evaluating same-day candidates. XNYS session calculation naturally handles
weekends and exchange holidays.

The first rollout runs a dry-run report, then a resumable backfill for the latest
60 calendar days. Backfill execution against production remains an explicit
operator action after code deployment and database verification.

## 8. Strategy-Evolution Input Budget

Time windows and prompt cardinality are separate controls:

- Reflection rows, learning factors, proposal hints, and rejected-candidate
  summaries use a 60-day window.
- Final outcome evidence uses a 270-day window so 63- and 126-session strategies
  can be evaluated.
- The LLM sees bounded aggregates and representative rows, never the raw query
  window.

`StrategyEvolutionEvidenceBuilder` applies these deterministic caps:

- At most 20 evidence groups keyed by
  `strategy_id × horizon × regime × sector/theme`.
- At most 5 representative final outcome rows per group, selected to maximize
  distinct dates and tickers.
- At most 50 rejected-candidate aggregate groups. Representative examples are
  included only for the top 20 groups, at most 2 per group and 40 globally.
- At most 20 deduplicated reflection hints.
- At most 30 recent/high-confidence candidate or observation learning factors.
- Existing strategies use a compact contract: id, display name, horizon,
  lifecycle, source, thesis, required signals, and risk tags. Full `config_json` is
  excluded.

Evidence groups are first restricted to complete directional final rows and must
pass the existing evidence gate across the full group. Eligible groups are ranked
by this exact tuple:

1. mean alpha descending
2. win rate descending
3. final-row count descending
4. most recent decision time descending
5. normalized group key ascending

Representative rows are chosen greedily until five rows are selected. At each
step, rank remaining rows by: unseen decision date first, unseen ticker first,
absolute distance from the group's median alpha ascending, decision time
descending, ticker ascending, and outcome id ascending. This avoids top-alpha
cherry-picking while maximizing date/ticker diversity and makes fixtures stable.
The representative subset must itself satisfy the same minimum final-row,
distinct-date, distinct-ticker, win-rate, and mean-alpha gate; otherwise the group
is omitted from the LLM input.

Rejected-candidate groups are ranked by count descending, latest decision time
descending, then normalized `(strategy_id, reason, date)` ascending. Representative
examples use decision time descending, ticker ascending, then candidate id
ascending. Reflection hints and learning factors use confidence descending,
trade-date descending, then their stable id/key ascending. All sorting happens
before caps are applied.

The fully rendered prompt must be at most 120 KiB in UTF-8. Selection is completed
before rendering. If the structured input still exceeds the limit, the runtime is
persisted as `skipped` with `input_budget_exceeded`; the code does not truncate JSON
or call the provider.

If no evidence group can meet the minimum final-row/date/ticker requirements, the
runtime is persisted as `skipped` with `insufficient_final_evidence`, and no LLM
call is made.

The existing Python gate continues to validate every cited outcome id and enforce
final-only evidence, distinct dates, distinct tickers, win rate, and positive mean
alpha. Interim rows can inform reflection but cannot satisfy proposal or promotion
gates.

HTTP errors are caught at the model boundary. Runtime metadata may retain status
code, provider error code, and a short sanitized message; it must not persist API
keys, authorization headers, full request payloads, or provider URLs containing
credentials.

## 9. System UI Read Models

The System tab shows four explicit sections.

### 9.1 Current Strategies

- Always loads `strategy_definitions`, independent of outcomes and proposals.
- Shows counts and rows for active, experimental, shadow, and candidate states.
- Displays source and canonical horizon.

### 9.2 Strategy Edge

- Uses only `candidate_outcome_evaluations`.
- Groups final outcomes by strategy and displays final sample count, distinct
  dates/tickers, win rate, mean/median alpha, and MFE/MAE.
- Displays interim coverage separately.
- Replaces the current incorrect `Total P&L = sum(alpha)` label. Alpha is a return
  difference, not dollar P&L.
- Clearly labels this as candidate/replay evidence, not traded account performance.

### 9.3 Traded Performance

- Uses only real paper stock and option fills.
- Stock cycles are reduced chronologically by
  `(ticker, strategy_id, trade_identity)` using signed order actions. A cycle closes
  when cumulative quantity returns to zero.
- Option cycles are grouped by option-strategy decision/order lineage and close
  action.
- A completed cycle's realized P&L is the sum of its fill cash effects; return is
  realized P&L divided by opening cash at risk.
- Shows closed-trade sample count, win rate, realized P&L, and average return.
- Open cycles are excluded. Unpairable legacy fills are excluded and surfaced as
  an `unpaired execution count`; the UI never guesses their P&L.

### 9.4 Proposal History and Runtime State

- Keeps the recent ten-day proposal region as the primary view.
- When it is empty, shows last proposal date, retained historical count, and the
  latest strategy-evolution runtime status/reason.
- Makes retained historical proposals available in a bounded expandable region.
- Shows the latest outcome-evaluation, reflection, and evolution statuses so an
  operator can distinguish no evidence, skipped, degraded, and failed states.

## 10. Error Handling and Observability

Every post-close phase persists a normalized runtime report for successful,
degraded, skipped, and failed executions.

Required outcome summary fields:

- due candidate/checkpoint count
- created interim/final counts
- already-evaluated count
- unsupported-horizon count
- missing-price and provider-error counts
- decision dates attempted/completed/failed
- provider request/budget metadata
- semantic result status (`passed` or `degraded`) when the persisted runtime status
  is `passed`

Required evolution reason codes include:

- `insufficient_final_evidence`
- `input_budget_exceeded`
- `provider_http_error`
- `provider_timeout`
- `validation_failed_after_retry`

Logs and UI show reason codes and safe summaries. Full evidence remains in database
records and prompt telemetry subject to the existing redaction contract.

## 11. Testing Strategy

Implementation follows TDD and uses fake providers for ordinary tests.

Unit coverage:

- Every canonical horizon and unknown-horizon rejection.
- XNYS weekend, holiday, pre-open, and intraday price boundaries.
- Interim/final return, alpha, direction-adjusted MFE/MAE, and sample-standard-
  deviation information-ratio calculation.
- Exact direction mapping, including terminal observational handling for legacy
  `risk_warning` and other unsupported values.
- Missing candidate/benchmark bars and degraded results.
- Evidence grouping, diversity selection, caps, and 120 KiB preflight.
- Execution-ledger partial fills, reduce/exit, multiple cycles, option cycles, open
  cycles, and unpairable rows.

Repository/integration coverage:

- SQL due-checkpoint filtering.
- Outcome/run round-trip and uniqueness enforcement.
- Re-running the same backfill without increasing outcome count.
- Per-date transaction isolation and resumable backfill.
- Runtime report persistence for every terminal state.

Scheduler/runtime coverage:

- Outcome → reflection → evolution ordering.
- No LLM call for insufficient evidence or over-budget input.
- Provider failure does not suppress later scheduler runs.

Web coverage:

- Current strategies remain visible when outcomes/proposals are empty.
- Strategy Edge and Traded Performance never mix sources or units.
- Proposal empty state shows retained history and runtime reason.
- Machine statuses are rendered through user-facing labels.
- `ui-development` render verification covers the System tab at desktop and narrow
  widths.

Standalone smoke coverage:

- Fixture-only outcome pipeline smoke.
- Database-backed dry-run/backfill smoke with an explicit small date range.
- Production backfill remains opt-in and rate-limit conscious.

## 12. Rollout

1. Add horizon policy, persistence/idempotency, outcome pipeline, and offline tests.
2. Add dry-run/resumable backfill command and runtime observability.
3. Add bounded evolution evidence builder and safe provider error handling.
4. Add the scheduler job and assert post-close ordering.
5. Add the four System UI read models and render verification.
6. Verify Postgres `SHOW data_directory;` maps to persistent disk before migration
   or backfill.
7. Deploy through the existing Docker Compose infrastructure.
8. Run a production dry-run, inspect due counts/provider budget, then explicitly
   run the 60-day backfill.
9. Confirm non-zero, duplicate-free final outcomes and a bounded evolution prompt
   before enabling the daily outcome job.

## 13. Acceptance Criteria

- A 60-day dry-run reports due interim/final checkpoints without writing rows.
- The corresponding live backfill can resume after failure and produces no
  duplicates when repeated.
- `candidate_outcome_evaluations` contains complete rows linked to the original
  candidate scores, with candidate and benchmark prices on identical boundaries.
- The daily post-close sequence is outcome evaluation, reflection, then evolution.
- Strategy evolution never sends a rendered prompt larger than 120 KiB.
- Missing or insufficient evidence skips safely and is visible in runtime state.
- Proposal and promotion gates consume only complete final outcomes.
- The System UI always shows current strategy definitions.
- Strategy Edge uses return/alpha units; Traded Performance uses actual fill-derived
  realized P&L and never includes replay alpha.
- An empty recent proposal window shows retained history and the latest reason.
- Targeted repository, trading, scheduler, agent, and web suites pass; the System
  tab passes visual verification.
