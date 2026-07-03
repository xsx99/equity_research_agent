# Handoff — Insider signals: distinguish "no activity" from "never fetched" + kill the 9-line missing spam

**Investigation done → implementation handoff.** Root cause confirmed in code (file:line below).
Nothing applied. Line numbers approximate — reconfirm before editing.

## Owner constraint (read first)

**Insider (Form 4) data is genuinely sparse — most tickers have no insider activity on any given
window, and that is fine. "Missing" is an acceptable outcome; do NOT fabricate insider data or try
to force these fields to always be populated.** This task is *not* "make insider always present."
It is about representing the sparse reality honestly and cutting misleading noise:

1. When we KNOW the collector has covered the window and a ticker simply had no filings, that is a
   real fact ("no insider buying") → represent it as **zeros/False**, not as 9 "missing" gaps.
2. When we genuinely have NOT fetched insider data for the window, keep it "missing" — that's honest.
3. Either way, stop emitting 9 separate `Missing signal: insider.*` counterarguments (see CRDO
   screenshot) — collapse to a single, accurate statement.

## Context / problem

CRDO's decision lists **all nine** insider fields as separate "Missing signal:" counterarguments:
`purchase_count_30d, sale_count_30d, insider_net_buy_value_30d, insider_net_buy_value_90d,
insider_cluster_buy_count_90d, officer_buy_flag, director_buy_flag, sale_concentration_score,
recent_form4_filing_at`. This reads as "we failed to get 9 pieces of data" when the reality is one
fact: this ticker had no Form 4 activity in the window.

## Root cause (confirmed)

- **Builder asymmetry** — `src/trading/signals/insider.py:37-38`: when there are **zero** insider
  records, it returns `values={}` and reports the entire `REQUIRED_INSIDER_FIELDS` tuple as missing.
  But when there is *any* record (:40-96) it produces sensible **zeros/False** (`purchase_count_30d=0`,
  `officer_buy_flag=False`, `sale_concentration_score=0.0`, …) and almost nothing is missing. So the
  "no activity" case and the "zero records" case are modeled completely differently — the former is
  informative, the latter is a wall of "missing."
- **Collector IS running** (verified) — `SECEdgarJob` is a daily APScheduler cron (default 02:00,
  `src/scheduler/jobs/sec_edgar_job.py:23`, wired via `src/scheduler/service.py:80` →
  `scripts/run_scheduler_service.py:22` → `Dockerfile:20` / `docker-compose.yml`). It is NOT
  orphaned. It fetches **market-wide** Form 4 filings (not watchlist-scoped) from SEC EDGAR's
  current-filings feed (`src/collectors/sec_edgar/collector.py:28,57-91`) and upserts to
  `insider_trades`.
- **But it only fetches `target_date = today`** (`sec_edgar_job.py:66-69`, offset default 0,
  `src/core/config.py:36`). It never backfills. So the 30d/90d windows only contain history
  accumulated since the cron started — on a young deployment insider history is thin, which is a
  big reason so many tickers currently show no insider rows.
- **Insider flows in read-side only** — it is deliberately NOT in the pre-open ingestion family
  list (`src/trading/workflows/signal_snapshot.py:73` = technical/fundamental/events_news/
  social_macro/option_chain), and `SourceIngestionService` has no insider branch
  (`src/trading/signals/source_ingestion.py:110`). `records_for_ticker`
  (`src/trading/repositories/source_sqlalchemy.py:171-194`) joins whatever the daily cron deposited.
  **This is by design — do NOT add `insider` to the ingestion family list.**
- **No coverage/freshness tracking** — the SEC collector writes only to `insider_trades`; it never
  records a `SourceIngestionRun`. Snapshot freshness (`src/trading/signals/snapshots.py:76-79`) is
  inferred purely from row presence: `insider → "fresh"` iff there's ≥1 row for the ticker, else
  `"missing"`. **So today the code literally cannot tell "collector ran, this ticker had no filings"
  from "collector never ran."** Both collapse to all-9-missing. Fixing that ambiguity is the crux.

## Solution — three parts

### Part 1 — a coverage signal (so we can tell the two cases apart)

We need a boolean "have we actually collected market-wide insider filings recent enough to cover
this decision window?" Because the feed is **market-wide**, on any normal trading day there are many
Form 4 filings across the market — so a recent *global* latest filing date is a reliable indicator
the collector is live and current, independent of any single ticker.

**Recommended (no schema change, no writer change): global-latest-filing heuristic.** Add a repo
method that returns the max filing/published timestamp across the whole `insider_trades` table:

- In the insider repository (same module as the join, `source_sqlalchemy.py`), add e.g.
  `latest_insider_filing_at() -> datetime | None` = `SELECT max(published_at) FROM insider_trades`.
- Define coverage as: `insider_data_covered = latest is not None and latest >= decision_time - COVERAGE_WINDOW`
  where `COVERAGE_WINDOW` is a small tolerance (~3–4 calendar days to ride over weekends/holidays
  when no Form 4s post). Put the constant somewhere config-visible.

**Alternative (more work, more precise): record a `SourceIngestionRun` for the SEC job.** Have
`SECEdgarJob` write a run row (family `insider`) on success so freshness uses the same machinery as
other families (`source_ingestion_runs`, `db/models/trading/signals.py:28`). Cleaner long-term but
needs a writer change + migration; the heuristic above is enough to ship the UX fix now.

### Part 2 — builder: model "covered but empty" as zeros, keep "uncovered" as missing

Thread the coverage flag into the builder. `src/trading/signals/insider.py`:

```python
def build_insider_signals(
    records: list[SourceRecord] | tuple[SourceRecord, ...],
    *,
    decision_time: datetime,
    data_covered: bool = False,   # NEW: did the collector cover this window?
) -> InsiderSignals:
    if not records:
        if data_covered:
            # Collector is current and this ticker simply had no Form 4 activity.
            # That is a real, informative signal — represent it as zeros/False,
            # not as nine missing gaps.
            values = {
                "purchase_count_30d": 0,
                "sale_count_30d": 0,
                "insider_net_buy_value_30d": 0.0,
                "insider_net_buy_value_90d": 0.0,
                "insider_cluster_buy_count_90d": 0,
                "officer_buy_flag": False,
                "director_buy_flag": False,
                "sale_concentration_score": 0.0,
                "recent_form4_filing_at": None,  # legitimately null — no filing exists
            }
            # recent_form4_filing_at is null-by-nature here, not a data gap; do NOT
            # list it as missing when covered (see note).
            return InsiderSignals(values=values, missing=())
        # Genuinely not fetched — honest "unknown".
        return InsiderSignals(values={}, missing=REQUIRED_INSIDER_FIELDS)
    ...  # existing populated path unchanged (already yields zeros/False sensibly)
```

Decision to confirm with owner: when `data_covered` and no records, should `recent_form4_filing_at`
be listed as missing? Recommend **no** — it's null because no filing exists, which is consistent
with the zeros above; listing it re-introduces a spurious "missing" line. (If you'd rather flag that
one, keep `missing=("recent_form4_filing_at",)` — but then update Part 3 so the UI shows it as
"no recent filing", not "missing signal".)

Then in `src/trading/signals/snapshots.py:58-61`, pass the flag and fix freshness:

```python
    insider = build_insider_signals(
        records_by_family.get("insider", ()),
        decision_time=decision_time,
        data_covered=insider_data_covered,   # threaded in as a new param to build_signal_snapshot
    )
```

`build_signal_snapshot` is a pure function (snapshots.py:40-48) with no repo access, so add an
`insider_data_covered: bool = False` parameter and have the **caller** (the signal-snapshot
workflow / wherever `records_for_ticker` + `build_signal_snapshot` are invoked) compute it via the
Part-1 repo method and pass it down. Also update `source_freshness` (snapshots.py:76-79) so insider
reports `"fresh"` when `insider_data_covered` (even with no rows) and `"missing"` only when not
covered — otherwise the freshness label stays wrong for the covered-but-empty case.

### Part 3 — collapse the 9-line "missing" spam in the UI / counterarguments

Even after Part 2, an *uncovered* insider family still contributes 9 prefixed entries to
`missing_signals_json` (snapshots.py:70). Those nine feed the decision agent's counterargument list
(the `Missing signal: insider.*` bullets in the screenshot). When an **entire family** is missing,
present it as ONE item, not nine:

- Simplest: collapse at the presenter that renders counterarguments/missing signals (grep the
  `src/web/presenters/` layer that emits the EVIDENCE tab counterarguments — same area touched in
  `today_realdata_bugs_handoff.md`). When all `REQUIRED_INSIDER_FIELDS` are present in the missing
  list, replace the nine `insider.*` bullets with a single line:
  - covered + empty (post Part 2 this won't be missing at all, but for safety): "No insider Form 4
    activity in the last 90 days" — treat as neutral/informative, not a data gap.
  - not covered: "Insider data not yet available for this window."
- If the counterarguments are generated by the LLM decision agent from `missing_signals_json`,
  collapse family-complete-missing sets **before** they reach the agent prompt (a helper that maps a
  full-family missing set to one synthetic token like `insider_family_unavailable`), so the agent
  doesn't enumerate nine of them. Check where `missing_signals_json` is fed into the agent input.

## Optional (context, not required) — speed up the history ramp

Because the collector only ever fetches `target_date = today` (`sec_edgar_job.py:66-69`), the 90d
window is empty on a fresh deploy and fills in one day at a time. If the owner wants insider signals
meaningful sooner, a **one-time historical backfill** (loop `collect(target_date)` over the past
~90 calendar days) would populate `insider_trades` immediately. The collector already accepts a
`target_date` arg, so this is a script, not a code change. Purely optional — consistent with "sparse
is fine", the window will self-fill over ~90 days regardless.

## Explicitly OUT of scope / do-not-do

- Do NOT add `insider` to the pre-open/intraday ingestion family list — insider is read-side by
  design (SEC cron is the sole writer).
- Do NOT fabricate insider values or synthesize filings.
- The market-wide-fetch design is fine; no need to make the collector watchlist-scoped.

## Tests

- `build_insider_signals` with `records=(), data_covered=True` → all count/flag fields zero/False,
  `missing == ()` (and freshness "fresh" at the snapshot level).
- `build_insider_signals` with `records=(), data_covered=False` → `missing == REQUIRED_INSIDER_FIELDS`
  (unchanged legacy behavior).
- Populated-records path unchanged (existing tests should still pass).
- Repo test for `latest_insider_filing_at()` (global max) and the `insider_data_covered` derivation
  across the coverage-window boundary (fresh vs stale vs empty table → None → not covered).
- Presenter/agent test: a full insider-family missing set renders as ONE line, not nine.

## Definition of done

- Code can distinguish "collector current, no activity for this ticker" (→ zeros/False, informative,
  not missing) from "insider data not fetched for this window" (→ honest single "unavailable").
- CRDO-style decisions no longer emit nine `Missing signal: insider.*` bullets — at most one line.
- No insider fabrication; sparse/absent insider data remains an accepted, clearly-labeled outcome.
- Insider stays read-side only (ingestion family list unchanged).

## Relationship to the other handoffs

- Fundamental-family missing (`ev_sales_percentile`, `fcf_margin_score`, `short_interest_bucket`,
  `valuation_percentile`) → `pr_44_yfinance_fundamentals_backfill.md`.
- Technical `rs_vs_spy_1d` / `rs_vs_qqq_1d` / `premarket_gap_pct` → `pr_45_technical_relative_strength_gap.md`.
- Capability markers (`option_chain_availability`, `full_transcript_interpretation`,
  `macro_sector_readthrough`) remain intentional always-missing (`snapshots.py:72-74`); not in scope.
