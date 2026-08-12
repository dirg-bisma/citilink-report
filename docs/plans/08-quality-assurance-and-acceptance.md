# Phase 8 — Quality Assurance and Acceptance

## Goal

Prove that the implementation meets business, functional, technical, and output requirements.

## Test Layers

1. Unit tests for normalization, formulas, and source mapping.
2. Parser fixture tests for WTT, PPRP, and GHP.
3. Database tests for constraints, lineage, immutability, and idempotency.
4. Service tests for monthly processing.
5. Export tests for workbook structure and values.
6. API tests for authorization and error handling.
7. Browser/E2E tests for the complete operator workflow.
8. Regression tests using every supplied sample file.

## Mandatory Acceptance Scenarios

- Initial WTT creates the monthly plan.
- GHP match by flight/date/route sets `1`.
- GHP no-match sets `0`.
- Final ATD/ATA remain WTT values despite different GHP times.
- Dashboard uses GHP STD/ATD and delay code.
- PPRP date/time change creates a new row below the old row.
- New row uses the latest PPRP date/letter and applicable WTT ATD/ATA.
- Old row and daily flags remain unchanged.
- Multiple revisions remain ordered and traceable.
- Re-upload is idempotent.
- Final Excel structure is preserved.

## UAT Evidence

- Test case ID, input files, project/month, expected result, actual result, evidence path, tester, and date.
- Business sign-off for source precedence and boundary formulas.
- Defect log with severity and disposition.

## Release Gate

- Zero open critical/high defects.
- All mandatory acceptance scenarios pass.
- Parser and export regression suite passes.
- Backup/restore procedure tested.
- User guide and operator runbook complete.

