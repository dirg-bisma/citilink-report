# Phase 7 — Web Workspace and Security

## Goal

Expose the processing engine through a secure monthly workspace using the existing Django/Unfold direction.

## Screens

1. Login/logout.
2. Project list.
3. Create project/month.
4. Project workspace with upload modal.
5. Preview table with source labels and version rows.
6. Upload history and processing errors.
7. Dashboard charts.
8. Download final report.
9. Admin user management.

## API/Action Contract

- Create project.
- Upload WTT/PPRP/GHP/template.
- Start/retry processing.
- Read processing status.
- Read preview rows.
- Read dashboard aggregates.
- Download validated final report.

Each write must enforce authentication, project authorization, CSRF protection, file validation, and audit logging.

## UX Rules

- Show source badges: WTT, PPRP, GHP.
- Show `ATD/ATA: WTT` explicitly in preview.
- Show `status_operasi: GHP` explicitly.
- Display historical rows as read-only.
- Highlight new PPRP rows without implying a data mismatch.
- Show processing progress and actionable parser errors.
- Disable download until required processing and validation gates pass.

## Security

- Store DB credentials in environment configuration.
- Restrict project/month access by role and ownership policy.
- Validate file content, extension, size, and storage path.
- Prevent path traversal and unsafe filename use.
- Use Django session authentication and permissions.
- Log uploads, processing, exports, and failures.

## Tests

- Role access matrix.
- Unauthorized project access.
- CSRF and upload validation.
- Download authorization.
- Preview source-label correctness.
- Browser workflow from upload to download.

## Exit Criteria

- A user can complete a full monthly workflow without manual database access.
- Security and end-to-end tests pass.

