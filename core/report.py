"""
Report Generator — Block-Format Excel Injection
================================================
Menginjeksi data dari database ScheduleVersion ke dalam template Excel otoritas
bandara (format blok musiman seperti form_realisasi_winter26.xlsx).

Algoritma:
1. Buka template Excel menggunakan openpyxl (load_workbook, keep_vba=False).
2. Deteksi otomatis koordinat kolom dari header (baris 5-6).
3. Temukan semua "blok flight" dari kolom B (flight number QG-xxx).
4. Untuk setiap flight yang ada di DB:
   a. Jika ada data PPRP -> duplikasi blok ke bawah, isi kolom Periode & Surat baru.
   b. Isi kolom absensi harian (1/0) per bulan dari data GHP (operational_flag).
5. Rebuild nomor urut (kolom A) dan perbaiki rumus SUM di kolom Total Realisasi.
6. Simpan sebagai file baru, kembalikan path-nya.
"""

import re
import calendar
import datetime
import os
import tempfile
from copy import copy
import openpyxl
from openpyxl import load_workbook, Workbook
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.formula.translate import Translator

from core.models import Project, ScheduleVersion
from core.services import _utc_time_to_local, _utc_offset_for_airport


# ---------------------------------------------------------------------------
# Konstanta
# ---------------------------------------------------------------------------

INDONESIAN_MONTHS = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember",
}
MONTH_ABBR = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MEI", 6: "JUN",
    7: "JUL", 8: "AGU", 9: "SEP", 10: "OKT", 11: "NOV", 12: "DES",
}


def _normalize_flight(s):
    """'QG-488' atau 'QG 488' -> 'QG488'."""
    return str(s).replace('-', '').replace(' ', '').upper().strip()


def _pprp_letter_end_date(pdf_path, flight_norm, start_date, cache):
    """
    Ambil tanggal akhir berlaku sebuah segmen PPRP dari PDF surat aslinya
    (tidak tersimpan di DB, hanya ada di file sumber). Segmen dicocokkan
    berdasarkan flight number + tanggal mulai berlaku; fallback ke match
    flight number saja. cache: dict per-run agar satu PDF hanya diparse sekali.
    """
    if not pdf_path or not os.path.exists(pdf_path):
        return None
    if pdf_path not in cache:
        try:
            from core.parsers.pprp import parse_pprp
            cache[pdf_path] = parse_pprp(pdf_path)
        except Exception:
            cache[pdf_path] = None
    parsed = cache[pdf_path]
    if not parsed:
        return None
    fallback = None
    for f in parsed.get('flights', []):
        if _normalize_flight(f['flight_number']) != flight_norm:
            continue
        if start_date and f.get('pprp_date') == start_date:
            return f.get('end_date')
        if fallback is None:
            fallback = f.get('end_date')
    return fallback


def _assign_pprp_periods(fn, fd, pdf_cache):
    """
    Urutkan pprp_list kronologis lalu isi string periode tiap entri:
    - periode_semula hanya pada entri PERTAMA (baseline WTT dipotong sampai
      sehari sebelum PPRP pertama berlaku).
    - periode entri non-terakhir berakhir sehari sebelum entri berikutnya mulai.
    - periode entri TERAKHIR berakhir pada tanggal akhir berlaku di surat PPRP
      (diparse dari PDF); fallback ke tanggal WTT terakhir bila PDF tak terbaca.
    """
    wtt_start = fd.get('wtt_start_date')
    wtt_end = fd.get('wtt_end_date')
    fd['pprp_list'].sort(key=lambda p: p.get('pprp_date') or datetime.date.max)
    plist = fd['pprp_list']
    for i, pprp in enumerate(plist):
        d_pprp = pprp.get('pprp_date')
        pprp['periode_semula'] = ''
        pprp['periode'] = ''
        if not d_pprp:
            continue
        if i == 0 and wtt_start:
            semula_end = d_pprp - datetime.timedelta(days=1)
            pprp['periode_semula'] = (
                f"{wtt_start.day} {MONTH_ABBR[wtt_start.month]} {wtt_start.year}"
                f"/{semula_end.day} {MONTH_ABBR[semula_end.month]} {semula_end.year}"
            )
        if i + 1 < len(plist) and plist[i + 1].get('pprp_date'):
            seg_end = plist[i + 1]['pprp_date'] - datetime.timedelta(days=1)
        else:
            seg_end = _pprp_letter_end_date(
                pprp.get('source_pprp_path'), fn, d_pprp, pdf_cache
            ) or wtt_end
        if seg_end:
            pprp['periode'] = (
                f"{d_pprp.day} {MONTH_ABBR[d_pprp.month]} {d_pprp.year}"
                f"/{seg_end.day} {MONTH_ABBR[seg_end.month]} {seg_end.year}"
            )


def _resolve_menjadi_times(fd, pprp):
    """
    Isi jam final baris MENJADI sesuai aturan sumber data yang dikonfirmasi user:
    - etd_utc: STD dari GHP (Local) dikonversi ke UTC; None (sel kosong) bila
      segmen belum punya data GHP sama sekali.
    - eta    : STA dari surat PPRP, sudah UTC, dipakai apa adanya (key 'sta') —
      GHP tidak memuat jam tiba di bandara tujuan.
    - atd/ata: jam WTT (Local) pada tanggal pertama periode segmen; fallback ke
      tanggal WTT terdekat setelahnya. Bila flight tidak ada di WTT sama sekali
      (rute baru murni dari PPRP): ATD = jam realisasi GHP (Local), ATA = STA
      surat PPRP (UTC) dikonversi Local per zona waktu bandara tujuan.
    """
    ghp_std = pprp.get('ghp_std')
    if ghp_std:
        utc_t = _utc_time_to_local(ghp_std, -_utc_offset_for_airport(fd.get('origin')))
        pprp['etd_utc'] = utc_t.strftime('%H:%M')
    else:
        pprp['etd_utc'] = None

    atd = ata = None
    d = pprp.get('pprp_date')
    v1_times = fd.get('v1_times') or {}
    if d and v1_times:
        if d in v1_times:
            atd, ata = v1_times[d]
        else:
            later = sorted(dt for dt in v1_times if dt >= d)
            if later:
                atd, ata = v1_times[later[0]]

    # Fallback untuk flight tanpa data WTT (rute baru murni dari surat PPRP)
    if atd is None and pprp.get('ghp_atd'):
        atd = pprp['ghp_atd'].strftime('%H:%M')
    if ata is None and pprp.get('sta'):
        try:
            sta_utc = datetime.datetime.strptime(pprp['sta'], '%H:%M').time()
            ata = _utc_time_to_local(
                sta_utc, _utc_offset_for_airport(fd.get('destination'))
            ).strftime('%H:%M')
        except (ValueError, TypeError):
            pass

    pprp['atd'] = atd
    pprp['ata'] = ata


def _build_flight_data(schedules):
    """
    Bangun struktur data per-flight dari iterable ScheduleVersion (harus sudah
    diurutkan flight_number, version_number, flight_date). Dipakai bersama oleh
    generate_report, generate_rekap_report, dan get_project_report_data supaya
    aturan sumber data tidak menyimpang antar keluaran (Excel vs preview HTML).

    flight_data[fn] = {
        'flight_str', 'origin', 'destination',
        'wtt': {std, sta, atd, ata} | None,   # jam WTT record pertama (Local)
        'wtt_start_date' / 'wtt_end_date',    # rentang tanggal WTT
        'pprp_list': [entry per segmen],      # segmen = (surat, tanggal mulai)
        'daily': {(y,m,d): 1|0},              # flag operasional dari GHP
        'v1_times': {date: (std, sta)},       # jam WTT per tanggal (Local)
        'first_seen': datetime | None,        # created_at paling awal (utk rekap)
    }
    """
    flight_data = {}
    for sv in schedules:
        fn = _normalize_flight(sv.flight_number)
        if fn not in flight_data:
            flight_data[fn] = {
                'flight_str': sv.flight_number,
                'origin': sv.origin,
                'destination': sv.destination,
                'wtt': None,
                'wtt_start_date': None,
                'wtt_end_date': None,
                'pprp_list': [],
                'daily': {},
                'v1_times': {},
                'first_seen': None,
            }

        fd = flight_data[fn]
        d = sv.flight_date

        if fd['first_seen'] is None or sv.created_at < fd['first_seen']:
            fd['first_seen'] = sv.created_at

        # Jangan timpa angka 1 dengan 0 jika ada duplikasi versi jadwal
        if sv.operational_flag:
            fd['daily'][(d.year, d.month, d.day)] = 1
        elif (d.year, d.month, d.day) not in fd['daily']:
            fd['daily'][(d.year, d.month, d.day)] = 0

        if sv.version_number == 1 and not sv.pprp_letter:
            # Baris WTT asli — lacak tanggal awal dan akhir musim
            if fd['wtt_start_date'] is None or sv.flight_date < fd['wtt_start_date']:
                fd['wtt_start_date'] = sv.flight_date
            if fd['wtt_end_date'] is None or sv.flight_date > fd['wtt_end_date']:
                fd['wtt_end_date'] = sv.flight_date
            # Metadata WTT (sekali, dari record pertama = tanggal paling awal).
            # ATD/ATA laporan = jam WTT (Local); pakai std/sta v1 yang selalu
            # murni WTT (kolom atd v1 bisa tercemar data GHP lama).
            if not fd['wtt']:
                fd['wtt'] = {
                    'std': sv.std.strftime('%H:%M') if sv.std else None,
                    'sta': sv.sta.strftime('%H:%M') if sv.sta else None,
                    'atd': sv.std.strftime('%H:%M') if sv.std else None,
                    'ata': sv.sta.strftime('%H:%M') if sv.sta else None,
                }
            fd['v1_times'][sv.flight_date] = (
                sv.std.strftime('%H:%M') if sv.std else None,
                sv.sta.strftime('%H:%M') if sv.sta else None,
            )
        elif sv.pprp_letter:
            # Satu entry per SEGMEN (surat + tanggal mulai berlaku) — satu surat
            # bisa memuat >1 segmen jadwal untuk flight yang sama.
            entry = next((p for p in fd['pprp_list']
                          if p['pprp_letter'] == sv.pprp_letter and p['pprp_date'] == sv.pprp_date), None)
            if entry is None:
                fd['pprp_list'].append({
                    'pprp_letter': sv.pprp_letter,
                    'pprp_date': sv.pprp_date,           # tanggal mulai berlaku segmen
                    'periode': '',                        # dihitung _assign_pprp_periods
                    'std': sv.std.strftime('%H:%M') if sv.std else None,
                    'sta': sv.sta.strftime('%H:%M') if sv.sta else None,
                    'ghp_std': sv.ghp_std,                # STD GHP (Local) untuk kolom ETD
                    'ghp_atd': sv.ghp_atd,                # ATD aktual GHP (Local), fallback ATD non-WTT
                    'source_pprp_path': sv.source_pprp.file_path if sv.source_pprp else None,
                    'dates': {sv.flight_date: bool(sv.operational_flag)},
                })
            else:
                entry['dates'][sv.flight_date] = bool(sv.operational_flag)
                # Pakai data GHP dari tanggal paling awal segmen yang memilikinya
                if entry.get('ghp_std') is None and sv.ghp_std:
                    entry['ghp_std'] = sv.ghp_std
                if entry.get('ghp_atd') is None and sv.ghp_atd:
                    entry['ghp_atd'] = sv.ghp_atd

    return flight_data


def _finalize_flight_data(flight_data):
    """Hitung periode & jam final tiap segmen PPRP. Kembalikan cache parse PDF
    (dipakai lagi oleh pemanggil untuk membaca tipe permohonan surat)."""
    pdf_cache = {}
    for fn, fd in flight_data.items():
        _assign_pprp_periods(fn, fd, pdf_cache)
        for pprp in fd['pprp_list']:
            _resolve_menjadi_times(fd, pprp)
    return pdf_cache


def _submission_type_for(pprp, pdf_cache, default='Perubahan'):
    """Tipe permohonan (Perubahan/Perpanjangan/Penambahan/...) dari PDF surat
    segmen tsb — tidak tersimpan di DB, hanya ada di file sumber."""
    pdf_path = pprp.get('source_pprp_path')
    if pdf_path and os.path.exists(pdf_path):
        if pdf_path not in pdf_cache:
            try:
                from core.parsers.pprp import parse_pprp
                pdf_cache[pdf_path] = parse_pprp(pdf_path)
            except Exception:
                pdf_cache[pdf_path] = None
        parsed = pdf_cache[pdf_path]
        if parsed and parsed.get('submission_type'):
            return parsed['submission_type']
    return default


# ---------------------------------------------------------------------------
# Deteksi Kolom Template
# ---------------------------------------------------------------------------

def _detect_columns(ws):
    """
    Deteksi posisi kolom dari template berdasarkan header baris 5-6.
    Kembalikan dict dengan key nama kolom -> nomor kolom (1-indexed).
    Juga deteksi mapping bulan -> kolom_mulai (untuk pengisian harian).
    """
    cols = {
        'no': None,
        'flight': 2,
        'to': 3,
        'etd': 4,
        'eta': 5,
        'atd': 6,
        'ata': 7,
        'periode': 8,
        'surat': 9,
        'tipe': None,
        'hari': 10,
        'bulan_tahun': 13,
        'day_start': None,
        'total': None,
    }
    month_col_map = {}  # {month_num: start_col}

    # Scan baris 2 untuk menemukan nama bulan (kolom harian)
    for c in range(1, ws.max_column + 1):
        v = ws.cell(row=2, column=c).value
        if not v:
            continue
        v_str = str(v).strip().upper()
        for m_num, m_name in INDONESIAN_MONTHS.items():
            if v_str == m_name.upper():
                month_col_map[m_num] = c
                break

    # Scan baris 4-7 untuk mapping kolom metadata (baris terbawah prioritas tertinggi jika ada tumpang tindih)
    for row_idx in [4, 5, 6, 7]:
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row_idx, c).value
            if v is None:
                continue
            v_str = str(v).strip().upper()
            if v_str in ('NO', 'NO.') and cols['no'] is None:
                cols['no'] = c
            elif 'FLT' in v_str and 'NO' in v_str:
                cols['flight'] = c
            elif v_str == 'TO':
                cols['to'] = c
            elif v_str == 'ETD' or v_str == 'STD':
                cols['etd'] = c
            elif v_str == 'ETA' or v_str == 'STA':
                cols['eta'] = c
            elif v_str == 'ATD':
                cols['atd'] = c
            elif v_str == 'ATA':
                cols['ata'] = c
            elif 'PERIODE' in v_str:
                cols['periode'] = c
            elif 'SURAT' in v_str:
                cols['surat'] = c
            elif 'TIPE' in v_str or 'PENGAJUAN' in v_str:
                cols['tipe'] = c
            elif 'DAY' in v_str or 'HARI' in v_str:
                cols['hari'] = c
            elif 'TOTAL' in v_str or 'REALISASI' in v_str:
                cols['total'] = c

    # Kolom hari pertama: cari kolom dengan header angka "1" di baris 6 atau 7
    for row_idx in [6, 7]:
        for c in range(1, ws.max_column + 1):
            v = ws.cell(row_idx, c).value
            if str(v).strip() == '1' or v == 1:
                cols['day_start'] = c
                break
        if cols.get('day_start'):
            break

    if cols['no'] is None:
        cols['no'] = 1

    return cols, month_col_map


# ---------------------------------------------------------------------------
# Find Flight Headers
# ---------------------------------------------------------------------------

def _find_flight_headers(ws, col_flight):
    """
    Temukan semua baris awal 'blok flight' di kolom B (flight).
    Return list of (row_num, flight_str_normalized).
    Setiap blok flight mencakup beberapa baris (satu per bulan musim).
    """
    headers = []
    last_flight = None
    for r in range(1, ws.max_row + 1):
        v = ws.cell(r, col_flight).value
        if v is None:
            last_flight = None
            continue
        v_str = str(v).strip()
        norm = _normalize_flight(v_str)
        # Hanya ambil baris pertama dari masing-masing flight number
        if re.match(r'^QG\d+[A-Z]?$', norm):
            if norm != last_flight:
                headers.append((r, norm, v_str))
                last_flight = norm
        else:
            last_flight = None
    return headers


# ---------------------------------------------------------------------------
# Block Extent
# ---------------------------------------------------------------------------

def _block_end(ws, start, next_start, total_rows):
    """Tentukan baris akhir dari sebuah blok flight."""
    if next_start is not None:
        return next_start - 1
    # Blok terakhir: cari baris kosong pertama (tidak ada data di col 13 / bulan_tahun atau col 2)
    # Biasanya setelah blok flight ada 1-2 baris kosong sebelum Keterangan/Signature
    for r in range(start + 1, total_rows + 1):
        has_data = False
        for c in range(2, 14):
            if ws.cell(r, c).value is not None and str(ws.cell(r, c).value).strip() != '':
                has_data = True
                break
        
        if not has_data:
            return r - 1
            
    return total_rows


# ---------------------------------------------------------------------------
# Copy Row
# ---------------------------------------------------------------------------

def _copy_row(ws, src_row, dst_row):
    """Salin nilai, style, dan tinggi baris dari src ke dst, termasuk menerjemahkan formula."""
    for col in range(1, ws.max_column + 1):
        src = ws.cell(src_row, col)
        dst = ws.cell(dst_row, col)
        
        val = src.value
        if isinstance(val, str) and val.startswith('='):
            try:
                dst.value = Translator(val, src.coordinate).translate_formula(dst.coordinate)
            except Exception:
                dst.value = val
        else:
            dst.value = val
        if src.has_style:
            dst.font = copy(src.font)
            dst.border = copy(src.border)
            dst.fill = copy(src.fill)
            dst.number_format = src.number_format
            dst.protection = copy(src.protection)
            dst.alignment = copy(src.alignment)
    if ws.row_dimensions[src_row].height:
        ws.row_dimensions[dst_row].height = ws.row_dimensions[src_row].height


# ---------------------------------------------------------------------------
# Copy Merged Ranges for Block
# ---------------------------------------------------------------------------

def _copy_merged_ranges_for_block(ws, src_start, dst_start, block_len):
    """Duplikasi seluruh merged ranges yang sepenuhnya berada di dalam blok."""
    to_add = []
    # Kumpulkan range yang akan diduplikasi (menggunakan list untuk menghindari mutasi saat iterasi)
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= src_start and rng.max_row < src_start + block_len:
            offset = dst_start - src_start
            to_add.append((rng.min_row + offset, rng.min_col,
                           rng.max_row + offset, rng.max_col))
    
    for sr, sc, er, ec in to_add:
        # Hindari menduplikasi jika range sudah ada (walau kemungkinannya kecil)
        overlap = False
        for ex_rng in ws.merged_cells.ranges:
            if ex_rng.min_row <= sr and ex_rng.max_row >= er and ex_rng.min_col <= sc and ex_rng.max_col >= ec:
                overlap = True
                break
        if not overlap:
            ws.merge_cells(start_row=sr, start_column=sc, end_row=er, end_column=ec)


# ---------------------------------------------------------------------------
# Shift Merged Ranges
# ---------------------------------------------------------------------------

def _shift_merged_ranges_below(ws, row_idx, amount):
    """Geser koordinat merged cell di bawah row_idx sebanyak amount baris."""
    to_remove = []
    to_add = []
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= row_idx:
            to_remove.append(str(rng))
            to_add.append((rng.min_row + amount, rng.min_col,
                           rng.max_row + amount, rng.max_col))
        elif rng.min_row < row_idx <= rng.max_row:
            to_remove.append(str(rng))
            if rng.min_row < row_idx - 1:
                to_add.append((rng.min_row, rng.min_col,
                               row_idx - 1, rng.max_col))
            to_add.append((row_idx + amount, rng.min_col,
                           rng.max_row + amount, rng.max_col))
    for rng_str in to_remove:
        # Cari dan hapus merged range berdasarkan string (kompatibel semua versi openpyxl)
        for existing_rng in list(ws.merged_cells.ranges):
            if str(existing_rng) == rng_str:
                ws.merged_cells.ranges.discard(existing_rng)
                break
    for sr, sc, er, ec in to_add:
        if sr <= er:
            ws.merge_cells(start_row=sr, start_column=sc,
                           end_row=er, end_column=ec)


# ---------------------------------------------------------------------------
# Shift Formulas
# ---------------------------------------------------------------------------

def _shift_formulas_below(ws, row_idx, amount):
    """Update seluruh formula di bawah row_idx karena ada penyisipan baris."""
    for r in range(row_idx + amount, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            cell = ws.cell(r, c)
            val = cell.value
            if isinstance(val, str) and val.startswith('='):
                old_coord = ws.cell(r - amount, c).coordinate
                try:
                    cell.value = Translator(val, old_coord).translate_formula(cell.coordinate)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Rebuild Totals
# ---------------------------------------------------------------------------

def _rebuild_totals(ws, start, end, cols, month_col_map):
    """Perbaiki rumus SUM/COUNTIF di kolom Total Realisasi."""
    if not cols.get('total'):
        return
    for r in range(start, end + 1):
        cell = ws.cell(r, cols['total'])
        cell_type = type(cell).__name__
        if cell_type == 'MergedCell':
            continue
        if not cell.value and r != start:
            continue
        # Hitung rentang kolom harian untuk baris ini
        if month_col_map:
            all_day_cols = []
            for m_num in sorted(month_col_map.keys()):
                m_start = month_col_map[m_num]
                days = calendar.monthrange(2026, m_num)[1]
                all_day_cols.extend(range(m_start, m_start + days))
            if all_day_cols:
                c_start = get_column_letter(min(all_day_cols))
                c_end = get_column_letter(max(all_day_cols))
                cell.value = f'=SUM({c_start}{r}:{c_end}{r})'


# ---------------------------------------------------------------------------
# Main: Generate Report
# ---------------------------------------------------------------------------

def generate_report(project_id: int, template_path: str, output_path: str) -> int:
    """
    Fungsi utama pembuatan laporan.
    
    Args:
        project_id: ID project dari database.
        template_path: Path ke file template Excel (jika kosong, cari dari project.template_path).
        output_path: Path output file Excel.
    
    Returns:
        Jumlah blok penerbangan yang diisi.
    """
    # --- Ambil data dari database ---
    project = Project.objects.get(id=project_id)
    year = project.year
    month = project.month

    # Tentukan template path
    if not template_path:
        template_path = project.template_path
        
    # Fallback ke static template
    if not template_path or not os.path.exists(template_path):
        from django.conf import settings
        static_template = os.path.join(settings.BASE_DIR, 'static', 'tpl', 'form_realisasi_winter26.xlsx')
        if os.path.exists(static_template):
            template_path = static_template
        else:
            raise FileNotFoundError(
                f"Template Excel tidak ditemukan: '{template_path}' maupun di folder static. "
                "Pastikan file form_realisasi_winter26.xlsx ada di dalam folder static/tpl/."
            )

    # --- Ambil semua schedule versions untuk project ini ---
    schedules = ScheduleVersion.objects.filter(
        project_id=project_id,
    ).order_by('flight_number', 'version_number', 'flight_date')

    # --- Bangun struktur data per-flight + hitung periode/jam tiap segmen ---
    flight_data = _build_flight_data(schedules)
    _finalize_flight_data(flight_data)

    # --- Buka template Excel ---
    wb = load_workbook(template_path)
    ws = wb.active

    # Deteksi kolom
    cols, month_col_map = _detect_columns(ws)

    col_flight = cols['flight']

    # Temukan semua blok flight di template
    headers = _find_flight_headers(ws, col_flight)
    if not headers:
        raise RuntimeError(
            "Tidak ada blok flight ditemukan di template. "
            "Pastikan kolom B berisi nomor penerbangan QG-xxx."
        )

    # --- Proses duplikasi PPRP (dari bawah ke atas agar baris tidak bergeser) ---
    for i in reversed(range(len(headers))):
        row_start, flight_norm, flight_str = headers[i]
        fd = flight_data.get(flight_norm)
        if not fd:
            continue

        # --- UPDATE ORIGINAL BLOCK (WTT/SEMULA) ---
        # Isi ATD, ATA asli dari data WTT (ETD/ETA biarkan bawaan template)
        if fd.get('wtt'):
            if cols.get('atd') and fd['wtt'].get('atd'):
                ws.cell(row_start, cols['atd']).value = fd['wtt']['atd']
            if cols.get('ata') and fd['wtt'].get('ata'):
                ws.cell(row_start, cols['ata']).value = fd['wtt']['ata']

        # Update SEMULA block: pastikan Tipe Pengajuan diset ke 'Perpanjangan'
        if cols.get('tipe'):
            target_row = row_start
            for rng in ws.merged_cells.ranges:
                if (rng.min_col <= cols['tipe'] <= rng.max_col and
                        rng.min_row <= row_start <= rng.max_row):
                    target_row = rng.min_row
                    break
            cell = ws.cell(target_row, cols['tipe'])
            if type(cell).__name__ != 'MergedCell':
                cell.value = 'Perpanjangan'

        # Jika tidak ada PPRP, skip proses duplikasi blok
        if not fd['pprp_list']:
            continue

        # Tentukan batas blok
        next_row = headers[i + 1][0] if i + 1 < len(headers) else None
        row_end = _block_end(ws, row_start, next_row, ws.max_row)
        block_len = row_end - row_start + 1

        # Iterasi kronologis: segmen paling awal disisipkan lebih dulu sehingga
        # tampil tepat di bawah blok SEMULA, disusul segmen berikutnya.
        # periode_semula hanya terisi pada segmen pertama (lihat _assign_pprp_periods),
        # jadi blok SEMULA hanya ditulis sekali.
        for pprp in fd['pprp_list']:
            # --- UPDATE SEMULA block: ubah periode end date menjadi pprp_date - 1 ---
            if cols.get('periode') and pprp.get('periode_semula'):
                periode_col = cols['periode']
                # Cari top-left cell dari merged range di kolom periode pada baris start
                # (merged cell hanya bisa ditulis melalui top-left cell-nya)
                target_row = row_start
                for rng in ws.merged_cells.ranges:
                    if (rng.min_col <= periode_col <= rng.max_col and
                            rng.min_row <= row_start <= rng.max_row):
                        target_row = rng.min_row
                        break
                cell = ws.cell(target_row, periode_col)
                if type(cell).__name__ != 'MergedCell':
                    cell.value = pprp['periode_semula']

            # --- INSERT MENJADI block setelah blok SEMULA ---
            insert_at = row_end + 1
            ws.insert_rows(insert_at, block_len)
            _shift_merged_ranges_below(ws, insert_at, block_len)
            _shift_formulas_below(ws, insert_at, block_len)

            # Salin seluruh blok SEMULA ke posisi MENJADI
            for offset in range(block_len):
                _copy_row(ws, row_start + offset, insert_at + offset)
                
            # Salin struktur merged cells dari blok SEMULA ke MENJADI
            _copy_merged_ranges_for_block(ws, row_start, insert_at, block_len)

            # Update nilai di baris pertama blok MENJADI
            top_row = insert_at
            # Kosongkan kolom NO (akan di-rebuild)
            ws.cell(top_row, cols['no']).value = None
            # Update Periode MENJADI
            if cols.get('periode') and pprp['periode']:
                ws.cell(top_row, cols['periode']).value = pprp['periode']
            # Update Nomor Surat PPRP
            if cols.get('surat') and pprp['pprp_letter']:
                ws.cell(top_row, cols['surat']).value = pprp['pprp_letter']
            # Update Tipe Pengajuan MENJADI
            if cols.get('tipe'):
                ws.cell(top_row, cols['tipe']).value = 'Perubahan'
            # Jam baris MENJADI: ETD = STD GHP dikonversi UTC (kosong bila GHP
            # belum ada), ETA = STA surat PPRP (UTC), ATD/ATA = jam WTT (Local).
            # Selalu ditulis (termasuk None) agar nilai warisan salinan blok
            # SEMULA tidak tertinggal di baris MENJADI.
            if cols.get('etd'):
                ws.cell(top_row, cols['etd']).value = pprp.get('etd_utc')
            if cols.get('eta'):
                ws.cell(top_row, cols['eta']).value = pprp.get('sta')
            if cols.get('atd'):
                ws.cell(top_row, cols['atd']).value = pprp.get('atd')
            if cols.get('ata'):
                ws.cell(top_row, cols['ata']).value = pprp.get('ata')
            # Kosongkan kolom harian (akan diisi ulang berdasarkan GHP)
            if cols.get('day_start') and month_col_map:
                for m_num, m_col_start in month_col_map.items():
                    days_in_month = calendar.monthrange(year, m_num)[1]
                    for offset in range(block_len):
                        for day_col in range(m_col_start, m_col_start + days_in_month):
                            ws.cell(insert_at + offset, day_col).value = None

            row_end = insert_at + block_len - 1  # Update row_end

    # --- Refresh headers setelah insert ---
    headers = _find_flight_headers(ws, col_flight)

    # --- Isi data harian (1/0) per blok per bulan ---
    for i, (row_start, flight_norm, flight_str) in enumerate(headers):
        fd = flight_data.get(flight_norm)
        if not fd or not fd['daily']:
            continue

        next_row = headers[i + 1][0] if i + 1 < len(headers) else None
        row_end = _block_end(ws, row_start, next_row, ws.max_row)

        day_start_col = cols.get('day_start')
        bulan_tahun_col = cols.get('bulan_tahun', 13)
        if not day_start_col:
            continue

        # Iterasi setiap baris di dalam blok flight ini
        for r in range(row_start, row_end + 1):
            bln_val = ws.cell(r, bulan_tahun_col).value
            if not bln_val:
                continue
                
            m_num = None
            if isinstance(bln_val, (datetime.datetime, datetime.date)):
                m_num = bln_val.month
            else:
                bln_str = str(bln_val).strip().lower()
                for num, name in INDONESIAN_MONTHS.items():
                    if name.lower()[:3] in bln_str or MONTH_ABBR[num].lower() in bln_str:
                        m_num = num
                        break
            
            if not m_num:
                continue
                
            # Isi dari tanggal 1 sampai akhir bulan
            days_in_month = calendar.monthrange(year, m_num)[1]
            for day in range(1, days_in_month + 1):
                day_col = day_start_col + (day - 1)
                flag = fd['daily'].get((year, m_num, day), 0)
                cell = ws.cell(r, day_col)
                if type(cell).__name__ != 'MergedCell':
                    cell.value = flag

    # --- Rebuild nomor urut (kolom A) ---
    seq = 1
    for row_start, flight_norm, flight_str in _find_flight_headers(ws, col_flight):
        cell = ws.cell(row_start, cols['no'])
        cell_type = type(cell).__name__
        if cell_type != 'MergedCell':
            cell.value = seq
        seq += 1

    # --- Update Tanggal Pengesahan (Current Date) ---
    now = datetime.datetime.now()
    tgl_sekarang = f"Surabaya, {INDONESIAN_MONTHS.get(now.month, 'Januari')} {now.year}"
    
    # Cari sel signature (mulai dari bawah untuk efisiensi)
    for r in range(ws.max_row, max(1, ws.max_row - 100), -1):
        for c in range(1, ws.max_column + 1):
            val = ws.cell(r, c).value
            if val and isinstance(val, str) and 'Surabaya' in val:
                ws.cell(r, c).value = tgl_sekarang

    # --- Simpan output ---
    wb.save(output_path)
    return seq - 1  # Jumlah blok yang diisi


def _insert_pprp_subblocks(ws, cols, month_col_map, row_start, block_len, pprp_entries, year):
    """
    Sisipkan sub-blok PPRP (baris 'MENJADI') di bawah blok row_start..row_start+block_len-1.
    Diekstrak dari logika sisip-blok yang sudah teruji di generate_rekap_report, supaya bisa
    dipakai ulang baik untuk flight yang sudah ada di template maupun blok flight baru.
    Mengembalikan row_end blok setelah semua sisipan (posisi baris terakhir blok saat ini).
    """
    row_end = row_start + block_len - 1
    # Iterasi kronologis (entries sudah terurut naik oleh _assign_pprp_periods);
    # hanya entri dengan periode_semula terisi (entri pertama) yang menulis
    # ulang periode blok induk.
    for pprp in pprp_entries:
        if cols.get('periode') and pprp.get('periode_semula'):
            periode_col = cols['periode']
            target_row = row_start
            for rng in ws.merged_cells.ranges:
                if (rng.min_col <= periode_col <= rng.max_col and rng.min_row <= row_start <= rng.max_row):
                    target_row = rng.min_row
                    break
            cell = ws.cell(target_row, periode_col)
            if type(cell).__name__ != 'MergedCell':
                cell.value = pprp['periode_semula']

        insert_at = row_end + 1
        ws.insert_rows(insert_at, block_len)
        _shift_merged_ranges_below(ws, insert_at, block_len)
        _shift_formulas_below(ws, insert_at, block_len)

        for offset in range(block_len):
            _copy_row(ws, row_start + offset, insert_at + offset)
        _copy_merged_ranges_for_block(ws, row_start, insert_at, block_len)

        top_row = insert_at
        ws.cell(top_row, cols['no']).value = None
        if cols.get('periode') and pprp.get('periode'):
            ws.cell(top_row, cols['periode']).value = pprp['periode']
        if cols.get('surat') and pprp.get('pprp_letter'):
            ws.cell(top_row, cols['surat']).value = pprp['pprp_letter']
        if cols.get('tipe'):
            ws.cell(top_row, cols['tipe']).value = 'Perubahan'
        # Jam baris MENJADI: ETD = STD GHP dikonversi UTC (kosong bila GHP belum
        # ada), ETA = STA surat PPRP (UTC), ATD/ATA = jam WTT (Local). Selalu
        # ditulis agar nilai warisan salinan blok induk tidak tertinggal.
        if cols.get('etd'):
            ws.cell(top_row, cols['etd']).value = pprp.get('etd_utc')
        if cols.get('eta'):
            ws.cell(top_row, cols['eta']).value = pprp.get('sta')
        if cols.get('atd'):
            ws.cell(top_row, cols['atd']).value = pprp.get('atd')
        if cols.get('ata'):
            ws.cell(top_row, cols['ata']).value = pprp.get('ata')

        if cols.get('day_start') and month_col_map:
            for m_num, m_col_start in month_col_map.items():
                days_in_month = calendar.monthrange(year, m_num)[1]
                for offset in range(block_len):
                    for day_col in range(m_col_start, m_col_start + days_in_month):
                        ws.cell(insert_at + offset, day_col).value = None

        row_end = insert_at + block_len - 1

    return row_end


def generate_rekap_report(output_path: str) -> int:
    """
    Menghasilkan laporan rekapitulasi satu musim penuh dengan menggabungkan 
    data realisasi (1/0) dan perubahan PPRP dari SELURUH Project yang ada.
    """
    latest_project = Project.objects.order_by('-created_at').first()
    if not latest_project:
        raise ValueError("Belum ada data Project sama sekali di dalam sistem.")
        
    template_path = latest_project.template_path
    if not template_path or not os.path.exists(template_path):
        from django.conf import settings
        static_template = os.path.join(settings.BASE_DIR, 'static', 'tpl', 'form_realisasi_winter26.xlsx')
        if os.path.exists(static_template):
            template_path = static_template
        else:
            raise FileNotFoundError("Template Excel tidak ditemukan untuk generate rekap.")

    schedules = ScheduleVersion.objects.all().order_by('flight_number', 'version_number', 'flight_date')

    flight_data = _build_flight_data(schedules)
    pdf_cache = _finalize_flight_data(flight_data)

    wb = load_workbook(template_path)
    ws = wb.active

    cols, month_col_map = _detect_columns(ws)
    col_flight = cols['flight']

    headers = _find_flight_headers(ws, col_flight)
    if not headers:
        raise RuntimeError("Tidak ada blok flight ditemukan di template.")

    for i in reversed(range(len(headers))):
        row_start, flight_norm, flight_str = headers[i]
        fd = flight_data.get(flight_norm)
        if not fd:
            continue

        if fd.get('wtt'):
            if cols.get('atd') and fd['wtt'].get('atd'):
                ws.cell(row_start, cols['atd']).value = fd['wtt']['atd']
            if cols.get('ata') and fd['wtt'].get('ata'):
                ws.cell(row_start, cols['ata']).value = fd['wtt']['ata']

        if cols.get('tipe'):
            target_row = row_start
            for rng in ws.merged_cells.ranges:
                if (rng.min_col <= cols['tipe'] <= rng.max_col and rng.min_row <= row_start <= rng.max_row):
                    target_row = rng.min_row
                    break
            cell = ws.cell(target_row, cols['tipe'])
            if type(cell).__name__ != 'MergedCell':
                cell.value = 'Perpanjangan'

        if not fd['pprp_list']:
            continue

        next_row = headers[i + 1][0] if i + 1 < len(headers) else None
        row_end = _block_end(ws, row_start, next_row, ws.max_row)
        block_len = row_end - row_start + 1

        _insert_pprp_subblocks(ws, cols, month_col_map, row_start, block_len, fd['pprp_list'], latest_project.year)

    headers = _find_flight_headers(ws, col_flight)

    # --- Flight yang sama sekali baru (belum pernah ada di template) ---
    # Ditambahkan sebagai blok baru di baris paling bawah daftar flight (sebelum
    # legenda "Keterangan Pengisian" & blok tanda tangan), diurutkan berdasarkan
    # kapan pertama kali flight itu tercatat di database. Hanya flight yang punya
    # data PPRP yang diproses (surat + periode wajib berasal dari PPRP resmi;
    # flight yang murni WTT tanpa PPRP dilewati, bukan ditebak-tebak).
    existing_norms = {h[1] for h in headers}
    new_flights = [
        (fn, fd) for fn, fd in flight_data.items()
        if fn not in existing_norms and fd['pprp_list']
    ]
    new_flights.sort(key=lambda item: item[1]['first_seen'] or datetime.datetime.max)

    if new_flights and headers:
        tmpl_start = headers[-1][0]
        tmpl_len = _block_end(ws, tmpl_start, None, ws.max_row) - tmpl_start + 1
        insert_cursor = tmpl_start + tmpl_len - 1  # = row akhir blok terakhir saat ini

        for fn, fd in new_flights:
            pprp_sorted = fd['pprp_list']  # sudah terurut kronologis oleh _assign_pprp_periods
            first_pprp = pprp_sorted[0]

            # Ambil tipe permohonan dari PDF surat pertama (tidak tersimpan di DB).
            submission_type = _submission_type_for(first_pprp, pdf_cache, 'Penambahan')

            insert_at = insert_cursor + 1
            ws.insert_rows(insert_at, tmpl_len)
            _shift_merged_ranges_below(ws, insert_at, tmpl_len)
            _shift_formulas_below(ws, insert_at, tmpl_len)
            for offset in range(tmpl_len):
                _copy_row(ws, tmpl_start + offset, insert_at + offset)
            _copy_merged_ranges_for_block(ws, tmpl_start, insert_at, tmpl_len)

            top_row = insert_at
            display_flight = ('QG-' + fn[2:]) if fn.startswith('QG') else fn
            route_str = f"{fd['origin']}-{fd['destination']}"

            if cols.get('flight'):
                ws.cell(top_row, cols['flight']).value = display_flight
            if cols.get('to'):
                ws.cell(top_row, cols['to']).value = route_str

            # Flight baru: aturan jam sama dengan baris MENJADI — ETD = STD GHP
            # dikonversi UTC (kosong bila GHP belum ada), ETA = STA surat PPRP
            # (UTC), ATD/ATA = jam WTT bila flight muncul di WTT (umumnya kosong
            # untuk rute yang benar-benar baru).
            if cols.get('etd'):
                ws.cell(top_row, cols['etd']).value = first_pprp.get('etd_utc')
            if cols.get('eta'):
                ws.cell(top_row, cols['eta']).value = first_pprp.get('sta')
            if cols.get('atd'):
                ws.cell(top_row, cols['atd']).value = first_pprp.get('atd')
            if cols.get('ata'):
                ws.cell(top_row, cols['ata']).value = first_pprp.get('ata')

            # Periode segmen pertama sudah dihitung _assign_pprp_periods
            # (dipotong sebelum segmen berikutnya; segmen terakhir memakai
            # tanggal akhir berlaku dari PDF surat).
            periode_str = first_pprp.get('periode') or 'PERLU REVIEW - SURAT TIDAK TERBACA'
            if cols.get('periode'):
                ws.cell(top_row, cols['periode']).value = periode_str
            if cols.get('surat') and first_pprp.get('pprp_letter'):
                ws.cell(top_row, cols['surat']).value = first_pprp['pprp_letter']
            if cols.get('tipe'):
                ws.cell(top_row, cols['tipe']).value = submission_type

            block_end = insert_at + tmpl_len - 1

            # Kalau flight baru ini punya >1 segmen PPRP, sisipkan sub-blok
            # tambahan; periode tiap segmen sudah dihitung _assign_pprp_periods
            # (segmen non-terakhir dipotong sehari sebelum segmen berikutnya,
            # segmen terakhir memakai tanggal akhir berlaku dari PDF surat).
            if len(pprp_sorted) > 1:
                block_end = _insert_pprp_subblocks(
                    ws, cols, month_col_map, insert_at, tmpl_len, pprp_sorted[1:], latest_project.year
                )

            insert_cursor = block_end

        headers = _find_flight_headers(ws, col_flight)

    latest_year = latest_project.year
    for i, (row_start, flight_norm, flight_str) in enumerate(headers):
        fd = flight_data.get(flight_norm)
        if not fd or not fd['daily']:
            continue

        next_row = headers[i + 1][0] if i + 1 < len(headers) else None
        row_end = _block_end(ws, row_start, next_row, ws.max_row)

        day_start_col = cols.get('day_start')
        bulan_tahun_col = cols.get('bulan_tahun', 13)
        if not day_start_col:
            continue

        for r in range(row_start, row_end + 1):
            bln_val = ws.cell(r, bulan_tahun_col).value
            if not bln_val:
                continue
                
            m_num = None
            if isinstance(bln_val, (datetime.datetime, datetime.date)):
                m_num = bln_val.month
            else:
                bln_str = str(bln_val).strip().lower()
                for num, name in INDONESIAN_MONTHS.items():
                    if name.lower()[:3] in bln_str or MONTH_ABBR[num].lower() in bln_str:
                        m_num = num
                        break
            
            if not m_num:
                continue
                
            days_in_month = calendar.monthrange(latest_year, m_num)[1]
            for day in range(1, days_in_month + 1):
                day_col = day_start_col + (day - 1)
                flag = fd['daily'].get((latest_year, m_num, day), 0)
                cell = ws.cell(r, day_col)
                if type(cell).__name__ != 'MergedCell':
                    cell.value = flag

    seq = 1
    for row_start, flight_norm, flight_str in _find_flight_headers(ws, col_flight):
        cell = ws.cell(row_start, cols['no'])
        if type(cell).__name__ != 'MergedCell':
            cell.value = seq
        seq += 1

    now = datetime.datetime.now()
    tgl_sekarang = f"Surabaya, {INDONESIAN_MONTHS.get(now.month, 'Januari')} {now.year}"
    for r in range(ws.max_row, max(1, ws.max_row - 100), -1):
        for c in range(1, ws.max_column + 1):
            val = ws.cell(r, c).value
            if val and isinstance(val, str) and 'Surabaya' in val:
                ws.cell(r, c).value = tgl_sekarang

    wb.save(output_path)
    return seq - 1


def load_template_flight_metadata(template_path: str = None) -> dict:
    """
    Ekstrak metadata baseline per flight dari template Excel resmi:
    - route (misal: 'SUB-CGK', 'SUB-BTH', 'SUB-BDJ')
    - etd & eta (jam UTC bawaan template, string 'HH:MM')
    - periode (misal: '29 MAR 2026/24 OKT 2026')
    - surat (misal: 'AU.012/29/19/DRJU-DAU-2026')
    - tipe (misal: 'Perpanjangan')
    - start_date & end_date (parsed datetime.date)
    """
    MONTHS_ID = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MEI': 5, 'JUN': 6, 'JUL': 7, 'AGU': 8, 'SEP': 9, 'OKT': 10, 'NOV': 11, 'DES': 12}
    
    def _parse_d(s):
        m = re.search(r'(\d{1,2})\s+([A-Z]{3})\s+(\d{4})', s.upper())
        if m:
            d = int(m.group(1))
            mon = MONTHS_ID.get(m.group(2), 1)
            yr = int(m.group(3))
            return datetime.date(yr, mon, d)
        return None

    path_to_use = template_path if (template_path and os.path.exists(template_path)) else os.path.join('static', 'tpl', 'form_realisasi_winter26.xlsx')
    if not os.path.exists(path_to_use):
        return {}

    try:
        wb = load_workbook(path_to_use, data_only=True)
        ws = wb.active
        meta = {}
        for r in range(8, ws.max_row + 1):
            flt = ws.cell(r, 2).value
            if flt and re.match(r'^QG[- ]?\d+', str(flt).strip(), re.IGNORECASE):
                norm = _normalize_flight(flt)
                route = ws.cell(r, 3).value
                periode = ws.cell(r, 8).value
                surat = ws.cell(r, 9).value
                tipe = ws.cell(r, 10).value

                def _fmt_t(v):
                    if isinstance(v, (datetime.time, datetime.datetime)):
                        return v.strftime('%H:%M')
                    return str(v).strip() if v is not None else ''

                start_d, end_d = None, None
                if periode and '/' in str(periode):
                    parts = str(periode).split('/')
                    start_d = _parse_d(parts[0])
                    end_d = _parse_d(parts[1]) if len(parts) > 1 else None

                meta[norm] = {
                    'route': str(route).strip() if route else '',
                    'etd': _fmt_t(ws.cell(r, 4).value),
                    'eta': _fmt_t(ws.cell(r, 5).value),
                    'periode': str(periode).strip() if periode else '',
                    'surat': str(surat).strip() if surat else '',
                    'tipe': str(tipe).strip() if tipe else 'Perpanjangan',
                    'start_date': start_d,
                    'end_date': end_d,
                }
        return meta
    except Exception:
        return {}


def get_project_report_data(project_id: int) -> dict:
    """
    Susun data rekonsiliasi penerbangan untuk Report Viewer HTML
    (/admin/core/project/<id>/view-report/). Memakai pipeline data yang sama
    dengan generator Excel (_build_flight_data + _assign_pprp_periods +
    _resolve_menjadi_times) supaya preview identik dengan hasil Excel:
    - Baris SEMULA hanya untuk flight yang punya baseline WTT; ETD/ETA dari
      template, ATD/ATA dari WTT (Local).
    - Satu baris Perubahan per SEGMEN PPRP (bukan hanya surat pertama), periode
      terpotong antar segmen; ETD dari GHP (UTC), ETA dari surat PPRP (UTC).
    Hanya penerbangan keberangkatan dari Surabaya (origin='SUB').
    """
    project = Project.objects.get(id=project_id)
    year, month = project.year, project.month
    tpl_meta = load_template_flight_metadata(project.template_path)

    schedules = ScheduleVersion.objects.filter(
        project=project,
        origin='SUB',
    ).order_by('flight_number', 'version_number', 'flight_date')

    flight_data = _build_flight_data(schedules)
    pdf_cache = _finalize_flight_data(flight_data)

    periode_label = f"Summer {str(year)[-2:]} (S-{str(year)[-2:]})" if month in range(3, 11) else f"Winter {str(year)[-2:]} (W-{str(year)[-2:]})"
    month_label = f"{INDONESIAN_MONTHS.get(month, '')[:3]}-{str(year)[-2:]}"

    def _make_days_row(day_flags):
        """day_flags: {nomor_hari: operated_bool} -> grid 31 sel tanggal."""
        out = []
        for day in range(1, 32):
            if day in day_flags:
                operated = day_flags[day]
                out.append({'day': day, 'is_scheduled': True,
                            'is_operated': operated, 'val': '1' if operated else '0'})
            else:
                out.append({'day': day, 'is_scheduled': False,
                            'is_operated': False, 'val': '-'})
        return out

    def _day_pattern(dates):
        weekdays = {dt.isoweekday() for dt in dates}
        return "".join(str(d) if d in weekdays else "-" for d in range(1, 8))

    rows = []
    grand_planned = 0
    grand_operated = 0
    row_seq = 1

    for fn in sorted(flight_data.keys()):
        fd = flight_data[fn]
        base_meta = tpl_meta.get(fn, {})
        route_str = base_meta.get('route') or f"SUB-{fd['destination']}"
        plist = fd['pprp_list']  # sudah kronologis (diurutkan _assign_pprp_periods)
        first_pprp_date = plist[0].get('pprp_date') if plist else None

        # --- Baris SEMULA: hanya bila flight punya baseline WTT ---
        if fd.get('wtt'):
            if first_pprp_date:
                semula_dates = [dt for dt in fd['v1_times'] if dt < first_pprp_date]
            else:
                semula_dates = list(fd['v1_times'])
            day_flags = {dt.day: fd['daily'].get((dt.year, dt.month, dt.day)) == 1
                         for dt in semula_dates}

            if plist and plist[0].get('periode_semula'):
                periode = plist[0]['periode_semula']
            else:
                periode = base_meta.get('periode') or f"29 MAR {year}/24 OKT {year}"

            total_planned = len(semula_dates)
            total_operated = sum(1 for v in day_flags.values() if v)
            grand_planned += total_planned
            grand_operated += total_operated

            rows.append({
                'no': row_seq,
                'flight_number': fd['flight_str'],
                'origin': fd['origin'] or 'SUB',
                'to': route_str,
                'etd': base_meta.get('etd') or '',
                'eta': base_meta.get('eta') or '',
                'atd': fd['wtt'].get('atd') or '',
                'ata': fd['wtt'].get('ata') or '',
                'periode': periode,
                'pprp_no': base_meta.get('surat') or '-',
                'pprp_type': 'Perpanjangan',
                'day_pattern': _day_pattern(semula_dates),
                'total_planned': total_planned,
                'month_label': month_label,
                'days': _make_days_row(day_flags),
                'total_operated': total_operated,
                'pct': round((total_operated / total_planned * 100) if total_planned else 0, 1),
            })
            row_seq += 1

        # --- Satu baris Perubahan per segmen PPRP ---
        for i, pprp in enumerate(plist):
            seg_dates = sorted(pprp['dates'])
            day_flags = {dt.day: pprp['dates'][dt] for dt in seg_dates}

            default_type = 'Perubahan' if (fd.get('wtt') or i > 0) else 'Penambahan'
            total_planned = len(seg_dates)
            total_operated = sum(1 for v in day_flags.values() if v)
            grand_planned += total_planned
            grand_operated += total_operated

            rows.append({
                'no': row_seq,
                'flight_number': fd['flight_str'],
                'origin': fd['origin'] or 'SUB',
                'to': route_str,
                'etd': pprp.get('etd_utc') or '',
                'eta': pprp.get('sta') or '',
                'atd': pprp.get('atd') or '',
                'ata': pprp.get('ata') or '',
                'periode': pprp.get('periode') or 'PERLU REVIEW - SURAT TIDAK TERBACA',
                'pprp_no': pprp.get('pprp_letter') or '-',
                'pprp_type': _submission_type_for(pprp, pdf_cache, default_type),
                'day_pattern': _day_pattern(seg_dates),
                'total_planned': total_planned,
                'month_label': month_label,
                'days': _make_days_row(day_flags),
                'total_operated': total_operated,
                'pct': round((total_operated / total_planned * 100) if total_planned else 0, 1),
            })
            row_seq += 1

    grand_pct = (grand_operated / grand_planned * 100) if grand_planned > 0 else 0
    now = datetime.datetime.now()
    signature_date = f"Surabaya, {now.day} {INDONESIAN_MONTHS.get(now.month, 'Januari')} {now.year}"

    return {
        'project': project,
        'periode_label': periode_label,
        'month_name': INDONESIAN_MONTHS.get(month, ''),
        'year': year,
        'rows': rows,
        'grand_planned': grand_planned,
        'grand_operated': grand_operated,
        'grand_pct': round(grand_pct, 1),
        'days_header': list(range(1, 32)),
        'signature_date': signature_date,
        'total_flight_groups': len(rows),
    }

