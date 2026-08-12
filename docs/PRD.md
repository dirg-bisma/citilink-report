# Product Requirements Document (PRD)
**Project Name:** Automated Flight Schedule Reporting System
**Version:** 1.1
**Date:** 2026-08-08

## 1. Product Overview
Produk ini adalah aplikasi berbasis Web (menggunakan backend Python) yang dirancang untuk mengotomatisasi pengisian laporan pengajuan perencanaan perubahan penerbangan. Aplikasi ini akan digunakan oleh Station Manager dan tim Operator/Staf yang ditunjuk untuk mengurangi beban kerja manual dan *human error*.

## 2. Target Audience (Pengguna)
- **Operator / Station Manager:** Pengguna utama yang akan mengunggah file acuan, meninjau (*preview*) data, dan mengunduh laporan.
- **Admin / IT:** Pengguna yang memiliki hak akses untuk mengelola akun (User Management).
- **Manajemen:** Pengguna yang mungkin mengakses dasbor (*dashboard*) untuk melihat ringkasan data atau visualisasi chart.

## 3. Product Scope & Modules (Minimum Viable Product - MVP)
Aplikasi Web ini harus memiliki 5 modul utama berikut:

### 3.1. Modul Autentikasi (Login & Logout)
- Halaman login mandiri yang membutuhkan *Username* dan *Password*.
- Tombol **Logout** yang jelas untuk mengakhiri sesi pengguna dengan aman.

### 3.2. Modul Dashboard
- Halaman beranda setelah pengguna berhasil login.
- Untuk dashboard, nilai STD dan ATD diambil dari GHP. Aturan ini hanya berlaku untuk penyajian dashboard dan tidak mengubah aturan final report.
- Menampilkan visualisasi data (Chart/Grafik) dengan metrik sebagai berikut:
  1. **Pencapaian PPRP**
     - Selisih ATD terhadap STD lebih dari 45 menit: `0%`.
     - Selisih ATD terhadap STD kurang dari atau sama dengan 45 menit: `100%`.
     - Nilai diagregasikan per flight dalam satu bulan.
  2. **Pencapaian OTP (On Time Performance)**
     - Selisih ATD terhadap STD lebih dari 1 menit dihitung sebagai delay.
     - Delay dikaitkan dengan delay code dari GHP jika tersedia.
  3. **Faktor Terbesar Delay** (berdasarkan Delay Code)
     - Diambil dari frekuensi delay code pada GHP.
  4. **Delay Terbanyak** (berdasarkan jam di setiap harinya)

### 3.3. Modul Manajemen File (Upload)
- Fitur bagi pengguna untuk mengunggah 4 file referensi sistem:
  1. Data Master (Misal: data GHP Excel).
  2. Template Laporan (Misal: `form_realisasi_winter26.xlsx`).
  3. File PPRP (PDF).
  4. File WTT (PDF).
- Validasi sederhana untuk memastikan ekstensi file sesuai (PDF untuk PPRP/WTT, Excel untuk Data Master/Template).

### 3.4. Modul Report Extractor (Core)
- **Data Processing:** Mesin utama (di *backend* Python) yang membaca dan mengekstrak data dari ke-4 file yang diunggah.
- **Data Preview:** Setelah proses ekstraksi berhasil, sistem **tidak** langsung mengunduh (*auto-download*) file. Sistem akan menampilkan tabel pratinjau (*preview*) berisi rangkuman data yang telah ditarik.
- **Action Buttons:** Terdapat tombol **Download** bagi pengguna untuk menyimpan hasil akhir dalam bentuk Excel jika *preview* dirasa sudah akurat.

### 3.5. Modul User Management
- Sistem pembagian hak akses (*User Privilege/Role-Based Access Control*), di mana fungsi manajemen *user* hanya bisa diakses oleh level Admin/Station Manager.
- Fitur *Create, Read, Update, Delete* (CRUD) akun pengguna.
- Fitur untuk **Menonaktifkan Sementara (Suspend)** akun pengguna tertentu.

## 4. Metrics & Success Criteria
- **Waktu Eksekusi:** Waktu yang dibutuhkan dari proses *upload* hingga *preview* muncul tidak boleh memakan waktu yang lama (misal: di bawah 1 menit).
- **Akurasi Data:** 100% data yang di-ekstrak harus cocok dengan dokumen sumber dan tertuang pada kolom Excel template yang tepat.
- **User Adoption:** Operator berhasil menggunakan sistem tanpa harus meminta bantuan tim IT untuk pembuatan setiap laporan.

## 5. Assumptions (Asumsi Product)
- [ASSUMPTION] Lingkungan (*environment*) sistem menggunakan Python (misal: Flask/Django/FastAPI) untuk *backend* web, dan HTML/JS standar untuk *frontend*.
- [ASSUMPTION] Aplikasi akan di-*host* di server internal/lokal (*on-premise*) perusahaan karena menyangkut data sensitif operasional maskapai.

## 6. Out of Scope (Di Luar Cakupan)
- Otomatisasi pengiriman email laporan langsung ke Otoritas Bandara (Sistem saat ini hanya batas *download* Excel, operator yang akan mengirimkannya sendiri).
