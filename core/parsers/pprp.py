"""PPRP Parser - extract schedule changes from official letter PDF (format Citilink S26)

Format PDF PPRP:
- Halaman 1: Nomor surat, tanggal surat
- Halaman terakhir-1 (SEMULA): jadwal lama
- Halaman terakhir (MENJADI): jadwal baru yang berlaku

Dari bagian MENJADI, kita ekstrak:
- Nomor surat PPRP baru
- Untuk setiap flight: nomor, rute, STD, STA, tanggal mulai berlaku, tanggal akhir berlaku
"""
import pdfplumber
import re
from datetime import datetime, date
from typing import List, Dict, Optional


# Mapping nama bulan Indonesia -> angka
_MONTHS_ID = {
    'Januari': 1, 'Februari': 2, 'Maret': 3, 'April': 4,
    'Mei': 5, 'Juni': 6, 'Juli': 7, 'Agustus': 8,
    'September': 9, 'Oktober': 10, 'November': 11, 'Desember': 12,
}


def _parse_id_date(date_str: str) -> Optional[date]:
    """Parse tanggal format Indonesia: '13 Juli 2026' -> date(2026, 7, 13)"""
    date_str = date_str.strip()
    parts = date_str.split()
    if len(parts) != 3:
        return None
    try:
        day = int(parts[0])
        month = _MONTHS_ID.get(parts[1])
        year = int(parts[2])
        if not month:
            return None
        return date(year, month, day)
    except (ValueError, TypeError):
        return None


def parse_pprp(pdf_path: str) -> Dict:
    """
    Extract letter metadata dan schedule baru (MENJADI) dari PDF PPRP.

    Returns:
        Dict berisi:
            - letter_number (str): Nomor surat PPRP baru
            - pprp_date (date|None): Tanggal mulai berlaku PPRP (dari MENJADI)
            - flights (list): Daftar jadwal penerbangan dari bagian MENJADI
              Setiap item: {flight_number, origin, destination, std, sta, pprp_date, end_date}
    """
    with pdfplumber.open(pdf_path) as pdf:
        full_text = '\n'.join(
            (page.extract_text() or '') for page in pdf.pages
        )

    # --- 1. Nomor Surat ---
    # Contoh: "Nomor :AU.012/46/25/DJPU-DAU-2026"
    letter_match = re.search(r'Nomor\s*:\s*([A-Z0-9./\-]+)', full_text)
    letter_number = letter_match.group(1).strip() if letter_match else ''

    # --- 2. Isolasi bagian MENJADI ---
    # Cari posisi kata MENJADI terakhir (biasanya ada di halaman paling akhir)
    menjadi_idx = full_text.rfind('MENJADI')
    if menjadi_idx == -1:
        return {
            'letter_number': letter_number,
            'pprp_date': None,
            'flights': [],
        }

    menjadi_text = full_text[menjadi_idx:]

    # --- 3. Parse setiap baris flight dari MENJADI ---
    # Format baris per penerbangan (UTC):
    # BTH-SUB 320 180 QG949 05:20 07:45 1234567 7X VV / 7X 13 Juli 2026
    # 24 Oktober 2026
    # atau tanpa "VV / 7X":
    # SUB-BTH 320 180 QG948 02:25 04:50 1234567 7X 13 Juli 2026
    # 24 Oktober 2026
    #
    # Pattern: RUTE TIPE KAPASITAS FLIGHT_NO STD STA DAY_PATTERN FREKUENSI [VV/...] START_DATE \n END_DATE

    # Regex yang robust untuk semua variasi format
    flight_pattern = re.compile(
        r'([A-Z]{3}-[A-Z]{3})\s+'       # Rute: BTH-SUB
        r'\d+\s+\d+\s+'                  # Tipe pesawat + kapasitas
        r'(QG\d+)\s+'                    # Nomor flight: QG948
        r'(\d{2}:\d{2})\s+'              # STD (UTC)
        r'(\d{2}:\d{2})\s+'              # STA (UTC)
        r'\d{7}[^\n]*?'                  # Day pattern + frekuensi (skip)
        r'(\d{1,2}\s+\w+\s+\d{4})'      # Tanggal mulai berlaku
        r'\s*\n\s*'                      # Newline
        r'(\d{1,2}\s+\w+\s+\d{4})',     # Tanggal akhir berlaku
        re.DOTALL
    )

    flights = []
    for m in flight_pattern.finditer(menjadi_text):
        route_str = m.group(1)          # e.g. "BTH-SUB"
        flight_number = m.group(2)      # e.g. "QG948"
        std = m.group(3)                # e.g. "02:25"
        sta = m.group(4)                # e.g. "04:50"
        start_date_str = m.group(5)     # e.g. "13 Juli 2026"
        end_date_str = m.group(6)       # e.g. "24 Oktober 2026"

        # Parse rute
        route_parts = route_str.split('-')
        if len(route_parts) != 2:
            continue
        origin, destination = route_parts[0], route_parts[1]

        # Parse tanggal
        pprp_start = _parse_id_date(start_date_str)
        pprp_end = _parse_id_date(end_date_str)

        if not pprp_start or not pprp_end:
            continue

        flights.append({
            'flight_number': flight_number,
            'origin': origin,
            'destination': destination,
            'std': std,
            'sta': sta,
            'pprp_date': pprp_start,   # Tanggal mulai berlaku
            'end_date': pprp_end,      # Tanggal akhir berlaku (akhir musim)
        })

    # Tanggal PPRP keseluruhan = tanggal mulai paling awal dari semua flight
    overall_pprp_date = min(
        (f['pprp_date'] for f in flights), default=None
    )

    return {
        'letter_number': letter_number,
        'pprp_date': overall_pprp_date,
        'flights': flights,
    }
