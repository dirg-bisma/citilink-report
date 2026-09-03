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

### D5: Surat PPRP berlaku lintas bulan (fan-out & adopt)
**Date:** 2026-09-03  
**Rationale:** Satu surat PPRP (mis. AU.012/47/2, 13 Jul–24 Okt) berlaku untuk beberapa bulan, tetapi record `SourceFile` terikat satu project. Diputuskan: surat cukup diupload SEKALI. Setelah diproses di satu bulan, `core.ingest._fan_out_letter` mendaftarkan salinan (file fisik sama, `file_hash` sama) ke setiap project bulan lain di dalam rentang berlakunya dan menerapkannya; project bulan baru (WTT diupload) menarik surat lama yang mencakupnya lewat `adopt_letters`. `manage.py sync_pprp` menjalankan hal yang sama untuk semua bulan (idempoten, dipakai untuk backfill). Menghapus surat mencabutnya dari SEMUA bulan; file fisik dihapus hanya bila tidak ada salinan lain.

### D6: Presedensi surat untuk satu flight+tanggal
**Date:** 2026-09-03  
**Rationale:** Sebelumnya `update_or_create` v2 dengan kunci (project, flight, tanggal) dimenangkan surat yang diupload belakangan. Sekarang `core.services.letter_rank`: tanggal mulai berlaku segmen terbaru menang, seri dipecah dengan angka nomor surat, lalu hash file. Hasil DB tidak bergantung pada urutan upload (dikunci tes `tests.test_cross_month`). Saat surat dicabut, surat lain di bulan itu diterapkan ulang supaya tanggal yang ditinggalkan kembali ke surat berikutnya, bukan langsung ke WTT.

### D7: Pintu ketiga ditutup
**Date:** 2026-09-03  
**Rationale:** Aksi admin "Process selected files" memanggil parser langsung tanpa validasi/resync (bisa membuat jadwal dobel). Diganti aksi "Sinkronkan ulang bulan" yang memakai `core.ingest.resync_project` — jalur yang sama dengan halaman Upload Data.

---

**Note:** Mark questions RESOLVED when decided. Add new questions as discovered.
