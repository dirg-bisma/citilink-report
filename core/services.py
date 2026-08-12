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
    """Apply PPRP changes: create child rows, mark active"""
    project = Project.objects.get(id=project_id)
    pprp_file = SourceFile.objects.get(id=pprp_file_id)
    
    data = parse_pprp(pprp_file.file_path)
    
    with transaction.atomic():
        for flight in data['flights']:
            # Find parent: active version with same flight_number + origin + dest
            parent = ScheduleVersion.objects.filter(
                project=project,
                flight_number=flight['flight_number'],
                origin=flight['origin'],
                destination=flight['destination'],
                is_active=True,
            ).first()
            
            if not parent:
                continue  # ponytail: no parent = skip, log later if needed
            
            # Deactivate parent
            parent.is_active = False
            parent.save()
            
            # Create child
            ScheduleVersion.objects.create(
                project=project,
                parent_version=parent,
                version_number=parent.version_number + 1,
                is_active=True,
                flight_number=flight['flight_number'],
                origin=flight['origin'],
                destination=flight['destination'],
                flight_date=parent.flight_date,  # ponytail: keep original date, PPRP only changes time
                aircraft=flight['aircraft'],
                std=flight['std'],
                sta=flight['sta'],
                atd=flight['std'],  # ponytail: PPRP std = new atd
                ata=flight['sta'],
                pprp_letter=data['letter_number'],
                source_wtt=parent.source_wtt,
                source_pprp=pprp_file,
            )
    
    pprp_file.status = 'SUCCESS'
    pprp_file.save()
    return len(data['flights'])


def process_ghp(project_id: int, ghp_file_id: int):
    """Match GHP to active schedules, set operational flag"""
    project = Project.objects.get(id=project_id)
    ghp_file = SourceFile.objects.get(id=ghp_file_id)
    
    records = parse_ghp(ghp_file.file_path)
    matched = 0
    
    with transaction.atomic():
        for rec in records:
            # Match key: flight_num + date + origin + dest
            schedule = ScheduleVersion.objects.filter(
                project=project,
                is_active=True,
                flight_number=rec['flight_number'],
                flight_date=rec['flight_date'],
                origin=rec['origin'],
                destination=rec['destination'],
            ).first()
            
            if schedule:
                schedule.operational_flag = True
                schedule.save()
                matched += 1
    
    ghp_file.status = 'SUCCESS'
    ghp_file.save()
    return matched
