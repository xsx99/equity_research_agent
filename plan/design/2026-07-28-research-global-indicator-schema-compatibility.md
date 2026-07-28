# Research Global-Indicator Schema Compatibility

Date: 2026-07-28
Status: Approved in conversation

## Problem

The global-context provider began emitting `previous_close` and
`return_vs_previous_close` for macro indicators on 2026-07-21. The research
input contract still rejects both fields because `ResearchGlobalIndicator`
uses `extra="forbid"` and does not declare them. Every scheduled research
ticker therefore fails input validation before the research model is called.

## Scope

- Add `previous_close` and `return_vs_previous_close` as optional floats on
  `ResearchGlobalIndicator`.
- Preserve strict rejection of all other undeclared fields.
- Add a regression test that validates a research payload containing both
  provider fields and asserts that their values survive validation.
- Run the focused schema, research-pipeline, and global-context provider tests,
  followed by the full unit-test suite.
- Update `plan/progress_tracker.md` after implementation is verified.

## Non-Goals

- Do not change provider output, scheduler behavior, database schema, prompts,
  or UI rendering.
- Do not deploy to the Raspberry Pi or trigger a production research run.
- Do not relax the research input model to accept arbitrary extra fields.

## Design

`ResearchGlobalIndicator` remains the single strict consumer contract for
global macro indicators. It gains two nullable fields:

```python
previous_close: Optional[float] = None
return_vs_previous_close: Optional[float] = None
```

The fields are optional because some providers or observations cannot supply a
previous value. Existing payloads remain valid, while current provider payloads
no longer fail validation.

The regression test extends the existing valid research input fixture with both
fields and asserts their parsed values. The test must fail before the schema
change with `extra_forbidden`, then pass after the minimal model update.

## Verification

1. Run the focused regression test and confirm the expected RED failure.
2. Add the two optional schema fields.
3. Re-run the focused test and the related agent, research pipeline, and
   provider test files.
4. Run the full unit-test suite and compare any failures with the documented
   project baseline.
5. Run `git diff --check`.
