# PR 39 `config_json` Schema Validation (Pydantic) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

> **Origin:** This is the deferred sub-item of backlog #3 (split out of `pr_35` because it is independent of the live order-drop bug). `pr_35` handles the `paper_trade_authorized` column cutover; this PR handles "`config_json` drives strategy matching/selection with no schema validation → add pydantic validation."

**Goal:** `strategy_definitions.config_json` (and the expression-bucket `config_json`) currently flows from seed → DB → runtime as an untyped `dict`, read everywhere with defensive `.get(key) or default`. A typo or drifted key fails *silently* (falls back to a default, changing selection/matching behavior with no error). Introduce a pydantic model that is the typed representation of `config_json`, validate at the DB boundary (load + save/seed), and route invalid configs through the existing repair/log path instead of silently degrading.

**Architecture:** Two pydantic models — `StrategyConfig` and `ExpressionBucketConfig` — capture the real key sets (they share the `config_json` column but differ: expression configs carry `suitability` / `allowed_option_strategy_types`, etc.). Parse-don't-validate: the repository load path (`matching.py` `StrategyDefinitionRecord.from_row` / `mixins/strategy.py`) parses raw JSON into the model once; consumers read typed attributes instead of `.get(...)`. **Critical compatibility constraint:** existing DB rows may be missing keys or partially drifted (today's `.get(... ) or default` tolerates this). The model MUST default-and-coerce optional fields and only hard-fail on genuinely invalid types / out-of-enum values — never reject a row merely for a missing optional key. Integrate with the existing config repair in `src/trading/runtime/support.py:44-49` (from `pr_27`) rather than duplicating it.

**Tech Stack:** Python, pydantic (confirm v1 vs v2 in the repo before writing models), SQLAlchemy JSONB, pytest.

---

## Required Pre-Read

1. `documents/general_instructions.md`
2. `plan/module_contracts.md` — strategy definition / config contract
3. `plan/implementation/pr_27_strategy_seed_selection_policy_repair.md` — the existing config-repair mechanism this must cooperate with
4. `plan/implementation/pr_03_strategy_matching_replay.md`, `pr_10_strategy_evolution.md`
5. `plan/design/03_strategy_architecture.md`
6. `plan/progress_tracker.md` — **Recent** section only
7. `plan/review_backlog.md` — item #3

## Context: how `config_json` is produced, stored, and consumed (verified file:line)

**Produced (seed):** `src/trading/strategies/catalog.py:39 StrategyCatalogItem.config_json()` serializes these keys:
`strategy_id, display_name, strategy_layer, typical_horizon, core_thesis, required_signals, optional_signals, scoring_rules, selection_policy, risk_tags, macro_blocked_regimes, invalidators, default_trade_identity, allowed_trade_identities, allowed_instruments, allowed_option_strategy_types, required_option_leg_fields, required_assignment_fields, option_policy, earnings_policy, default_exit_policy`.
Expression-bucket configs are produced via `src/trading/strategies/definitions/expressions.py:24` and additionally carry `suitability` (read at `selector.py:366`).

**`selection_policy` sub-shape** (`catalog.py:92 _default_selection_policy`): `actionable_score_threshold: float`, `default_candidate_action: str`, `default_candidate_direction: str`, `eligible_expression_bucket_ids: list[str]`, and `allowed_expression_bucket_ids: list[str]` (read at `selector.py:339`).

**Stored:** `src/db/models/trading/strategy.py:45` — `config_json = Column(JSONB, nullable=False, default=dict)` on `strategy_definitions`. Persisted in `src/trading/repositories/mixins/strategy.py:22` (`row.config_json = dict(definition.config_json)`) and read back at `:37` (`config_json=dict(row.config_json or {})`).

**Loaded into record:** `src/trading/strategies/matching.py:35` (`config_json: dict[str, Any]`), `:50` (`config_json=dict(row.get("config_json") or {})`).

**Consumed (the silent-default sites — all read with `.get(...) or default`):**
- `matching.py:145` `required_signals`, `:261` `invalidators`, `:262` `risk_tags`, `:316`/`:513` `required_signals`, `:575` `selection_policy`, `:598` `macro_blocked_regimes`
- `selector.py:338` `selection_policy`, `:339` `allowed_expression_bucket_ids`, `:342` `eligible_expression_bucket_ids`, `:366` `suitability`
- `option_strategy_builder_policy.py:37` `default_trade_identity`, `:70` `allowed_instruments`, `:111` `allowed_option_strategy_types`, `:181` `earnings_policy`, `:196` `option_policy`
- `strategy_evolution.py:318` reads, `:214`/`:405` writes config

**Existing repair path:** `src/trading/runtime/support.py:44-49` compares `current.config_json` vs `expected.config_json` and produces a `repaired_config` (the `pr_27` selection-policy repair). The new validation must feed/extend this, not bypass it.

## Guardrails

- **No behavior change on valid configs.** A config that is well-formed today must parse and produce byte-identical consumed values. Add a parity test over the entire `INITIAL_STRATEGY_CATALOG` + expression catalog: every catalog item's `config_json()` must validate cleanly and round-trip.
- **Tolerate missing optional keys.** Optional fields get the SAME defaults the current `.get(... ) or default` reads use. Do NOT make a previously-optional key required.
- **Confirm pydantic version first** (`grep -rn "pydantic" pyproject.toml requirements*.txt src/`). Match the version + the project's existing model style (likely there are pydantic models for LLM I/O — mirror them).
- **Fail loud only on real corruption** (wrong type that can't coerce, out-of-enum value for a constrained field like `default_candidate_direction`). Route these through the repair/log path; do not crash strategy loading for one bad row — log it, repair or quarantine that definition, keep the rest.
- Enum value sets must be **derived from existing sources** (`src/db/models/trading/enums.py`, the `CheckConstraint`s, `TradeIdentity.check_in_sql()`, instrument_type `('stock','option','watch')`), not hardcoded duplicates that can drift.
- This is data-model integrity work — code-only, verification handed off (no app/DB env per memory).

## File Map

- Create: `src/trading/strategies/config_schema.py` — `StrategyConfig`, `ExpressionBucketConfig`, `SelectionPolicy`, `OptionPolicy` pydantic models + a `parse_strategy_config(raw: dict) -> StrategyConfig` entrypoint that returns `(model, list[ValidationIssue])`
- Modify: `src/trading/strategies/matching.py` — parse `config_json` into the model at the load boundary (`from_row` ~:50); optionally expose typed accessors so the `:145/:261/:316/...` sites read the model
- Modify: `src/trading/strategies/selector.py` — read `selection_policy` / `suitability` from the typed model
- Modify: `src/trading/workflows/option_strategy_builder_policy.py` — read `allowed_instruments` / `allowed_option_strategy_types` / `option_policy` / `earnings_policy` from the typed model
- Modify: `src/trading/repositories/mixins/strategy.py` — validate at save (`:22`) and surface issues
- Modify: `src/trading/runtime/support.py` — wire validation issues into the existing repair flow (`:44-49`)
- Modify: `src/trading/strategies/catalog.py` — optionally have `config_json()` build from / validate against the model so seed and runtime share one schema
- Create: `tests/trading/test_pr39_config_schema.py`
- Modify: `plan/progress_tracker.md`, `plan/review_backlog.md`

## Task 1: Inventory the real schema (do this before writing models)

- [ ] Step 1: From `catalog.py:39-63` + every consumer site listed above, build the authoritative key → (type, required/optional, default, allowed-values) table for BOTH strategy config and expression-bucket config. Capture it in the PR description. Note keys that appear ONLY in consumers but not in the seed (drift candidates) and keys ONLY in seed but never read (dead).
- [ ] Step 2: Resolve each constrained field's allowed values from the existing enums/constraints (`enums.py`, `TradeIdentity`, instrument_type, decision actions). List the source for each so the models reference them, not literals.
- [ ] Step 3: Confirm pydantic version + existing model conventions in the repo.

## Task 2: The pydantic models

**Files:** `src/trading/strategies/config_schema.py`.

- [ ] Step 1: Write `SelectionPolicy` (fields: `actionable_score_threshold: float` with `0 <= x <= 1`, `default_candidate_action: str` constrained to the decision-action set, `default_candidate_direction: Literal["bullish","bearish","neutral"]`, `eligible_expression_bucket_ids: list[str] = []`, `allowed_expression_bucket_ids: list[str] = []`). All optional with the current defaults.
- [ ] Step 2: Write `OptionPolicy` and any nested sub-models (`scoring_rules`, `suitability`) — start permissive (`dict`/typed where the keys are known) and tighten only where consumers depend on a key.
- [ ] Step 3: Write `StrategyConfig` and `ExpressionBucketConfig` with all keys from Task 1. Configure the model to **ignore unknown extra keys** (forward-compat) but **default missing optional keys**. Coerce types where safe (e.g. tuple↔list, str numbers→float).
- [ ] Step 4: Write `parse_strategy_config(raw)` / `parse_expression_config(raw)` returning `(model, issues)` where `issues` is a list of structured `ValidationIssue(field, kind, detail)` — distinguishing `coerced` / `defaulted_missing` / `invalid` (the last is the only fail-loud class).
- [ ] Step 5 (verify): **Parity test** — every item in `INITIAL_STRATEGY_CATALOG` and the expression catalog parses with zero `invalid` issues, and the model's consumed values equal what the current `.get(...) or default` reads produce.

## Task 3: Validate at the boundary + cut consumers over to typed reads

**Files:** `matching.py`, `selector.py`, `option_strategy_builder_policy.py`, `mixins/strategy.py`.

- [ ] Step 1: At the load boundary (`StrategyDefinitionRecord.from_row`, `matching.py:50`), parse `config_json` into the model once and attach it to the record (keep the raw `config_json` dict too, for back-compat / display, during transition).
- [ ] Step 2: Convert the consumer sites (`matching.py:145/261/316/513/575/598`, `selector.py:338/339/342/366`, `option_strategy_builder_policy.py:37/70/111/181/196`) to read typed attributes from the parsed model. Keep behavior identical — same defaults. Do this incrementally; each converted site keeps its test green.
- [ ] Step 3: At save (`mixins/strategy.py:22`), validate the config before writing; on `invalid` issues, do not silently write a degraded row — raise or route to repair (Task 4).
- [ ] Step 4 (verify): existing matching/selector/option-policy tests still pass; add cases proving a typo'd key is now surfaced (issue) rather than silently defaulted.

## Task 4: Cooperate with the existing repair / log path

**Files:** `src/trading/runtime/support.py`.

- [ ] Step 1: Where the `pr_27` repair compares `current` vs `expected` config (`support.py:44-49`), feed in the validation `issues`: `defaulted_missing` / `coerced` issues become candidates for repair toward the expected seed; `invalid` issues get logged with the strategy_id + field so a corrupt definition is visible, not swallowed.
- [ ] Step 2: Ensure one bad definition does not crash loading of the whole catalog — quarantine/skip-with-log the bad row, keep the rest. Add a test for the "one corrupt row among many" case.
- [ ] Step 3 (verify): test that a drifted config (missing `selection_policy` key) is repaired toward the expected seed via the existing path, with an emitted issue.

## Task 5: Tests, tracker, backlog

- [ ] Step 1: `tests/trading/test_pr39_config_schema.py` — full-catalog parity, per-field coercion/default, out-of-enum fail-loud, missing-optional tolerance, typo surfaced-not-swallowed, corrupt-row quarantine, repair-path integration.
- [ ] Step 2: Run targeted strategy/selector/option-policy tests, then the broader `tests/trading/` strategy suite. Record results in the PR.
- [ ] Step 3: Prepend a dated `plan/progress_tracker.md` **Recent** entry noting `config_json` is now schema-validated and the consumer sites read typed values.
- [ ] Step 4: In `plan/review_backlog.md`, mark the `config_json` validation sub-item of #3 resolved (this completes #3 alongside `pr_35`).

## Done when

- `config_json` for strategies and expression buckets is parsed through a pydantic model at the DB boundary; consumers read typed attributes, not raw `.get(...) or default`.
- The entire seed catalog validates cleanly and round-trips with identical consumed values (parity test).
- A typo'd / out-of-enum key now surfaces a structured issue (logged + repaired/quarantined) instead of silently degrading selection/matching.
- Missing optional keys still tolerated; one corrupt definition doesn't crash catalog loading.
- Tests pass; tracker + backlog updated; #3 fully closed.
