# Prompt 09 — Stop leaking internal/smoke names into the UI

You are editing the equity_research_agent repo. Make ONLY the changes described.

## Problem
Internal and smoke-test strings appear in the user-facing UI, e.g.:
- Strategy names like `Lpsmoke 181857`, `lpsmoke`
- Reasons like `codex live preopen verification`,
  `codex live preopen order smoke:NVDA`
- The line `"Backend audit linkage has not reached a signal snapshot yet."`

These must not be shown to the user.

## Do this
- Grep for these strings to find where they originate and where they're rendered:
  `grep -rni "lpsmoke\|preopen verification\|order smoke\|audit linkage has not" src/`
- Choose the cleaner of these two approaches per case:
  1. Filter smoke-origin records out of the operator-facing views (preferred when a
     record is clearly smoke/test data), or
  2. Map internal strategy/reason codes to clean human-readable display labels.
- For degraded/placeholder copy like "Backend audit linkage has not reached a signal
  snapshot yet.", replace it with plain user-facing wording (e.g. "Signal details not
  available yet.") or hide the line when there's nothing to show.

## Acceptance criteria
- None of the listed internal/smoke strings appear in the rendered UI.
- Strategy names shown to the user are clean labels, not smoke identifiers.
- `pytest tests/web/ -q` passes.
