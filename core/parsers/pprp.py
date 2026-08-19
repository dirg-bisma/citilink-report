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


def detect_pprp_period(pdf_path: str) -> tuple[int, int]:
    """Detect month and year from PPRP PDF letter date or schedule date"""
    data = parse_pprp(pdf_path)
    if data.get('pprp_date'):
        d = data['pprp_date']
        return d.month, d.year
    # fallback: scan for Indonesian dates in text
    with pdfplumber.open(pdf_path) as pdf:
        full_text = '\n'.join((page.extract_text() or '') for page in pdf.pages)
        months_pattern = '|'.join(_MONTHS_ID.keys())
        date_match = re.search(r'\b(\d{1,2})\s+(' + months_pattern + r')\s+(\d{4})\b', full_text)
        if date_match:
            month = _MONTHS_ID[date_match.group(2)]
            year = int(date_match.group(3))
            return month, year
    raise ValueError("Tidak dapat mendeteksi tanggal periode pada file PPRP PDF.")


def parse_pprp(pdf_path: str) -> Dict:
    """
    Extract letter metadata dan schedule baru (MENJADI) dari PDF PPRP.

    Returns:
        Dict berisi:
            - letter_number (str): Nomor surat PPRP baru
            - submission_type (str): Tipe permohonan (Perubahan / Perpanjangan / Penambahan / Pengurangan)
            - pprp_date (date|None): Tanggal mulai berlaku PPRP (dari MENJADI)
            - flights (list): Daftar jadwal penerbangan dari bagian MENJADI
              Setiap item: {flight_number, origin, destination, std, sta, day_pattern, pprp_date, end_date}
    """
    with pdfplumber.open(pdf_path) as pdf:
        full_text = '\n'.join(
            (page.extract_text() or '') for page in pdf.pages
        )

    # --- 1. Nomor Surat & Tipe Permohonan ---
    letter_match = re.search(r'Nomor\s*:\s*([A-Z0-9./\-]+)', full_text)
    letter_number = letter_match.group(1).strip() if letter_match else ''

    hal_match = re.search(r'Hal\s*:\s*([^\n]+)', full_text)
    submission_type = 'Perubahan'
    if hal_match:
        first_word = hal_match.group(1).strip().split()[0]
        if first_word.lower() in ['perubahan', 'perpanjangan', 'penambahan', 'pengurangan', 'pencabutan']:
            submission_type = first_word.capitalize()

    # --- 2. Isolasi bagian MENJADI ---
    menjadi_idx = full_text.rfind('MENJADI')
    if menjadi_idx == -1:
        return {
            'letter_number': letter_number,
            'submission_type': submission_type,
            'pprp_date': None,
            'flights': [],
        }

    menjadi_text = full_text[menjadi_idx:]

    # --- 3. Parse setiap baris flight dari MENJADI ---
    flight_pattern = re.compile(
        r'([A-Z]{3}-[A-Z]{3})\s+'       # Rute: BTH-SUB
        r'\d+\s+\d+\s+'                  # Tipe pesawat + kapasitas
        r'(QG\d+)\s+'                    # Nomor flight: QG948
        r'(\d{2}:\d{2})\s+'              # STD (UTC)
        r'(\d{2}:\d{2})\s+'              # STA (UTC)
        r'(\d{7}|(?:[1-7-]{7}))\s+'      # Day pattern: 1234567 or -2-4-6-
        r'[^\n]*?'                       # Frekuensi / VV (skip)
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
        day_pattern = m.group(5)        # e.g. "1234567"
        start_date_str = m.group(6)     # e.g. "13 Juli 2026"
        end_date_str = m.group(7)       # e.g. "24 Oktober 2026"

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
            'day_pattern': day_pattern,
            'pprp_date': pprp_start,   # Tanggal mulai berlaku
            'end_date': pprp_end,      # Tanggal akhir berlaku (akhir musim)
        })

    # Tanggal PPRP keseluruhan = tanggal mulai paling awal dari semua flight
    overall_pprp_date = min(
        (f['pprp_date'] for f in flights), default=None
    )

    return {
        'letter_number': letter_number,
        'submission_type': submission_type,
        'pprp_date': overall_pprp_date,
        'flights': flights,
    }
