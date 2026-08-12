# Phase 5 — Dashboard Analytics

## Goal

Provide monthly operational charts using GHP analytics without changing final-report source rules.

## Source Boundary

- Dashboard STD: GHP.
- Dashboard ATD: GHP.
- Dashboard delay code: GHP.
- Final-report ATD/ATA: WTT; not dashboard-derived.

## Metrics

### PPRP Achievement

For each flight in the selected month:

- Difference `ATD - STD > 45 minutes` → `0%`.
- Difference `ATD - STD <= 45 minutes` → `100%`.
- Aggregate and display by flight number for the month.

### OTP

- Difference `ATD - STD > 1 minute` → delayed.
- Difference `ATD - STD <= 1 minute` → on time.
- Associate delayed records with delay code when present.

### Delay Factor

- Count GHP delay-code occurrences by month.
- Sort descending for the chart.
- Preserve unknown/blank codes as an explicit category if approved.

### Delay by Hour

- Group delayed GHP departures by scheduled/actual hour according to the approved dashboard definition.
- Document whether the chart uses STD hour or ATD hour before implementation.

## Tests

- Exact 45-minute boundary is `100%`.
- Exact 1-minute boundary is on time.
- Delay code aggregation is correct.
- Month and project filters isolate data.
- Dashboard never changes final-report rows.
- Empty and incomplete GHP data produce a visible empty state.

## Exit Criteria

- Chart APIs return tested monthly aggregates.
- Dashboard displays source context and period.
- Formula and boundary tests pass.

