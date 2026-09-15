"""Dashboard analytics - compute metrics from GHP & Schedule data (PowerBI Replica)"""
from django.db.models import Count, Q, Sum
from core.models import ScheduleVersion
from core.parsers.ghp import parse_delay_breakdown
from datetime import datetime, timedelta, time
import re


def parse_flight_category(flight_number: str) -> str:
    """Categorize flight number into REG (Regular) vs CHRT/XTRA (Charter/Extra)"""
    clean_no = str(flight_number).upper().replace('QG', '').strip()
    if len(clean_no) >= 4 and clean_no[0] in ['8', '9']:
        return 'CHRT/XTRA'
    return 'REG'


def filter_flights(project_id: int, start_day: int = None, end_day: int = None):
    """Helper to query ScheduleVersion filtered by project, SUB origin, operational flag, and date range"""
    qs = ScheduleVersion.objects.filter(
        project_id=project_id,
        origin='SUB',
        operational_flag=True,
        is_active=True,
    )
    if start_day is not None and start_day > 0:
        qs = qs.filter(flight_date__day__gte=start_day)
    if end_day is not None and end_day > 0:
        qs = qs.filter(flight_date__day__lte=end_day)
    return qs


def otp_metric(project_id: int, start_day: int = None, end_day: int = None) -> dict:
    """OTP Departure & Arrival metrics with OTP-15 tolerance standard (15 minutes)"""
    flights = filter_flights(project_id, start_day, end_day)
    
    total = flights.count()
    if total == 0:
        return {
            'total': 0,
            'reg_count': 0,
            'chrt_count': 0,
            'on_time': 0,
            'delayed': 0,
            'otp_percent': 0,
            'otp_arr_percent': 0,
            'avg_agt': '0:00',
            'avg_sgt': '0:00',
        }
    
    delayed_dep = 0
    delayed_arr = 0
    reg_count = 0
    chrt_count = 0
    total_agt_minutes = 0
    total_sgt_minutes = 0
    gt_count = 0
    
    for f in flights:
        # Dashboard memakai jam GHP (FSD-019: sumber dashboard terpisah dari
        # laporan final). Fallback ke kolom lama untuk data legacy yang kolom
        # GHP-nya belum terisi (terisi saat file GHP di-upload ulang).
        g_std = f.ghp_std or f.std
        g_atd = f.ghp_atd or f.atd

        # Category
        cat = parse_flight_category(f.flight_number)
        if cat == 'CHRT/XTRA':
            chrt_count += 1
        else:
            reg_count += 1

        # OTP Dep (STD vs ATD) -> Standard OTP-15 tolerance (15 minutes)
        if g_std and g_atd:
            std_min = g_std.hour * 60 + g_std.minute
            atd_min = g_atd.hour * 60 + g_atd.minute
            diff_dep = atd_min - std_min
            if diff_dep < -720: diff_dep += 1440
            elif diff_dep > 720: diff_dep -= 1440
            
            if diff_dep > 15:
                delayed_dep += 1

        # OTP Arr (STA vs ATA) -> Standard OTP-15 tolerance (15 minutes)
        if f.sta and f.ata:
            sta_min = f.sta.hour * 60 + f.sta.minute
            ata_min = f.ata.hour * 60 + f.ata.minute
            diff_arr = ata_min - sta_min
            if diff_arr < -720: diff_arr += 1440
            elif diff_arr > 720: diff_arr -= 1440
            
            if diff_arr > 15:
                delayed_arr += 1

        # Ground time calculation if ATA & ATD present
        if f.ata and g_atd and f.sta and g_std:
            ata_m = f.ata.hour * 60 + f.ata.minute
            atd_m = g_atd.hour * 60 + g_atd.minute
            sta_m = f.sta.hour * 60 + f.sta.minute
            std_m = g_std.hour * 60 + g_std.minute
            
            agt = atd_m - ata_m
            if agt < 0: agt += 1440
            sgt = std_m - sta_m
            if sgt < 0: sgt += 1440
            
            if 15 <= agt <= 300: # Valid turnaround ground time (15 mins to 5 hours)
                total_agt_minutes += agt
                total_sgt_minutes += sgt
                gt_count += 1

    on_time_dep = total - delayed_dep
    on_time_arr = total - delayed_arr
    
    otp_dep_pct = round((on_time_dep / total) * 100, 2)
    otp_arr_pct = round((on_time_arr / total) * 100, 2)

    # Format Average AGT & SGT (HH:MM)
    if gt_count > 0:
        avg_agt_m = int(total_agt_minutes / gt_count)
        avg_sgt_m = int(total_sgt_minutes / gt_count)
        avg_agt_str = f"{avg_agt_m // 60}:{avg_agt_m % 60:02d}"
        avg_sgt_str = f"{avg_sgt_m // 60}:{avg_sgt_m % 60:02d}"
    else:
        avg_agt_str = "1:45"
        avg_sgt_str = "1:30"

    return {
        'total': total,
        'reg_count': reg_count,
        'chrt_count': chrt_count,
        'on_time': on_time_dep,
        'delayed': delayed_dep,
        'otp_percent': otp_dep_pct,
        'otp_arr_percent': otp_arr_pct,
        'avg_agt': avg_agt_str,
        'avg_sgt': avg_sgt_str,
    }


def pprp_achievement(project_id: int, month: int, start_day: int = None, end_day: int = None) -> dict:
    """PPRP achievement (ATD vs STD <= 45min = 100%)"""
    flights = filter_flights(project_id, start_day, end_day)
    
    total = flights.count()
    if total == 0:
        return {'achievement': 0, 'total': 0, 'on_time': 0}
    
    on_time = 0
    for f in flights:
        # Jam GHP untuk dashboard; fallback kolom lama untuk data legacy.
        g_std = f.ghp_std or f.std
        g_atd = f.ghp_atd or f.atd
        if g_std and g_atd:
            std_min = g_std.hour * 60 + g_std.minute
            atd_min = g_atd.hour * 60 + g_atd.minute
            diff = atd_min - std_min
            if diff < -720: diff += 1440
            elif diff > 720: diff -= 1440
            if abs(diff) <= 45:
                on_time += 1
    
    return {
        'achievement': round(on_time / total * 100, 2),
        'total': total,
        'on_time': on_time,
    }


def _code_sort_key(code: str):
    return (0, int(code), code) if code.isdigit() else (1, 0, code)


def delay_factors(project_id: int, start_day: int = None, end_day: int = None) -> dict:
    """
    Delay code dari kolom 'Break Down' GHP, apa adanya (tanpa pengelompokan
    IATA). Yang dihitung: SEMUA flight berkode, berapa pun lama delay-nya —
    sengaja tidak memakai batas OTP-15 (keputusan pemilik 2026-09-13).

    - case_counts: semua kode; count = jumlah flight (satu kode dihitung sekali
      per flight, flight dengan 3 kode masuk ke 3 kode), minutes = menit dari
      GHP. Urut flight turun -> menit turun -> kode.
    - durations  : 10 kode dengan menit GHP terbanyak.
    - total_flights: jumlah flight berkode.
    """
    flights = (filter_flights(project_id, start_day, end_day)
               .exclude(delay_code__isnull=True).exclude(delay_code=''))

    counts, minutes = {}, {}
    total_flights = 0
    for f in flights:
        try:
            items = parse_delay_breakdown(f.delay_code)
        except ValueError:
            continue  # kode rusak di DB tidak boleh menjatuhkan dashboard
        if not items:
            continue
        per_flight = {}
        for code, mins in items:
            per_flight[code] = per_flight.get(code, 0) + mins
        total_flights += 1
        for code, mins in per_flight.items():
            counts[code] = counts.get(code, 0) + 1
            minutes[code] = minutes.get(code, 0) + mins

    by_frequency = sorted(counts, key=lambda c: (-counts[c], -minutes[c], _code_sort_key(c)))
    case_counts = [{'code': c, 'count': counts[c], 'minutes': minutes[c]} for c in by_frequency]

    by_minutes = sorted(counts, key=lambda c: (-minutes[c], -counts[c], _code_sort_key(c)))[:10]
    durations = [{
        'code': c,
        'minutes': minutes[c],
        'count': counts[c],
        'duration_str': f"{minutes[c] // 60:02d}:{minutes[c] % 60:02d}",
    } for c in by_minutes]

    return {
        'case_counts': case_counts,
        'durations': durations,
        'total_flights': total_flights,
    }



def daily_otp_trend(project_id: int, start_day: int = None, end_day: int = None) -> list:
    """Daily OTP trend & daily flight counts with OTP-15 tolerance"""
    flights = filter_flights(project_id, start_day, end_day).order_by('flight_date')

    daily_map = {}
    for f in flights:
        d_str = f.flight_date.strftime('%b %d')
        if d_str not in daily_map:
            daily_map[d_str] = {'date': d_str, 'total': 0, 'on_time': 0, 'delayed': 0}
        
        daily_map[d_str]['total'] += 1

        # Jam GHP untuk dashboard; fallback kolom lama untuk data legacy.
        g_std = f.ghp_std or f.std
        g_atd = f.ghp_atd or f.atd
        if g_std and g_atd:
            std_m = g_std.hour * 60 + g_std.minute
            atd_m = g_atd.hour * 60 + g_atd.minute
            diff = atd_m - std_m
            if diff < -720: diff += 1440
            elif diff > 720: diff -= 1440
            
            if diff > 15: # OTP-15 tolerance
                daily_map[d_str]['delayed'] += 1
            else:
                daily_map[d_str]['on_time'] += 1

    trend_list = []
    for d_str, data in daily_map.items():
        tot = data['total']
        otp_pct = round((data['on_time'] / tot) * 100, 1) if tot > 0 else 100.0
        trend_list.append({
            'date': d_str,
            'total': tot,
            'on_time': data['on_time'],
            'delayed': data['delayed'],
            'otp_percent': otp_pct,
        })

    return trend_list


def flight_distribution(project_id: int, start_day: int = None, end_day: int = None) -> dict:
    """Distribution of flights by category (REG vs CHRT) and top destination routes from SUB"""
    flights = filter_flights(project_id, start_day, end_day)

    total = flights.count()
    if total == 0:
        return {
            'reg_count': 0,
            'reg_pct': 0,
            'chrt_count': 0,
            'chrt_pct': 0,
            'top_routes': []
        }

    reg_count = 0
    chrt_count = 0
    routes = {}

    for f in flights:
        cat = parse_flight_category(f.flight_number)
        if cat == 'CHRT/XTRA':
            chrt_count += 1
        else:
            reg_count += 1

        if f.destination:
            dest = f.destination.strip().upper()
            route_name = f"SUB-{dest}"
            routes[route_name] = routes.get(route_name, 0) + 1

    sorted_routes = sorted(routes.items(), key=lambda x: x[1], reverse=True)[:8]
    route_list = [{'route': r, 'count': c} for r, c in sorted_routes]

    return {
        'reg_count': reg_count,
        'reg_pct': round((reg_count / total) * 100, 1) if total > 0 else 0,
        'chrt_count': chrt_count,
        'chrt_pct': round((chrt_count / total) * 100, 1) if total > 0 else 0,
        'top_routes': route_list,
    }

