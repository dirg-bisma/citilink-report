# Audit Keamanan (read-only)

**Project:** CITILINK AVIOR
**Date:** 2026-09-15
**Status:** Temuan tersimpan, **belum ada yang diperbaiki**. Ditunda atas permintaan pemilik ("next saja").
**Cakupan yang dibaca:** `config/settings.py`, `config/urls.py`, `core/views.py`, `core/admin.py`, `core/ingest.py`,
`core/services.py`, JS di template admin, `Dockerfile`, `docker-compose.yml`, `nginx/conf.d/app.conf`, `.gitignore`,
riwayat git. Isi `.env` tidak dibaca.

Kesimpulan: bukan celah kode klasik (ORM dipakai konsisten, CSRF aktif di semua POST, jenis file dicek dari isinya).
Kerentanannya di **konfigurasi dan hak akses**.

## Dua pertanyaan yang harus dijawab pemilik dulu

1. Repo GitHub `dirg-bisma/citilink-report` dan `yogidirgantara/Citilink-report-V3` — publik atau privat?
   Kalau publik, `docs/Source/` (surat PPRP asli, WTT, GHP) sudah terbuka untuk umum — lebih besar dari semua poin di bawah.
2. Cara pakai: hanya PC pemilik, jaringan kantor, atau internet? Poin 1, 2, 5 baru berbahaya bila bukan lokal.

## Temuan (urut prioritas)

| # | Tingkat | Di mana | Masalah | Perbaikan |
|---|---|---|---|---|
| 1 | **Tinggi** (bila Docker) | `nginx/conf.d/app.conf` `location /media/`; compose port `8080:80` | Semua file upload (PPRP/WTT/GHP) di `media/uploads/` disajikan nginx **tanpa login**, dengan nama asli yang mudah ditebak. Tidak aktif saat `runserver` lokal. | Hapus blok `/media/` di nginx; tidak ada fitur yang butuh URL media. |
| 2 | **Tinggi** (bila `.env` tak lengkap) | `settings.py:27-30` | `DEBUG` default `True`; `SECRET_KEY` punya default `django-insecure-…` yang ada di repo. `.env.example` juga `DEBUG=True`. | `DEBUG` default `False`; `SECRET_KEY` wajib dari env (gagal start bila kosong). |
| 3 | Sedang | `views.py` `@staff_member_required`; semua URL custom `admin.py` via `admin_view` | Hanya cek `is_staff`. Staf tanpa izin model apa pun tetap bisa upload/ganti/**hapus** WTT/PPRP/GHP + data turunan, unduh laporan. Halaman Pengguna/Grup tidak berpengaruh ke fitur inti. | Cek `core.add/delete_sourcefile`, `core.view_project` per view; minimal hapus/replace hanya superuser. |
| 4 | Sedang-rendah | `models.py:11` `Project.template_path` (bisa diedit di admin) → `report.py:797` `load_workbook` → `download_report` | Staf bisa mengarahkan ke `.xlsx` lain di server lalu mengunduh isinya. | `template_path` read-only / dihapus; selalu pakai `static/tpl/form_realisasi_winter26.xlsx`. |
| 5 | Sedang (bila di jaringan) | `settings.py` tanpa `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_*`, `SECURE_PROXY_SSL_HEADER`; nginx `listen 80`; tanpa pembatas login | Password/cookie lewat HTTP polos; `/admin/login/` bisa brute-force tanpa batas. | HTTPS di proxy, aktifkan `SECURE_*`, tambah `django-axes`. |
| 6 | Rendah | `JsonResponse({'message': str(e)})` di `views.py` (3×), `admin.py` (upload PPRP, detail JSON) | Exception mentah (path server, pesan MySQL) sampai ke browser staf. | Log di server, pesan umum ke klien. |
| 7 | Rendah (ketersediaan) | `admin.py` `download_report`, `download_rekap_view`: `NamedTemporaryFile(delete=False)` | File `.xlsx` sementara tidak pernah dihapus → disk penuh lama-lama. | Hapus setelah dikirim (`FileResponse` + cleanup) atau pakai `BytesIO`. |
| 8 | Rendah | `custom_upload.html`: `showNotification(..., message)` via `innerHTML`; nama file di riwayat | Nama file dipilih pengupload sendiri → paling jauh self-XSS. `onclick` modal hapus sudah `escapejs` (commit `04ea932`). | Pakai `escapeHtml()` yang sudah ada untuk pesan error. |

## Yang sudah benar

CSRF aktif; ORM di semua query; password validator aktif; `.env`, `db.sqlite3`, `media/`, `backups/`, `*.sql`
di-ignore dan tidak pernah masuk riwayat git; jenis dokumen dideteksi dari isi; MySQL di Docker tidak diekspos ke
host; nginx `client_max_body_size 20M`; dependensi dipinned (Django 6.1, pdfplumber 0.11.10, xlrd 2.0.2,
openpyxl 3.1.5) — advisory CVE belum dicek daring.

## Catatan lokal (bukan di repo, jangan sampai ter-commit)

`reset_pw.sql`, `db.sqlite3`, `prof*.txt`, `report_1.xlsx`, `backups/` ada di root kerja; semuanya sudah tercakup
`.gitignore`.
