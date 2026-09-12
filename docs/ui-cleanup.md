# Perapian Antarmuka (UI Cleanup)

**Project:** Automated Flight Schedule Reporting System (CITILINK AVIOR)
**Date:** 2026-09-13
**Status:** Diterapkan untuk Langkah 0–5; halaman laporan resmi sengaja tidak disentuh.

## 1. Latar belakang

Tampilan admin terasa "hasil generate AI": tema gelap sendiri di dashboard, tombol berbentuk pil,
kartu melayang saat hover, label huruf kapital semua dengan `tracking-wider`, angka `font-weight: 800`,
ikon berwarna-warni di tiap judul, gradient di progress bar, dan efek blur di belakang modal.
Audiens layar ini sampai ke manajemen, sehingga arah yang dipilih: **seragam dengan tema `django-unfold`**,
ikut mode terang/gelap admin, tanpa efek dekoratif.

Tiga temuan teknis yang menjadi akar masalah:

1. **`static/css/unfold_override.css`** menimpa Unfold di semua halaman dengan `!important`
   (radius 16px untuk semua kartu, pil 20px untuk semua tombol, `translateY(-1px)` saat hover)
   dan mengimpor Inter dari Google Fonts padahal Unfold sudah membawanya secara lokal.
2. **Tangga warna `primary` di `config/settings.py` patah.** `50`–`500` dan `700`–`900` memakai hijau
   Tailwind, sedangkan `600` = `#006b32` (hijau Citilink). Akibatnya `700` lebih terang daripada `600`,
   kelas `primary-*` tidak bisa dipercaya, dan template menulis `style="background-color: #006b32"` manual
   di puluhan tempat.
3. **CSS Unfold adalah Tailwind yang sudah di-*purge*.** Hanya kelas yang dipakai template Unfold sendiri
   yang ada di `unfold/static/unfold/css/styles.css`. Ratusan kelas di template proyek
   (`text-gray-*`, `dark:bg-gray-*`, `rounded-xl`, `space-y-6`, `font-mono`, `font-black`, `text-[18px]`,
   `backdrop-blur-*`, `max-w-md`, …) **tidak berfungsi sama sekali** dan hanya menambah kebisingan.
   Mode gelap pun tidak bekerja di elemen-elemen itu karena `dark:text-gray-*` tidak ada.

## 2. Prinsip yang dipakai

- **Pakai kelas Unfold yang benar-benar ada.** Sebelum menulis kelas baru, pastikan ada di
  `styles.css` (lihat §6). Token teks: `text-font-important-light dark:text-font-important-dark`
  (judul/nilai), `text-font-default-light dark:text-font-default-dark` (isi), dan
  `text-font-subtle-light dark:text-font-subtle-dark` (label/keterangan).
- **Kartu** = `bg-white border border-base-200 rounded-default shadow-xs dark:bg-base-900 dark:border-base-800`
  (persis `unfold/components/card.html`). **Tombol** memakai kelas dari `unfold/components/button.html`
  (varian primary: `bg-primary-600 text-white hover:bg-primary-600/80`; varian default: `border-base-200 bg-white
  shadow-xs text-important …`). **Select** memakai `BASE_CLASSES` + `SELECT_CLASSES` dari `unfold/widgets.py`.
- **Satu warna aksen**: hijau Citilink lewat `primary-*`. Merah hanya untuk delay/gagal/hapus, oranye untuk
  peringatan, abu-abu (`base-*`) untuk sisanya. Tidak ada cyan/ungu/teal/kuning.
- **Tipografi**: judul `font-semibold`, label huruf biasa (bukan kapital), tidak ada `font-black`/`font-extrabold`/
  `tracking-wider`. Ukuran ikon Material memakai `text-base`/`text-lg`/`text-xl`/`text-2xl`, bukan `text-[Npx]`.
- **Tanpa efek**: tidak ada hover melayang, blur, gradient, `active:scale-*`, `hover:brightness-*`.
- **Logika tidak disentuh.** Semua `id` dan nama kelas yang dirujuk JavaScript dipertahankan
  (`.btn-upload`, `.file-input`, `.progress-area`, `.progress-bar-fill` + `.uploading/.parsing/.done/.error`,
  `.result-notification`, `.drop-zone`, `.step-overlay`, `.page-focus-blur`, `.empty-placeholder`, `.chart-box`,
  `.stitch-card/.stitch-label/.stitch-stamp`, semua `#st-*`, `#val*`, `#modal-*`). Yang berubah hanya
  nilai properti CSS di balik nama itu, dan string kelas Tailwind yang ditulis JS ke `className`/`innerHTML`
  (murni gaya, bukan alur).

## 3. Perubahan per file

### `config/settings.py`
- `UNFOLD["COLORS"]["primary"]` diganti satu tangga warna turunan `#006b32` (50 `#f0f8f3` → 950 `#002310`),
  monoton dari terang ke gelap, ditambah kunci `950` (sebelumnya jatuh ke default ungu Unfold lewat deep-merge).
- Ditambah bobot `UNFOLD["COLORS"]["base"]["350"]` = `oklch(79% .016 259.8)` untuk border input halaman login
  (lihat bagian "Halaman login" di §4).
- Cache-buster `unfold_override.css?v=2` → `?v=5` (dinaikkan tiap kali isi CSS berubah, supaya browser tidak
  memakai versi lama dari cache).

### `static/css/unfold_override.css`
- Semua override `!important` dan `@import` Google Fonts dibuang. Sidebar tidak perlu "ditambal" lagi.
- Isinya kini hanya utilitas yang ikut ter-purge dari Unfold: `.font-mono`, `.tabular-nums`, `.av-spinner`,
  `.av-overlay`, `.av-modal-sm`, dan `table td/th { font-variant-numeric: tabular-nums }`.
- Ditambah satu aturan border input halaman login (lihat bagian "Halaman login" di §4).

### `templates/admin/index.html` (Dashboard OTP)
- Blok gaya `.pbi-*` (tema gelap slate/cyan) dihapus; kartu KPI dan kartu chart memakai kelas kartu Unfold
  sehingga ikut tema terang/gelap admin.
- Header: ikon `flight_takeoff` dalam kotak cyan dan tagline *"AViation Operations Report • Real-Time Analytics"*
  dihapus; judul jadi "OTP Dashboard" dengan subjudul "Station A Class SUB".
- Selector project/tanggal memakai kelas select Unfold + ikon `expand_more`; kotak berbingkai "Tgl" dihapus.
- KPI: **susunan tetap 7 kartu sejajar** (`grid-cols-2 md:grid-cols-4 lg:grid-cols-7`). Label huruf biasa,
  angka `text-2xl font-semibold tabular-nums`; Delay merah, OTP Dep/Arr hijau `primary`, lainnya warna teks penting.
  Badge REG/CHRT jadi teks kecil biasa. Tidak ada hover melayang.
- Chart: ikon berwarna di judul dihapus. Palet Chart.js: `C_GREEN #006b32`, `C_GREEN_2 #4faa79`, `C_GREEN_3 #b8dfc7`,
  `C_GRAY #8b9299`, `C_GRAY_2 #c7ccd1`, `C_RED #dc2626`. Garis OTP hijau, garis target abu-abu putus-putus,
  batang jumlah penerbangan abu-abu transparan, durasi delay merah, donat IATA & PPRP keluarga hijau + abu-abu,
  distribusi rute hijau. `Chart.defaults.color` abu-abu menengah agar terbaca di kedua tema.
- JavaScript: **hanya nilai warna** yang diganti; fungsi, `id`, urutan render, dan panggilan API tidak berubah.
- **Border kartu dinaikkan** dari `border-base-200` ke `border-base-350` (21 tempat: kartu KPI, kartu chart,
  garis pemisah judul chart, garis bawah header, dropdown Project/Tgl) karena `base-200` (oklch 92.8%) terlalu
  samar di layar. Kelas `.border-base-350` **tidak ada** di CSS Unfold, jadi utilitasnya disediakan di
  `unfold_override.css`; menulis kelas itu tanpa menyediakannya akan diam-diam tidak berefek.
  Keputusan pemilik: **hanya dashboard**, halaman lain tetap `base-200`. Mode gelap (`dark:border-base-800`,
  18 tempat) belum diubah.

### `templates/admin/core/scheduleversion/change_list.html` (Rincian Penerbangan)
- **Susunan field tidak diubah.** Yang berubah hanya gaya.
- `.stitch-card/.stitch-label` memakai variabel Unfold (`--color-base-*`, `--color-font-subtle-*`, `--border-radius`).
- `.stitch-stamp` tidak lagi miring (`rotate(-3deg)` dihapus); jadi badge merah lurus.
- Judul seksi dan 18 label kartu dari HURUF KAPITAL ke kalimat biasa ("1. Informasi dasar penerbangan",
  "Nomor penerbangan", "STD (departure)", …). Teks status data (`ACTIVE`, `NO OPS`, `OPERATED`,
  "TERKONFIRMASI BEROPERASI …") **tidak diubah**.
- `font-black`/`font-extrabold uppercase` → `font-semibold`/`font-medium`; semua `text-gray-*`, `emerald`, `rose`,
  `slate`, `text-[Npx]`, `text-[#006b32]` dipetakan ke kelas Unfold; tombol "Tutup Formulir" memakai tombol primary
  Unfold; spinner memakai `.av-spinner`.
- Komentar `EXACT GOOGLE STITCH AI REPLICA` / `STITCH AI DESIGN` dihapus. Jarak antar seksi lewat aturan
  `#dt-content > div + div { margin-top: 1.5rem }` karena `space-y-6` tidak ada di CSS Unfold.

### `templates/admin/core/sourcefile/custom_upload.html` (Upload Data)
- 4 `linear-gradient` progress bar → warna solid (`--color-primary-600`, `--color-primary-400`, `--color-red-600`).
- `backdrop-filter: blur(4px)` pada `.step-overlay` dan `backdrop-blur-xs` pada modal dihapus; overlay modal memakai
  `.av-overlay`, kartu modal `.av-modal-sm`.
- Ikon `auto_awesome` di banner Auto-Detect → `calendar_month`; banner biru → abu-abu netral.
- Nomor langkah 1/2/3 tidak lagi biru/ungu/oranye, semuanya netral; badge "Mandatory"/"Optional" dan badge tipe/status
  di tabel riwayat dari pil ke sudut biasa dengan warna muted (WTT biru, PPRP hijau `primary`, GHP oranye;
  SUCCESS hijau, FAILED merah, PROCESSING oranye).
- Semua tombol (Upload, Skip, Atur Ulang, Refresh, Batal, Ya Ganti, Ya Hapus) memakai kelas tombol Unfold;
  `style="background-color: #006b32"` di markup dihapus. Dua baris JS `step.btn.style.backgroundColor/color`
  di fungsi reset **dibiarkan** (nilainya sama dengan `primary-600`).
- Tabel riwayat: `divide-y` (tidak ada) diganti `border-b` per baris; header huruf biasa.

### `templates/admin/core/project/change_list.html` (Modal PPRP & Unduh Rekap)
- `filter: blur(8px) grayscale(10%)` pada halaman di belakang modal dan `backdrop-filter: blur(10px)` dihapus.
  `.page-focus-blur` tetap ada (dirujuk JS) tetapi kini hanya mengunci klik (`pointer-events: none`).
- Kartu modal `rounded-2xl shadow-2xl` → kartu Unfold + `shadow-lg`; tombol Batal/Upload/Download Rekap memakai
  tombol Unfold; ikon kotak hijau `#d1fae5` → `bg-primary-50`; progress bar memakai `bg-primary-600`.
- Tombol "Hapus Terpilih" yang dibuat JS: string kelasnya (±40 kelas termasuk `group-hover:scale-110`) diganti
  tombol outline merah sederhana. Komentar "desain premium" dihapus.

### Halaman login

Halaman login tidak punya template override di proyek — yang tampil adalah `admin/login.html` bawaan Unfold.
Satu-satunya keluhan nyata: kotak input Username/Password nyaris tak terlihat sebelum diklik, karena
`BASE_INPUT_CLASSES` memakai `border-base-200` (oklch 92.8%, praktis menyatu dengan latar putih).

- Perbaikannya lewat **warna**, bukan menebalkan garis: `1px` dipertahankan supaya tidak berat dibanding tombol
  dan kartu; yang dinaikkan adalah kekontrasan.
- `base-300` masih tipis, `base-400` terlalu tegas, jadi didaftarkan bobot baru **`base-350`** =
  `oklch(79% .016 259.8)` (titik tengah 300 dan 400) di `UNFOLD["COLORS"]["base"]`. Unfold membangkitkan
  `--color-<nama>-<bobot>` dari tiap kunci di `COLORS` (`unfold/layouts/skeleton.html:71-75`), dan deep-merge
  hanya menimpa kunci yang disebut, sehingga bobot `base` lainnya tetap bawaan Unfold.
- Aturannya di `unfold_override.css`, dibatasi `body.login` (kelas itu dipasang Unfold di layout
  `unauthenticated.html`). Mode gelap ikut dinaikkan dari `base-700` ke `base-600`.
- Tanpa `!important`: `input[type="text"]` (0,1,1) sudah mengalahkan `.border-base-200` (0,1,0).
- Gaya fokus hijau bawaan Unfold tidak disentuh.
- **Tombol "Return to site" dihilangkan** lewat `UNFOLD["SITE_URL"] = None`. Aplikasi ini tidak punya situs
  publik di luar admin: `config/urls.py:7` hanya me-redirect `/` ke `/admin/`, dan bagi pengunjung yang belum
  login `/admin/` memantul balik ke `/admin/login/` — jadi tombol itu berputar ke halaman login itu sendiri
  (`GET /` → 302 `/admin/` → 302 `/admin/login/`). Template Unfold membungkusnya dengan `{% if site_url %}`
  sehingga `None` cukup untuk menyembunyikannya; sakelar tema di pojok kanan atas tetap ada, dan tidak ada
  rute atau logika yang berubah.

**Catatan:** border tipis yang sama masih berlaku di seluruh form admin lain (kotak pencarian, select di halaman
Upload, form Projects). Sengaja dibiarkan karena keluhannya khusus halaman login; untuk menyeragamkan, cukup
hapus `body.login` dari selektornya.

### Animasi buka/tutup sidebar

`templates/admin/nav_sidebar.html` adalah **satu-satunya template Unfold yang disalin ke proyek**. Alasannya:
Unfold memakai `x-show="sidebarOpen"` pada pembungkus sidebar, dan `x-show` milik Alpine hanya menyetel
`display:none` — tidak ada tahap animasi, sehingga sidebar lenyap seketika dan area konten melompat melebar.
Tidak ada jalan lain lewat CSS saja: elemen yang `display:none` tidak bisa ditransisikan lebarnya.

- `x-show` diganti kelas `av-sidebar--closed`; lebar dianimasikan lewat CSS di `unfold_override.css`
  (`width` 0.24s pada pembungkus, `transform: translateX(-100%)` pada `#nav-sidebar` yang posisinya `fixed`
  sehingga tidak ikut terpotong lebar induknya).
- **Jebakan `sidebarOpen`:** di `unfold/js/app.js` ia dideklarasikan sebagai *method*, lalu diganti menjadi
  boolean oleh `sidebarToggle()`. Alpine memanggil method itu bila ekspresinya berdiri sendiri (seperti
  `x-show="sidebarOpen"`), tetapi TIDAK bila dipakai di tengah ekspresi lain. Karena itu binding di template
  memakai `typeof sidebarOpen === 'function' ? sidebarOpen() : sidebarOpen`. Tanpa itu, sidebar selalu dianggap
  terbuka saat halaman pertama dimuat meski pengguna terakhir menutupnya.
- Transisi dimatikan saat lebar sidebar sedang ditarik dengan mouse (`av-sidebar--instant`), dan saat
  `prefers-reduced-motion: reduce`.
- `visibility: hidden` ditunda 0.24s supaya menu yang tersembunyi tidak bisa dijangkau tab/pembaca layar,
  tanpa memotong animasinya.

**Konsekuensi yang perlu diingat:** salinan ini membeku pada versi Unfold saat ini. Isi menunya sendiri masih
diambil dari `unfold/helpers/navigation.html`, jadi yang membeku hanya kerangka pembungkus (±15 baris). Bila
Unfold diperbarui dan mengubah struktur `nav_sidebar.html`, bandingkan ulang dengan berkas aslinya.

**Verifikasi:** `element.getAnimations()` di headless Chrome menunjukkan `CSSTransition` aktif — `width` 240ms
pada pembungkus dan `transform` 240ms pada `#nav-sidebar` — serta tangkapan layar sebelum/sesudah membuktikan
konten melebar penuh saat sidebar ditutup. Catatan untuk pengujian berikutnya: panel Browser di lingkungan ini
berjalan dengan `document.hidden === true`, dan browser menghentikan transisi CSS pada tab tersembunyi, sehingga
pengukuran lebar lewat panel itu tidak sahih.

## 4. Yang sengaja tidak diubah

- **`report_view.html`** — format dokumen resmi (kop surat PPRP). Tidak disentuh sama sekali.
- **`report_loading.html`** — layar tunggu yang gayanya mengikuti `report_view`; ikut dikunci supaya transisinya
  tetap serasi.
- **Tata letak KPI dashboard** — dua opsi dibuat mockup-nya (A: 7 sejajar, B: OTP Dep/Arr jadi dua kartu
  besar). **Keputusan pemilik (2026-09-13): Opsi A** — susunan lama dipertahankan, hanya gaya yang berubah.
- **Teks status domain** (`NO OPS`, `OPERATED`, `ACTIVE`, "NILAI 1 DI FORM LAPORAN", "Mandatory", "Optional",
  "Upload History", "Auto-Detect Periode") — dibiarkan apa adanya.
- ~~`templates/admin/core/project/dashboard_view.html` dan `login.html` (root)~~ — **dihapus 2026-09-13** atas
  persetujuan pemilik. Yang pertama template dashboard lama yang tidak dirujuk kode mana pun dan memuat Tailwind
  dari CDN; yang kedua hasil *Save Page As* (UTF-16, tidak pernah dilacak git) yang memuat token CSRF basi.
- Baris JS yang menyetel warna lewat `style.*` (`#006b32`) di Upload dan modal Unduh Rekap — dibiarkan karena
  nilainya identik dengan `primary-600`.

## 5. Verifikasi

- `manage.py check`: tidak ada masalah.
- `manage.py test`: **Ran 55 tests — OK** (exit code 0, ±13 menit karena DB uji MySQL dan parsing PDF).
- Tangkapan layar headless Chrome 1400px (terang & gelap) untuk dashboard, kartu rincian penerbangan, upload,
  modal hapus file, dan modal PPRP: tata letak, tombol, badge, dan mode gelap sesuai gaya Unfold.
- Skrip render (Django test client, DB uji sementara, superuser sementara) memuat `/admin/`,
  `/admin/core/scheduleversion/`, `/admin/upload-data/`, `/admin/core/project/`: semua HTTP 200, penanda gaya
  lama (`pbi-`, `Real-Time`, `STITCH`, `rotate(-3deg)`, `auto_awesome`, `linear-gradient`, `backdrop-filter`,
  `blur(`, `rounded-2xl`, `shadow-2xl`) tidak ada lagi, `unfold_override.css?v=3` termuat di `<head>`.
- Pemeriksaan visual yang masih perlu dilakukan di browser: mode gelap (toggle di header Unfold), dashboard dengan
  project berisi data (warna chart), alur upload WTT→PPRP→GHP (progress bar tiga fase), modal PPRP dan modal
  Unduh Rekap, kartu rincian penerbangan untuk flight *operated* dan *no ops*.

## 6. Panduan ke depan

- **Jangan menambah `!important` di `unfold_override.css`.** File itu hanya untuk utilitas yang memang tidak
  dikirim Unfold.
- **Jangan menulis `#006b32` di template.** Pakai `bg-primary-600`, `text-primary-600`, `border-primary-600`, atau
  `var(--color-primary-600)` di CSS.
- **Cek kelas sebelum dipakai.** Cara cepat (nama kelas di-escape seperti Tailwind: `:` → `\:`, `/` → `\/`,
  `[` → `\[`, `!` → `\!`):

  ```bash
  grep -c '\.dark\\:bg-base-900' venv/Lib/site-packages/unfold/static/unfold/css/styles.css
  ```

  Hasil `0` berarti kelas itu tidak ada dan tidak akan berefek apa pun.
- Kelas yang **tidak ada** dan sering tergoda dipakai: `text-gray-*`, `bg-gray-*`, `space-y-*` (pakai
  `flex flex-col gap-*`), `font-mono`/`tabular-nums` (ada di override), `text-[Npx]`, `max-w-md`/`max-w-lg`,
  `w-12`/`w-13`, `divide-y`, `list-disc`, `items-baseline`, `sr-only`, `scale-95`, `animate-pulse`,
  `backdrop-blur-*`, `bg-black/50`, `hover:brightness-*`, warna `emerald`/`rose`/`amber`/`purple`/`yellow`/`slate`/`cyan`.
- Komponen siap pakai Unfold yang bisa dipanggil dari template: `unfold/components/card.html`, `button.html`,
  `title.html`, `text.html`, `progress.html`, `table.html`, `chart/line.html`, `chart/bar.html`.
