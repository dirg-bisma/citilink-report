# Phase 4 — Schedule Processing Engine

## Goal

Build the deterministic domain engine that creates monthly rows, applies PPRP revisions, calculates GHP operation flags, and preserves history.

## Processing Order

1. Load project/month configuration.
2. Load and validate WTT records.
3. Create the initial schedule-version rows from WTT.
4. Apply PPRP revisions in document/date order.
5. For each revision, create a new row immediately below its parent row.
6. Set the new flight date and PPRP number from the latest applicable PPRP.
7. Resolve the new row's ATD/ATA from the applicable WTT.
8. Match the new row to GHP by `flight_num + date + origin + destination`.
9. Set daily operation flags to `1` or `0`.
10. Freeze each generated row as a snapshot.
11. Mark only the latest applicable version active; retain all prior versions.

## Rules

- PPRP changes create a new row even when only time changes.
- Old rows are never recalculated, overwritten, or deleted.
- Old daily `1/0` values remain unchanged.
- GHP match means `1`; no match means `0`.
- Final ATD/ATA always come from WTT.
- Dashboard fields are calculated separately and do not mutate schedule rows.

## Idempotency

- Key each processing event by project, month, source hash, and parser version.
- Reprocessing an unchanged file returns the prior result.
- A new PPRP document creates a new revision only when its normalized content differs.
- Re-uploading GHP may update only the eligible current processing result; historical snapshots remain frozen.

## Tests

- Initial WTT row creation.
- PPRP date change creates child row below parent.
- PPRP time-only change creates child row.
- Latest PPRP number and date applied to new row.
- WTT ATD/ATA wins over conflicting GHP time.
- GHP match/no-match produces `1/0`.
- Route is part of matching key.
- Historical row and flags remain unchanged.
- Multiple revisions produce an ordered row chain.

## Exit Criteria

- Core processing is deterministic and transaction-safe.
- Domain tests pass with at least one real-world fixture per source type.
- Output dataset is ready for both preview and Excel generation.

