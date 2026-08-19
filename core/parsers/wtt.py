"""WTT Parser - extract flights from Working Time Table PDF"""
import pdfplumber
import re
from datetime import datetime, timedelta
from typing import List, Dict


import pdfplumber
import re
from datetime import datetime, timedelta
from typing import List, Dict

MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'mei': 5,
    'jun': 6, 'jul': 7, 'aug': 8, 'agt': 8, 'agu': 8, 'sep': 9,
    'oct': 10, 'okt': 10, 'nov': 11, 'dec': 12, 'des': 12
}


def parse_flight_date(date_str: str, year: int) -> datetime:
    """Parse flight date string (e.g. '01 Jul' or '31 Jul') to datetime object"""
    m = re.match(r'(\d{1,2})\s*([A-Za-z]+)', date_str.strip())
    if not m:
        raise ValueError(f"Invalid flight date: {date_str}")
    day = int(m.group(1))
    month_name = m.group(2).lower()[:3]
    month = MONTH_MAP.get(month_name)
    if not month:
        raise ValueError(f"Unknown month name: {month_name}")
    return datetime(year, month, day)


def detect_wtt_period(pdf_path: str) -> tuple[int, int]:
    """Detect month and year from WTT PDF header (e.g. returns (7, 2026))"""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            full_text = page.extract_text()
            if not full_text:
                continue
            date_match = re.search(r'(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})', full_text)
            if date_match:
                page_start_date = datetime.strptime(date_match.group(1), '%d/%m/%Y')
                return page_start_date.month, page_start_date.year
    raise ValueError("Tidak dapat mendeteksi periode (tanggal berlaku) dari file WTT PDF.")


def parse_wtt(pdf_path: str) -> List[Dict]:
    """Extract normalized flight records from WTT PDF (Surabaya Departures only)"""
    records = []
    
    dual_header_regex = r'^(.*?)\b([A-Z]{3})\b\s+(.*?)\b([A-Z]{3})$'
    single_header_regex = r'^(.*?)\b([A-Z]{3})$'
    flight_row_regex = r'^(\d{1,2}\s+[A-Za-z]+)\s*-\s*(\d{1,2}\s+[A-Za-z]+)\s+([0-9\s-]{7,9})\s+(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})\s+(QG\d+[A-Z]?)\s+(\d{3})\s+Non stop'

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # 1. Ambil teks full page terlebih dahulu khusus untuk mencari tanggal berlaku halaman
            full_text = page.extract_text()
            if not full_text:
                continue
                
            date_match = re.search(r'(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})', full_text)
            if not date_match:
                continue
            
            # Mendapatkan tahun aktif dokumen dari tanggal berlaku halaman
            page_start_date = datetime.strptime(date_match.group(1), '%d/%m/%Y')
            year = page_start_date.year
            
            # 2. Crop hanya sisi kiri halaman (Departures dari Surabaya)
            width = page.width
            height = page.height
            left_half = page.crop((0, 0, width / 2, height))
            left_text = left_half.extract_text()
            if not left_text:
                continue
                
            lines = left_text.split('\n')
            
            origin_code = None
            dest_code = None
            has_origin = False
            
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                
                # Cek apakah baris berupa dual header (From & To pertama di halaman)
                if not has_origin:
                    m_dual = re.match(dual_header_regex, line_str)
                    if m_dual:
                        origin_code = m_dual.group(2)
                        dest_code = m_dual.group(4)
                        has_origin = True
                        continue
                
                # Cek apakah baris berupa jadwal penerbangan
                m_flight = re.match(flight_row_regex, line_str)
                if m_flight:
                    if not origin_code or not dest_code:
                        # Skip jika data bandara asal/tujuan belum terdeteksi
                        continue
                        
                    start_date_str = m_flight.group(1)
                    end_date_str = m_flight.group(2)
                    pattern = m_flight.group(3)
                    std = m_flight.group(4)
                    sta = m_flight.group(5)
                    flight_no = m_flight.group(6)
                    aircraft = m_flight.group(7)
                    
                    try:
                        flight_start = parse_flight_date(start_date_str, year)
                        flight_end = parse_flight_date(end_date_str, year)
                    except ValueError:
                        continue
                    
                    for date in expand_dates(flight_start, flight_end, pattern):
                        records.append({
                            'flight_number': flight_no,
                            'origin': origin_code,
                            'destination': dest_code,
                            'flight_date': date.strftime('%Y-%m-%d'),
                            'std': std,
                            'sta': sta,
                            'aircraft': aircraft,
                            'atd': std,
                            'ata': sta,
                        })
                    continue
                
                # Cek apakah baris berupa single header (sub-tujuan berikutnya di bawahnya)
                m_single = re.match(single_header_regex, line_str)
                if m_single:
                    dest_code = m_single.group(2)
                    continue
                    
    return records


def expand_dates(start: datetime, end: datetime, pattern: str) -> List[datetime]:
    """Convert day pattern (1234567 = Mon-Sun) to date list"""
    dates = []
    current = start
    
    while current <= end:
        weekday = current.weekday() + 1  # 1=Mon, 7=Sun
        if str(weekday) in pattern:
            dates.append(current)
        current += timedelta(days=1)
        
    return dates
