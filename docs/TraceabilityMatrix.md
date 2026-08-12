# Requirements Traceability Matrix (RTM)

**Project:** Automated Flight Schedule Reporting System  
**Version:** 2.0  
**Date:** 2026-08-12

The matrix below maps the current high-level business requirements to product capabilities, functional specifications, technical decisions, and planned test cases.

| Req ID | Business requirement | Product capability | FSD | Technical design / test coverage |
|---|---|---|---|---|
| REQ-01 | Accept WTT, PPRP, and GHP source files | Monthly project upload | FSD-001, FSD-002 | TD upload/storage; TC-001 file type validation |
| REQ-02 | Extract source data automatically | WTT/PPRP/GHP processing | FSD-003, FSD-004, FSD-005 | TD parser pipeline; TC-002 extraction |
| REQ-03 | Validate cross-source matching | Composite-key matching | FSD-005, FSD-008–FSD-015 | TD matching/idempotency; TC-003 matching and exceptions |
| REQ-04 | Generate the final Excel report | Preview and download | FSD-006, FSD-007 | TD template injection; TC-004 output preservation |
| REQ-05 | Support authorized users | Authentication and role access | FSD-001, FSD-002 | Django Auth/permissions; TC-005 authorization |
| REQ-06 | Provide operational visibility | Dashboard and history | FSD-006, FSD-016–FSD-019 | Design dashboard/history; TC-006 read-only history; TC-012 dashboard calculations |
| REQ-07 | GHP determines only status `1/0` | Operational flag calculation | FSD-005 | TD composite key; TC-007 status 1/0 |
| REQ-08 | WTT is the source of final ATD/ATA | Source precedence | FSD-003, FSD-005, Final-Output Mapping | TD source precedence; TC-008 GHP times do not override WTT |
| REQ-09 | PPRP latest schedule governs new version | PPRP schedule versioning | FSD-004 | TD schedule lineage; TC-009 new row and latest PPRP |
| REQ-10 | Preserve old PPRP rows and daily flags | Immutable schedule history | FSD-004, FSD-005, FSD-006, FSD-007 | TD immutable snapshot; TC-010 old row unchanged |
| REQ-11 | Process a project month by month | Period/month workspace | FSD-001, FSD-002 | TD project-period relation; TC-011 month isolation |

## Traceability Notes

- `REQ-07`–`REQ-10` capture the business decisions added during clarification.
- The obsolete rule “ATD from GHP” has been removed.
- The obsolete mismatch-ATD duplication rule has been removed.
- A PPRP change is now a schedule-version event that creates a new row below the previous row.
- Historical rows and their daily `1/0` values are immutable snapshots.
- Final ATD and ATA always follow the applicable WTT; GHP actual-time columns are not used for final-output mapping.
- Dashboard calculations are a separate use case: dashboard STD/ATD and delay analysis use GHP, while final-report ATD/ATA use WTT.
- The current `TechDesign.md` must still be updated in the next documentation pass to map these requirements to the verified `cilink_report` schema.

## Quality Validation Summary

- **Completeness:** Core source precedence, matching, versioning, preview, and output behaviors are covered.
- **Consistency:** FSD and RTM now use the same WTT/PPRP/GHP rules.
- **Traceability:** Each current requirement maps to FSD and planned technical/test coverage.
- **Testability:** Acceptance criteria cover status calculation, source precedence, immutable history, and report generation.
- **Remaining gap:** SRS-FRS and detailed test-case documents are not yet present in `docs`.
