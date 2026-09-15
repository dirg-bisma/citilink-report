import os
import re
from dataclasses import dataclass, field
from django.db import transaction
from core.models import Project, SourceFile, ScheduleVersion
from core.parsers.wtt import parse_wtt
from core.parsers.pprp import parse_pprp
from core.parsers.ghp import parse_ghp
from datetime import datetime, timedelta

# Zona waktu sumber data (tertulis eksplisit di masing-masing dokumen):
# - WTT PDF  : "Times in Local"           -> STD/STA/ATD/ATA Local
# - PPRP PDF : "Jadwal Penerbangan (UTC)" -> STD/STA UTC
# - GHP Excel: jam Local (konsisten dengan WTT)
# Helper konversi di bawah dipakai a.l. oleh report untuk mengubah STD GHP
# (Local) menjadi UTC. Offset tergantung bandara: SUB selalu WIB, lainnya bervariasi.
WITA_AIRPORTS = {'DPS', 'UPG', 'LOP', 'BPN', 'AAP', 'BDJ', 'MDC', 'KDI', 'PLW', 'KOE', 'TRK', 'LBJ', 'BMU', 'TMC', 'MOF'}
WIT_AIRPORTS = {'AMQ', 'DJJ', 'SOQ', 'TIM', 'TTE', 'MKQ'}


def _utc_offset_for_airport(iata_code):
    code = (iata_code or '').strip().upper()
    if code in WIT_AIRPORTS:
        return 9
    if code in WITA_AIRPORTS:
        return 8
    return 7  # WIB default


def _utc_time_to_local(time_obj, offset_hours):
    """Tambahkan offset zona waktu ke objek time (wraparound tengah malam diabaikan,
    karena ScheduleVersion.std/atd hanya TimeField, bukan datetime)."""
    if time_obj is None:
        return None
    dummy = datetime.combine(datetime(2000, 1, 1), time_obj) + timedelta(hours=offset_hours)
    return dummy.time()


def delete_source_file(source_file_id: int) -> dict:
    """
    Hapus SourceFile beserta seluruh data turunannya.

    WTT : semua jadwal (v1 + v2 turunannya) project itu dihapus.
    PPRP: surat adalah SATU dokumen yang bisa berlaku di beberapa bulan; salinan
          surat yang sama (file_hash sama) di project bulan lain ikut dihapus,
          supaya tidak ada bulan yang diam-diam masih memakai surat yang sudah
          dicabut. Di tiap bulan: baris v2 surat itu dihapus, surat lain yang
          masih ada diterapkan ulang (mengisi tanggal yang tadinya dimenangkan
          surat ini), baris WTT dihidupkan kembali bila tidak ada pengganti,
          lalu GHP dicocokkan ulang.
    GHP : flag operasional + jam GHP project itu direset.
    File fisik dihapus hanya bila tidak ada SourceFile lain yang memakainya.
    """
    source_file = SourceFile.objects.get(id=source_file_id)
    project = source_file.project
    file_type = source_file.file_type
    file_path = source_file.file_path

    affected_count = 0
    projects = []
    with transaction.atomic():
        if file_type == 'WTT':
            # Deletes all schedules created by this WTT (including child PPRPs)
            deleted_tuple = ScheduleVersion.objects.filter(project=project, source_wtt=source_file).delete()
            affected_count = deleted_tuple[0]
            projects.append(project)
            source_file.delete()
        elif file_type == 'PPRP':
            siblings = list(SourceFile.objects.filter(file_type='PPRP', file_hash=source_file.file_hash)
                            .order_by('project__year', 'project__month'))
            for sib in siblings:
                affected_count += _remove_letter_from_project(sib)
                projects.append(sib.project)
                sib.delete()
        elif file_type == 'GHP':
            # Reset operational flag + jam GHP for all schedules in this project
            affected_count = ScheduleVersion.objects.filter(project=project, operational_flag=True).update(
                operational_flag=False, ghp_std=None, ghp_atd=None, delay_code=None)
            projects.append(project)
            source_file.delete()

        # Delete physical file (bila tidak dipakai record lain, mis. salinan surat)
        if file_path and os.path.exists(file_path) and not SourceFile.objects.filter(file_path=file_path).exists():
            try:
                os.remove(file_path)
            except OSError:
                pass

    return {
        'file_id': source_file_id,
        'file_type': file_type,
        'affected_count': affected_count,
        'project_id': project.id,
        'project_code': project.project_id,
        'projects': [f"{p.year}-{p.month:02d}" for p in projects],
        'project_ids': [p.id for p in projects],
    }


def _remove_letter_from_project(pprp_file) -> int:
    """Cabut satu surat dari satu project (lihat delete_source_file). Kembalikan
    jumlah baris v2 yang dihapus."""
    project = pprp_file.project
    v2_rows = ScheduleVersion.objects.filter(project=project, source_pprp=pprp_file)
    affected_keys = set(v2_rows.values_list('flight_number', 'flight_date'))
    deleted = v2_rows.delete()[0]
    if not affected_keys:
        return deleted
    # Surat lain di bulan ini mungkin juga mencakup tanggal-tanggal itu tapi
    # kalah saat diterapkan; terapkan ulang supaya mereka mengisi kekosongan.
    others = SourceFile.objects.filter(project=project, file_type='PPRP', status='SUCCESS').exclude(id=pprp_file.id)
    for other in sorted(others, key=letter_sort_key):
        process_pprp(project.id, other.id)
    # Hidupkan kembali baris WTT (v1) yang tidak punya pengganti aktif — kalau
    # tidak, flight itu lenyap dari laporan padahal jadwal WTT-nya masih berlaku.
    for fn, d in affected_keys:
        if not ScheduleVersion.objects.filter(project=project, flight_number=fn, flight_date=d, is_active=True).exists():
            ScheduleVersion.objects.filter(project=project, flight_number=fn, flight_date=d, version_number=1).update(is_active=True)
    # Baris yang baru aktif belum punya flag GHP -> cocokkan ulang.
    ghp_file = SourceFile.objects.filter(project=project, file_type='GHP', status='SUCCESS').order_by('-uploaded_at').first()
    if ghp_file:
        process_ghp(project.id, ghp_file.id)
    return deleted


def process_wtt(project_id: int, wtt_file_id: int):
    """Load WTT baseline into schedule versions"""
    project = Project.objects.get(id=project_id)
    wtt_file = SourceFile.objects.get(id=wtt_file_id)
    
    records = parse_wtt(wtt_file.file_path)
    created = 0

    with transaction.atomic():
        for rec in records:
            # Hanya keberangkatan dari Surabaya. WTT memuat jadwal seluruh
            # station; leg masuk ke SUB dan rute station lain bukan tanggung
            # jawab laporan ini (sama seperti filter di process_pprp).
            if rec.get('origin') != 'SUB':
                continue
            # Charter/extra flight (4 digit) tidak masuk laporan — lihat is_charter_flight.
            if is_charter_flight(rec['flight_number']):
                continue
            created += 1
            ScheduleVersion.objects.create(
                project=project,
                parent_version=None,
                version_number=1,
                is_active=True,
                flight_number=rec['flight_number'],
                origin=rec['origin'],
                destination=rec['destination'],
                flight_date=rec['flight_date'],
                aircraft=rec['aircraft'],
                std=parse_time_str(rec.get('std')),
                sta=parse_time_str(rec.get('sta')),
                atd=parse_time_str(rec.get('atd')),
                ata=parse_time_str(rec.get('ata')),
                source_wtt=wtt_file,
            )
    
    wtt_file.status = 'SUCCESS'
    wtt_file.save()
    return created


def letter_rank(pprp_date, letter_number, file_hash=''):
    """
    Urutan keberlakuan surat untuk satu flight+tanggal (yang lebih besar menang):
    1. tanggal mulai berlaku segmen (surat yang berlaku lebih baru menggantikan
       surat sebelumnya — prinsip yang sama dengan pemotongan segmen di laporan);
    2. angka-angka di nomor surat (mis. AU.012/50/15/... > AU.012/47/2/...);
    3. hash file, sekadar pemutus seri yang deterministik.
    Tidak bergantung pada urutan upload, jadi hasil DB sama apa pun urutannya.
    """
    nums = tuple(int(x) for x in re.findall(r'\d+', letter_number or ''))
    return (pprp_date or datetime.min.date(), nums, file_hash or '')


def letter_sort_key(source_file):
    """Kunci urutan penerapan surat (SourceFile PPRP) dalam satu project."""
    return (source_file.uploaded_at, source_file.id)


def letter_sub_flights(flights):
    """Baris MENJADI yang menjadi tanggung jawab laporan: keberangkatan SUB, bukan charter."""
    return [f for f in (flights or [])
            if f.get('origin') == 'SUB' and not is_charter_flight(f.get('flight_number'))]


def letter_covers_month(flights, year, month) -> bool:
    """Benar bila ada rute SUB di surat yang rentang berlakunya menyentuh bulan itu."""
    import calendar
    from datetime import date
    m_start = date(year, month, 1)
    m_end = date(year, month, calendar.monthrange(year, month)[1])
    return any(f['pprp_date'] <= m_end and f['end_date'] >= m_start for f in letter_sub_flights(flights))


def process_pprp(project_id: int, pprp_file_id: int):
    """
    Apply PPRP: buat ScheduleVersion baru (version_number=2) untuk setiap hari aktif
    sesuai day_pattern dan rentang tanggal mulai berlaku s/d akhir bulan project.

    Satu flight+tanggal hanya punya SATU baris v2. Bila tanggal itu sudah diisi
    surat lain, pemenangnya ditentukan letter_rank (surat berlaku terbaru
    menang), bukan urutan upload; surat yang kalah tidak menyentuh baris itu.
    Menerapkan ulang surat yang sama selalu menyegarkan barisnya sendiri.
    """
    import calendar
    from datetime import date

    project = Project.objects.get(id=project_id)
    pprp_file = SourceFile.objects.get(id=pprp_file_id)

    data = parse_pprp(pprp_file.file_path)

    if not data['flights']:
        pprp_file.status = 'FAILED'
        pprp_file.error_message = 'Tidak ada data flight ditemukan di bagian MENJADI pada PDF ini.'
        pprp_file.save()
        return 0

    num_days = calendar.monthrange(project.year, project.month)[1]
    m_start = date(project.year, project.month, 1)
    m_end = date(project.year, project.month, num_days)

    created = 0
    with transaction.atomic():
        # Segmen diterapkan urut tanggal berlaku: bila satu surat memuat dua
        # segmen flight yang sama dan tanggalnya beririsan, segmen terbaru menang.
        for flight in sorted(letter_sub_flights(data['flights']), key=lambda f: f['pprp_date']):
            f_num = flight['flight_number']
            pprp_start = flight['pprp_date']
            pprp_end = flight['end_date']
            day_pat = flight.get('day_pattern', '1234567')
            my_rank = letter_rank(pprp_start, data['letter_number'], pprp_file.file_hash)

            eff_start = max(m_start, pprp_start)
            eff_end = min(m_end, pprp_end)

            if eff_start > eff_end:
                continue

            for d in range((eff_end - eff_start).days + 1):
                cur_date = date.fromordinal(eff_start.toordinal() + d)
                iso_day = str(cur_date.isoweekday())

                # Check if day is active in day_pattern
                if iso_day not in day_pat:
                    continue

                # Surat lain yang lebih baru sudah berlaku pada tanggal ini?
                existing = ScheduleVersion.objects.filter(
                    project=project, flight_number=f_num, flight_date=cur_date, version_number=2,
                ).select_related('source_pprp').first()
                if existing and existing.source_pprp_id not in (None, pprp_file.id):
                    other_rank = letter_rank(existing.pprp_date, existing.pprp_letter,
                                             existing.source_pprp.file_hash)
                    if other_rank > my_rank:
                        continue

                # Find parent WTT record on this date
                parent = ScheduleVersion.objects.filter(
                    project=project,
                    flight_number=f_num,
                    flight_date=cur_date,
                    version_number=1,
                ).first()

                # Deactivate parent WTT on and after PPRP start date
                if parent:
                    parent.is_active = False
                    parent.save()

                # Create or update PPRP Version 2 record for this date.
                # STD/STA disimpan apa adanya dari surat PPRP (UTC).
                # ATD/ATA laporan bersumber dari WTT (Local) — diambil dari baris
                # WTT (v1) tanggal yang sama via std/sta-nya, yang selalu murni
                # nilai WTT (kolom atd v1 bisa tercemar data GHP lama).
                std_time = parse_time_str(flight.get('std'))
                sta_time = parse_time_str(flight.get('sta'))
                atd_time = parent.std if parent else None
                ata_time = parent.sta if parent else None
                ScheduleVersion.objects.update_or_create(
                    project=project,
                    flight_number=f_num,
                    flight_date=cur_date,
                    version_number=2,
                    defaults={
                        'parent_version': parent,
                        'is_active': True,
                        'origin': flight['origin'],
                        'destination': flight['destination'],
                        'std': std_time,
                        'sta': sta_time,
                        'atd': atd_time,
                        'ata': ata_time,
                        'pprp_letter': data['letter_number'],
                        'pprp_date': flight['pprp_date'],
                        'source_wtt': parent.source_wtt if parent else None,
                        'source_pprp': pprp_file,
                    }
                )
                created += 1

    pprp_file.status = 'SUCCESS'
    pprp_file.save()
    return created



def _ghp_std_distance(schedule, rec):
    """
    Selisih menit (sirkular, 0-720) antara STD baris GHP dan jadwal resmi
    schedule tsb dalam Local: baris v1 pakai std WTT apa adanya (sudah Local),
    baris v2/PPRP pakai std surat (UTC) dikonversi ke Local bandara asal.
    None bila salah satu jam tidak tersedia (tidak bisa dibandingkan).
    """
    ghp_std = parse_time_str(rec.get('std'))
    if ghp_std is None or schedule.std is None:
        return None
    if schedule.pprp_letter:
        expected = _utc_time_to_local(schedule.std, _utc_offset_for_airport(schedule.origin))
    else:
        expected = schedule.std
    m1 = ghp_std.hour * 60 + ghp_std.minute
    m2 = expected.hour * 60 + expected.minute
    d = abs(m1 - m2)
    return min(d, 1440 - d)


def parse_time_str(time_val):
    if not time_val:
        return None
    import re, datetime
    if isinstance(time_val, datetime.time):
        return time_val
    time_str = str(time_val).strip()
    m = re.search(r'(\d{1,2}):(\d{2})', time_str)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if hour >= 24:
            hour = hour % 24
        return datetime.time(hour, minute)
    return None


_CHARTER_RE = re.compile(r'^[A-Z]{2}(\d+)')
_MONTH_ABBR_ID = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'Mei', 6: 'Jun',
                  7: 'Jul', 8: 'Agu', 9: 'Sep', 10: 'Okt', 11: 'Nov', 12: 'Des'}


def is_charter_flight(flight_number) -> bool:
    """Charter / extra flight ditandai nomor 4 digit atau lebih setelah 'QG'
    (mis. QG9694, QG1505). Aturan dari pengguna (2026-09-02): penerbangan
    seperti ini tidak masuk laporan, jadi baris GHP-nya diabaikan tanpa
    peringatan."""
    m = _CHARTER_RE.match((flight_number or '').strip().upper())
    return bool(m) and len(m.group(1)) >= 4


def _fmt_date_id(d) -> str:
    """'2026-08-14' / date -> '14 Agu 2026'."""
    if isinstance(d, str):
        d = datetime.strptime(d, '%Y-%m-%d').date()
    return f"{d.day} {_MONTH_ABBR_ID[d.month]} {d.year}"


@dataclass
class GhpMatchResult:
    """Hasil pencocokan satu file GHP ke jadwal aktif project."""
    matched: int = 0
    charter_skipped: int = 0
    # flight_number -> daftar tanggal (ISO, terurut) yang ada di GHP tapi
    # tidak punya jadwal WTT/PPRP. Ini bukti pesawat terbang yang akan
    # TERBUANG dari laporan bila tidak ditindaklanjuti (kasus QG356, QG719).
    unmatched: dict = field(default_factory=dict)
    # (flight_number, tanggal ISO, teks mentah) untuk keberangkatan SUB yang
    # kolom Break Down-nya tidak bisa dibaca; delay code-nya dikosongkan.
    invalid_delay_codes: list = field(default_factory=list)

    @property
    def unmatched_rows(self) -> int:
        return sum(len(v) for v in self.unmatched.values())

    def warnings(self) -> list:
        """Satu kalimat peringatan per flight yang tidak ketemu jadwalnya,
        yang paling banyak harinya di urutan teratas; lalu satu kalimat per
        delay code yang tidak terbaca."""
        out = []
        for fn, dates in sorted(self.unmatched.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            span = _fmt_date_id(dates[0]) if len(dates) == 1 else f"{_fmt_date_id(dates[0])} s/d {_fmt_date_id(dates[-1])}"
            out.append(f"{fn}: {len(dates)} hari tercatat terbang di GHP tapi tidak ada jadwalnya ({span}). "
                       f"Cek apakah WTT/surat PPRP-nya belum diupload.")
        for fn, d, raw in sorted(self.invalid_delay_codes, key=lambda x: (x[1], x[0])):
            out.append(f"{fn} {_fmt_date_id(d)}: delay code GHP \"{raw}\" tidak bisa dibaca "
                       f"(format yang dikenal: 00:05/89,00:10/80), jadi tidak dihitung di dashboard.")
        return out


def process_ghp(project_id: int, ghp_file_id: int) -> GhpMatchResult:
    """Match GHP to active schedules, set operational flag and update actual times (atd)"""
    project = Project.objects.get(id=project_id)
    ghp_file = SourceFile.objects.get(id=ghp_file_id)

    records = parse_ghp(ghp_file.file_path)
    result = GhpMatchResult()
    # Decision log Q3 (dipertajam): bila beberapa baris GHP cocok ke flight+tanggal
    # yang sama (baris rotasi multileg ganda, contoh QG834 muncul sebagai
    # 'QG834-QG815' jam 19:00 DAN 'QG833-QG834' jam 17:00), pilih baris yang STD
    # GHP-nya PALING DEKAT dengan jadwal resmi baris itu (WTT untuk baris v1,
    # surat PPRP untuk baris v2). Seri/tak terbandingkan -> baris pertama di file.
    best = {}  # schedule.id -> {'schedule', 'rec', 'diff'}
    unmatched = {}  # flight_number -> set(tanggal)

    with transaction.atomic():
        for rec in records:
            if is_charter_flight(rec['flight_number']):
                result.charter_skipped += 1
                continue

            if rec.get('delay_code_invalid') and rec.get('origin') == 'SUB':
                result.invalid_delay_codes.append(
                    (rec['flight_number'], rec['flight_date'], rec['delay_code_invalid']))

            # Match key: flight_num + date, prioritize active version
            schedule = ScheduleVersion.objects.filter(
                project=project,
                is_active=True,
                flight_number=rec['flight_number'],
                flight_date=rec['flight_date'],
            ).order_by('-version_number').first()

            if not schedule:
                # Hanya leg keberangkatan SUB yang memang tanggung jawab laporan
                # ini; leg lain (mis. HLP->SUB) memang tidak punya jadwal di DB.
                if rec.get('origin') == 'SUB':
                    unmatched.setdefault(rec['flight_number'], set()).add(rec['flight_date'])
                continue

            diff = _ghp_std_distance(schedule, rec)
            cur = best.get(schedule.id)
            if cur is None or (diff is not None and (cur['diff'] is None or diff < cur['diff'])):
                best[schedule.id] = {'schedule': schedule, 'rec': rec, 'diff': diff}

        for item in best.values():
            schedule, rec = item['schedule'], item['rec']
            schedule.operational_flag = True
            # Jam GHP disimpan di kolom khusus dashboard (ghp_std/ghp_atd).
            # Kolom atd/ata laporan (sumber: WTT) TIDAK boleh ditimpa GHP.
            if rec.get('std'):
                parsed_std = parse_time_str(rec['std'])
                if parsed_std:
                    schedule.ghp_std = parsed_std
            if rec.get('atd'):
                parsed_atd = parse_time_str(rec['atd'])
                if parsed_atd:
                    schedule.ghp_atd = parsed_atd
            # Selalu ditimpa (juga dengan kosong) supaya pencocokan ulang tidak
            # meninggalkan kode dari GHP sebelumnya.
            schedule.delay_code = rec.get('delay_code') or None
            schedule.save()
            result.matched += 1

    result.unmatched = {fn: sorted(dates) for fn, dates in unmatched.items()}
    ghp_file.status = 'SUCCESS'
    ghp_file.save()
    return result
