# Design System & UI/UX Guidelines
**Project:** Automated Flight Schedule Reporting System
**Version:** 1.0
**Date:** 2026-08-08

## 1. UI/UX Framework Base
Antarmuka pengguna (UI) akan dibangun menggunakan **`django-unfold`**. 
Ini adalah keputusan arsitektur UI yang sangat cerdas karena `django-unfold` merupakan tema modern bergaya *Tailwind CSS* untuk antarmuka Django. Dengan `django-unfold`, kita akan mendapatkan *Dashboard*, *User Management*, dan form *Upload* berkelas *enterprise* secara nyaris otomatis tanpa harus mendesain komponen *frontend* dari nol.

## 2. Global Color Palette (Tema Warna)
Mengacu pada identitas warna maskapai (nuansa hijau Citilink), tema warna `django-unfold` akan di-kustomisasi (*override*) dengan spesifikasi berikut:
*   **Primary Color (Hijau Utama):** Digunakan untuk warna *Sidebar* (opsional), warna tombol utama (seperti tombol *Upload*, *Generate*, *Download*), dan tautan aktif.
*   **Secondary Color (Hijau Muda):** Digunakan untuk status komponen sukses, aksen *hover* pada menu, atau warna latar komponen *card* di Dashboard.
*   **Accent Color (Kuning):** Digunakan untuk status *Warning*, misalnya saat *Preview* menampilkan baris baru hasil perubahan PPRP, data WTT belum lengkap, atau terdapat perbedaan sumber yang perlu ditinjau. Baris histori PPRP dapat diberi penanda visual tanpa mengubah datanya.
*   **Neutral/Background:** Abu-abu sangat terang (hampir putih) untuk latar belakang halaman utama (*workspace*) agar data tabel mudah dibaca.

## 3. Layout & Navigation (Tata Letak)
*   **Navigasi Utama (Sidebar Kiri):** Menu navigasi akan menggunakan *Sidebar* di sebelah kiri yang memiliki kemampuan *Collapsible* (bisa dilipat/dipersempit menjadi ikon saja, atau dilebarkan). Ini memaksimalkan ruang layar (*real-estate*) saat operator sedang membaca tabel *Preview* yang panjang.
*   **Menu Item pada Sidebar:**
    1. 📊 Dashboard
    2. 📤 Upload & Generate (Report Extractor)
    3. 🕰️ Riwayat Pengajuan (History)
    4. 👥 Manajemen Pengguna (User Management - *khusus Admin*)
*   **Top Bar:** Hanya berisi *Breadcrumbs* (informasi posisi halaman saat ini), profil pengguna aktif, dan tombol **Logout**.

## 4. Typography & Komponen (Tipografi)
*   **Font:** Memanfaatkan font *sans-serif* bawaan Tailwind CSS (seperti *Inter* atau *Roboto*) yang sangat mudah dibaca untuk data angka/tabular.
*   **Data Table (Tabel Preview):** Menggunakan tabel modern dengan *border* tipis, *hover effect* pada setiap baris (baris berubah warna sedikit jika disorot mouse), dan *sticky-header* agar operator tidak kehilangan konteks nama kolom saat melakukan *scroll* ke bawah.
*   **Grafik/Chart:** *Dashboard* akan memanfaatkan komponen grafik yang kompatibel dengan `django-unfold` dengan warna batang grafik/garis menggunakan dominasi hijau dan hijau muda.
