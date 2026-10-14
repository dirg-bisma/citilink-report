# Alur Kerja Penyempurnaan AVIOR (bahasa sederhana)

**Tanggal:** 26 September 2026
**Untuk siapa:** pemilik aplikasi. Dokumen teknis lengkapnya ada di `2026-09-26-rekomendasi-penyempurnaan.md`;
dokumen ini hanya menjelaskan **urutan kerja dan apa yang harus Anda lakukan**.

## Cara membaca dokumen ini

Pekerjaan dibagi 4 tahap. Tiap tahap berisi beberapa langkah. Tiap langkah punya tiga bagian:

- **Masalahnya** — kenapa perlu diperbaiki, dalam satu-dua kalimat.
- **Yang saya kerjakan** — perubahan kode, tes, dan pemeriksaan. Saya yang mengerjakan.
- **Yang Anda lakukan** — biasanya cuma satu: mencoba hasilnya di aplikasi dan bilang "oke" atau "belum".

Aturan main yang sudah kita sepakati dan tetap berlaku:
- Satu langkah = satu commit. Tidak ada push sebelum Anda melihat hasilnya.
- Template Excel resmi dan halaman kop surat PPRP tidak disentuh.
- Tampilan (tombol hijau, bilah progres) tidak diubah kecuali Anda minta.

Setiap kali satu langkah selesai, saya akan tulis di sini: **SELESAI (commit xxx)**.

---

## TAHAP 1 — Menutup celah yang bisa membuat laporan salah

Ini prioritas paling atas karena laporan ini diserahkan ke audit. Semua langkah di sini kecil dan cepat.

### Langkah 1. Tahun pada file GHP

**Masalahnya.** File GHP hanya mencantumkan tanggal-bulan (misalnya 05/01), tanpa tahun. Kode sekarang selalu
menganggap tahunnya 2026. Mulai Januari 2027, semua data GHP akan gagal cocok dan seluruh flight tampak
"tidak beroperasi", tanpa ada pesan kesalahan.

**Yang saya kerjakan.** Ambil tahun dari judul file GHP, teruskan ke proses pencocokan. Tambah tes "GHP Januari 2027 cocok".

**Yang Anda lakukan.** Tidak ada. Cukup tahu bahwa ini sudah aman.

### Langkah 2. Ganti file tidak boleh mengosongkan bulan

**Masalahnya.** Saat Anda mengganti file WTT atau GHP lewat "Atur Ulang", data lama dihapus dulu, baru file baru
diproses. Kalau file baru ternyata gagal diproses, data lama sudah terlanjur hilang dan bulan itu jadi kosong.

**Yang saya kerjakan.** Hapus data lama dan proses file baru dijadikan satu paket: kalau yang baru gagal, yang lama
kembali utuh. Tambah tes untuk skenario gagal.

**Yang Anda lakukan.** Coba upload file yang sengaja salah (misalnya PDF WTT di kartu GHP) untuk bulan yang sudah ada,
lalu pastikan data bulan itu masih ada.

### Langkah 3. Baris yang dilewati harus dilaporkan

**Masalahnya.** Saat membaca PDF WTT, PDF PPRP, atau Excel GHP, baris yang formatnya tidak dikenali dibuang
diam-diam. Anda tidak pernah tahu ada flight yang hilang.

**Yang saya kerjakan.** Setiap kali upload, hasilnya menyebutkan "N baris dilewati" beserta contohnya, sama seperti
peringatan "flight tidak punya jadwal" yang sudah ada. Surat PPRP yang tidak punya bagian MENJADI atau tidak
punya nomor surat akan ditolak, bukan diproses setengah.

**Yang Anda lakukan.** Upload ulang satu bulan yang sudah ada (pakai Atur Ulang) dan lihat apakah muncul peringatan
baris dilewati. Kalau muncul, kita periksa bersama apakah itu memang baris sampah atau flight sungguhan.

### Langkah 4. Empat baris kembar April

**Masalahnya.** Di data April ada 4 baris jadwal ganda (QG352 dan QG494, tanggal 8 dan 15). Sistem sekarang tidak
punya pagar yang mencegah baris ganda, dan kalau dibiarkan bisa membuat proses PPRP berhenti dengan error.

**Yang saya kerjakan.** Cari tahu asal 4 baris itu, bersihkan, lalu pasang pagar di database supaya baris ganda
tidak bisa terbentuk lagi. Ini butuh satu migrasi database (0006).

**Yang Anda lakukan.** Setelah dibersihkan, buka laporan April dan pastikan QG352 dan QG494 tampil benar.

### Langkah 5. Dua orang upload bersamaan

**Masalahnya.** Kalau dua upload untuk bulan yang sama berjalan bersamaan, keduanya bisa saling menimpa.

**Yang saya kerjakan.** Pasang kunci: upload untuk bulan yang sama menunggu giliran.

**Yang Anda lakukan.** Tidak ada.

### Langkah 6. Dua file tes yang ternyata tidak pernah jalan

**Masalahnya.** Dua file tes lama ditulis dengan cara yang tidak dikenali Django, jadi selama ini tidak pernah
dijalankan. Salah satunya malah memeriksa angka yang sudah basi.

**Yang saya kerjakan.** Perbaiki atau hapus, supaya "70 tes lulus" benar-benar mencakup semuanya.

**Yang Anda lakukan.** Tidak ada.

### Langkah 7. Excel dan pratinjau di layar harus sama persis

**Masalahnya.** Ada dua perbedaan kecil antara file Excel dan pratinjau di browser:
1. Tanggal tanda tangan: Excel menulis "Surabaya, September 2026", pratinjau menulis "Surabaya, 26 September 2026".
2. Kolom Tipe Pengajuan pada baris MENJADI: Excel selalu "Perubahan", pratinjau menghitung sendiri.

**Yang saya kerjakan.** Menyamakan keduanya sesuai jawaban Anda, lalu mengunci dengan tes.

**Yang Anda lakukan (perlu jawaban).** Pilih mana yang resmi:
- Tanggal tanda tangan: **tanpa tanggal** ("Surabaya, September 2026") atau **dengan tanggal**?
- Tipe Pengajuan baris MENJADI: **selalu "Perubahan"** atau **dihitung** (bisa "Penambahan"/"Pembatalan")?

Kalau Anda belum yakin, saya pakai versi Excel (tanpa tanggal, selalu "Perubahan") karena itu yang selama ini
diserahkan ke audit.

**Selesai Tahap 1:** saya jalankan seluruh tes (±13 menit), Anda coba aplikasi, lalu kita push.

---

## TAHAP 2 — Membuat laporan cepat

### Langkah 8. Simpan hasil pembacaan file di database

**Masalahnya.** Ini penyebab Download Rekap butuh 4–5 menit. Setiap kali Anda minta laporan atau pratinjau, sistem
membuka ulang **semua** PDF PPRP dan **semua** Excel GHP dari awal, karena hasil bacaannya tidak pernah disimpan.
Membaca PDF itu lambat.

**Yang saya kerjakan.** Saat file diupload, hasil bacaannya disimpan ke database (tabel baru untuk baris GHP, dua
kolom tambahan untuk tanggal akhir dan pola hari surat PPRP). Laporan lalu cukup membaca database. Perlu satu migrasi
(0007) dan satu kali "Atur Ulang" untuk semua bulan supaya tabel baru terisi.

Perkiraan hasil: rekap dari ±4,5 menit menjadi belasan detik; pratinjau laporan hampir seketika.

**Yang Anda lakukan.** Sebelum langkah ini saya buat backup database. Setelah selesai, Anda unduh rekap dan laporan
bulanan, lalu bandingkan dengan hasil sebelumnya. Saya juga akan membandingkannya sel per sel dengan tes, seperti
yang dulu kita lakukan di bulan September awal. Isinya **harus sama persis**, hanya lebih cepat.

### Langkah 9. Percepat penulisan Excel

**Masalahnya.** Cara menyisipkan baris ke template Excel sekarang makin lambat setiap kali ada blok baru ditambahkan.

**Yang saya kerjakan.** Hitung dulu semua posisi sisipan, lalu tulis sekali jalan.

**Yang Anda lakukan.** Unduh rekap sekali lagi, bandingkan.

### Langkah 10. Percepat upload

**Masalahnya.** Upload WTT butuh 20–30 detik karena menyimpan baris satu per satu ke database (±900 kali).

**Yang saya kerjakan.** Simpan sekaligus. Target: di bawah 10 detik.

**Yang Anda lakukan.** Upload satu WTT, rasakan bedanya.

### Langkah 11. Bersihkan file sementara

**Masalahnya.** Setiap unduhan laporan meninggalkan satu file Excel sementara di server yang tidak pernah dihapus.
Lama-lama memenuhi disk.

**Yang saya kerjakan.** File dikirim langsung ke browser tanpa disimpan.

**Yang Anda lakukan.** Tidak ada.

**Catatan.** Bilah progres saat unduh rekap **tidak saya ubah**. Kalau setelah Langkah 8–9 rekap sudah belasan detik,
bilah itu tidak perlu dipikirkan lagi.

---

## TAHAP 3 — Supaya aplikasi aman dan bisa dipulihkan

### Langkah 12. Catatan kesalahan (log)

**Masalahnya.** Aplikasi tidak menulis catatan apa pun. Kalau ada yang gagal, jejaknya hilang dan pesan kesalahan
mentah (termasuk path server) dikirim ke browser.

**Yang saya kerjakan.** Semua kesalahan dicatat ke folder `logs/` dengan tanggal; pesan ke layar dibuat singkat.

**Yang Anda lakukan.** Tahu bahwa kalau ada masalah, kirimkan file di `logs/` ke saya.

### Langkah 13. Backup otomatis

**Masalahnya.** Backup terakhir tanggal 3 September, dibuat manual. Folder `media/` (file PDF dan Excel asli)
belum pernah dibackup sama sekali.

**Yang saya kerjakan.** Perintah `manage.py backup` yang menyimpan database + folder media ke `backups/`, dijadwalkan
tiap malam lewat Task Scheduler Windows, simpan 30 hari terakhir.

**Yang Anda lakukan (perlu jawaban).** Backup disimpan di mana? Pilihan paling sederhana: folder `backups/` di PC ini.
Lebih aman: folder di drive lain atau di jaringan kantor. Beri saya lokasinya.

### Langkah 14. Perbaikan keamanan dari audit 15 September

**Masalahnya.** Ada 8 temuan yang belum dikerjakan. Yang paling penting: (a) kalau dijalankan lewat Docker, file
upload bisa dibuka siapa saja tanpa login; (b) mode debug dan kunci rahasia masih nilai bawaan pengembangan;
(c) semua staf bisa menghapus data, bukan hanya yang diberi izin.

**Yang saya kerjakan.** Perbaiki sesuai tabel audit. Tambahan: pustaka grafik dan font yang sekarang diambil dari
internet disimpan lokal supaya aplikasi tetap jalan tanpa internet.

**Yang Anda lakukan (perlu jawaban, ini yang dari 15 September).**
1. Repo GitHub Anda **publik atau privat**? Kalau publik, file surat PPRP asli di folder `docs/Source` terbuka untuk
   umum dan harus segera ditangani.
2. Aplikasi dipakai **di PC ini saja**, **di jaringan kantor**, atau **lewat internet**?

Jawaban ini menentukan mana yang mendesak dan mana yang boleh ditunda.

### Langkah 15. Bersih-bersih file sensitif di PC

**Masalahnya.** Di folder proyek ada `reset_pw.sql` (berisi password root MySQL) dan `test_db.py` (skrip tebak
password). Tidak ikut ke git, tapi ada di disk.

**Yang saya kerjakan.** Minta izin Anda lalu hapus.

**Yang Anda lakukan.** Bilang "hapus" kalau setuju.

---

## TAHAP 4 — Merapikan kode (tidak mengubah perilaku)

### Langkah 16. Buang kode mati dan file sampah
File lama dari versi FastAPI (1.900 baris), fungsi yang tidak dipanggil, file coba-coba di folder utama
(`prof.py`, `test_regex.py`, `report_1.xlsx`, `db.sqlite3`, dll). **Yang Anda lakukan:** tidak ada.

### Langkah 17. Satukan yang berulang
Daftar nama bulan ditulis di 7 tempat, logika sisip blok Excel ditulis dua kali, dsb. Disatukan supaya perbaikan
berikutnya cukup di satu tempat. **Yang Anda lakukan:** tidak ada; tes memastikan hasil tidak berubah.

### Langkah 18. Tulis ulang README
Panduan sekarang masih menyebut alur lama dan folder `F:\extractor-citilink`. **Yang Anda lakukan:** baca sekali,
koreksi kalau ada yang tidak sesuai kebiasaan Anda.

---

## Yang saya butuhkan dari Anda SEKARANG

Cukup satu hal untuk memulai: **"mulai Tahap 1"**. Langkah 1–6 tidak butuh keputusan apa pun dari Anda.

Jawaban untuk Langkah 7, 13, dan 14 boleh menyusul; saya akan bertanya lagi tepat saat langkah itu tiba, satu per satu.

## Hal rutin yang tetap perlu Anda lakukan (di luar rencana ini)

- Saat data September lengkap: upload WTT September dulu, baru GHP September. Sebelum itu saya perlu menjalankan
  migrasi 0005 (satu perintah, sudah disiapkan sejak 15 September).
- Commit terakhir (`c53f7c4`, percepatan rekap 20 September) belum di-push. Bilang kalau mau saya push sekarang.
