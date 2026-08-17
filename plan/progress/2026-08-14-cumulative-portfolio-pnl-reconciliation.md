# Cumulative Portfolio P&L Reconciliation Progress

**Design:** `plan/design/2026-08-14-cumulative-portfolio-pnl-reconciliation.md`  
**Implementation plan:** `plan/implementation/2026-08-14-cumulative-portfolio-pnl-reconciliation.md`  
**Status:** Implementation in progress
**Production data:** Unchanged; backfill not run

## Tasks

- [x] Task 1: Build the pure weighted-average P&L ledger.
- [x] Task 2: Add active-lifecycle boundary selection and snapshot enrichment.
- [x] Task 3: Add normalized repository P&L inputs.
- [x] Task 4: Correct future stock execution cash effects.
- [x] Task 5: Enrich every live broker snapshot before persistence.
- [x] Task 6: Make Today header P&L snapshot-consistent across tabs.
- [x] Task 7: Add the safe historical repair command.
- [x] Task 8: Document operations and update trackers.
- [ ] Task 9: Verify, dry-run, obtain explicit apply approval, apply, and render.

## Required Gates

- [x] User confirmed cumulative realized P&L means since the active `$1,000,000` account reset.
- [x] User approved historical snapshot backfill in scope.
- [x] User approved the design.
- [x] Spec review approved after three iterations.
- [x] User approved the written spec.
- [x] Implementation plan review approved after two iterations.
- [x] Isolated implementation worktree created and baseline verified.
- [ ] Every production behavior has a witnessed RED test before implementation.
- [ ] Persistent Postgres data directory and host mount verified.
- [ ] Production dry-run report reviewed.
- [ ] User explicitly approves the exact dry-run report.
- [ ] Production `--apply` completed atomically.
- [ ] Second dry-run proves idempotency.
- [ ] Overview, Risk & Macro, and System rendered and visually checked.
- [ ] Final code review approved.

## Evidence Log

- 2026-08-13: Diagnosed absent Alpaca account `realized_pl`/`unrealized_pl` fields being defaulted to zero, tab-dependent unrealized header fallback, and negative sell `net_cash_effect` values.
- 2026-08-13: Independent replay of 41 closed stock reductions produced approximately `-$11,065.49` cumulative realized P&L; screenshot-time account identity implied approximately `-$11,071.94`, leaving a small reconciliation difference to preserve rather than hide.
- 2026-08-14: Design finalized and approved at `plan/design/2026-08-14-cumulative-portfolio-pnl-reconciliation.md`.
- 2026-08-14: Detailed TDD implementation plan finalized and approved at `plan/implementation/2026-08-14-cumulative-portfolio-pnl-reconciliation.md`.
- 2026-08-17: Task 1 RED failed during collection because `src.trading.portfolio.pnl` did not exist; GREEN passed `tests/trading/test_portfolio_pnl.py` (`10 passed`). The pure ledger now covers weighted-average buys, partial/full reductions, gains/losses, deterministic equal-time ordering, cutoff filtering, duplicate ids, invalid values, and oversells.
- 2026-08-17: Task 2 RED failed because the lifecycle/enrichment contracts and tolerance constants were absent; GREEN passed `tests/trading/test_portfolio_pnl.py` (`18 passed`). Snapshot enrichment now selects the latest clean reset, rejects ambiguous reset timestamps and position mismatches, preserves metadata, uses replay cost basis, and audits residuals/excluded rows with shared tolerances.
- 2026-08-17: Task 3 RED produced two missing-loader failures; GREEN passed the two focused SQLAlchemy/in-memory repository tests and `tests/trading/test_portfolio_sync.py` (`5 passed`). Both repositories now emit deterministically ordered filled-stock events joined to order action plus ascending portfolio P&L points, and reject orphan executions.
- 2026-08-17: Task 4 RED showed both `reduce` and `exit` fills persisted `-2.2715` instead of `+2.2715`; GREEN passed the focused cases and the full `tests/trading/test_paper_stock_broker.py` module (`20 passed`). Future long buys remain cash outflows while reductions/exits are cash inflows.
- 2026-08-17: Task 5 RED showed live sync still persisted `realized_pnl=0.0` and accepted a fill/broker quantity mismatch; GREEN passed `tests/trading/test_portfolio_sync.py` (`7 passed`) plus live runtime regression (`52 passed`). Every broker snapshot is now enriched from the active-lifecycle ledger and validated before position or snapshot persistence.
- 2026-08-17: Task 6 RED showed position-loading tabs using `20.25` while snapshot-only tabs used `-2452.55`; GREEN passed Today/portfolio loader tests (`89 passed`) and the full web suite (`179 passed`). The header now reads realized and unrealized P&L exclusively from the reconciled portfolio snapshot across all six tabs, while position rows retain their independently tested unrealized totals.
- 2026-08-17: Task 7 RED failed import because the historical repair module did not exist; GREEN passed all repair command tests (`15 passed`) and the combined ledger/repository/repair regression (`68 passed`). The CLI defaults to rollback-only dry-run, locks rows only for apply, validates the latest mirrored position and persistent PostgreSQL storage before writes, repairs only the active lifecycle, commits once, and is idempotent.
- 2026-08-17: Task 8 documented persistent-storage verification, dry-run review, explicit apply approval, lifecycle isolation, idempotency, and the required post-apply zero-change dry-run. The main tracker now records implementation evidence and keeps production data explicitly unchanged until the operator gate.
- 2026-08-17: Task 9 pre-production verification passed the focused feature suite (`184 passed`), compilation, and diff checks. Full verification reached `1151 passed, 12 failed`, exactly matching the accepted baseline failure categories: three unavailable-local-Postgres integration tests, eight pre-existing option/hedge environment tests, and one pre-existing macro-event smoke test. No feature regression remains; production dry-run/apply and rendered UI verification are still gated.
- 2026-08-17: Read-only Raspberry Pi checks passed: Postgres is accepting connections, `SHOW data_directory` returned `/var/lib/postgresql/data`, and Docker reports the persistent bind mount `/data/postgres_data -> /var/lib/postgresql/data`. The rollback-only production dry-run selected boundary `2026-06-26T12:50:00.197377+00:00`, excluded 1 earlier snapshot and 0 fills, replayed 94 fills across 246 active snapshots, proposed 246 snapshot repairs and 43 sell cash-effect repairs, and found no current-position mismatch. Latest values were realized `-$14,265.4442`, unrealized `+$3,059.3933`, residual `-$6.4591`; the largest historical absolute residual was `$24,912.2374` on `2026-07-21T14:09:28.393389+00:00`, retained as an explicit unreconciled audit difference. Production remains unchanged pending review and exact-report approval.
- 2026-08-17: Initial final review blocked apply on historical inventory validation and irreversible broker-fill durability. TDD follow-up now rejects any snapshot/replay inventory-presence mismatch even when the latest account is flat, ignores unsupported pre-boundary actions, returns structured dry-run validation errors plus earliest/latest update timestamps, checkpoints normal and late-discovered broker fills before fallible portfolio reconciliation, and makes the standalone live execution CLI use the persisted SQL lifecycle instead of fabricating a reset. Review-fix regression passed (`162 passed`). The renewed rollback-only production dry-run returned `validation_errors=[]` over update range `2026-06-26T12:50:00.197377+00:00` through `2026-08-17T16:00:00.152012+00:00`; no rows were changed.
- 2026-08-17: Second final review found that aggregate historical market value still could not prove mixed per-ticker inventory and that a shared-session fill checkpoint committed unrelated phase writes. The repair now leaves every non-flat historical snapshot untouched, reports its exact unverified range, repairs only flat history plus the latest snapshot after complete per-ticker quantity/cost validation, and accumulates all current position mismatches in a complete blocked report. Irreversible orders, fills, and submitted attempts now use an isolated SQL session with nullable decision links, while the caller's transaction remains uncommitted; normal and late-fill paths share this contract. The standalone CLI now loads positions through the repository API. Review-fix regression passed (`139 passed`); production has not been changed.
- 2026-08-17: Third review approved rollback-only production dry-run but found a same-transaction delayed-order self-lock risk and incomplete blocked-report scope. Every broker-submitted stock order is now independently committed before it can become a late fill; a later isolated fill update therefore sees the committed order instead of contending with an uncommitted duplicate unique key. Position mismatch reporting now completes the read-only snapshot proposal/unverified scan before returning, so blocked reports contain the real mutation and unverified ranges. Targeted regression passed (`89 passed`); apply remains blocked pending renewed review and dry-run.
- 2026-08-17: Final review found no Critical/Important issues and approved rollback-only dry-run plus apply only after exact-report user authorization. Final focused regression passed (`256 passed`); full regression reached `1161 passed, 12 failed`, with the same accepted three local-Postgres, eight option/hedge, and one macro-smoke baseline failures. Persistent production storage revalidated as `/var/lib/postgresql/data` backed by `/data/postgres_data`. The final rollback-only dry-run used boundary `2026-06-26T12:50:00.197377+00:00`, replayed 94 fills over 247 active snapshots, proposed 2 safe snapshot repairs and 43 sell cash-effect repairs, and left 245 non-flat historical snapshots untouched as unverified (`2026-06-26T14:00:00.188936+00:00` through `2026-08-17T16:00:00.152012+00:00`). The latest update target is `2026-08-17T17:00:00.200831+00:00`; calculated latest P&L is realized `-$14,265.4442`, unrealized `+$2,759.7933`, residual `-$6.4591`. Position mismatches and validation errors are empty; the sole cost diagnostic is FPS average cost difference `0.0000001062`, far below the `$0.01` tolerance. Production remains unchanged pending explicit user approval of this exact report.

## Final Results

Pending implementation and production dry-run/apply.
