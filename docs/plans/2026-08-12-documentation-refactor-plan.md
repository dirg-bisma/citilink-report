# Documentation Refactor Plan

**Project:** Automated Flight Schedule Reporting System  
**Date:** 2026-08-12  
**Command:** `/trace`  
**Status:** Planned — current documentation requires alignment before implementation

## 1. Objective

Refactor the project documentation using the `software-documentor` lifecycle:

`BRD -> PRD -> SRS-FRS -> FSD -> Design -> Technical Design -> Test Coverage`

The refactor must preserve the existing Django/Python, MySQL, HTML/CSS/Vanilla JavaScript, Excel, and PDF technology decisions while aligning the documents with the confirmed business rules.

## 2. Confirmed Business Decisions

- The database is `cilink_report`.
- The initial planning source is WTT for the relevant month.
- PPRP is the official source for schedule changes.
- The latest PPRP applicable to a month governs the new active schedule version.
- GHP is matched by `flight_num + tanggal penerbangan + rute`.
- GHP determines only the operational flag:
  - `1` = matching flight exists in GHP.
  - `0` = matching flight does not exist in GHP.
- ATD and ATA in the final output are sourced from the applicable WTT, not from GHP.
- When PPRP changes a flight, the system creates a new row below the previous row.
- A changed row receives the new flight date, latest PPRP number, and ATD/ATA from the latest applicable WTT.
- The previous row remains in the database and final output unchanged, including its daily `1/0` values.
- A project represents a working period and is processed month by month.

## 3. Traceability Assessment

| Area | Current state | Result | Required action |
|---|---|---|---|
| BRD business intent | Correctly identifies GHP, PPRP, WTT, and final report | Partial | Add the confirmed source-of-truth rules and project/month scope |
| PRD product scope | Describes upload, preview, and download | Partial | Replace generic “4 files” wording with the confirmed monthly workflow and immutable history behavior |
| SRS-FRS | Missing as a standalone document | Gap | Create software and non-functional requirements with stable IDs |
| FSD extraction rules | Says ATD is taken from GHP and describes obsolete mismatch duplication | Conflict | Rewrite around WTT ATD/ATA, GHP-only status, PPRP version rows, and immutable history |
| Technical Design | Uses generic `UploadHistory` and incomplete schema | Partial | Align with actual `cilink_report` tables and define schedule-version persistence |
| RTM | Uses unstable `REQ-*` IDs and obsolete FSD mappings | Conflict | Replace with BR/FEAT/FR/FSD/TD/TC trace chain |
| Design documents | UI direction is broadly compatible | Partial | Update preview/history states and PPRP-version visual treatment |
| Test coverage | Not documented | Gap | Add test cases for monthly matching, source precedence, versioning, and immutable rows |

## 4. Refactoring Work Plan

### Step 1 — BRD

- Establish business terminology: PPRP, WTT, GHP, operational status, ATD, ATA, and schedule version.
- Define the three-stage business flow: initial WTT plan, monthly PPRP change, monthly final report.
- Add in-scope and out-of-scope boundaries.
- Replace unresolved validation questions with confirmed matching and source-precedence rules.
- Assign stable `BR-*` identifiers.

### Step 2 — PRD

- Define the monthly project workflow and actors.
- Clarify upload responsibilities for WTT, PPRP, GHP, and the final-output template.
- Define preview, history, and download capabilities.
- Add product behavior for immutable old rows and newly generated PPRP rows.
- Remove or mark dashboard delay/OTP metrics as `[OPEN QUESTION]` if their source is not yet confirmed.
- Assign stable `FEAT-*` and `US-*` identifiers.

### Step 3 — SRS-FRS

- Create `docs/SRS-FRS.md`.
- Specify functional requirements for project creation, file upload, parsing, matching, status calculation, schedule versioning, preview, and final report generation.
- Specify non-functional requirements for file validation, auditability, performance, security, and failure handling.
- Define use cases and acceptance criteria with `FR-*`, `NFR-*`, `UC-*`, `DATA-*`, and `RPT-*` identifiers.

### Step 4 — FSD

- Rewrite `FSD_ReportExtractor.md` using screen/workflow/field specifications.
- Define the matching key exactly as `flight_num + tanggal penerbangan + rute`.
- Define source precedence:
  - WTT -> plan, ATD, ATA.
  - PPRP -> official schedule change, flight date, and PPRP number.
  - GHP -> operational flag only.
- Define the PPRP change workflow and row ordering.
- Make historical rows immutable, including their daily `1/0` values.
- Define behavior when WTT or GHP matching data is missing.
- Assign `FSD-*`, `SCR-*`, `WF-*`, and `API-*` identifiers.

### Step 5 — Technical Design

- Keep Django/Python, MySQL, HTML/CSS/Vanilla JavaScript, `pandas`, `openpyxl`, and PDF parsing libraries.
- Update database design to the verified database name `cilink_report`.
- Map the existing tables (`flight_schedules`, `flight_doc_upload`, `m_periode`, `delay_code`, `route_code`) and identify required additions or changes without silently applying migrations.
- Define immutable schedule-version fields, source-file references, PPRP lineage, and monthly operational flags.
- Define transaction and idempotency rules for repeat uploads.
- Assign `TD-*` and `ADR-*` identifiers.

### Step 6 — Design and UI Documentation

- Update the process diagram with Mermaid and preserve `alur.svg` as the source reference.
- Show the monthly project flow and the PPRP branch that creates a new row.
- Show old-row read-only/history treatment in the preview.
- Show source labels for WTT, PPRP, and GHP-derived fields.
- Retain the existing Citilink green visual direction and Django Unfold decision.

### Step 7 — Traceability and Test Coverage

- Replace the current RTM with a complete chain:

  `BR-* -> FEAT-* -> FR-* -> FSD-* -> TD-* -> TC-*`

- Add tests for:
  - GHP match producing status `1`.
  - No GHP match producing status `0`.
  - Matching by flight number, date, and route.
  - ATD/ATA sourced from WTT.
  - GHP ATD/ATA not overriding WTT.
  - PPRP changes creating a new row below the old row.
  - Latest PPRP values applied to the new row.
  - Old row and old daily flags remaining unchanged.
  - Repeated upload idempotency.

## 5. Blocking Open Questions

These must be resolved in the FSD before implementation:

1. If a flight is operational in GHP but no matching ATD/ATA exists in WTT, should the system produce a warning with blank ATD/ATA or block final report generation?
2. If multiple PPRP revisions apply to the same flight in one month, should every revision remain as a row chain while only the latest is active?
3. Should the existing dashboard metrics for OTP and delay remain in MVP when GHP is only an operational-status source?
4. The current template contains daily columns `1–31`; confirm whether each PPRP version row receives flags only for its applicable month.

## 6. Quality Gate for Completion

The documentation refactor is complete when:

- No document states that GHP supplies final ATD/ATA.
- No document describes obsolete mismatch-based duplication.
- All requirements have stable IDs and backward/forward traceability.
- The process diagram describes initial WTT, monthly PPRP change, GHP status matching, and final report download.
- The actual database name `cilink_report` is used consistently.
- Historical rows and their `1/0` values are explicitly immutable.
- Every major functional rule has at least one test case and objective acceptance criteria.

