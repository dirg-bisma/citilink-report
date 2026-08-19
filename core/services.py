import os
from django.db import transaction
from core.models import Project, SourceFile, ScheduleVersion
from core.parsers.wtt import parse_wtt
from core.parsers.pprp import parse_pprp
from core.parsers.ghp import parse_ghp
from datetime import datetime


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
            # Reset operational flag for all schedules in this project
            affected_count = ScheduleVersion.objects.filter(project=project, operational_flag=True).update(operational_flag=False)
            
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

                # Create or update PPRP Version 2 record for this date
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
                        'std': flight['std'],
                        'sta': flight['sta'],
                        'atd': flight['std'],
                        'ata': flight['sta'],
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



def process_ghp(project_id: int, ghp_file_id: int):
    """Match GHP to active schedules, set operational flag"""
    project = Project.objects.get(id=project_id)
    ghp_file = SourceFile.objects.get(id=ghp_file_id)
    
    records = parse_ghp(ghp_file.file_path)
    matched = 0
    
    with transaction.atomic():
        for rec in records:
            # Match key: flight_num + date, prioritize active version
            schedule = ScheduleVersion.objects.filter(
                project=project,
                is_active=True,
                flight_number=rec['flight_number'],
                flight_date=rec['flight_date'],
            ).order_by('-version_number').first()
            
            if schedule:
                schedule.operational_flag = True
                schedule.save()
                matched += 1
    
    ghp_file.status = 'SUCCESS'
    ghp_file.save()
    return matched
