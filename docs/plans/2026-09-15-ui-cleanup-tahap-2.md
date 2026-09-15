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
