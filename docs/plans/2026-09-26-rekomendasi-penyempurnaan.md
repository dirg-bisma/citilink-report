# Rekomendasi Penyempurnaan Sistem

**Project:** CITILINK AVIOR
**Date:** 2026-09-26
**Status:** Usulan, belum dikerjakan. Hanya dokumen ini yang ditambahkan; tidak ada kode yang diubah.
**Posisi kode:** `main` = `c53f7c4` (1 commit di depan `origin/main`, belum push). Migrasi 0005 belum dijalankan ke DB kerja.
DB kerja: 6 project (Mar–Agu 2026), 30 file sumber, 6543 baris jadwal, 0 baris ber-delay-code.

Dokumen ini melengkapi `2026-09-15-audit-keamanan.md` (8 temuan keamanan, belum diperbaiki) dan pekerjaan terbuka
dari serah-terima 3 Sep (panel kesehatan data, backup terjadwal, 4 baris kembar April, surat QG719/QG179).

## Ringkasan penilaian

Fondasi sudah kuat: aturan bisnis dikunci tes (70 tes), alur upload satu pintu, surat lintas bulan, presedensi surat.
Kelemahan utama sekarang ada di tiga hal:

1. **Kebenaran diam-diam** — beberapa jalur bisa menghilangkan flight tanpa peringatan (tahun GHP dikunci 2026,
   mode ganti tanpa transaksi, baris parser dilewati tanpa hitungan).
2. **Kinerja** — semua pekerjaan berat berjalan di dalam request; Download Rekap ±265 detik karena setiap kali
   membaca ulang seluruh PDF PPRP dan Excel GHP dari disk, lalu menyisipkan baris openpyxl secara kuadratik.
3. **Operasional** — tanpa logging, tanpa backup terjadwal, konfigurasi keamanan masih default pengembangan.

## Prioritas 1 — Kebenaran data (kerjakan lebih dulu, berdampak ke laporan audit)

| # | Masalah | Di mana | Perbaikan |
|---|---|---|---|
| 1.1 | **Tahun GHP dikunci 2026.** `process_ghp` memanggil `parse_ghp` tanpa `year`; mulai Januari 2027 semua baris GHP gagal cocok, `operational_flag` = 0 semua, tanpa pesan. `report.py` sudah benar (meneruskan `project.year`), jadi DB dan laporan akan berbeda. | `core/parsers/ghp.py:72`, `core/services.py:408` | Teruskan `project.year`; tambah tes "GHP Januari 2027 cocok". Pilihan project GHP di `ingest.py:313` (`filter(month=...)`) juga harus memakai tahun dari judul file GHP (`detect_ghp_range` sudah membacanya). |
| 1.2 | **Mode ganti bisa mengosongkan bulan.** `_replace_existing_if_allowed` menghapus WTT/GHP lama + turunannya, baru memproses file baru. Bila proses gagal, `except` juga menghapus file baru → bulan itu tanpa WTT/GHP. Tidak ada `transaction.atomic()` di `_ingest_one`. | `core/ingest.py:205-242` | Bungkus hapus-lama + proses-baru dalam satu `transaction.atomic()`; hapus file fisik lama hanya setelah commit. Tes: proses gagal → data lama utuh. |
| 1.3 | **Baris parser dilewati tanpa jejak.** WTT: origin/destination tak dikenal atau tanggal rusak dilewati diam-diam; regex baris mengunci teks `Non stop` dan kode pesawat 3 digit. GHP: bila pandas membaca kolom tanggal sebagai datetime, baris dibuang. PPRP: nomor surat boleh kosong; bila kata `MENJADI` tak ditemukan, seluruh teks (termasuk SEMULA) diparse; nama bulan peka huruf besar. | `wtt.py:120,151-159`; `ghp.py:114-119`; `pprp.py:34,80,90-94` | Setiap parser mengembalikan `skipped` (jumlah + contoh baris) dan ditampilkan sebagai peringatan hasil upload, sama seperti `GhpMatchResult.warnings()`. PPRP tanpa `MENJADI` atau tanpa nomor surat = gagal, bukan diproses. |
| 1.4 | **Tanpa unique constraint** pada `(project, flight_number, flight_date, version_number)`. Sekali ada duplikat, `update_or_create` di `process_pprp` melempar `MultipleObjectsReturned`; kemungkinan asal 4 baris kembar April. | `core/models.py:94-100`, `services.py:264,285` | Bersihkan duplikat April (selidiki dulu), lalu migrasi 0006 `UniqueConstraint`. Beri `order_by` eksplisit pada setiap `.first()`. |
| 1.5 | **Upload paralel tanpa kunci.** Dua upload WTT bulan sama dengan hash berbeda bisa lolos bersamaan; `resync_project` dari aksi admin/command/upload tidak saling menunggu. | `ingest.py:330` | `select_for_update()` pada `Project` di awal `_ingest_one` dan `resync_project`. |
| 1.6 | **`except Exception` yang mengubah isi laporan.** `load_template_flight_metadata` mengembalikan `{}` bila gagal → daftar flight di laporan berubah tanpa pesan. Juga `report.py:224,465,626,717`, `ingest.py:251-262,436,479,531`, `services.py:86`. | `core/report.py:1367` dkk | Untuk yang mempengaruhi isi laporan: lempar error. Sisanya: catat ke log (lihat 3.1). |
| 1.7 | **Aturan charter tidak seragam.** `analytics.py` = 4 digit berawalan 8/9; `services.py` = 4 digit apa saja. Akibatnya `chrt_count` di dashboard selalu 0. | `analytics.py:9-14`, `services.py:355` | Satu fungsi `is_charter_flight` dipakai semua. |
| 1.8 | **Excel dan pratinjau HTML berbeda**: Tipe Pengajuan MENJADI selalu "Perubahan" di Excel tapi dihitung di HTML; tanggal tanda tangan "Bulan Tahun" di Excel vs "hari Bulan Tahun" di HTML; `datetime.now()` naif padahal `USE_TZ=True`. | `report.py:891,990,1509,935,1294,1521` | Samakan lewat satu fungsi; kunci dengan tes seperti `test_report_cells`. **Perlu keputusan pemilik** mana format yang resmi. |
| 1.9 | Kartu rincian flight OPERATED menampilkan ATD/ATA `--:--` karena membaca kolom WTT, bukan `ghp_atd`. | template kartu rincian | **Perlu keputusan pemilik**: kartu menampilkan jam GHP atau WTT (catatan 15 Sep). |

## Prioritas 2 — Kinerja (Download Rekap ±265 dtk, upload WTT 20–30 dtk)

Akar masalah: hasil parsing tidak pernah disimpan, jadi dibaca ulang dari file tiap kali.

| # | Masalah | Di mana | Perbaikan |
|---|---|---|---|
| 2.1 | **Setiap laporan/pratinjau membaca ulang semua PDF PPRP dan Excel GHP** (`_load_ghp_actual`, `_pprp_letter_flight`); cache hanya hidup satu run. `adopt_letters` mem-parse ulang semua PDF PPRP tiap upload WTT. Satu PPRP diparse di 4 tempat. GHP dibaca 2–3× per file. | `report.py:176,210`; `ingest.py:188,451,471-485`; `services.py:216` | Simpan hasil parse saat upload: tabel `GhpRecord` (flight, tanggal, origin, std, atd, delay) + rentang cakupan file; kolom `pprp_end_date` dan `day_pattern` di `ScheduleVersion` (sekarang hanya ada di PDF). Laporan lalu murni dari DB. Perkiraan: rekap turun ke belasan detik. |
| 2.2 | **Penyisipan baris openpyxl kuadratik**: `_copy_row`/`_shift_formulas_below` memindai semua kolom di semua baris bawah untuk tiap penyisipan. | `report.py:616,702` | Hitung dulu semua posisi sisipan, geser sekali dari bawah ke atas; atau bangun sheet baru dari template baris per baris. |
| 2.3 | **Query per baris saat ingest**: `create()` per baris WTT (±900), ±4 query per flight-hari PPRP, 1 query per baris GHP (±1600) + `save()` per cocok. | `services.py:135-160,245-305,419-465` | `bulk_create`, muat jadwal bulan itu sekali ke dict, `bulk_update`. |
| 2.4 | **Semua pekerjaan berat di dalam request** (gunicorn 3 worker sinkron, timeout 600 dtk). Tiga unduhan rekap bersamaan membekukan situs. | `entrypoint.sh`, `admin.py:127,149` | Setelah 2.1–2.3 mungkin sudah cukup cepat. Bila masih >30 dtk: jalankan lewat `django-tasks` (bawaan Django 6) + halaman status, bilah progres jadi nyata (pemilik ingin bilah + persen tetap ada). |
| 2.5 | Dashboard: 5 pass penuh atas queryset sama, aritmetika di Python; laporan `ScheduleVersion.objects.all()` tanpa `select_related('source_pprp')` (N+1 di `report.py:428`). | `views.py:181-185`, `analytics.py`, `report.py:791,1240,1390` | `select_related`, satu pass, agregasi DB. |
| 2.6 | Berkas `.xlsx` sementara tidak pernah dihapus (`NamedTemporaryFile(delete=False)`). | `admin.py:127,149` | `BytesIO` atau hapus setelah dikirim. |

## Prioritas 3 — Operasional & keamanan

| # | Masalah | Perbaikan |
|---|---|---|
| 3.1 | **Tidak ada logging sama sekali** (tanpa `LOGGING`, tanpa `logger`). Error hanya ditelan atau dikirim mentah ke browser. | `LOGGING` ke file berputar di `logs/`; setiap `except` mencatat; pesan ke klien umum. |
| 3.2 | **Backup**: hanya dump manual (terakhir 3 Sep). `media_volume` (PDF sumber yang masih dibaca ulang laporan) tidak dibackup. | `manage.py backup` (dumpdata + salin `media/`) dijadwalkan harian (Task Scheduler / cron di compose); simpan 30 hari. Setelah 2.1, media hanya arsip. |
| 3.3 | **Keamanan** (dari audit 15 Sep, belum satu pun): `/media/` publik di nginx, `DEBUG` default True, `SECRET_KEY` default di repo, semua view hanya `is_staff`, `template_path` bisa diarahkan ke file lain, tanpa `SECURE_*`. | Kerjakan sesuai tabel audit setelah 2 pertanyaan (repo publik? dipakai di jaringan?) dijawab. Tambahan baru: Chart.js dimuat dari jsDelivr tanpa versi/SRI (`templates/admin/index.html:21`) → simpan lokal di `static/`; Google Fonts di `report_view.html`/`report_loading.html` gagal offline → simpan lokal. |
| 3.4 | Validasi upload hanya di HTML (`accept=`) dan nginx 20M; file disimpan ke disk sebelum divalidasi; `UPLOAD_DIR` relatif ke cwd, path absolut disimpan di DB (patah bila pindah host/container). | Batas ukuran + ekstensi di server; simpan path relatif `MEDIA_ROOT`. |
| 3.5 | Docker: tanpa healthcheck web/nginx, tanpa `/health`, container root, `build-essential` ikut di image akhir, `.dockerignore` membuang `tests/` dan `docs/` (tes tak bisa dijalankan di image). | Endpoint `/health` + healthcheck; multi-stage build; user non-root. |
| 3.6 | Migrasi 0005 belum dijalankan di DB kerja; `main` 1 commit di depan origin. | Jalankan `migrate` saat upload September; push setelah dikonfirmasi. |
| 3.7 | Berkas sensitif di root kerja (gitignored, tapi ada di disk): `reset_pw.sql` (password root MySQL), `test_db.py` (skrip tebak password). | Hapus dari disk. |

## Prioritas 4 — Perawatan kode & tes

| # | Masalah | Perbaikan |
|---|---|---|
| 4.1 | **Dua file tes tidak pernah dijalankan** `manage.py test`: `tests/test_parsers.py` dan `tests/test_processing.py` berisi fungsi polos, bukan `TestCase`; `test_processing.py` memanggil `django.setup()` ke DB asli dan memeriksa angka basi 842. | Ubah jadi `TestCase` atau hapus. |
| 4.2 | Tanpa tes: `global_dashboard_api`, `pprp_achievement`, `daily_otp_trend`, `flight_distribution`, semua view admin (unduh laporan, rekap, pratinjau, detail JSON, aksi resync), `sync_pprp`, skenario rollback mode ganti, izin akses. | Tambah bertahap, dimulai dari rollback (1.2) dan tahun GHP (1.1). |
| 4.3 | Suite penuh ±13 menit karena parsing PDF WTT nyata; DB uji bernama sama sehingga dua suite tak bisa jalan bersamaan. | Fixture hasil parse (JSON) untuk tes non-parser; `TEST['NAME']` unik. Tanpa CI (tidak ada `.github/`). |
| 4.4 | Kode mati dilacak git: `docs/app.py` + `docs/core.py` (FastAPI lama, 1900 baris), `_pprp_letter_end_date`, `_rebuild_totals`, `detect_pprp_period`, `matching_key`, import ganda di `admin.py`, `core/tests.py` kosong. Sampah root: `prof.py`, `prof.txt`, `profile.txt`, `test_regex.py`, `test_translator.py`, `report_1.xlsx`, `db.sqlite3`, `__pycache__/`. | Hapus. |
| 4.5 | Duplikasi: peta nama bulan di 7 tempat; logika sisip blok ditulis dua kali (`generate_report` inline vs `_insert_pprp_subblocks`); `generate_report` dan `generate_rekap_report` berbagi ±80 baris; rumus selisih menit disalin 4× di `analytics.py`. `generate_report` ±190 baris, `get_project_report_data` ±165. | Satu modul `core/constants.py`; satu jalur laporan dengan parameter "satu bulan / satu musim". |
| 4.6 | Hardcode: URL admin di `admin.py:59,140,144` (pakai `reverse`), rentang tahun filter 2024–2029, nama template di 3 tempat, aturan musim summer/winter di `report.py:1399`. | Pindahkan ke settings/konstanta. |
| 4.7 | `README.md` basi (alur "Process selected files" yang sudah ditutup, path `F:\extractor-citilink`, tanpa bagian Docker). | Tulis ulang singkat: setup, upload, laporan, tes, Docker. |
| 4.8 | `LANGUAGE_CODE='en-us'` padahal UI Indonesia (lihat catatan 15 Sep tentang teks bawaan admin). | **Perlu keputusan pemilik** (mengubah format tanggal admin). |

## Urutan pengerjaan yang disarankan

1. **Sprint 1 — kebenaran** (1.1, 1.2, 1.3, 1.5, 4.1): kecil, terukur, langsung mengurangi risiko laporan salah.
   Satu commit per nomor, tes untuk tiap nomor.
2. **Sprint 2 — simpan hasil parse** (2.1 → 2.3 → 2.2 → 2.6): ini pengubah terbesar; rekap dari menit ke detik,
   pratinjau laporan instan, panel kesehatan data (pekerjaan terbuka 3 Sep) jadi mudah karena datanya sudah di DB.
3. **Sprint 3 — operasional** (3.1, 3.2, 3.3 setelah 2 pertanyaan audit dijawab, 3.4, 3.7).
4. **Sprint 4 — perawatan** (4.4–4.7), lalu 2.4 hanya bila masih diperlukan.

Pekerjaan terbuka lama tetap: panel kesehatan data (paling pas dikerjakan setelah Sprint 2), 4 baris kembar April
(dikerjakan bersama 1.4), surat QG719/QG179, blok QG-179 tanpa baris Oktober (keputusan Oktober).

## Pertanyaan untuk pemilik (maksimal tiga)

1. Setuju urutan Sprint 1 → 2 di atas, dimulai dari 1.1 (tahun GHP) dan 1.2 (mode ganti)?
2. Untuk 1.8: format resmi tanda tangan laporan "Surabaya, September 2026" (Excel) atau "Surabaya, 26 September 2026" (HTML)?
   Dan Tipe Pengajuan MENJADI: selalu "Perubahan" atau dihitung?
3. Dua pertanyaan audit keamanan 15 Sep masih menunggu: repo GitHub publik atau privat, dan aplikasi dipakai
   hanya di PC ini, jaringan kantor, atau internet?
