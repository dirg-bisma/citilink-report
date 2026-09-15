# Implementation Plan — Grafik Delay Code dari GHP

**Project:** Automated Flight Schedule Reporting System (CITILINK AVIOR)
**Date:** 2026-09-13
**Status:** Diimplementasikan 2026-09-15 (belum di-commit). K1–K3 (§8) disetujui pemilik sesuai rekomendasi.

## 1. Tujuan

Grafik donat di dashboard ("Kategori Delay Breakdown (IATA Standard)") diganti menjadi **frekuensi per delay code
apa adanya**, bersumber dari kolom "Break Down" GHP — tanpa pengelompokan kategori IATA.

## 2. Keputusan yang sudah dikonfirmasi pemilik

| # | Keputusan |
|---|---|
| D1 | Tidak ada pengelompokan. Grafik menampilkan delay code mentah (mis. "89", "80") dan berapa kali muncul. |
| D2 | Yang dihitung: **semua flight yang punya delay code** di GHP, berapa pun lama delay-nya. Aturan "> 15 menit" tidak dipakai untuk grafik ini. |

## 3. Fakta dari data sumber

Diperiksa pada `ghp2026-09-13_092926.xls` — "SUB - Ground Handling Punctuality (01/09/2026 - 12/09/2026 - Detail)".

- 296 baris penerbangan, 12 hari, seluruhnya berbentuk 2 flight / 3 stasiun dengan **SUB di tengah**
  (bentuk yang sama di kelima file GHP Maret–Juli di `docs/Source/`).
- Kolom 13 "Total" = durasi total `HH:MM`; kolom 14 "Break Down" = pasangan **`DURASI/KODE`** dipisah koma,
  mis. `00:04/63,00:19/80,00:04/89`.
- 97 baris punya Break Down; **format valid di semua baris**; jumlah durasi = "Total" di semua baris.
- 34 flight punya lebih dari satu kode (maks. 3). String terpanjang 26 karakter.
- 25 kode berbeda: 10, 15, 16, 19, 32, 34, 36, 40, 42, 46, 50, 61, 63, 68, 70, 72, 77, 80, 87, 89, 90, 91, 95, 96, 99.
- Makna baris: jam dan delay milik **keberangkatan dari stasiun tengah**, yaitu flight **kedua**.
  Contoh `QG726 -QG484 /CGK -SUB -BDJ` → QG484 berangkat SUB.
- Satu baris berdelay adalah charter 4 digit (`QG9693 -QG9692 /DPS -SUB -DPS`, `01:17/80`), yang menurut aturan
  bisnis dikecualikan saat GHP dicocokkan.
- Keenam GHP yang sudah terupload (Maret–Agustus) kolom 13–14-nya **kosong seluruhnya** — tidak ada data lama
  yang perlu dimigrasi.

## 4. Kondisi kode sekarang dan masalahnya

| Lokasi | Perilaku sekarang | Masalah |
|---|---|---|
| `core/parsers/ghp.py:107` | Isi sel Break Down disimpan utuh ke `delay_code`, **untuk kedua flight** di baris | Satu "kode" = `00:04/63,00:19/80,00:04/89`; flight yang datang ke SUB ikut menerima kode milik flight yang berangkat |
| `core/services.py:450` | `delay_code` hanya ditulis bila GHP baru punya kode | Kode lama **tidak pernah dihapus** saat GHP dicocokkan ulang |
| `core/services.py:77` | Hapus file GHP me-reset `operational_flag`, `ghp_std`, `ghp_atd` | `delay_code` **tidak** ikut di-reset — kode basi tertinggal |
| `core/analytics.py:16` | `map_iata_category` mencocokkan potongan teks | Durasi `00:41` terbaca kode `41`; pengelompokan juga tidak dibutuhkan lagi (D1) |
| `core/analytics.py:187` | Hanya flight dengan ATD−STD > 15 menit; durasi = ATD−STD | Bertentangan dengan D2; durasi bukan dari GHP |
| `templates/admin/index.html:584` | Donat diberi `iata_categories` | `case_counts` sudah dihitung API tetapi tidak pernah ditampilkan |
| `core/models.py:81` | `delay_code = CharField(max_length=50)` | Muat untuk data sekarang (26), tapi MySQL mode strict **menolak** penyimpanan bila suatu hari > 50 karakter |

## 5. Rancangan perubahan

### T1 — Parser `core/parsers/ghp.py`

- Fungsi baru `parse_delay_breakdown(text) -> list[tuple[str, int]]`: `"00:04/63,00:19/80"` → `[("63", 4), ("80", 19)]`.
  Toleran spasi; teks kosong → `[]`; format tidak valid → `ValueError`.
- `parse_ghp`: kolom 14 dibaca, dinormalisasi (spasi dibuang), dan **hanya ditempelkan ke flight terakhir di baris**
  (yang berangkat dari stasiun tengah). Flight pertama mendapat `delay_code = ''`.
- Baris dengan Break Down tidak valid: `delay_code = ''` dan isi mentahnya dicatat di `delay_code_invalid` agar
  bisa dilaporkan sebagai peringatan (T3), bukan membuat upload gagal.
- **Tidak diubah:** jumlah record, `std`, `atd`, `origin`, `destination`, dan pencocokan jadwal. Laporan Excel
  (sel harian 1/0) bergantung pada jalur itu dan berada di luar cakupan.

Format simpan `delay_code`: string Break Down yang sudah dinormalisasi, mis. `00:04/63,00:19/80,00:04/89`.
Dipilih karena tetap bisa ditelusuri balik ke file GHP apa adanya, dan durasi per kode ikut tersimpan tanpa kolom baru.

### T2 — Model dan migrasi (keputusan K1)

Bila K1 disetujui: `delay_code` diperlebar `max_length=50 → 255` lewat migrasi `0005`. Perubahan ini hanya
memperlebar kolom `VARCHAR`, tanpa memindahkan data.

### T3 — Pencocokan `core/services.py`

- `process_ghp`: selalu `schedule.delay_code = rec.get('delay_code') or None`, sehingga pencocokan ulang idempoten
  dan kode basi terhapus.
- `delete_source_file` (tipe GHP): `update(...)` ditambah `delay_code=None`.
- `GhpMatchResult.warnings()`: tambah peringatan untuk baris `delay_code_invalid`, tampil di hasil upload seperti
  peringatan GHP yang sudah ada.

### T4 — Analitik `core/analytics.py`

`delay_factors` ditulis ulang:

- Sumber: `filter_flights(...)` yang sudah ada (asal SUB, `operational_flag`, `is_active`, filter tanggal) **dan**
  `delay_code` terisi. Tanpa filter > 15 menit (D2).
- Untuk setiap flight: pecah dengan `parse_delay_breakdown`. Satu kode dihitung **sekali per flight**; flight dengan
  3 kode masuk ke 3 kode.
- Hasil:
  - `case_counts`: **semua** kode, urut jumlah flight turun → menit turun → kode. Tiap item
    `{code, count, minutes}`.
  - `durations`: sesuai keputusan K2.
  - `total_flights`: jumlah flight berkode (untuk keterangan grafik).
- `map_iata_category` dan kunci `iata_categories` **dihapus** (satu-satunya pemakai adalah donat ini).
- `delay_code` yang gagal di-parse dari database dilewati dan tidak membuat API error.

### T5 — `core/views.py`

Nilai default `delay_data` disesuaikan dengan kunci baru (`case_counts`, `durations`, `total_flights`).

### T6 — Tampilan `templates/admin/index.html`

- `renderIataDonutChart` → `renderDelayCodeChart(caseCounts)`, dipanggil dengan `data.delay_data.case_counts`.
- Judul kartu: **"Delay Code Terbanyak"**; keterangan kanan: "`N` flight berkode".
- Label legenda "Kode 89"; tooltip "Kode 89 — 30 flight".
- Jumlah irisan sesuai keputusan K3.
- Palet: gradasi hijau Citilink + abu-abu (konsisten dengan `docs/ui-cleanup.md`); warna diambil berurutan sesuai
  peringkat, bukan acak.
- Pesan kosong: "Belum ada delay code pada GHP periode ini."
- Grafik "Total Delay Time in Hours by Delay Reason": sesuai K2.

### T7 — Tes

- Fixture: salin GHP September ke `docs/Source/data_master_september_2026_01-12.xls` (konvensi nama yang sama;
  `.xls` tidak diabaikan git).
- `tests/test_parsers.py`
  - `parse_delay_breakdown`: satu kode, multi-kode, spasi, kosong, format tidak valid.
  - GHP September: 97 record keberangkatan membawa kode; 0 record kedatangan membawa kode; jumlah menit per baris
    = kolom "Total".
  - Regresi: GHP April tetap 1614 record dan tanpa kode.
- `tests/test_processing.py` (DB uji):
  - Pencocokan ulang dengan GHP tanpa kode mengosongkan `delay_code`.
  - Hapus file GHP mengosongkan `delay_code`.
  - `delay_factors` dengan jadwal sintetis: flight multi-kode masuk ke tiap kode; flight berkode dengan delay < 15
    menit tetap dihitung; flight bukan asal SUB / tidak aktif tidak dihitung.
- Suite lengkap dijalankan ulang (±13 menit, DB uji MySQL).

## 6. Hasil yang diharapkan setelah WTT + GHP September diupload

Angka mentah dari GHP (sebelum dicocokkan ke jadwal):

| Kode | Flight | Menit |
|---|---|---|
| 89 | 30 | 143 |
| 80 | 26 → **25** | 470 → **393** |
| 63 | 19 | 85 |
| 15 | 15 | 90 |
| 70 | 6 | 265 |

Angka di dashboard akan **sedikit lebih kecil** dari tabel mentah, dan itu wajar:

- Charter `QG9692` dikecualikan → kode 80 turun menjadi 25 flight, total maksimal 96 flight.
- Flight GHP yang tidak punya jadwal di WTT/PPRP tidak dihitung; daftarnya muncul sebagai peringatan saat upload.

Kartu KPI "Delay" (flight ATD−STD > 15 menit) **tetap** memakai definisi OTP-15, sehingga angkanya berbeda dengan
jumlah flight berkode di donat. Ini konsekuensi D2, bukan kesalahan.

## 7. Di luar cakupan

- Definisi OTP, kartu KPI, dan grafik OTP harian.
- Laporan Excel bulanan/rekap — tidak membaca `delay_code` (sudah diperiksa).
- Atribusi `std`/`atd` untuk flight pertama di baris GHP.
- Data bulan lama — kolom delay-nya memang kosong.
- Upload WTT September — prasyarat operasional, dilakukan pemilik lewat halaman Upload Data.

## 8. Keputusan terbuka

| # | Pertanyaan | Rekomendasi |
|---|---|---|
| **K1** | Perlebar kolom `delay_code` dari 50 ke 255 karakter? | **Ya.** Data sekarang maks. 26 karakter, tetapi flight dengan 5 kode atau lebih akan membuat upload GHP **gagal total** di MySQL mode strict. Migrasinya hanya memperlebar kolom. |
| **K2** | Grafik "Total Delay Time in Hours by Delay Reason" ikut diubah: menit **per kode dari GHP**, untuk semua flight berkode? | **Ya.** Sekarang grafik itu memakai ATD−STD > 15 menit sehingga tidak sejalan dengan donat. Dengan GHP, menit tiap kode tercatat terpisah — flight dengan 3 kode tidak lagi menjatuhkan seluruh durasinya ke satu kode. |
| **K3** | Berapa irisan di donat? 25 kode terlalu banyak untuk dibedakan warnanya. | **9 kode teratas + "Lainnya"**, supaya donat tetap menjumlah 100% dan terbaca saat diproyeksikan. Daftar lengkap tetap tersedia di API. |

Catatan untuk K3: karena satu flight bisa punya beberapa kode, persentase tiap irisan = porsi dari **total kemunculan
kode**, bukan dari jumlah flight. Tooltip menampilkan jumlah flight agar tidak disalahpahami.

## 9. Urutan kerja

1. Keputusan K1–K3 dari pemilik.
2. T7 (fixture + tes parser) → T1 → T2 → T3 → T4 → T5 → T6.
3. `manage.py check`, lalu suite tes lengkap.
4. Pratinjau dashboard memakai data sintetis yang dibentuk dari GHP September (tanpa login, tanpa menulis DB).
5. Commit — hanya bila diminta pemilik.
6. Pemilik mengupload WTT September lalu GHP September, kemudian mencocokkan dashboard dengan tabel §6.

## 10. Risiko

| Risiko | Mitigasi |
|---|---|
| Perubahan parser menggeser sel harian laporan | Hanya kolom `delay_code` yang berubah; tes regresi April (1614 record) dan tes sel laporan yang sudah ada tetap dijalankan |
| Ekspor GHP lain memakai format Break Down berbeda | Baris tidak valid dilewati dan dilaporkan sebagai peringatan; upload tidak gagal |
| Selisih angka donat dengan kartu KPI "Delay" membingungkan pembaca | Keterangan "`N` flight berkode" pada kartu; dijelaskan di §6 |
