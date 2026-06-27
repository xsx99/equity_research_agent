# News Condensation For Trading Event Signals And LLM Evidence

Date: 2026-06-07
Status: Draft approved in conversation, pending user review

## Summary

The current `events_news` path admits too many duplicate and low-signal headlines into `event_news_items`, which then pollutes:

- `high_signal_news_count_24h`
- `high_signal_news_count_7d`
- `catalyst_quality_score`
- intraday alert generation
- `signal_snapshot.evidence_items` consumed by the trading decision LLM

This design adds a deterministic, ingestion-first news condensation layer that filters low-signal items, collapses near-duplicates, preserves replayability, and limits the number of evidence items sent to the trading decision prompt.

## User Decisions Captured

The design reflects the following approved choices:

- Precision policy: `balanced`
- Storage model: `filtered raw only`
- Relevance/dedupe method: `deterministic only`
- Persistence changes: `allow schema change`

Operational meaning:

- Some news will be intentionally discarded before reaching `event_news_items`.
- The system should avoid aggressive dedupe that could suppress genuinely new facts.
- All filtering and dedupe decisions must be explainable without a secondary model.
- The retained rows must carry enough metadata to explain why they were kept.

## Goals

- Reduce duplicate and low-value news before it enters the trading signal pipeline.
- Make `events_news` aggregate signals represent distinct, decision-relevant events rather than raw headline volume.
- Shrink LLM prompt evidence to a small, high-signal representative set.
- Preserve point-in-time behavior and replayability.
- Improve debugging by persisting condensation metadata and ingestion counters.

## Non-Goals

- No new canonical event table in the first version.
- No LLM or embedding model in the condensation path.
- No historical backfill requirement for previously stored `event_news_items`.
- No attempt to fully solve semantic event extraction across all possible corporate news types.

## Current Problems

The current pipeline has four structural issues:

1. Provider adapters truncate `published_at` to a date string in several cases, which weakens point-in-time fidelity and makes intraday windows too coarse.
2. `SourceIngestionService._refresh_events_news()` converts provider items directly into `event_news_items` without a shared filtering or dedupe step.
3. `build_event_news_signals()` aggregates counts from whatever rows exist, so duplicate media rewrites inflate event counts and catalyst scores.
4. `TradingDecisionPipeline._build_evidence_items()` forwards all windowed news rows to the LLM, so the prompt sees too many noisy and redundant items.

## Design Overview

The new path is:

```text
provider.fetch_recent()
  -> normalize provider item
  -> deterministic news condenser
      -> low-signal filter
      -> event typing refinement
      -> near-duplicate grouping
      -> representative-item selection
      -> condensation metadata
  -> save kept event_news_items only
  -> build event/news signals from kept rows
  -> build intraday alerts from kept rows
  -> build LLM evidence_items from kept rows with a small budget
```

The condensation layer lives inside trading ingestion, before rows are persisted, so downstream consumers inherit cleaner data by default.

## Architecture

### 1. Shared condensation helper

Expand `src/providers/news_data/helpers.py` from a lightweight provider helper module into a reusable deterministic news condensation utility.

Responsibilities:

- normalize title, summary, source, and url
- preserve full provider timestamps
- identify obvious low-signal content
- refine event typing beyond the current coarse `signal_type`
- build canonical duplicate grouping keys
- score specificity
- choose one representative item per duplicate group
- emit keep/drop metadata and aggregate counters

The helper must remain pure and deterministic so it is easy to test with fixture inputs.

### 2. Ingestion integration

Modify `src/trading/signals/source_ingestion.py` so `SourceIngestionService._refresh_events_news()` no longer persists provider items one-by-one immediately after fetch.

Instead it should:

1. fetch provider items
2. normalize them
3. run the deterministic condenser
4. convert kept items into `EventNewsItemRecord`
5. persist only the kept records
6. attach aggregate condensation statistics to `SourceIngestionRun.metadata_json`

### 3. Downstream consumers

All current consumers continue to read `event_news_items`, but they now consume already-condensed rows:

- `build_event_news_signals()`
- `TradingDecisionPipeline._build_windowed_events_news_view()`
- `TradingDecisionPipeline._build_evidence_items()`
- intraday `NewsAlertService`

This keeps the first rollout small while still improving all current trading consumers.

## Detailed Condensation Rules

### 1. Preserve full timestamps

Provider adapters in:

- `src/providers/news_data/finnhub.py`
- `src/providers/news_data/marketaux.py`
- `src/providers/news_data/alpaca.py`

must retain full ISO-8601 timestamps instead of truncating to `YYYY-MM-DD`.

This is required for:

- accurate `24h` windows
- intraday dedupe
- correct `available_for_decision_at`
- consistent replay around pre-open and intraday boundaries

### 2. Normalization

Before scoring or dedupe:

- trim and collapse whitespace in title and summary
- normalize casing for comparison purposes while preserving original text for storage
- remove trailing boilerplate fragments when they are obviously templated
- normalize url when present
- preserve the original provider/source fields for provenance

### 3. Low-signal hard filters

Discard items that match obvious low-value templates, such as:

- `is it too late`
- `should you buy`
- `top N stocks`
- `best stocks`
- `prediction`
- `why <ticker> stock is up today`
- `why <ticker> stock is down today`

Also discard news classified as broad commentary when all of the following are true:

- the item resolves to `general_news`
- no explicit company catalyst terms are present
- title is generic
- summary is missing or empty

This filtering should be conservative. If a headline contains a concrete company event, it should survive even if the publisher style is promotional.

### 4. High-signal event preservation

The condenser should explicitly favor and preserve items that map to these event families:

- earnings result
- guidance raise or cut
- analyst upgrade or downgrade
- price target revision
- SEC filing
- regulatory action
- customer order or customer win
- product launch
- M&A or strategic transaction
- litigation
- recall
- offering
- bankruptcy or insolvency risk

### 5. Event typing refinement

The current `signal_type` mapping is not sufficient for reliable dedupe. The condenser should refine event typing into more specific `event_type` values where possible.

Examples:

- `analyst_rating` can become `analyst_upgrade`, `analyst_downgrade`, or `price_target_revision`
- `earnings_guidance` can become `guidance_raise`, `guidance_cut`, `preliminary_results`, or `earnings_beat_raise`
- `sec_filing` can become `form_8k`, `form_10q`, `form_10k`, `form_4`, or remain generic if necessary

The refined `event_type` remains the main downstream event classifier.

### 6. Near-duplicate grouping

Duplicate grouping must not rely only on url. Build a deterministic group key from:

- ticker
- refined `event_type`
- canonical headline key
- time bucket

The canonical headline key must preserve event-defining facts, for example:

- analyst items: broker name, action, and target price if present
- earnings items: quarter, beat or miss, raise or cut
- filing items: filing type, regulator, and action
- customer/product items: customer or product keywords when present

The time bucket should be narrow enough to collapse syndicated rewrites but not so broad that separate same-day events are merged by accident.

### 7. Representative selection

Within a duplicate group, keep one representative row.

Default selection priority:

1. earliest `available_for_decision_at`
2. highest specificity score
3. most complete title plus summary payload
4. deterministic tie-breaker by provider name then item identity

Earliest availability is prioritized to preserve point-in-time behavior. Later media rewrites should not replace the first actionable version unless they add genuinely new facts.

### 8. New-fact escape hatch

Do not dedupe later items if they introduce materially new facts relative to the earlier item.

Hard signals for a new fact:

- a numerical value changes, such as price target, guidance range, or deal value
- event polarity changes, such as `guidance` becoming `guidance_cut`
- event stage changes, such as `announced` becoming `approved` or `reported`
- a new explicit negative catalyst is introduced

When this happens, the later item should form a separate kept row rather than being absorbed into the earlier duplicate group.

## Data Model Changes

### EventNewsItem metadata

Keep the existing `event_news_items` table, but expand `EventNewsItemRecord.metadata_json` usage so retained rows explain the condensation outcome.

Recommended metadata keys for kept rows:

- `signal_type`
- `normalized_headline`
- `specificity_score`
- `compression_status`
- `compression_reason`
- `duplicate_group_key`
- `duplicate_count`
- `dropped_sources`
- `retained_rank_reason`

Required semantics:

- `compression_status` should be `kept` for persisted rows in the first version.
- `duplicate_count` counts how many raw items were represented by the kept row.
- `dropped_sources` lists providers or source labels absorbed into the kept row.
- `retained_rank_reason` states why this row won the group.

### Source ingestion run metadata

Extend `SourceIngestionRun.metadata_json` to include aggregate condensation counters for each refresh run:

- `raw_news_item_count`
- `kept_news_item_count`
- `dropped_low_signal_count`
- `dropped_duplicate_count`
- `dropped_irrelevant_count`

These counters provide debugging visibility without requiring a new table for discarded items.

## Signal Calculation Changes

`src/trading/signals/event_news.py` should treat its inputs as already-condensed event rows.

Consequences:

- `high_signal_news_count_24h` counts high-signal distinct kept events, not raw headlines.
- `high_signal_news_count_7d` counts high-signal distinct kept events, not raw headlines.
- `catalyst_quality_score` is computed from the kept set, so syndicated rewrites do not inflate it.
- `sentiment_direction` reflects the direction of the condensed set.
- `direct_negative_catalyst_type` should use deterministic precedence rather than whichever negative row happened to arrive first.

Recommended negative precedence:

1. `bankruptcy`
2. `fraud`
3. `offering`
4. `guidance_cut`
5. `regulatory_action`
6. `litigation`
7. `recall`

If multiple negative event types are present, the highest-precedence one should populate `direct_negative_catalyst_type`.

## LLM Evidence Changes

`src/trading/workflows/trading_decision.py` should apply an evidence budget even after condensation.

Recommended policy:

- maximum `4` evidence items
- maximum `1` item per `duplicate_group_key`
- higher `importance` preferred over lower `importance`
- higher `specificity_score` preferred when severity ties
- earlier `available_for_decision_at` preferred when two items describe the same event

Purpose:

- keep the prompt compact
- avoid repeated evidence phrased differently
- preserve the strongest representative proof for each retained event

The prompt contract in `src/agents/prompts/trading/trading_decision_v1.yaml` does not need major semantic changes, but it will receive a much smaller and cleaner `signal_snapshot.evidence_items` array.

## Intraday Alert Implications

`src/trading/intraday/news_alerts.py` already dedupes by `dedupe_key`, but it currently inherits noise from stored `event_news_items`.

After this design:

- alert inputs are cleaner by construction
- repeated rewrites should no longer create repeated alerts when they map to the same condensed event
- a genuinely new fact should still create a new alert because it survives condensation as a distinct row

## Backward Compatibility

- No historical backfill is required.
- Existing rows without new metadata keys must still be readable.
- Missing metadata should default safely in consumer code.
- Old rows with date-only `published_at` values will remain less precise than new rows, but new ingestion will be accurate going forward.

## Testing Strategy

### 1. Unit tests

Expand or add tests covering:

- full timestamp preservation in provider adapters
- low-signal filtering
- duplicate grouping across different urls with equivalent event facts
- new-fact escape hatch
- representative selection priority
- negative catalyst precedence

Relevant test files:

- `tests/providers/test_news_data.py`
- `tests/trading/test_event_news_signals.py`
- `tests/trading/test_signal_sources.py`

### 2. Workflow tests

Extend workflow-level coverage to prove the trading pipeline behavior actually changes:

- duplicate earnings rewrites should count as one distinct event in pre-open signals
- intraday alerts should not duplicate on repeated rewrites
- candidate scoring should no longer be inflated by duplicate headline volume
- LLM evidence should remain within the new budget and include representative items only

Relevant test files:

- `tests/trading/test_trading_decision_repository.py`
- `tests/trading/test_intraday_signals.py`
- `tests/trading/test_news_alerts.py`
- `tests/trading/test_strategy_matching.py`

### 3. Smoke test

Because this path touches external provider ingestion, add a standalone smoke test using stable fixtures or recorded responses.

The smoke test should print:

- raw fetched item count
- kept item count
- dropped low-signal count
- dropped duplicate count
- representative headlines retained

This will make future rule tuning far easier to validate.

## Rollout Plan

### Feature flags

Introduce runtime controls:

- `TRADING_NEWS_CONDENSER_ENABLED`
- `TRADING_NEWS_EVIDENCE_LIMIT`

Suggested defaults for first rollout:

- condenser enabled in local and paper trading environments
- evidence limit set to `4`

### Rollout order

1. provider timestamp preservation
2. deterministic condenser and metadata
3. signal aggregation against condensed rows
4. LLM evidence budget

This staged rollout makes it easier to isolate regressions.

## Risks And Mitigations

### Risk: over-deduping

Problem:

- two related but distinct same-day items may be collapsed incorrectly

Mitigation:

- prefer conservative grouping
- preserve event-defining numeric and polarity facts in the group key
- add explicit new-fact escape logic

### Risk: hidden data loss

Problem:

- discarded rows are no longer queryable from `event_news_items`

Mitigation:

- persist detailed keep metadata
- persist aggregate drop counters in ingestion runs
- keep the first rollout deterministic and reviewable

### Risk: test brittleness

Problem:

- heuristic ranking can become unstable if not fully deterministic

Mitigation:

- define explicit tie-break order
- round or normalize scores consistently
- test with fixed fixtures and deterministic ordering

## Open Questions Deferred

- Whether a future version should preserve dropped rows in a separate audit store.
- Whether provider-specific source trust ranking should influence representative selection beyond the first version.
- Whether the same condensation logic should later be reused by the research workflow outside trading.

## Recommended Next Step

After user approval of this design spec, create an implementation plan covering:

1. provider timestamp preservation
2. condensation helper design and tests
3. source ingestion integration
4. event signal contract updates
5. LLM evidence budget changes
6. smoke test and rollout controls
