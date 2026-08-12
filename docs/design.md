# System and Design Documentation
**Project:** Automated Flight Schedule Reporting System
**Date:** 2026-08-11

Dokumen ini merupakan rangkuman desain arsitektur, UI/UX, dan spesifikasi fungsional dari aplikasi Automated Flight Schedule Reporting System, yang disintesis dari dokumen BRD, PRD, FSD, Tech Design, Design System, dan Traceability Matrix.

## 1. Ikhtisar Sistem
Aplikasi ini adalah sistem berbasis web yang dirancang untuk mengotomatisasi proses pembuatan laporan pengajuan perencanaan perubahan jadwal penerbangan kepada otoritas bandara. Sistem ini mengekstrak dan memvalidasi data dari tiga file sumber (GHP, PPRP, WTT) dan menyuntikkannya ke dalam file template Excel baku (`form_realisasi_winter26.xlsx`).

*   **Tujuan Utama:** Meningkatkan efisiensi, mengeliminasi *human error*, dan memastikan kepatuhan regulasi operasional.
*   **Pengguna Utama:** Operator (Staf/Station Manager) dan Admin/Manajemen.

## 2. Arsitektur Sistem dan Teknologi
Sistem menggunakan arsitektur **Monolithic** berbasis Web.

*   **Backend Framework:** **Django (Python)**. Dipilih karena memiliki *built-in* Admin Panel, Auth System, dan ORM yang kuat.
*   **Database:** **MySQL**. Menangani transaksi data relasional.
*   **Frontend:** HTML5, CSS3, Vanilla JavaScript, dan Django Templates.
*   **Library Inti (Python):**
    *   `pandas` & `openpyxl`: Pemrosesan Excel (GHP dan Template Output).
    *   `pdfplumber` / `PyMuPDF (fitz)`: Pemrosesan teks dan tabel PDF (PPRP dan WTT).

### 2.1 Desain Database (High-Level)
*   **Tabel `Users` (Django Auth):** Menyimpan kredensial pengguna, status aktif/suspend, dan peran (Admin vs Operator).
*   **Tabel `UploadHistory`:** Menyimpan riwayat pengajuan, relasi ke operator (`uploaded_by`), waktu unggah, status, dan *file path* ke file referensi (GHP, Template, PPRP, WTT).

### 2.2 Penyimpanan File (File Storage)
Sistem tidak menyimpan blob file di dalam database. Semua file disimpan di **Local Server Storage** dengan pengorganisasian direktori berbasis tanggal: `/media/uploads/YYYY/MM/DD/`. Database hanya menyimpan alamat lokasi fisik (*path*) file.

## 3. Modul Aplikasi (Fungsionalitas)
Aplikasi memiliki 5 modul utama (MVP):

1.  **Modul Autentikasi:** Login berbasis sesi (Sistem bawaan Django) dan Logout.
2.  **Modul Dashboard:** Visualisasi metrik operasional berupa grafik (Pencapaian PPRP, Pencapaian OTP, Faktor Terbesar Delay, Jam Delay Terbanyak).
3.  **Modul Manajemen File (Upload):** Sistem unggah file berbasis *Stateful Project Mode*. Pengguna membuat *workspace* (Tahun, Bulan, ID) dan mengunggah Template, GHP, PPRP, dan WTT via modal *pop-up*.
4.  **Modul Report Extractor (Core):**
    *   Mengekstrak data dari file yang diunggah.
    *   **Aturan Sumber Data:** GHP hanya menentukan status operasi `1/0` pada final report; ATD/ATA final report bersumber dari WTT. Untuk dashboard, STD dan ATD serta delay code bersumber dari GHP.
    *   **Aturan Versi PPRP:** Perubahan PPRP membuat baris baru di bawah baris lama. Baris lama dan nilai harian `1/0` dipertahankan tanpa perubahan.
    *   **Data Preview:** Menampilkan hasil ekstraksi secara *real-time* (Auto-refresh) dalam bentuk tabel sebelum diunduh.
    *   **Generate & Download:** Menyuntikkan data *preview* ke Template Excel dan menyediakan tombol unduh. ATD/ATA yang ditulis ke final report mengikuti WTT.
5.  **Modul User Management:** Fitur CRUD dan Suspend pengguna (Hanya dapat diakses oleh Admin).

## 4. Design System dan Panduan UI/UX (Berbasis django-unfold)
Sistem UI akan memanfaatkan secara penuh kapabilitas **`django-unfold`**, yang mana merupakan tema admin Django modern berbasis Tailwind CSS. Antarmuka tidak akan dibangun dari nol, melainkan dengan mengkustomisasi ekosistem Django Admin menggunakan Unfold.

### 4.1 Konfigurasi Tema & Warna (`UNFOLD` Settings)
Identitas warna akan diatur melalui konfigurasi `UNFOLD = { "COLORS": { ... } }` pada `settings.py` dengan mengacu pada standar maskapai Citilink:
*   **Primary (`primary`):** Hijau Utama Citilink. Akan diaplikasikan secara otomatis oleh Unfold pada *active sidebar items*, tombol aksi utama (*Save*, *Upload*), dan *checkbox/radio*.
*   **Status Colors:** Memanfaatkan kelas bawaan Tailwind CSS di Unfold (seperti `bg-green-100` untuk sukses, `bg-yellow-100` untuk penanda perubahan PPRP atau data WTT yang perlu ditinjau, dan `bg-red-100` untuk *error*).
*   **Dark Mode:** `django-unfold` mendukung mode gelap secara *native*. Fitur ini dapat dibiarkan aktif atau dinonaktifkan di pengaturan `UNFOLD` sesuai preferensi operasional.

### 4.2 Tata Letak, Sidebar, & Custom Views
*   **Navigasi Sidebar (`UNFOLD["SIDEBAR"]`):** Menu akan dikonfigurasi melalui *settings* menggunakan *grouping* dan *custom icons* (misal: Material Symbols). Menu meliputi: Dashboard, Report Extractor, Riwayat Pengajuan, dan Manajemen Pengguna. Sidebar Unfold sudah mendukung fitur *collapsible* secara *default*.
*   **Custom Admin Views:** Halaman *Report Extractor* (Preview Data & Upload Modal) tidak menggunakan tampilan *form* bawaan, melainkan menggunakan kelas yang diturunkan dari **`unfold.admin.ModelAdmin`** dengan *custom template* atau *custom view*, sehingga memungkinkan injeksi JavaScript (AJAX/HTMX) untuk *auto-refresh* tabel tanpa memuat ulang (*reload*) halaman.
*   **Dashboard (`DASHBOARD_CALLBACK`):** Beranda akan dikustomisasi menggunakan fitur *Dashboard Callback* dari Unfold atau menimpa (*override*) `unfold/layouts/index.html` untuk menyisipkan *chart* dan metrik operasional (PPRP, OTP, Delay).

### 4.3 Tipografi dan Komponen Tabel
*   **Font:** Mempertahankan font *sans-serif* (Inter) bawaan `django-unfold` yang dirancang serasi dengan Tailwind CSS dan nyaman untuk membaca data tabular.
*   **Data Table:** Memanfaatkan komponen *changelist* bawaan Unfold yang sudah memiliki *styling* tabel modern (*border* halus, *hover state*, *sticky action bar*) untuk diimplementasikan pada *Preview Table* data ekstraksi.
