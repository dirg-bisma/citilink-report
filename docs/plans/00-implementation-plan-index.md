# Implementation Plan Index

**Project:** Automated Flight Schedule Reporting System  
**Database:** `cilink_report`  
**Status:** Ready for execution planning  
**Date:** 2026-08-12

## Objective

Build the monthly flight-reporting workflow while preserving the agreed source rules:

- WTT supplies schedule context and final-report ATD/ATA.
- PPRP supplies official schedule changes, new flight date, and latest letter number.
- GHP supplies final-report operational flags `1/0` using `flight_num + tanggal + rute`.
- Dashboard STD/ATD and delay analysis use GHP independently from final-report mapping.
- PPRP changes create a new row below the prior row; old rows and daily flags are immutable.

## Phase Sequence

| Phase | File | Outcome | Gate |
|---|---|---|---|
| 0 | `00-implementation-plan-index.md` | Scope, sequence, and gates | Approved plan |
| 1 | `01-discovery-and-contract.md` | Frozen domain contract and sample fixtures | No unresolved blocking rule |
| 2 | `02-project-and-database-foundation.md` | Django project, models, migrations, storage | DB tests pass |
| 3 | `03-source-parsers.md` | WTT, PPRP, GHP parsers with normalized output | Parser fixtures pass |
| 4 | `04-schedule-processing-engine.md` | Versioning, matching, immutable snapshots | Core business tests pass |
| 5 | `05-dashboard-analytics.md` | Monthly dashboard metrics/charts | Formula tests pass |
| 6 | `06-final-report-generator.md` | Template-preserving Excel export | Output contract passes |
| 7 | `07-web-workspace-and-security.md` | Upload, preview, history, download UI/API | E2E workflow passes |
| 8 | `08-quality-assurance-and-acceptance.md` | Full verification and UAT evidence | Acceptance signed |
| 9 | `09-deployment-and-handover.md` | Production-ready runbook and handover | Release approved |

## Global Definition of Done

- All source mappings and formulas are covered by automated tests.
- Final-report ATD/ATA never comes from GHP.
- Dashboard calculations explicitly use GHP STD/ATD.
- Historical rows cannot be updated by later uploads.
- Re-uploading the same file is idempotent.
- Files are scoped to project and month.
- The final workbook preserves the supplied template structure.
- Audit logs identify source files, user, timestamp, status, and errors.
- No implementation phase is marked complete without its gate evidence.

## Execution Rules

1. Execute phases in order; parallel work is allowed only inside a phase.
2. Do not apply destructive database changes to existing `cilink_report` data.
3. Use fixtures copied from `docs/Source` for parser and export tests.
4. Treat any unresolved business rule as a release blocker, not a silent default.
5. Record deviations in a decision log before changing the plan.

