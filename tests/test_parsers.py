"""Tests for core parsers"""
from core.parsers.wtt import parse_wtt
from core.parsers.pprp import parse_pprp
from core.parsers.ghp import parse_ghp


def test_wtt():
    records = parse_wtt('docs/Source/Working Time Table [WTT] April 2026.pdf')
    assert len(records) == 696
    assert records[0]['flight_number'].startswith('QG')
    assert all(r['origin'] == 'SUB' for r in records)
    print('[OK] WTT parser April (left half)')


def test_wtt_july():
    records = parse_wtt('docs/Source/Working Time Table [WTT] Juli 2026 (1).pdf')
    assert len(records) == 961
    assert records[0]['flight_number'].startswith('QG')
    assert all(r['origin'] == 'SUB' for r in records)
    print('[OK] WTT parser July (left half)')


def test_pprp():
    data = parse_pprp('docs/Source/PPRP SUB-BPN S26 UPDATE.pdf')
    assert data['letter_number'] == 'AU.012/47/3/DJPU-DAU-2026'
    assert len(data['flights']) == 4
    assert data['flights'][0]['flight_number'].startswith('QG')
    print('[OK] PPRP parser')


def test_ghp():
    records = parse_ghp('docs/Source/data_master_april_2026.xls')
    assert len(records) == 1614
    assert records[0]['flight_number'].startswith('QG')
    assert records[0]['origin'] in ['HLP', 'CGK', 'LOP', 'SUB']
    print('[OK] GHP parser')


if __name__ == '__main__':
    test_wtt()
    test_wtt_july()
    test_pprp()
    test_ghp()
    print('All parser tests pass')
