# Decision Log

**Project:** Automated Flight Schedule Reporting System  
**Date:** 2026-08-12

## Open Questions (Phase 1)

### Q1: Missing WTT ATD/ATA behavior
**Status:** OPEN  
**Question:** What should system do when WTT has no ATD/ATA for a flight?  
**Options:**
- Flag as error, block report generation
- Leave blank in final report
- Use PPRP time if available

**Decision:** TBD before Phase 6

### Q2: Multiple PPRP same flight same month
**Status:** RESOLVED  
**Question:** How to handle multiple PPRP revisions for same flight?  
**Decision:** Create new row below parent, mark latest as active, preserve all history

### Q3: GHP match ambiguity
**Status:** RESOLVED  
**Question:** Multiple GHP rows match same key?  
**Decision:** Take first match, log warning, show in validation preview

### Q4: Timezone handling
**Status:** RESOLVED  
**Question:** Explicit timezone storage or implicit WIB?  
**Decision:** Store times as local WIB strings, explicit timezone policy in docs, no conversion logic

### Q5: PPRP without WTT baseline
**Status:** OPEN  
**Question:** Can PPRP be uploaded before WTT?  
**Options:**
- Block upload, require WTT first
- Queue PPRP, apply after WTT uploaded

**Decision:** TBD before Phase 4

## Implementation Decisions

### D1: No timezone conversion library
**Date:** 2026-08-12  
**Rationale:** All times are WIB (UTC+7). No cross-timezone conversion needed. Stdlib datetime + string format sufficient.

### D2: File hash for idempotency
**Date:** 2026-08-12  
**Rationale:** Use `hashlib.sha256(file_content).hexdigest()` to detect duplicate uploads

### D3: Django built-in auth
**Date:** 2026-08-12  
**Rationale:** User model, session auth, permissions all in stdlib. No custom auth needed.

### D4: Local file storage only
**Date:** 2026-08-12  
**Rationale:** Internal app, no cloud needed. Django FileField + local media directory.

---

**Note:** Mark questions RESOLVED when decided. Add new questions as discovered.
