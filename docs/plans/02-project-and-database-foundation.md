# Phase 2 — Project and Database Foundation

## Goal

Create the Django foundation and persist projects, uploads, normalized schedules, immutable schedule versions, and monthly flags safely in `cilink_report`.

## Work Items

1. Configure Django connection for `cilink_report` using environment variables; never commit the password.
2. Inventory existing tables before migration:
   - `flight_schedules`
   - `flight_doc_upload`
   - `m_periode`
   - `delay_code`
   - `route_code`
3. Define Django models or integration mappings for:
   - Project and project month.
   - Uploaded source file and processing status.
   - Schedule version lineage (`parent_version_id`, version number, active flag).
   - Normalized WTT/PPRP schedule fields.
   - Immutable daily operational flags.
4. Add unique constraints for project/month/source hash and normalized schedule-version identity.
5. Add indexes for matching key, project/month, flight number, date, route, and active version.
6. Add audit fields: created by, created at, source file, parser version, and error details.
7. Store files on local media with project/month/type partitioning; store paths and hashes in MySQL.
8. Implement transaction boundaries for upload processing and PPRP row creation.
9. Add migration safety checks and a read-only schema compatibility report.

## Required Invariants

- Existing schedule rows are never updated when a new PPRP version is created.
- Daily flags on historical rows are immutable.
- A duplicate source hash does not create new schedule versions.
- All rows belong to exactly one project month.

## Tests

- Connection and health check.
- Migration/model validation.
- Unique constraint tests.
- Historical row immutability test.
- Upload idempotency test.
- File path and access-control tests.

## Exit Criteria

- Django can read/write the required project-scoped records.
- Existing `cilink_report` data is preserved.
- Database tests pass against a disposable test database and a read-only compatibility check passes against local MariaDB.

