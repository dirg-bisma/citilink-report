"""
Satu pintu untuk semua upload file sumber (WTT / PPRP / GHP).

Dipakai oleh halaman Upload Data (core.views) DAN tombol Upload PPRP di menu
Project (core.admin). Sebelumnya keduanya punya kode sendiri-sendiri dengan
perilaku berbeda: halaman Upload Data hanya memproses file PERTAMA dari
pilihan multi-file dan tetap melapor "Berhasil" (kasus QG356 hilang,
2026-09-02). Di sini aturannya satu dan berlaku untuk semua pintu:

- setiap file diproses sendiri-sendiri; satu file gagal/duplikat tidak
  membatalkan file lain dalam batch yang sama;
- hasil per file dilaporkan apa adanya: diproses / dilewati / gagal + alasan;
- file PPRP diterima bila bulan project berada di DALAM rentang berlaku surat
  (bukan sekadar cocok bulan mulainya), supaya satu surat lintas bulan bisa
  dimasukkan ke tiap project bulan yang dicakupnya;
- satu bulan hanya punya SATU file WTT dan SATU file GHP. File kedua yang
  berbeda isinya ditolak, kecuali pemanggil memberi replace=True (mode
  "Atur Ulang" di halaman Upload Data): file lama dihapus beserta data
  turunannya, file baru diproses, lalu bulan itu disusun ulang;
- setelah batch selesai, data turunan disinkronkan ulang (PPRP -> GHP,
  WTT -> PPRP -> GHP) supaya urutan upload tidak mengubah hasil akhir.
"""
import calendar
import os
from dataclasses import dataclass, field
from datetime import date

from django.core.files.storage import FileSystemStorage

from core.models import Project, SourceFile
from core.parsers.ghp import detect_ghp_period
from core.parsers.pprp import parse_pprp
from core.parsers.wtt import detect_wtt_period
from core.services import delete_source_file, process_ghp, process_pprp, process_wtt, _fmt_date_id

UPLOAD_DIR = os.path.join('media', 'uploads')

MONTH_NAMES = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
    5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
    9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember',
}

# Satuan angka hasil proses per jenis file (dipakai di pesan ke pengguna).
DETAIL_LABELS = {
    'WTT': 'jadwal penerbangan terbentuk',
    'PPRP': 'jadwal terdampak perubahan PPRP',
    'GHP': 'jadwal terverifikasi beroperasi',
}


def period_name(year, month) -> str:
    return f"{MONTH_NAMES.get(month, month)} {year}"


@dataclass
class FileResult:
    filename: str
    status: str                 # 'processed' | 'skipped' | 'failed'
    message: str
    count: int = 0
    warnings: list = field(default_factory=list)
    source_file_id: int | None = None
    replaced_filename: str | None = None   # nama file lama yang digantikan (mode Atur Ulang)

    def as_dict(self):
        return {
            'filename': self.filename,
            'status': self.status,
            'message': self.message,
            'count': self.count,
            'warnings': list(self.warnings),
            'source_file_id': self.source_file_id,
            'replaced_filename': self.replaced_filename,
        }


@dataclass
class IngestResult:
    file_type: str
    project: Project | None = None
    files: list = field(default_factory=list)
    resync_messages: list = field(default_factory=list)
    # Peringatan tingkat batch (hasil pencocokan ulang GHP setelah WTT/PPRP).
    warnings: list = field(default_factory=list)

    @property
    def processed(self):
        return [f for f in self.files if f.status == 'processed']

    @property
    def skipped(self):
        return [f for f in self.files if f.status == 'skipped']

    @property
    def failed(self):
        return [f for f in self.files if f.status == 'failed']

    @property
    def success(self) -> bool:
        return bool(self.processed)

    @property
    def total_count(self) -> int:
        return sum(f.count for f in self.processed)

    def summary_message(self) -> str:
        parts = []
        if self.processed:
            parts.append(f"{len(self.processed)} file {self.file_type} diproses "
                         f"({self.total_count} {DETAIL_LABELS[self.file_type]})")
        if self.skipped:
            parts.append(f"{len(self.skipped)} file dilewati karena sudah pernah diupload")
        if self.failed:
            parts.append(f"{len(self.failed)} file gagal")
        if not parts:
            return "Tidak ada file yang diproses."
        return '. '.join(parts) + '.'

    def as_dict(self):
        p = self.project
        return {
            'success': self.success,
            'message': self.summary_message(),
            'file_type': self.file_type,
            'detail': DETAIL_LABELS[self.file_type],
            'processed_count': self.total_count,
            'files_count': len(self.processed),
            'files': [f.as_dict() for f in self.files],
            'resync': list(self.resync_messages),
            'warnings': list(self.warnings),
            'project_id': p.id if p else None,
            'project_code': p.project_id if p else None,
            'period_name': period_name(p.year, p.month) if p else None,
        }


def ingest_uploaded_files(file_type, uploaded_files, user, project=None, upload_dir=None,
                          replace=False) -> IngestResult:
    """
    Simpan, validasi, daftarkan, dan proses setiap file yang diupload.

    project: wajib untuk PPRP/GHP bila pemanggil sudah tahu project-nya
             (tombol di menu Project). Bila None, project dicari dari isi
             file. Untuk WTT, project ditentukan (dibuat bila perlu) dari
             periode di dalam PDF; bila project diberikan, periodenya harus
             cocok (pengaman mode Atur Ulang).
    replace: izinkan file WTT/GHP menggantikan file sejenis yang sudah ada
             untuk bulan itu (file lama + data turunannya dihapus dulu).
    """
    if file_type not in DETAIL_LABELS:
        raise ValueError(f"Jenis file tidak dikenal: {file_type}")

    result = IngestResult(file_type=file_type, project=project)
    fs = FileSystemStorage(location=upload_dir or UPLOAD_DIR)
    touched_projects = []

    for uploaded in uploaded_files:
        fr, proj = _ingest_one(fs, file_type, uploaded, user, project, replace)
        result.files.append(fr)
        if fr.status == 'processed' and proj is not None:
            result.project = proj
            if proj not in touched_projects:
                touched_projects.append(proj)

    for proj in touched_projects:
        _resync_derived_data(result, proj)

    return result


def _ingest_one(fs, file_type, uploaded, user, project, replace):
    content = uploaded.read()
    file_hash = SourceFile.compute_hash(content)
    uploaded.seek(0)

    filename = fs.save(uploaded.name, uploaded)
    file_path = fs.path(filename)
    source_file = None
    try:
        pprp_data = parse_pprp(file_path) if file_type == 'PPRP' else None
        proj = _resolve_project(file_type, file_path, project, user, pprp_data)
        _validate_period(file_type, file_path, proj, pprp_data)

        # Di mode Atur Ulang, cek duplikat TIDAK boleh menghalangi: mengupload
        # ulang file WTT/GHP yang sama persis justru cara pengguna membangun
        # ulang bulan itu. Di luar mode itu, duplikat tetap dilewati.
        is_rebuild = replace and file_type in ('WTT', 'GHP')
        same_file_exists = SourceFile.objects.filter(
            project=proj, file_type=file_type, file_hash=file_hash).exists()
        if same_file_exists and not is_rebuild:
            _remove_file(file_path)
            hint = (" Klik Atur Ulang, pilih bulan ini, lalu upload lagi untuk membangun ulang."
                    if file_type in ('WTT', 'GHP') else "")
            return FileResult(uploaded.name, 'skipped',
                              f"Sudah pernah diupload untuk {period_name(proj.year, proj.month)}.{hint}"), proj

        replaced = _replace_existing_if_allowed(file_type, proj, replace)

        source_file = SourceFile.objects.create(
            project=proj,
            file_type=file_type,
            file_path=file_path,
            file_hash=file_hash,
            uploaded_by=user,
            status='PROCESSING',
        )
        count, warnings = _process(file_type, proj, source_file)
        message = f"{count} {DETAIL_LABELS[file_type]} ({period_name(proj.year, proj.month)})."
        if replaced and same_file_exists:
            message += " Dibangun ulang dari file yang sama."
        elif replaced:
            message += f" Menggantikan file lama: {replaced}."
        return FileResult(uploaded.name, 'processed', message, count, warnings,
                          source_file.id, replaced_filename=replaced), proj

    except Exception as e:
        # Salah kartu (mis. file WTT diupload lewat kartu PPRP) menghasilkan
        # pesan parser yang membingungkan — sebutkan jenis dokumen sebenarnya
        # dulu. Deteksi dilakukan sebelum file dihapus.
        message = _wrong_type_message(file_path, file_type) or str(e)
        # Record + file dibuang supaya file yang sama bisa diupload lagi
        # setelah penyebabnya dibetulkan (kalau dibiarkan, cek duplikat akan
        # menolaknya padahal datanya tidak pernah masuk).
        if source_file is not None:
            source_file.delete()
        _remove_file(file_path)
        return FileResult(uploaded.name, 'failed', message), None


def _detect_document_type(file_path):
    """Tebak jenis dokumen dari ISINYA (bukan nama file). None bila tidak yakin."""
    if os.path.splitext(file_path)[1].lower() in ('.xls', '.xlsx'):
        try:
            detect_ghp_period(file_path)
            return 'GHP'
        except Exception:
            return None
    try:
        if (parse_pprp(file_path).get('flights') or []):
            return 'PPRP'
    except Exception:
        pass
    try:
        detect_wtt_period(file_path)
        return 'WTT'
    except Exception:
        pass
    return None


def _wrong_type_message(file_path, expected):
    actual = _detect_document_type(file_path)
    if not actual or actual == expected:
        return None
    return (f"File ini isinya dokumen {actual}, bukan {expected}. "
            f"Sepertinya tertukar kartu — upload file ini lewat kartu {actual}, "
            f"dan pilih file {expected} untuk kartu ini.")


def _resolve_project(file_type, file_path, project, user, pprp_data):
    if file_type == 'WTT':
        month, year = detect_wtt_period(file_path)
        month, year = int(month), int(year)
        if project is not None and (project.year, project.month) != (year, month):
            raise ValueError(
                f"File WTT terdeteksi periode {period_name(year, month)}, tidak cocok dengan "
                f"project yang dipilih ({period_name(project.year, project.month)}).")
        proj, _ = Project.objects.get_or_create(
            month=month, year=year,
            defaults={
                'project_id': f"PRJ-{year}{month:02d}",
                'period': f"{year}-{month:02d}",
                'created_by': user,
            },
        )
        return proj

    if project is not None:
        return project

    if file_type == 'PPRP':
        start = pprp_data.get('pprp_date') if pprp_data else None
        if start is None:
            raise ValueError("Tidak dapat mendeteksi tanggal berlaku pada file PPRP ini.")
        proj = Project.objects.filter(year=start.year, month=start.month).first()
        if proj is None:
            raise ValueError(f"Belum ada project {period_name(start.year, start.month)}. "
                             f"Upload WTT bulan itu terlebih dahulu.")
        return proj

    # GHP: file hanya memuat DD/MM, jadi cari project bulan itu yang terbaru.
    month = detect_ghp_period(file_path)
    proj = Project.objects.filter(month=month).order_by('-year').first()
    if proj is None:
        raise ValueError(f"Belum ada project bulan {MONTH_NAMES.get(month, month)}. "
                         f"Upload WTT bulan itu terlebih dahulu.")
    return proj


def _replace_existing_if_allowed(file_type, proj, replace):
    """
    Satu bulan = satu WTT dan satu GHP. Bila sudah ada file sejenis dengan isi
    berbeda: tolak (supaya jadwal tidak dobel / flag lama tidak tertinggal),
    kecuali replace=True -> file lama dihapus lewat delete_source_file (yang
    juga membersihkan data turunannya). Kembalikan nama file lama yang
    digantikan, atau None.
    """
    if file_type not in ('WTT', 'GHP'):
        return None
    existing = list(SourceFile.objects.filter(project=proj, file_type=file_type).order_by('id'))
    if not existing:
        return None
    names = ', '.join(os.path.basename(sf.file_path) for sf in existing)
    if not replace:
        raise ValueError(
            f"Sudah ada file {file_type} untuk {period_name(proj.year, proj.month)} ({names}). "
            f"Untuk menggantinya, klik Atur Ulang, pilih bulan itu, lalu upload lagi.")
    for sf in existing:
        delete_source_file(sf.id)
    return names


def _validate_period(file_type, file_path, proj, pprp_data):
    if file_type == 'PPRP':
        flights = pprp_data.get('flights') or []
        if not flights:
            raise ValueError("Tidak ada data flight ditemukan di bagian MENJADI pada PDF ini.")
        sub_flights = [f for f in flights if f.get('origin') == 'SUB']
        if not sub_flights:
            raise ValueError("Surat ini tidak memuat rute keberangkatan dari SUB.")

        m_start = date(proj.year, proj.month, 1)
        m_end = date(proj.year, proj.month, calendar.monthrange(proj.year, proj.month)[1])
        if not any(f['pprp_date'] <= m_end and f['end_date'] >= m_start for f in sub_flights):
            rng_start = min(f['pprp_date'] for f in sub_flights)
            rng_end = max(f['end_date'] for f in sub_flights)
            raise ValueError(
                f"Surat berlaku {_fmt_date_id(rng_start)} s/d {_fmt_date_id(rng_end)}, "
                f"tidak mencakup {period_name(proj.year, proj.month)}. "
                f"Pilih project bulan yang berada di dalam rentang itu.")

    elif file_type == 'GHP':
        g_month = detect_ghp_period(file_path)
        if g_month != proj.month:
            raise ValueError(
                f"File GHP terdeteksi untuk bulan {MONTH_NAMES.get(g_month, g_month)}, "
                f"tidak cocok dengan project {period_name(proj.year, proj.month)}.")


def _process(file_type, proj, source_file):
    """Jalankan parser + loader. Kembalikan (jumlah, [peringatan])."""
    if file_type == 'WTT':
        return process_wtt(proj.id, source_file.id), []

    if file_type == 'PPRP':
        count = process_pprp(proj.id, source_file.id)
        # process_pprp memuat instance-nya sendiri; baca ulang status dari DB.
        source_file.refresh_from_db()
        if source_file.status == 'FAILED':
            raise ValueError(source_file.error_message or "File PPRP gagal diproses.")
        warnings = [] if count else [
            "Tidak ada jadwal yang terbentuk untuk bulan ini dari surat tersebut."]
        return count, warnings

    ghp = process_ghp(proj.id, source_file.id)
    return ghp.matched, ghp.warnings()


def _resync_derived_data(result, proj):
    """
    Terapkan ulang data turunan supaya hasil akhir tidak bergantung pada
    urutan upload:
    - setelah WTT : surat-surat PPRP project ini diterapkan ulang (baris v2
                    yang ikut terhapus saat WTT dihapus akan terbentuk lagi),
                    lalu GHP dicocokkan ulang;
    - setelah PPRP: GHP dicocokkan ulang (jadwal baru dapat flag operasional).
    """
    if result.file_type == 'WTT':
        pprp_files = SourceFile.objects.filter(project=proj, file_type='PPRP', status='SUCCESS').order_by('uploaded_at', 'id')
        n = 0
        for sf in pprp_files:
            process_pprp(proj.id, sf.id)
            n += 1
        if n:
            result.resync_messages.append(f"{n} surat PPRP {period_name(proj.year, proj.month)} diterapkan ulang.")

    if result.file_type in ('WTT', 'PPRP'):
        ghp_file = SourceFile.objects.filter(project=proj, file_type='GHP', status='SUCCESS').order_by('-uploaded_at').first()
        if ghp_file:
            ghp = process_ghp(proj.id, ghp_file.id)
            result.resync_messages.append(
                f"GHP {period_name(proj.year, proj.month)} dicocokkan ulang: {ghp.matched} jadwal beroperasi.")
            result.warnings.extend(ghp.warnings())


def _remove_file(file_path):
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
