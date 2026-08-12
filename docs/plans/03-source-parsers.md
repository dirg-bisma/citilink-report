# Phase 3 — Source Parsers

## Goal

Convert WTT PDF, PPRP PDF, and GHP Excel into validated normalized records without mixing source responsibilities.

## WTT Parser

1. Detect month/period and local-time declaration.
2. Extract flight number, origin, destination, aircraft, day pattern, date range, schedule, ATD, and ATA.
3. Expand day patterns/date ranges into daily schedule records for the selected month.
4. Normalize flight numbers, IATA routes, dates, and time values.
5. Preserve source page and row references for auditability.
6. Reject or flag rows with missing flight number, route, date, ATD, or ATA according to the approved contract.

## PPRP Parser

1. Extract letter number, letter date, route, season/period, and change type.
2. Parse attachment schedule rows and identify changed flight/date/time values.
3. Normalize records using the same WTT canonical fields.
4. Assign a deterministic document hash and revision identity.
5. Preserve page/attachment references.
6. Validate that the PPRP applies to the selected project month.

## GHP Parser

1. Detect the header row in `.xls`/`.xlsx` files.
2. Extract GHP date, route, flight number, STD, ATD, delay code, and supporting fields.
3. Normalize date and route values.
4. Create the operational matching key.
5. Retain STD/ATD/delay fields for dashboard analytics only.
6. Never map GHP ATD/ATA into final-report ATD/ATA.

## Validation

- File extension and MIME validation.
- Required-column validation.
- Date/month validation.
- Route and flight-format validation.
- Duplicate-row detection within one source file.
- Parser warnings versus blocking errors.

## Fixtures and Tests

- Use representative files from `docs/Source`.
- Add golden normalized JSON/CSV fixtures.
- Test each known layout variation in the samples.
- Test malformed files and unsupported layouts.
- Verify source references and deterministic hashes.

## Exit Criteria

- Each parser produces the documented normalized contract.
- Parser output is reproducible for the same file.
- All source-specific tests pass and no parser emits data into another source's responsibility.

