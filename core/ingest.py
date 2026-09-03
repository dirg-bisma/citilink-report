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
  (bukan sekadar cocok bulan mulainya). Surat adalah satu dokumen yang bisa
  berlaku beberapa bulan: setelah diproses di satu bulan, surat itu otomatis
  disalin & diterapkan ke setiap project bulan lain yang dicakupnya (fan-out),
  dan project bulan baru otomatis menarik surat-surat lama yang mencakupnya
  (adopt). Satu surat cukup diupload SEKALI;
- satu flight+tanggal hanya dipegang satu surat: yang tanggal berlakunya
  terbaru menang (core.services.letter_rank), bukan yang diupload belakangan;
- satu bulan hanya punya SATU file WTT dan SATU file GHP. File kedua yang
  berbeda isinya ditolak, kecuali pemanggil memberi replace=True (mode
  "Atur Ulang" di halaman Upload Data): file lama dihapus beserta data
  turunannya, file baru diproses, lalu bulan itu disusun ulang;
- setelah batch selesai, data turunan disinkronkan ulang (PPRP -> GHP,
  WTT -> PPRP -> GHP) supaya urutan upload tidak mengubah hasil akhir.
"""
import os
from dataclasses import dataclass, field

from django.core.files.storage import FileSystemStorage

from core.models import Project, SourceFile
from core.parsers.ghp import detect_ghp_period
from core.parsers.pprp import parse_pprp
from core.parsers.wtt import detect_wtt_period
from core.services import (delete_source_file, process_ghp, process_pprp, process_wtt, _fmt_date_id,
                           letter_covers_month, letter_sort_key, letter_sub_flights)

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
    also_applied_to: list = field(default_factory=list)  # nama periode bulan lain penerima surat (fan-out)

    def as_dict(self):
        return {
            'filename': self.filename,
            'status': self.status,
            'message': self.message,
            'count': self.count,
            'warnings': list(self.warnings),
            'source_file_id': self.source_file_id,
            'replaced_filename': self.replaced_filename,
            'also_applied_to': list(self.also_applied_to),
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
        fr, proj, extra_projects = _ingest_one(fs, file_type, uploaded, user, project, replace)
        result.files.append(fr)
        if fr.status == 'processed' and proj is not None:
            result.project = proj
            for p in [proj] + extra_projects:
                if p not in touched_projects:
                    touched_projects.append(p)

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
                              f"Sudah pernah diupload untuk {period_name(proj.year, proj.month)}.{hint}"), proj, []

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
        extra_projects = []
        if file_type == 'PPRP':
            extra_projects = _fan_out_letter(source_file, user)
            if extra_projects:
                names = ', '.join(period_name(p.year, p.month) for p in extra_projects)
                message += f" Surat ini juga berlaku untuk {names} dan sudah diterapkan ke bulan itu."
        return FileResult(uploaded.name, 'processed', message, count, warnings, source_file.id,
                          replaced_filename=replaced,
                          also_applied_to=[period_name(p.year, p.month) for p in extra_projects]), proj, extra_projects

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
        return FileResult(uploaded.name, 'failed', message), None, []


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
        sub_flights = letter_sub_flights(pprp_data.get('flights') if pprp_data else None)
        if not sub_flights:
            raise ValueError("Tidak dapat mendeteksi tanggal berlaku pada file PPRP ini.")
        # Surat berlaku lintas bulan: masukkan ke project bulan PERTAMA yang ada
        # di dalam rentangnya; bulan-bulan berikutnya dapat lewat fan-out.
        for cand in Project.objects.order_by('year', 'month'):
            if letter_covers_month(sub_flights, cand.year, cand.month):
                return cand
        rng_start = min(f['pprp_date'] for f in sub_flights)
        rng_end = max(f['end_date'] for f in sub_flights)
        raise ValueError(f"Belum ada project untuk bulan yang dicakup surat ini "
                         f"({_fmt_date_id(rng_start)} s/d {_fmt_date_id(rng_end)}). "
                         f"Upload WTT bulan itu terlebih dahulu.")

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

        if not letter_covers_month(sub_flights, proj.year, proj.month):
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
    - setelah WTT : surat dari bulan lain yang mencakup bulan ini ditarik
                    (adopt), semua surat project ini diterapkan ulang (baris v2
                    yang ikut terhapus saat WTT dihapus terbentuk lagi), lalu
                    GHP dicocokkan ulang — lihat resync_project;
    - setelah PPRP: GHP dicocokkan ulang (jadwal baru dapat flag operasional),
                    termasuk di bulan-bulan penerima fan-out.
    """
    if result.file_type == 'WTT':
        messages, warnings = resync_project(proj)
        result.resync_messages.extend(messages)
        result.warnings.extend(warnings)
        return

    if result.file_type == 'PPRP':
        msg, warnings = _resync_ghp(proj)
        if msg:
            result.resync_messages.append(msg)
        result.warnings.extend(warnings)


def _resync_ghp(proj):
    ghp_file = SourceFile.objects.filter(project=proj, file_type='GHP', status='SUCCESS').order_by('-uploaded_at').first()
    if not ghp_file:
        return None, []
    ghp = process_ghp(proj.id, ghp_file.id)
    return (f"GHP {period_name(proj.year, proj.month)} dicocokkan ulang: {ghp.matched} jadwal beroperasi.",
            ghp.warnings())


def _clone_letter(source_file, proj):
    """Daftarkan salinan surat (file fisik yang sama) ke project lain lalu
    terapkan. Kembalikan SourceFile salinan, atau None bila gagal (salinan
    yang gagal tidak disimpan)."""
    clone = SourceFile.objects.create(
        project=proj,
        file_type='PPRP',
        file_path=source_file.file_path,
        file_hash=source_file.file_hash,
        uploaded_by=source_file.uploaded_by,
        status='PROCESSING',
        parser_version=source_file.parser_version,
    )
    try:
        process_pprp(proj.id, clone.id)
        clone.refresh_from_db()
    except Exception:
        clone.delete()
        return None
    if clone.status != 'SUCCESS':
        clone.delete()
        return None
    return clone


def _fan_out_letter(source_file, user=None):
    """
    Setelah surat diproses di satu bulan, terapkan juga ke setiap project bulan
    lain yang berada di dalam rentang berlakunya dan belum memilikinya.
    Kembalikan daftar project penerima (urut bulan).
    """
    data = parse_pprp(source_file.file_path)
    targets = []
    for proj in Project.objects.exclude(id=source_file.project_id).order_by('year', 'month'):
        if not letter_covers_month(data['flights'], proj.year, proj.month):
            continue
        if SourceFile.objects.filter(project=proj, file_type='PPRP', file_hash=source_file.file_hash).exists():
            continue
        if _clone_letter(source_file, proj) is not None:
            targets.append(proj)
    return targets


def adopt_letters(proj):
    """
    Tarik surat-surat dari project bulan lain yang mencakup bulan ini tapi
    belum ada di project ini (mis. project bulan baru dibuat setelah suratnya
    diupload ke bulan sebelumnya). Kembalikan daftar (nomor surat, nama file).
    """
    have = set(SourceFile.objects.filter(project=proj, file_type='PPRP').values_list('file_hash', flat=True))
    adopted = []
    candidates = (SourceFile.objects.filter(file_type='PPRP', status='SUCCESS')
                  .exclude(project=proj).select_related('project')
                  .order_by('project__year', 'project__month', 'uploaded_at', 'id'))
    for sf in candidates:
        if sf.file_hash in have or not os.path.exists(sf.file_path):
            continue
        try:
            data = parse_pprp(sf.file_path)
        except Exception:
            continue
        if not letter_covers_month(data['flights'], proj.year, proj.month):
            continue
        have.add(sf.file_hash)
        if _clone_letter(sf, proj) is not None:
            adopted.append((data['letter_number'], os.path.basename(sf.file_path)))
    return adopted


def resync_project(proj):
    """
    Susun ulang data turunan satu bulan dari file-file sumbernya (idempoten):
    adopt surat bulan lain -> terapkan ulang semua surat -> hidupkan baris WTT
    tanpa pengganti -> cocokkan ulang GHP. Kembalikan (pesan, peringatan).
    Dipakai setelah WTT diupload/diganti, oleh aksi admin, dan oleh perintah
    `manage.py sync_pprp`.
    """
    from core.models import ScheduleVersion

    messages, warnings = [], []
    adopted = adopt_letters(proj)
    if adopted:
        names = '; '.join(f"{num} ({fname})" for num, fname in adopted)
        messages.append(f"{len(adopted)} surat PPRP dari bulan lain berlaku untuk "
                        f"{period_name(proj.year, proj.month)} dan diterapkan otomatis: {names}.")

    pprp_files = sorted(SourceFile.objects.filter(project=proj, file_type='PPRP', status='SUCCESS'), key=letter_sort_key)
    for sf in pprp_files:
        process_pprp(proj.id, sf.id)
    if pprp_files:
        messages.append(f"{len(pprp_files)} surat PPRP {period_name(proj.year, proj.month)} diterapkan ulang.")

    # Baris WTT yang tidak (lagi) tertutup surat harus aktif — pengaman bila ada
    # baris v2 yang hilang tanpa lewat delete_source_file.
    inactive_v1 = ScheduleVersion.objects.filter(project=proj, version_number=1, is_active=False)
    for sv in inactive_v1.only('id', 'flight_number', 'flight_date'):
        if not ScheduleVersion.objects.filter(project=proj, flight_number=sv.flight_number,
                                              flight_date=sv.flight_date, version_number=2, is_active=True).exists():
            ScheduleVersion.objects.filter(id=sv.id).update(is_active=True)

    msg, ghp_warnings = _resync_ghp(proj)
    if msg:
        messages.append(msg)
    warnings.extend(ghp_warnings)
    return messages, warnings


def _remove_file(file_path):
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass
