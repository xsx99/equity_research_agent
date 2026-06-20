# Prompt 02 — Fix the broken Net/Gross exposure (shows +4,917,061.64%)

You are editing the equity_research_agent repo. INVESTIGATE FIRST, then fix. Report
the root cause before changing the computation. Do not just clamp or hide the number.

## Problem
On the Today dashboard, the header and the Risk & Macro tab both show net/gross
exposure ≈ **+4,917,061.64%**, and "EXPOSURE USAGE 4917061.64". A portfolio cannot
be ~49,000× leveraged — this is a computation bug.

## Where to look
- `src/web/presenters/today_overview.py` — `_format_exposure(...)` at line 323, and
  the metric card built around lines 61-66 from `header.get("gross_exposure")`.
- Trace `gross_exposure` / `net_exposure` and the risk-snapshot `exposure_usage`
  value back to their source (the risk snapshot that feeds the overview/risk-macro
  presenters). Find where the percentage is computed.

## Likely root causes (verify which one)
- Notional divided by a near-zero or wrong equity base.
- Notional double-counted (summed across positions + overlays incorrectly).
- A raw notional value being formatted as a percentage.

## Required output
1. First, write a short note stating the exact root cause and the file:line where
   the wrong value originates.
2. Then fix the computation so exposure is a sane percentage of account equity
   (net and gross). Format with a normal number of decimals.

## Acceptance criteria
- Net/Gross exposure shows a realistic percentage (not millions of percent).
- The fix addresses the computation, not just the display formatting.
- `pytest tests/web/ -q` passes. Add/adjust a test asserting exposure stays within a
  sane range for a representative portfolio.
