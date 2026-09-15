# Perapian Antarmuka Tahap 2

**Project:** CITILINK AVIOR
**Date:** 2026-09-15
**Status:** Sedang dikerjakan. Lanjutan `docs/ui-cleanup.md` (13 Sep).
**Aturan:** satu commit per nomor, `manage.py check` + tes terkait tiap nomor, suite penuh di akhir, tidak push sampai pemilik melihat hasilnya.

## Keputusan pemilik (15 Sep)

- Nama **CITILINK AVIOR / AViation Operations Report** adalah nama dari pemilik — **tidak diubah**.
- **Istilah teknis tetap Inggris**: OTP, STD/STA/ATD/ATA, AGT/SGT, OPERATED, NO OPS, ACTIVE, WTT/PPRP/GHP.
  Yang diindonesiakan hanya label umum (menu, judul kolom, tombol).
- `report_view.html` dan `report_loading.html`: yang pertama tetap terkunci; yang kedua boleh diganti
  spinner (nomor 3) karena isinya bukan dokumen resmi.

## Urutan pengerjaan

Aman dulu (hanya teks/kelas), yang menyentuh logika di akhir.

| Urut | No | Halaman / file | Perubahan | Risiko |
|---|---|---|---|---|
| 1 | 1 | Flight Schedules → kartu rincian (`templates/admin/core/scheduleversion/change_list.html`) | hapus footer "Data Resmi Tersinkronisasi…", stempel "NO OPS DETECTED", ikon di judul seksi & di depan nilai, tanda kutip/miring pada keterangan; status kapital → kalimat biasa; satu tombol tutup; hapus "(Surabaya)" hardcode; perbaiki `style=` yang terselip di `class=` | tampilan saja |
| 2 | 5 | Upload Data (`templates/admin/core/sourcefile/custom_upload.html`) | badge Mandatory merah → abu; badge tipe WTT/GHP satu warna; hapus tanda seru; nama file utuh (`basename`, bukan potongan path); buang parameter warna mati di JS | tampilan saja |
| 3 | 6 | Paginasi (`templates/unfold/helpers/pagination_default.html`) | hapus "Total Query"; kelas `text-gray-*` → token Unfold | tampilan saja |
| 4 | 7 | Bahasa: sidebar (`config/settings.py`), Upload Data, paginasi, judul chart dashboard | label umum → Indonesia; istilah teknis tetap | tampilan saja |
| 5 | 4 | Dashboard AGT/SGT (`core/analytics.py`, `core/views.py`) | "1:45"/"1:30" saat data kosong → "-" | data (kecil) |
| 6 | 2 | Tombol tabel Projects & Flight Schedules (`core/admin.py`) | kelas tombol Unfold, tanpa `#006b32`/`brightness`/`scale`; "➔" → "→"; label OPERATED hijau; `text-gray-500` → token Unfold | `onclick` harus tetap; uji klik di browser |
| 7 | 3 | Progress palsu: modal Unduh Rekap (`project/change_list.html`) dan `report_loading.html` | ganti spinner + satu kalimat; logika fetch/unduh tetap | JS unduh & muat laporan; uji di browser |

## Yang sengaja tidak diubah

- `report_view.html` (dokumen resmi).
- Teks status teknis (OPERATED, NO OPS, ACTIVE, INACTIVE (PPRP)).
- Susunan seksi 1–4 pada kartu rincian (hanya elemen dekoratifnya yang dihapus).
- Subjudul kartu rincian "Detail log operasional dan rekonsiliasi jadwal" dan teks "Versi 1 (Baseline WTT)" — tidak termasuk daftar yang disetujui.
- Kolom `period`/`year`/`month` di tabel Projects — belum dijawab pemilik.

## Catatan pengerjaan

### No 1 — kartu rincian penerbangan (selesai)

- Dihapus: footer "Data Resmi Tersinkronisasi Dengan Master Database" + "Waktu Input" (data ganda dengan
  kartu "Waktu input" di seksi 1); stempel overlay "NO OPS DETECTED" beserta CSS `.stitch-stamp`; ikon di
  4 judul seksi, di header dua kartu waktu, dan di depan nilai rute/tanggal/waktu input/nama file; tombol
  panah kembali (tersisa satu tombol "Tutup" varian default).
- Teks status: "TIDAK BEROPERASI (UNVERIFIED) — NILAI 0 DI FORM LAPORAN" → "Tidak beroperasi — nilai 0 di
  laporan"; "TERKONFIRMASI BEROPERASI (OPERATED) — …" → "Beroperasi — nilai 1 di laporan". Label
  "Status operasional (nilai di matriks laporan)" → "Status operasional". Badge NO OPS/OPERATED/ACTIVE tetap.
- Keterangan tidak lagi miring dan tidak dibungkus tanda kutip; label "Keterangan / alasan sistem" → "Keterangan".
- Rute: `${origin} (Surabaya)` yang di-hardcode → `SUB → HLP` (teks biasa).
- Markup rusak diperbaiki: `class="h-1.5 rounded-full style="width:0.375rem" bg-green-600"` (3 tempat) →
  `class="stitch-dot"` dengan CSS sendiri, karena `w-1.5` tidak ada di CSS Unfold.
- JS: `st-stamp-container`, `st-ops-icon`, `st-footer-created-at` dibuang; `innerHTML` untuk rute/tanggal/
  nama file diganti `textContent`. `id` lain dan `openScheduleDetail`/`closeScheduleDetail` tetap.
- Verifikasi: `manage.py check` bersih; `test_both_upload_pages_render` lulus; pratinjau statis
  (DB kerja dibaca, tanpa login) untuk flight NO OPS (QG173 31 Agu) dan OPERATED (QG834 31 Agu) — kedua
  keadaan tampil benar di mode gelap.
- Ditemukan, tidak diubah (di luar cakupan): pada flight OPERATED, ATD/ATA tampil `--:--` karena kartu membaca
  `atd`/`ata` (WTT) padahal yang terisi `ghp_atd`. Perlu keputusan pemilik: kartu ini menampilkan jam GHP atau WTT?

### No 5 — Upload Data (selesai)

- Badge langkah: "Mandatory" merah → "Wajib" abu-abu; "Optional" → "Opsional".
- Badge tipe file di riwayat: WTT biru / PPRP hijau / GHP oranye → satu badge abu-abu (`bg-base-100`).
- "Proses Selesai!" → "Proses selesai"; "Refresh Halaman" → "Muat Ulang"; label progres "Selesai!"/"Gagal!" →
  tanpa tanda seru; tombol usai upload "Completed" → "Selesai".
- Nama file di riwayat: `file_path|slice:"-35:"` (35 karakter terakhir dari path, bisa terpotong di tengah nama)
  → filter baru `basename` di `core/templatetags/custom_tags.py`; nama juga dipakai modal hapus (`escapejs`).
- JS: parameter warna mati (`'bg-blue-600'`, `'bg-purple-600'`, `'bg-orange-600'`) dan `classList.remove(...)`
  untuk kelas yang sudah tidak ada dibuang; `step.btn.style.backgroundColor = '#006b32'` dibuang (tombol sudah
  `bg-primary-600`). Badge nomor langkah setelah sukses memakai `bg-green-50 text-green-700` (kelas yang ada di
  CSS Unfold; sebelumnya `bg-green-100`/`dark:bg-green-900/30` yang tidak ada).
- Verifikasi: `manage.py check` bersih; `tests.test_ingest.UploadEndpointsTests` (4 tes) lulus; pratinjau statis
  menampilkan badge "Wajib/Opsional/Wajib", nama file utuh di riwayat, `onclick` modal hapus membawa nama file utuh.

### No 6 — paginasi (selesai)

- `templates/unfold/helpers/pagination_default.html` ditulis ulang. "Total Query: N" dihapus (nilainya sama
  dengan "dari N data"); bila hasil tersaring, ditampilkan "(tersaring dari N)".
- Tombol First/Prev/Next/Last → « ‹ › » dengan `title` Indonesia (label bahasa untuk paginasi ikut selesai di sini,
  tidak diulang di No 7).
- Semua kelas `text-gray-*`/`bg-gray-*`/`border-gray-*`/`ring-*`/`min-w-[32px]` (tidak ada di CSS Unfold, mode gelap
  rusak) → kelas tombol Unfold varian default/primary + token `text-font-*`. Keberadaan tiap kelas dicek dengan
  `grep -F` di `styles.css` (catatan: cek `grep -c "\.dark\\:…"` di `ui-cleanup.md` §6 harus memakai `-F` atau
  backslash ganda, kalau tidak selalu 0).
- Verifikasi: `manage.py check` bersih; `test_both_upload_pages_render` lulus; pratinjau Flight Schedules
  (6543 baris, 131 halaman) menampilkan "Menampilkan 1–50 dari 6543 data" dan « ‹ 1 2 3 4 › » dengan gaya tombol Unfold.

### No 7 — bahasa label umum (selesai)

Istilah teknis (OTP, STD/STA/ATD/ATA, AGT/SGT, OPERATED, NO OPS, ACTIVE, WTT/PPRP/GHP, Upload, Dashboard,
Project) sengaja tetap.

- Sidebar (`config/settings.py`): Navigation → Navigasi; Flight Schedules → Jadwal Penerbangan; Projects → Project;
  Administration → Administrasi; User Management → Pengguna; Groups → Grup.
- Upload Data: judul "Upload Source File" → "Upload Data" (sama dengan menu); "Auto-Detect Periode" → "Periode";
  "Select WTT/PPRP/GHP file" → "Pilih file …"; "Uploading..." → "Mengunggah file..."; "Processing..." →
  "Memproses..."; Skip/Skipped → Lewati/Dilewati; "Upload History" → "Riwayat Upload"; kolom File Name / Type /
  Uploaded At / Uploader / Action → Nama File / Tipe / Waktu Upload / Diunggah oleh / Aksi.
- Dashboard: "On Time Performance Target vs Actual (Harian)" → "OTP Harian: Target vs Aktual"; "Total Delay Time in
  Hours by Delay Reason" → "Total Durasi Delay per Delay Code" (sekaligus mencerminkan isi grafik sejak `aa676d5`);
  "Realisasi PPRP (Toleransi <= 45 Min)" → "(Toleransi ≤ 45 Menit)"; "Distribusi Rute Penerbangan Terbanyak (SUB
  Origin) / Top 8 Destinasi" → "Rute Terbanyak dari SUB / 8 destinasi teratas"; legenda donat PPRP "Sesuai
  Tolerance (<=45m)" → "Dalam toleransi (≤45 menit)".
- `core/admin.py` (teks saja; kelas tombol dikerjakan di No 2): kolom "View Report" → "Laporan", tombolnya
  "Lihat Laporan"; "Route" → "Rute"; "Schedule (STD ➔ STA)" → "Jadwal (STD → STA)"; "Operation" → "Operasi".
- Verifikasi: `manage.py check` bersih; `test_both_upload_pages_render` lulus; pratinjau sidebar, Upload Data,
  dashboard (judul chart + legenda), dan tabel Projects menampilkan label baru.
- **Masih Inggris, perlu keputusan pemilik** (tidak diubah karena bukan dari template):
  1. Judul kolom dari nama field model: "Project id", "Period", "Year", "Month", "Created by", "Created at",
     "Flight date". Mengubahnya = `verbose_name` di `core/models.py` → Django membuat migrasi baru (0006).
  2. Breadcrumb "Core › Projects / Schedule versions", judul tab "Select project to change", "Type to search",
     "Filters", "Light/Dark/System", "Change password", "Global shortcuts": teks bawaan Django admin/Unfold.
     Cara paling murah: `LANGUAGE_CODE = 'id'` (Django punya terjemahan Indonesia; Unfold tidak membawa folder
     `locale`, jadi sebagian teks Unfold tetap Inggris). Efek samping: format tanggal admin berubah
     ("Aug. 4, 2026" → "4 Agustus 2026"); laporan Excel tidak terpengaruh (pakai nama bulan sendiri).
