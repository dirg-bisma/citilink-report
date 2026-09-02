"""WTT Parser - extract flights from Working Time Table PDF"""
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


WATERMARK_SIZE = 20   # teks jadwal ~8pt; watermark diagonal halaman ~60-73pt
COLUMN_GAP = 40       # celah antar kolom From/To jauh lebih lebar dari spasi antar kata


def _extract_lines(page, tol: float = 3) -> List[List[Dict]]:
    """
    Kelompokkan kata menjadi baris visual, urut kiri-ke-kanan.

    - Huruf watermark raksasa dibuang; `extra_attrs=['size']` juga mencegahnya
      menempel ke teks asli (tanpa itu 'BDJ' bisa terbaca 'FBDJ').
    - Toleransi vertikal dipakai karena kata dalam satu baris bisa berbeda
      beberapa pt (mis. 164.25 vs 165.09) dan akan terpecah bila dibandingkan persis.
    """
    words = [w for w in page.extract_words(extra_attrs=['size'])
             if w.get('size', 0) <= WATERMARK_SIZE]

    lines, current, ref_top = [], [], None
    for w in sorted(words, key=lambda x: (x['top'], x['x0'])):
        if ref_top is not None and abs(w['top'] - ref_top) > tol:
            lines.append(sorted(current, key=lambda x: x['x0']))
            current, ref_top = [], None
        if ref_top is None:
            ref_top = w['top']
        current.append(w)
    if current:
        lines.append(sorted(current, key=lambda x: x['x0']))
    return lines


def _detect_to_column(lines: List[List[Dict]], half_width: float):
    """Posisi x kolom 'To' dari baris header 'From ... To ... Return From ... To'."""
    for words in lines:
        labels = [w for w in words if w['x0'] < half_width and w['text'] in ('From', 'To')]
        if len(labels) >= 2 and labels[0]['text'] == 'From' and labels[1]['text'] == 'To':
            return labels[1]['x0']
    return None


def _split_columns(words: List[Dict], to_col_x: float):
    """
    Pisahkan kata satu baris header menjadi (bagian From, bagian To).

    Pemisahnya adalah celah horizontal lebar antar kolom — bukan pola teks —
    supaya nama bandara yang mengandung kata 3 huruf ('...NGURAH RAI DPS')
    tidak salah dibaca sebagai dua kolom. Bila tidak ada celah lebar, seluruh
    baris milik satu kolom saja (header yang hanya mengganti tujuan).
    """
    split_at, widest = None, 0
    for i in range(1, len(words)):
        gap = words[i]['x0'] - words[i - 1]['x1']
        if gap > widest:
            split_at, widest = i, gap
    if widest > COLUMN_GAP:
        return words[:split_at], words[split_at:]
    return ([], words) if words[0]['x0'] >= to_col_x - 25 else (words, [])


def _trailing_iata(words: List[Dict]):
    """Kode IATA bandara = token terakhir kolom, mis. '...PRANOTO AAP' -> 'AAP'."""
    if words and re.fullmatch(r'[A-Z]{3}', words[-1]['text']):
        return words[-1]['text']
    return None


def parse_wtt(pdf_path: str) -> List[Dict]:
    """
    Extract normalized flight records from WTT PDF.

    Tiap halaman punya 4 kolom: From | To | Return From | To. Hanya separuh
    kiri (leg berangkat) yang dibaca; separuh kanan adalah leg baliknya, yang
    selalu muncul lagi sebagai blok kirinya sendiri di halaman lain.

    Satu halaman bisa memuat beberapa station: header dengan bagian From baru
    mengganti bandara asal, header tanpa bagian From hanya mengganti tujuan.
    Pembagian kolom memakai koordinat x agar pergantian station di tengah
    halaman terbaca benar (dulu asal terkunci pada header pertama, sehingga
    penerbangan station lain ikut terlabeli SUB).
    """
    records = []
    flight_row_regex = r'^(\d{1,2}\s+[A-Za-z]+)\s*-\s*(\d{1,2}\s+[A-Za-z]+)\s+([0-9\s-]{7,9})\s+(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})\s+(QG\d+[A-Z]?)\s+(\d{3})\s+Non stop'

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Tanggal berlaku halaman dipakai untuk menentukan tahun dokumen
            full_text = page.extract_text()
            if not full_text:
                continue

            date_match = re.search(r'(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})', full_text)
            if not date_match:
                continue
            year = datetime.strptime(date_match.group(1), '%d/%m/%Y').year

            half_width = page.width / 2
            lines = _extract_lines(page)
            to_col_x = _detect_to_column(lines, half_width)
            if to_col_x is None:
                continue

            origin_code = None
            dest_code = None

            for words in lines:
                left = [w for w in words if w['x0'] < half_width]
                if not left:
                    continue
                line_str = ' '.join(w['text'] for w in left).strip()

                m_flight = re.match(flight_row_regex, line_str)
                if m_flight:
                    if not origin_code or not dest_code:
                        # Bandara asal/tujuan belum terbaca — jangan menebak
                        continue

                    try:
                        flight_start = parse_flight_date(m_flight.group(1), year)
                        flight_end = parse_flight_date(m_flight.group(2), year)
                    except ValueError:
                        continue

                    std, sta = m_flight.group(4), m_flight.group(5)
                    for date in expand_dates(flight_start, flight_end, m_flight.group(3)):
                        records.append({
                            'flight_number': m_flight.group(6),
                            'origin': origin_code,
                            'destination': dest_code,
                            'flight_date': date.strftime('%Y-%m-%d'),
                            'std': std,
                            'sta': sta,
                            'aircraft': m_flight.group(7),
                            'atd': std,
                            'ata': sta,
                        })
                    continue

                # Baris header: perbarui asal dan/atau tujuan. Bagian yang ada
                # tapi kodenya tak terbaca di-set None supaya baris di bawahnya
                # dilewati, bukan memakai kode station sebelumnya.
                from_part, to_part = _split_columns(left, to_col_x)
                if from_part:
                    origin_code = _trailing_iata(from_part)
                if to_part:
                    dest_code = _trailing_iata(to_part)

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
