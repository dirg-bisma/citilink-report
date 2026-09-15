"""GHP Parser - extract operational data from Excel"""
import pandas as pd
import re
from typing import List, Dict, Tuple


def detect_ghp_period(excel_path: str) -> int:
    """Detect month from GHP Excel date column (DD/MM)"""
    df = pd.read_excel(excel_path, header=None)
    for idx, row in df.iterrows():
        if idx < 7:
            continue
        date_str = row[0]
        if pd.isna(date_str):
            continue
        date_parts = str(date_str).strip().split('/')
        if len(date_parts) >= 2:
            try:
                month = int(date_parts[1])
                if 1 <= month <= 12:
                    return month
            except (ValueError, TypeError):
                continue
    raise ValueError("Tidak dapat mendeteksi bulan pada file GHP Excel.")


def detect_ghp_range(excel_path: str):
    """
    Rentang tanggal yang DICAKUP file GHP, dari judul laporannya:
    'SUB - Ground Handling Punctuality (01/08/2026 - 25/08/2026 - Detail)'
    -> (date(2026,8,1), date(2026,8,25)). Dipakai laporan untuk membedakan
    'tidak terbang' (0) dari 'belum ada datanya' (sel kosong): tanggal di
    luar rentang ini tidak boleh dibaca sebagai realisasi apa pun.
    None bila judul tidak memuat rentang.
    """
    from datetime import datetime
    df = pd.read_excel(excel_path, header=None, nrows=3)
    for idx in range(min(3, len(df))):
        for val in df.iloc[idx].tolist():
            if pd.isna(val):
                continue
            m = re.search(r'(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})', str(val))
            if m:
                return (datetime.strptime(m.group(1), '%d/%m/%Y').date(),
                        datetime.strptime(m.group(2), '%d/%m/%Y').date())
    return None


_BREAKDOWN_ITEM = re.compile(r'^(\d{1,3}):(\d{2})/([0-9A-Z]{1,3})$')


def parse_delay_breakdown(text) -> List[Tuple[str, int]]:
    """
    Kolom 'Break Down' GHP -> daftar (kode, menit), urutan sesuai file.
    '00:04/63,00:19/80' -> [('63', 4), ('80', 19)]. Teks kosong -> [].
    Format tidak dikenal -> ValueError (pemanggil yang memutuskan nasibnya).
    """
    if text is None:
        return []
    clean = re.sub(r'\s+', '', str(text))
    if not clean:
        return []
    items = []
    for part in clean.split(','):
        m = _BREAKDOWN_ITEM.match(part)
        if not m:
            raise ValueError(f"Format Break Down tidak dikenal: {text!r}")
        items.append((m.group(3), int(m.group(1)) * 60 + int(m.group(2))))
    return items


def parse_ghp(excel_path: str, year: int = 2026) -> List[Dict]:
    """Extract normalized operational records from GHP Excel.
    year: tahun untuk kolom tanggal DD/MM (file GHP tidak memuat tahun)."""
    df = pd.read_excel(excel_path, header=None)
    
    records = []
    for idx, row in df.iterrows():
        if idx < 7:  # Skip header rows
            continue
        
        date_str = row[0]
        route_str = row[1]
        aircraft = row[3]
        std = row[6]  # Scheduled departure
        atd = row[9]  # Actual departure
        
        if pd.isna(date_str) or pd.isna(route_str):
            continue
        
        # Parse flight number from route string
        flight_matches = re.findall(r'QG\d+', str(route_str))
        if not flight_matches:
            continue
            
        # Parse route: extract 3-letter codes
        routes = re.findall(r'\b([A-Z]{3})\b', str(route_str))
        if len(routes) < 2:
            continue
            
        # Jika ada multileg (misal: QG435 -QG486 /BPN -SUB -BDJ)
        # flight_matches = ['QG435', 'QG486']
        # routes = ['BPN', 'SUB', 'BDJ']
        # Pasangkan masing-masing flight dengan rutenya
        legs = []
        for i in range(min(len(flight_matches), len(routes) - 1)):
            legs.append({
                'flight': flight_matches[i],
                'origin': routes[i],
                'dest': routes[i+1]
            })
        
        # Parse date: "01/04" -> tahun dari parameter (file hanya memuat DD/MM)
        date_parts = str(date_str).split('/')
        if len(date_parts) == 2:
            day, month = date_parts
            flight_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        else:
            continue
        
        # Kolom 14 'Break Down' (DURASI/KODE) milik keberangkatan dari stasiun
        # tengah = flight TERAKHIR di baris; flight pertama (datang ke stasiun
        # itu) tidak boleh ikut menerima kodenya. Format tidak dikenal tidak
        # menggagalkan upload: kodenya dikosongkan dan teks mentahnya dibawa
        # sebagai peringatan.
        raw_breakdown = row[14] if len(row) > 14 and pd.notna(row[14]) else ''
        delay_code, delay_code_invalid = '', ''
        try:
            if parse_delay_breakdown(raw_breakdown):
                delay_code = re.sub(r'\s+', '', str(raw_breakdown))
        except ValueError:
            delay_code_invalid = str(raw_breakdown).strip()

        for i, leg in enumerate(legs):
            is_last = i == len(legs) - 1
            records.append({
                'flight_number': leg['flight'],
                'origin': leg['origin'],
                'destination': leg['dest'],
                'flight_date': flight_date,
                'std': str(std) if pd.notna(std) else '',
                'atd': str(atd) if pd.notna(atd) else '',
                'aircraft': str(aircraft) if pd.notna(aircraft) else '',
                'delay_code': delay_code if is_last else '',
                'delay_code_invalid': delay_code_invalid if is_last else '',
            })
    
    return records
