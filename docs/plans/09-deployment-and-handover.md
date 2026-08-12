# Phase 9 — Deployment and Handover

## Goal

Release the application safely and provide operational ownership.

## Deployment Steps

1. Provision the approved Python/Django runtime.
2. Configure environment variables for `cilink_report`, media storage, secret key, allowed hosts, and logging.
3. Apply reviewed migrations only after backup and schema compatibility checks.
4. Create media directories with least-privilege permissions.
5. Deploy static assets and Django/Unfold configuration.
6. Run health checks, parser smoke tests, and export smoke tests.
7. Create or verify admin/operator roles.
8. Execute a controlled sample-month workflow.
9. Enable monitoring and error logging.
10. Record release version, migration version, and rollback point.

## Operations

- Daily database and media backup.
- Retention policy for source files and generated reports.
- Parser failure alerting.
- Storage capacity monitoring.
- Audit-log review.
- Monthly reconciliation of WTT/PPRP/GHP processing.

## Rollback

- Stop new processing.
- Preserve uploaded files and audit records.
- Restore application version and database backup according to the approved runbook.
- Do not delete historical schedule rows during rollback.

## Handover Deliverables

- Architecture and configuration guide.
- Database/schema map.
- Operator guide.
- Admin guide.
- Parser fixture and regression instructions.
- Backup/restore runbook.
- Known limitations and change procedure for new file layouts.

## Exit Criteria

- Production smoke test passes.
- Named owner accepts operations and support responsibilities.
- Release notes and rollback evidence are stored.

