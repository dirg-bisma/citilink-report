# Implementasi Pengaitan Pengguna dengan Group Privilege (RBAC)

**Sistem:** CITILINK AVIOR (Aviation Operations Report)  
**Tanggal:** 04 Oktober 2026  
**Status:** Selesai Diimplementasikan & Teruji  
**Referensi:** PRD §3.5 (Modul User Management), TechDesign §6 (Security), TraceabilityMatrix REQ-05

---

## 1. Latar Belakang & Tujuan

Sebelum implementasi ini, sistem belum memiliki grup peran (roles) baku di database, antarmuka `UserAdmin` tidak menampilkan peran pengguna, dan seluruh pengguna staff memiliki akses tidak terbatas ke halaman Upload Data serta dapat menghapus file sumber.

Fitur ini mengimplementasikan **Role-Based Access Control (RBAC)** menyeluruh yang mengaitkan setiap pengguna (`User`) ke peran tertentu (`Group`) dengan hak akses operasional (`Permission`) yang terisolasi dengan aman.

---

## 2. Matriks Peran & Hak Akses (RBAC Matrix)

| Modul / Tindakan | Super Administrator | Station Manager | Operator | Management Viewer |
|---|:---:|:---:|:---:|:---:|
| **Dashboard OTP & Visualisasi** | Akses Penuh | Akses Penuh | Akses Penuh | Akses Penuh |
| **Lihat Jadwal & Status Operasi** | Akses Penuh | Akses Penuh | Akses Penuh | Akses Penuh |
| **Download Laporan Realisasi & Rekap** | Ya | Ya | Ya | Ya |
| **Unggah File Acuan (WTT, PPRP, GHP)** | Ya | Ya | Ya | ❌ Dibatasi |
| **Hapus File Acuan (SourceFile)** | Ya | Ya | ❌ Dibatasi | ❌ Dibatasi |
| **Sinkronisasi Ulang Jadwal (Resync)** | Ya | Ya | ❌ Dibatasi | ❌ Dibatasi |
| **Buat / Ubah Proyek Penerbangan** | Ya | Ya | ❌ Dibatasi | ❌ Dibatasi |
| **Kelola Akun Pengguna (Staff)** | Akses Penuh | Lihat & Ubah | ❌ Dibatasi | ❌ Dibatasi |
| **Kelola Grup & Hak Akses** | Akses Penuh | Lihat Saja | ❌ Dibatasi | ❌ Dibatasi |

---

## 3. Komponen yang Diimplementasikan

### 3.1. Management Command: `setup_roles`
* **Lokasi:** `core/management/commands/setup_roles.py`
* **Fungsi:** Menginisialisasi 3 grup peran default (`Station Manager`, `Operator`, `Management Viewer`) beserta pemetaan permission terkait secara otomatis dan idempoten.
* **Perintah Eksekusi:**
  ```bash
  python manage.py setup_roles
  ```

### 3.2. Penyempurnaan Django Unfold Admin (`core/admin.py`)
1. **`UserAdmin`**:
   - Kolom `display_roles`: Menampilkan badge pill peran pengguna dengan warna khas (Hijau Citilink untuk *Station Manager*, Biru untuk *Operator*, Abu-abu untuk *Viewer*, Emas/Amber untuk *Super Admin*, dan Merah untuk akun *Tanpa Role*).
   - Filter `list_filter`: Memungkinkan penyaringan daftar pengguna berdasarkan `groups`, `is_staff`, `is_active`, dan `is_superuser`.
   - Admin Actions: Menambahkan aksi cepat massal untuk menetapkan pengguna sebagai *Operator*, *Station Manager*, atau *Management Viewer*.
2. **`GroupAdmin`**:
   - Kolom `display_user_count`: Menampilkan jumlah pengguna aktif dalam masing-masing grup.
   - Kolom `display_permissions_summary`: Menampilkan ringkasan jumlah permission operasional vs administrasi.
   - Filter `formfield_for_manytomany`: Menyaring daftar pilihan permission saat mengedit grup sehingga hanya menampilkan model bisnis (`core` dan `auth`), menyingkirkan puluhan permission internal sistem Django (`contenttypes`, `sessions`, `admin`).
3. **Admin Actions & Views (`ProjectAdmin` & `SourceFileAdmin`)**:
   - `upload_pprp_view`: Memvalidasi hak akses `core.add_sourcefile`.
   - `download_report` & `download_rekap_view`: Memvalidasi hak akses `core.view_project`.
   - `resync_months`: Memvalidasi hak akses `core.change_sourcefile`.

### 3.3. Penegakan Hak Akses di Controller (`core/views.py`)
* Pada fungsi `upload_source_file_view`:
  - Akses halaman: Membutuhkan izin `core.view_sourcefile` atau `core.add_sourcefile`.
  - Aksi unggah: Memvalidasi `request.user.has_perm('core.add_sourcefile')`. Jika tidak memiliki hak, kembalikan HTTP 403 Forbidden.
  - Aksi hapus (`action == 'delete'`): Memvalidasi `request.user.has_perm('core.delete_sourcefile')`. Pengguna biasa/operator tidak dapat menghapus file acuan.

### 3.4. Dinamisasi Sidebar Navigasi Unfold (`config/settings.py`)
* Menambahkan callback `permission` pada konfigurasi `UNFOLD["SIDEBAR"]["navigation"]`:
  - Menu **Upload Data**: Hanya tampil jika pengguna memiliki hak `core.add_sourcefile`.
  - Menu **Pengguna & Grup (Administrasi)**: Hanya tampil jika pengguna memiliki hak `auth.view_user` / `auth.view_group`.
  - Menu **Report & Jadwal**: Tampil bagi pengguna dengan hak view data.

---

## 4. Prosedur Operasional & Deployment ke VPS

Saat melakukan deployment ke server VPS baru:
1. Jalankan migrasi database:
   ```bash
   python manage.py migrate
   ```
2. Jalankan seeder roles:
   ```bash
   python manage.py setup_roles
   ```
3. Buat akun superuser utama:
   ```bash
   python manage.py createsuperuser
   ```
4. Masuk ke panel admin (`/admin/`) -> menu **Pengguna**:
   - Buat akun staf baru (centang `Staff status`).
   - Pilih peran pengguna di kolom **Groups** (atau gunakan aksi massal di tabel daftar pengguna).

---

## 5. Pengujian & Verifikasi

Pengujian otomatis telah dibuat pada file `tests/test_rbac.py` dengan cakupan:
* `test_setup_roles_assigns_correct_permissions`: Memastikan seluruh role dan permission terdaftar dengan presisi.
* `test_operator_cannot_delete_source_file`: Memastikan Operator ditolak (HTTP 403) saat mencoba menghapus file sumber.
* `test_viewer_cannot_upload_file`: Memastikan Viewer ditolak (HTTP 403) saat mencoba mengunggah file.
* `test_station_manager_can_attempt_delete`: Memastikan Station Manager memiliki izin untuk mengeksekusi penghapusan.
* `test_user_admin_display_roles`: Memvalidasi render badge visual role pada antarmuka admin.
* `test_group_admin_display_and_filter`: Memvalidasi badge counter pengguna dan pembersihan opsi privilege.
