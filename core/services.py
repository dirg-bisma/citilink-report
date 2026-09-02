import os
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
    Cascaded deletion of a SourceFile and all its generated/associated database records.
    """
    source_file = SourceFile.objects.get(id=source_file_id)
    project = source_file.project
    file_type = source_file.file_type
    file_path = source_file.file_path
    
    affected_count = 0
    with transaction.atomic():
        if file_type == 'WTT':
            # Deletes all schedules created by this WTT (including child PPRPs)
            deleted_tuple = ScheduleVersion.objects.filter(project=project, source_wtt=source_file).delete()
            affected_count = deleted_tuple[0]
        elif file_type == 'PPRP':
            # Deletes all version 2 schedules created by this PPRP
            deleted_tuple = ScheduleVersion.objects.filter(project=project, source_pprp=source_file).delete()
            affected_count = deleted_tuple[0]
        elif file_type == 'GHP':
            # Reset operational flag + jam GHP for all schedules in this project
            affected_count = ScheduleVersion.objects.filter(project=project, operational_flag=True).update(
                operational_flag=False, ghp_std=None, ghp_atd=None)
            
        # Delete SourceFile model
        source_file.delete()
        
        # Delete physical file
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
                
    return {
        'file_id': source_file_id,
        'file_type': file_type,
        'affected_count': affected_count,
        'project_id': project.id,
        'project_code': project.project_id
    }


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


def process_pprp(project_id: int, pprp_file_id: int):
    """
    Apply PPRP: buat ScheduleVersion baru (version_number=2) untuk setiap hari aktif
    sesuai day_pattern dan rentang tanggal mulai berlaku s/d akhir bulan project.
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
        for flight in data['flights']:
            # Hanya proses rute keberangkatan dari Surabaya (origin == 'SUB')
            if flight.get('origin') != 'SUB':
                continue

            f_num = flight['flight_number']
            pprp_start = flight['pprp_date']
            pprp_end = flight['end_date']
            day_pat = flight.get('day_pattern', '1234567')

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


def process_ghp(project_id: int, ghp_file_id: int):
    """Match GHP to active schedules, set operational flag and update actual times (atd)"""
    project = Project.objects.get(id=project_id)
    ghp_file = SourceFile.objects.get(id=ghp_file_id)
    
    records = parse_ghp(ghp_file.file_path)
    matched = 0
    # Decision log Q3 (dipertajam): bila beberapa baris GHP cocok ke flight+tanggal
    # yang sama (baris rotasi multileg ganda, contoh QG834 muncul sebagai
    # 'QG834-QG815' jam 19:00 DAN 'QG833-QG834' jam 17:00), pilih baris yang STD
    # GHP-nya PALING DEKAT dengan jadwal resmi baris itu (WTT untuk baris v1,
    # surat PPRP untuk baris v2). Seri/tak terbandingkan -> baris pertama di file.
    best = {}  # schedule.id -> {'schedule', 'rec', 'diff'}

    with transaction.atomic():
        for rec in records:
            # Match key: flight_num + date, prioritize active version
            schedule = ScheduleVersion.objects.filter(
                project=project,
                is_active=True,
                flight_number=rec['flight_number'],
                flight_date=rec['flight_date'],
            ).order_by('-version_number').first()

            if not schedule:
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
            if 'delay_code' in rec and rec['delay_code']:
                schedule.delay_code = rec['delay_code']
            schedule.save()
            matched += 1
    
    ghp_file.status = 'SUCCESS'
    ghp_file.save()
    return matched
