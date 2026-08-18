"""WTT Parser - extract flights from Working Time Table PDF"""
import pdfplumber
import re
from datetime import datetime, timedelta
from typing import List, Dict


def parse_wtt(pdf_path: str) -> List[Dict]:
    """Extract normalized flight records from WTT PDF"""
    records = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            
            # Date range
            date_match = re.search(r'(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})', text)
            if not date_match:
                continue
            
            start_date = datetime.strptime(date_match.group(1), '%d/%m/%Y')
            end_date = datetime.strptime(date_match.group(2), '%d/%m/%Y')
            
            # Extract all flights: match flight_no + times anywhere in line
            # ponytail: single regex, no state machine
            for match in re.finditer(
                r'(QG\d+)\s+(\d{3})\s+Non stop',
                text
            ):
                flight_no = match.group(1)
                aircraft = match.group(2)
                
                # Find times before this flight
                line_start = text.rfind('\n', 0, match.start()) + 1
                prefix = text[line_start:match.start()]
                times = re.findall(r'(\d{1,2}:\d{2})', prefix)
                if len(times) < 2:
                    continue
                std, sta = times[-2], times[-1]
                
                # Find date pattern
                pattern_match = re.search(r'([0-9-]{7})', prefix)
                if not pattern_match:
                    continue
                pattern = pattern_match.group(1)
                
                # Find route: nearest 3-letter codes before this flight
                route_codes = re.findall(r'\b([A-Z]{3})\b', text[max(0, line_start-1000):match.start()])
                if len(route_codes) < 2:
                    continue
                origin, dest = route_codes[-2], route_codes[-1]
                
                for date in expand_dates(start_date, end_date, pattern):
                    records.append({
                        'flight_number': flight_no,
                        'origin': origin,
                        'destination': dest,
                        'flight_date': date.strftime('%Y-%m-%d'),
                        'std': std,
                        'sta': sta,
                        'aircraft': aircraft,
                        'atd': std,
                        'ata': sta,
                    })
    
    return records


def expand_dates(start: datetime, end: datetime, pattern: str) -> List[datetime]:
    """Convert day pattern (1234567 = Mon-Sun) to date list"""
    days = [int(d) if d.isdigit() else 0 for d in pattern]
    dates = []
    current = start
    
    while current <= end:
        weekday = current.weekday() + 1  # 1=Mon, 7=Sun
        if weekday <= len(days) and days[weekday - 1] == weekday:
            dates.append(current)
        current += timedelta(days=1)
    
    return dates
