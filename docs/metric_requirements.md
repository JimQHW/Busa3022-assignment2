# Metric requirements recorded before implementation

**Historical specification:** This original pre-code record includes volatility. The current three active dashboard measures and dual-condition signal are defined in README.md; the yield-change measure replaces volatility in the dashboard. The original formulas below are retained as development evidence.
Prepared on 28 October 2026, Australia/Sydney, before authoring transformation code in this project. These are AI-assisted proposed requirements for the student to review, not a claim of independent student authorship.

## Scope and grain
One row represents one scheduled Nasdaq US equity trading session. Work from 1 April 2026 through the last valid Nasdaq observation in the supplied snapshot (26 October 2026). Retain the complete five-year source files unchanged and profile every source row. Use the official 2026 Nasdaq holiday schedule; reject an unreviewed calendar year. Early-close days still count as sessions. The 90-calendar-day display interval ends at the fixed snapshot date, not the computer's current date.

## Exactly three calculated metrics
1. `nasdaq_ma20`: arithmetic mean of the current close and the preceding 19 scheduled-session closes, in index points. Require all 20 prices. The first 19 sessions have no result. Any missing scheduled-session close makes every affected window unavailable.
2. `nasdaq_return_1d`: current close divided by the immediately preceding scheduled-session close, minus one. Store a decimal fraction (0.01 means 1%). Require both closes and a positive denominator. Do not fill missing prices or bridge a missing scheduled session.
3. `nasdaq_volatility_14d`: sample standard deviation (denominator n minus 1) of the most recent 14 daily simple returns, including the current return. Store a decimal fraction, do not annualise, and require all 14 returns, which require 15 closes. An unavailable return invalidates any containing window.

MA20 makes the recent price trend easier to see. Daily return expresses comparable movements rather than raw point changes. Volatility distinguishes stable from unsettled periods and can support a later, separately justified RAG rule. These measures describe market context, not the bank's own performance or a causal effect of interest rates.

## Macro alignment and missing values
Left join DGS10 to the Nasdaq session date; keep the yield in percentage points (5.00 means 5%). Keep a missing yield blank and set `yield_missing=true`. Do not use forward fill, backward fill, interpolation or zero substitution. Preserve the index observation even if yield is missing. On 12 October 2026 the yield gap must remain visible. Non-session macro observations remain in the clean macro table, not in the dashboard table.

Both files contain date labels rather than event timestamps. Retain US observation/session dates, with the session calendar identified as America/New_York. Do not interpret a date label as UTC midnight or shift it to Sydney. A same-date retrospective join does not imply the values were simultaneously available. No real-time or historical decision-time backtest is claimed. Store ingestion timestamps in UTC. A production version must add actual publication timestamps and join only information available at the reporting cut-off.

## Validation before acceptance
Use hand-computable synthetic prices and independent scalar arithmetic to verify formulas, warm-up boundaries and missing-value propagation. Verify all expected sessions in the real analysis period and the explicit missing macro case. Inject malformed schema and invalid rows only into temporary test copies. Test that a failed run preserves the last successful publication pointer. Label all simulated failures as tests.

