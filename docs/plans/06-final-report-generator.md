# Phase 6 — Final Report Generator

## Goal

Generate the authority-compliant Excel report while preserving the supplied template and source rules.

## Mapping Contract

| Output field | Source |
|---|---|
| Flight number/route | WTT with PPRP revision context |
| Flight date | WTT initially; latest PPRP date for changed row |
| ATD/ATA | Applicable WTT only |
| PPRP number | Applicable/latest PPRP for changed row |
| Daily `1/0` | GHP match by flight/date/route |
| Historical daily `1/0` | Stored immutable snapshot |

## Work Items

1. Load a copy of the uploaded template, never modify the original.
2. Detect the target worksheet and header/data boundaries.
3. Preserve merged cells, styles, formulas, widths, and print settings.
4. Insert rows for historical and new PPRP versions in required order.
5. Write mapped values only to approved cells.
6. Write daily flags into the correct day columns for the project month.
7. Recalculate totals using existing formulas or controlled formula generation.
8. Validate row count, dates, source values, and totals before download.
9. Produce a deterministic file name containing project and month.
10. Store export metadata and checksum in the upload/report history.

## Validation

- No GHP ATD/ATA appears in final-report ATD/ATA cells.
- Old rows and old flags equal stored snapshots.
- PPRP new row is directly below its parent.
- All daily columns map to the correct calendar date.
- Workbook opens successfully and retains expected sheet names.

## Tests

- Golden workbook comparison for structure and key values.
- Formula and total validation.
- Historical row preservation.
- WTT source precedence with conflicting GHP times.
- Missing WTT ATD/ATA handling according to approved decision.
- Large monthly export performance.

## Exit Criteria

- Generated workbook passes structural and data validation.
- Export is downloadable only after successful validation.

