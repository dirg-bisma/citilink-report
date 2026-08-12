# Business Requirements Document (BRD)
**Project Name:** Automated Flight Schedule Reporting System
**Version:** 1.1
**Date:** 2026-08-07

## 1. Executive Summary
Sistem ini bertujuan untuk mengotomatisasi proses pembuatan laporan pengajuan perencanaan perubahan jadwal penerbangan kepada otoritas bandara selaku regulator penerbangan. Laporan ini merupakan syarat operasional maskapai yang krusial. Ketiga file masukan (GHP, PPRP, WTT) akan berfungsi sebagai acuan murni untuk pengisian data ke file output akhir.

## 2. Business Problem (Latar Belakang & Masalah)
Saat ini, penyusunan laporan pengajuan perencanaan perubahan penerbangan dilakukan secara manual. 
Permasalahan utama dari proses manual ini adalah:
- **Inefisiensi Waktu:** Membutuhkan waktu yang sangat lama untuk menyalin dan mencocokkan data dari berbagai sumber dokumen (Excel dan PDF).
- **Human Error:** Sangat rentan terjadi *miss data* (kesalahan ketik, data terlewat) saat proses input data secara manual.
- **Risiko Kepatuhan (Compliance):** Kesalahan data dalam laporan kepada regulator (Otoritas Bandara) dapat berdampak negatif pada kelancaran operasional penerbangan.

## 3. Business Objectives (Tujuan Bisnis)
- **Efisiensi:** Mempercepat proses pembuatan laporan.
- **Akurasi Data:** Mengeliminasi *human error* dengan menarik data langsung dari sumber asli ke laporan tujuan.
- **Otomatisasi & Validasi:** Memastikan integritas data melalui validasi otomatis saat penggabungan dari dokumen referensi.

## 4. Stakeholders & Pengguna (Aktor)
- **Operator (Staf/Station Manager):** Pengguna utama (yang ditunjuk oleh Station Manager) yang bertugas memproses data. Tidak ada sistem *approval* bertingkat; operator berwenang untuk langsung mengunggah 3 file acuan dan men-generate output *form_realisasi_winter26.xlsx*.
- **Manajemen (Manager Operational, Manager Service, Assman, dll.):** Level manajerial, yang meskipun tidak melakukan *approval* di sistem, tetap berkepentingan terhadap kelancaran operasional.
- **Otoritas Bandara (Eksternal):** Regulator penerbangan selaku pihak penerima output laporan akhir.

## 5. High-Level Requirements (Kebutuhan Bisnis Utama)
- **HLR-01:** Sistem harus dapat menerima file `GHP (Excel)`, `PPRP (PDF)`, dan `WTT (PDF)` sebagai sumber acuan data.
- **HLR-02:** Sistem harus mengekstrak data dari ketiga file tersebut secara otomatis.
- **HLR-03:** Sistem harus memiliki mekanisme validasi untuk memastikan kecocokan antar data acuan tersebut.
- **HLR-04:** Sistem harus menyusun dan menghasilkan (*generate*) *output* berupa file `form_realisasi_winter26.xlsx` yang datanya murni mengacu pada gabungan dari ketiga file sumber tersebut.
- **HLR-05:** Sistem harus mudah digunakan dan dapat langsung men-generate laporan akhir tanpa prosedur birokrasi *approval* tambahan di dalam aplikasinya.

## 6. Assumptions (Asumsi)
- [ASSUMPTION] Format dari file sumber (GHP, PPRP, WTT) memiliki struktur tabel yang konsisten saat ini sehingga program dapat mengekstrak datanya.
- [ASSUMPTION] File template output `form_realisasi_winter26.xlsx` adalah format baku (rigid) dari otoritas bandara yang tidak boleh diubah susunan kolomnya.

## 7. Open Questions (Pertanyaan Terbuka)
- [OPEN QUESTION] Seperti apa spesifikasi pasti terkait "validasi" yang diharapkan sistem (misal: membandingkan *flight number* atau *time* di antara ketiga file)? *(Akan dibahas dan dijabarkan pada tahap FSD - Functional Specification Document)*.

## 8. Risks (Risiko)
- **Accepted Risk:** Jika struktur atau *layout* file referensi PDF berubah di masa depan, algoritma ekstraksi data sistem mungkin perlu diperbarui. Tim bisnis (user) telah menyadari risiko ini dan akan berdiskusi lebih lanjut bila ada perubahan format di kemudian hari (saat ini format dianggap tetap).
