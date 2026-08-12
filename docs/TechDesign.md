# Technical Design Document
**Project:** Automated Flight Schedule Reporting System
**Version:** 1.0
**Date:** 2026-08-08

## 1. System Architecture Overview
Aplikasi ini dibangun menggunakan arsitektur *Monolithic* berbasis Web. Pendekatan ini dipilih karena memberikan kecepatan pengembangan dan kemudahan pemeliharaan (maintenance) untuk aplikasi internal perusahaan.

## 2. Technology Stack (Tumpukan Teknologi)
*   **Backend Framework:** **Django (Python)** 
    *   *Alasan:* Django sudah dilengkapi dengan *built-in Admin Panel*, *Authentication System* (Login/Logout), dan ORM (*Object-Relational Mapping*) yang sangat tangguh sehingga fitur *User Management* dapat dikembangkan dengan instan.
*   **Database:** **MySQL**
    *   *Alasan:* Relasional, stabil, dan mampu menangani transaksi data harian dalam skala perusahaan dengan baik.
*   **Frontend:** HTML5, CSS3, Vanilla JavaScript, dipadukan dengan *Django Templates*. (Penggunaan framework CSS seperti Bootstrap/Tailwind disarankan untuk mempercantik UI dengan cepat).

## 3. Core Libraries (Pustaka Inti Python)
Untuk menjalankan **Modul Report Extractor**, *backend* akan mengandalkan pustaka (library) berikut:
*   **`pandas`** & **`openpyxl`**: Untuk membaca Data Master (GHP) yang berbasis Excel, serta untuk "menulis/meng-inject" data akhir ke dalam *Template Output* Excel.
*   **`pdfplumber`** atau **`PyMuPDF (fitz)`**: Pustaka khusus Python yang paling optimal untuk mengekstrak (parsing) tabel dan teks dari dalam dokumen PDF (PPRP dan WTT).

## 4. Database Schema (High-Level Design)
Sistem ini akan memiliki 2 entitas tabel utama di dalam MySQL:

### 4.1. Tabel `Users` (Ditangani oleh Django Auth)
Menyimpan kredensial pengguna.
*   `id` (PK)
*   `username`
*   `password` (Hashed)
*   `is_active` (Untuk fitur *Suspend User*)
*   `is_staff` / `role` (Untuk membedakan hak akses Admin vs Operator)

### 4.2. Tabel `UploadHistory` (Riwayat Pengajuan)
Untuk memenuhi syarat bisnis penyimpanan file permanen dan pelacakan historis.
*   `id` (PK)
*   `uploaded_by` (FK -> `Users.id`) - Melacak *Username* operator yang bertugas.
*   `uploaded_at` (Datetime) - Menyimpan Tanggal, Bulan, Tahun, dan Jam secara otomatis.
*   `master_data_file` (File Path/URL) - Lokasi file GHP di server.
*   `template_file` (File Path/URL) - Lokasi file Template di server.
*   `pprp_file` (File Path/URL) - Lokasi file PPRP di server.
*   `wtt_file` (File Path/URL) - Lokasi file WTT di server.
*   `status` (String) - (Misal: "Success", "Failed", "Pending").

## 5. File Storage Architecture (Penyimpanan File)
*   Semua file yang diunggah tidak akan disimpan di dalam database secara langsung, melainkan disimpan di **Sistem File Server (Local Storage)**.
*   File akan diorganisasikan ke dalam direktori berdasarkan tanggal (contoh pola direktori: `/media/uploads/YYYY/MM/DD/`).
*   Database MySQL (Tabel `UploadHistory`) hanya akan menyimpan *path* atau alamat lokasi fisik file tersebut, sehingga performa database tetap ringan dan cepat.

## 6. Security (Keamanan)
*   **Authentication:** Menggunakan *Session-based Authentication* bawaan Django.
*   **Authorization:** Menggunakan sistem *User Groups/Permissions* Django. Hanya *role* Admin/Station Manager yang dapat mengakses halaman *User Management*, sedangkan Operator hanya dapat mengakses halaman Upload, Preview, Dashboard, dan Riwayat.
