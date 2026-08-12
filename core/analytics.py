"""Dashboard analytics - compute metrics from GHP data"""
from django.db.models import Count, Q
from core.models import ScheduleVersion
from datetime import datetime, timedelta


def pprp_achievement(project_id: int, month: int) -> dict:
    """PPRP: flights within 45min = 100%, else 0%. Aggregate per flight."""
    # ponytail: GHP STD/ATD in string format, parse as needed
    flights = ScheduleVersion.objects.filter(
        project_id=project_id,
        operational_flag=True,
        is_active=True,
    )
    
    total = flights.count()
    if total == 0:
        return {'achievement': 0, 'total': 0, 'on_time': 0}
    
    on_time = 0
    for f in flights:
        if f.std and f.atd:
            std_min = f.std.hour * 60 + f.std.minute
            atd_min = f.atd.hour * 60 + f.atd.minute
            if abs(atd_min - std_min) <= 45:
                on_time += 1
    
    return {
        'achievement': round(on_time / total * 100, 2),
        'total': total,
        'on_time': on_time,
    }


def otp_metric(project_id: int) -> dict:
    """OTP: ATD vs STD > 1min = delayed"""
    flights = ScheduleVersion.objects.filter(
        project_id=project_id,
        operational_flag=True,
        is_active=True,
    )
    
    total = flights.count()
    delayed = 0
    
    for f in flights:
        if f.std and f.atd:
            std_min = f.std.hour * 60 + f.std.minute
            atd_min = f.atd.hour * 60 + f.atd.minute
            if atd_min - std_min > 1:
                delayed += 1
    
    on_time = total - delayed
    return {
        'otp_percent': round(on_time / total * 100, 2) if total else 0,
        'total': total,
        'on_time': on_time,
        'delayed': delayed,
    }


def delay_factors(project_id: int) -> list:
    """Aggregate delay codes - ponytail: no delay_code field yet, placeholder"""
    # ponytail: delay_code not in model yet, return empty for now
    # Add field when GHP parser extracts it
    return []


def hourly_delays(project_id: int) -> dict:
    """Delays by hour - ponytail: parse ATD hour, count delays"""
    flights = ScheduleVersion.objects.filter(
        project_id=project_id,
        operational_flag=True,
        is_active=True,
    )
    
    hourly = {h: 0 for h in range(24)}
    
    for f in flights:
        if f.std and f.atd:
            std_min = f.std.hour * 60 + f.std.minute
            atd_min = f.atd.hour * 60 + f.atd.minute
            if atd_min - std_min > 1:
                hourly[f.atd.hour] += 1
    
    return hourly
