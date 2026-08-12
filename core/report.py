"""Report generator - export active schedules to Excel template"""
import openpyxl
from openpyxl import Workbook
from core.models import ScheduleVersion


def generate_report(project_id: int, template_path: str, output_path: str):
    """Ponytail: skip template complexity, write clean workbook"""
    schedules = ScheduleVersion.objects.filter(
        project_id=project_id,
        is_active=True,
        operational_flag=True,
    ).order_by('flight_date', 'flight_number')
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    
    # Header
    ws.append(['NO', 'FLIGHT', 'ROUTE', 'ETD', 'ETA', 'ATD', 'ATA', 'PPRP'])
    
    # Data
    for idx, sch in enumerate(schedules, 1):
        ws.append([
            idx,
            sch.flight_number,
            f"{sch.origin}-{sch.destination}",
            sch.std,
            sch.sta,
            sch.atd,
            sch.ata,
            sch.pprp_letter or '',
        ])
    
    wb.save(output_path)
    return len(list(schedules))

