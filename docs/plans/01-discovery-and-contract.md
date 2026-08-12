# Phase 1 — Discovery and Contract

## Goal

Freeze the domain contract before implementation so parser and database work cannot drift from the business rules.

## Inputs

- `docs/alur.svg`
- `docs/BRD.md`, `docs/PRD.md`, `docs/FSD_ReportExtractor.md`
- `docs/TechDesign.md`, `docs/TraceabilityMatrix.md`
- `docs/Source` sample WTT, PPRP, GHP, and final template files
- Existing `cilink_report` schema

## Work Items

1. Create a glossary for PPRP, WTT, GHP, STD, ATD, ATA, route, schedule version, and operational flag.
2. Document the source matrix:
   - Final report: WTT/PPRP for schedule and WTT for ATD/ATA; GHP for `1/0`.
   - Dashboard: GHP STD/ATD and GHP delay fields.
3. Define canonical normalization:
   - Flight number: uppercase, remove formatting-only separators consistently.
   - Route: normalized origin/destination IATA pair.
   - Date: ISO `YYYY-MM-DD` internally.
   - Time: local time with explicit timezone policy.
4. Define the exact matching key: `flight_num + flight_date + origin + destination`.
5. Define project identity: project ID, period/season, year, month, template, and owner.
6. Define version identity and ordering for PPRP changes.
7. Confirm the handling of missing WTT ATD/ATA before release.
8. Confirm behavior for multiple PPRP revisions: retain every revision as a row chain, latest marked active.
9. Capture decisions in `docs/decision-log.md`.

## Deliverables

- Domain glossary.
- Source-of-truth contract.
- Normalization contract.
- Open-question decision log.
- Fixture inventory and expected records.

## Exit Criteria

- No ambiguity remains about source precedence, matching, versioning, or dashboard formulas.
- Every later phase references stable field names and IDs.

