"""Processing service - load WTT, apply PPRP, match GHP"""
from django.db import transaction
from core.models import Project, SourceFile, ScheduleVersion
from core.parsers.wtt import parse_wtt
from core.parsers.pprp import parse_pprp
from core.parsers.ghp import parse_ghp
from datetime import datetime


def process_wtt(project_id: int, wtt_file_id: int):
    """Load WTT baseline into schedule versions"""
    project = Project.objects.get(id=project_id)
    wtt_file = SourceFile.objects.get(id=wtt_file_id)
    
    records = parse_wtt(wtt_file.file_path)
    
    with transaction.atomic():
        for rec in records:
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
                std=rec['std'],
                sta=rec['sta'],
                atd=rec['atd'],
                ata=rec['ata'],
                source_wtt=wtt_file,
            )
    
    wtt_file.status = 'SUCCESS'
    wtt_file.save()
    return len(records)


def process_pprp(project_id: int, pprp_file_id: int):
    """
    Apply PPRP: buat ScheduleVersion baru untuk setiap flight yang ada di bagian MENJADI.

    Catatan penting:
    - WTT records (version_number=1) TIDAK di-deactivate, agar GHP matching tetap berjalan.
    - Satu PPRP record dibuat per (flight_number + pprp_letter) — idempotent.
    - Matching parent dilakukan berdasarkan flight_number saja (bukan rute),
      karena PPRP sering mengubah rute penerbangan.
    """
    project = Project.objects.get(id=project_id)
    pprp_file = SourceFile.objects.get(id=pprp_file_id)

    data = parse_pprp(pprp_file.file_path)

    if not data['flights']:
        pprp_file.status = 'FAILED'
        pprp_file.error_message = 'Tidak ada data flight ditemukan di bagian MENJADI pada PDF ini.'
        pprp_file.save()
        return 0

    created = 0
    with transaction.atomic():
        for flight in data['flights']:
            # Cari parent WTT: cukup cocokkan berdasarkan flight_number saja
            parent = ScheduleVersion.objects.filter(
                project=project,
                flight_number=flight['flight_number'],
                version_number=1,
            ).first()

            if not parent:
                # Flight ini tidak ada di WTT — skip
                continue

            # Idempotent check: jika PPRP untuk flight ini sudah ada, skip
            already_exists = ScheduleVersion.objects.filter(
                project=project,
                flight_number=flight['flight_number'],
                pprp_letter=data['letter_number'],
            ).exists()

            if already_exists:
                continue

            # Buat ScheduleVersion baru untuk PPRP (MENJADI)
            ScheduleVersion.objects.create(
                project=project,
                parent_version=parent,
                version_number=2,
                is_active=True,
                flight_number=flight['flight_number'],
                origin=flight['origin'],
                destination=flight['destination'],
                # flight_date = tanggal mulai berlaku PPRP
                flight_date=flight['pprp_date'],
                std=flight['std'],
                sta=flight['sta'],
                atd=flight['std'],  # gunakan STD sebagai ATD default
                ata=flight['sta'],
                pprp_letter=data['letter_number'],
                pprp_date=flight['pprp_date'],
                source_wtt=parent.source_wtt,
                source_pprp=pprp_file,
            )
            created += 1

    pprp_file.status = 'SUCCESS'
    pprp_file.save()
    return created



def process_ghp(project_id: int, ghp_file_id: int):
    """Match GHP to active schedules, set operational flag"""
    project = Project.objects.get(id=project_id)
    ghp_file = SourceFile.objects.get(id=ghp_file_id)
    
    records = parse_ghp(ghp_file.file_path)
    matched = 0
    
    with transaction.atomic():
        for rec in records:
            # Match key: flight_num + date
            schedule = ScheduleVersion.objects.filter(
                project=project,
                is_active=True,
                flight_number=rec['flight_number'],
                flight_date=rec['flight_date'],
            ).first()
            
            if schedule:
                schedule.operational_flag = True
                schedule.save()
                matched += 1
    
    ghp_file.status = 'SUCCESS'
    ghp_file.save()
    return matched
