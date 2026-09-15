"""
Delay code GHP (kolom 'Break Down') -> grafik "Delay Code Terbanyak".

Fixture: docs/Source/data_master_september_2026_01-12.xls
('SUB - Ground Handling Punctuality (01/09/2026 - 12/09/2026 - Detail)').

Jalankan:  python manage.py test tests.test_delay_code
"""
import os
import shutil
import tempfile
from datetime import date
from unittest import mock

import pandas as pd
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from core.analytics import delay_factors
from core.models import Project, ScheduleVersion, SourceFile
from core.parsers.ghp import parse_delay_breakdown, parse_ghp
from core.services import delete_source_file, is_charter_flight, process_ghp

SRC = os.path.join('docs', 'Source')
GHP_SEPT = os.path.join(SRC, 'data_master_september_2026_01-12.xls')
GHP_APRIL = os.path.join(SRC, 'data_master_april_2026.xls')


class ParseDelayBreakdownTests(SimpleTestCase):
    def test_single_code(self):
        self.assertEqual(parse_delay_breakdown('00:19/80'), [('80', 19)])

    def test_multiple_codes_keep_file_order(self):
        self.assertEqual(parse_delay_breakdown('00:04/63,00:19/80,00:04/89'),
                         [('63', 4), ('80', 19), ('89', 4)])

    def test_spaces_and_hours_are_tolerated(self):
        self.assertEqual(parse_delay_breakdown(' 01:17 / 80 , 00:05/89 '), [('80', 77), ('89', 5)])

    def test_empty_is_no_code(self):
        for empty in (None, '', '   '):
            self.assertEqual(parse_delay_breakdown(empty), [])

    def test_unknown_format_raises(self):
        for bad in ('80', '00:05-80', '00:05/80,', 'abc'):
            with self.assertRaises(ValueError, msg=bad):
                parse_delay_breakdown(bad)


class GhpSeptemberParserTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.records = parse_ghp(GHP_SEPT)

    def test_codes_belong_to_the_departure_from_sub_only(self):
        coded = [r for r in self.records if r['delay_code']]
        self.assertEqual(len(coded), 97)
        self.assertTrue(all(r['origin'] == 'SUB' for r in coded))
        self.assertFalse(any(r['delay_code_invalid'] for r in self.records))

    def test_example_row_goes_to_second_flight(self):
        """'QG726 -QG484 /CGK -SUB -BDJ': jam & delay milik QG484 yang berangkat SUB."""
        arrivals = [r for r in self.records if r['destination'] == 'SUB']
        self.assertTrue(arrivals)
        self.assertFalse(any(r['delay_code'] for r in arrivals))

    def test_minutes_per_row_equal_total_column(self):
        df = pd.read_excel(GHP_SEPT, header=None)
        checked = 0
        for _, row in df.iloc[7:].iterrows():
            if pd.isna(row[14]):
                continue
            hours, mins = str(row[13]).split(':')
            self.assertEqual(sum(m for _, m in parse_delay_breakdown(row[14])), int(hours) * 60 + int(mins))
            checked += 1
        self.assertEqual(checked, 97)

    def test_april_regression_unchanged(self):
        records = parse_ghp(GHP_APRIL)
        self.assertEqual(len(records), 1614)
        self.assertFalse(any(r['delay_code'] for r in records))


class DelayCodeProcessingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('tester', 'tester@example.com', 'x', is_staff=True)

    def setUp(self):
        self.project = Project.objects.create(project_id='PRJ-202609', period='2026-09', year=2026, month=9,
                                              created_by=self.user)
        self.ghp = SourceFile.objects.create(project=self.project, file_type='GHP', file_path=GHP_SEPT,
                                             file_hash='ghp-9', uploaded_by=self.user)

    def schedule(self, flight_number, day, origin='SUB', destination='CGK', **extra):
        return ScheduleVersion.objects.create(project=self.project, flight_number=flight_number, origin=origin,
                                              destination=destination, flight_date=date(2026, 9, day), **extra)

    def schedules_for_every_sub_departure_in_ghp(self):
        """Jadwal sintetis untuk tiap keberangkatan SUB di GHP September (tanpa WTT September)."""
        seen = set()
        for rec in parse_ghp(GHP_SEPT):
            key = (rec['flight_number'], rec['flight_date'])
            if rec['origin'] != 'SUB' or is_charter_flight(rec['flight_number']) or key in seen:
                continue
            seen.add(key)
            ScheduleVersion.objects.create(project=self.project, flight_number=rec['flight_number'], origin='SUB',
                                           destination=rec['destination'], flight_date=rec['flight_date'])

    def test_dashboard_numbers_for_september(self):
        self.schedules_for_every_sub_departure_in_ghp()

        process_ghp(self.project.id, self.ghp.id)
        data = delay_factors(self.project.id)

        self.assertEqual(data['total_flights'], 96, 'charter QG9692 (01:17/80) tidak dihitung')
        top = {c['code']: (c['count'], c['minutes']) for c in data['case_counts']}
        self.assertEqual(data['case_counts'][0]['code'], '89')
        self.assertEqual(top['89'], (30, 143))
        self.assertEqual(top['80'], (25, 393))
        self.assertEqual(top['63'], (19, 85))
        self.assertEqual(len(data['case_counts']), 25)
        self.assertEqual(data['durations'][0]['code'], '80')
        self.assertEqual(data['durations'][0]['duration_str'], '06:33')
        self.assertLessEqual(len(data['durations']), 10)

    def test_rematch_with_ghp_without_codes_clears_stale_code(self):
        s = self.schedule('QG484', 1)
        rec = {'flight_number': 'QG484', 'origin': 'SUB', 'destination': 'CGK', 'flight_date': '2026-09-01',
               'std': '06:00', 'atd': '06:30', 'aircraft': '320', 'delay_code': '00:30/89', 'delay_code_invalid': ''}
        with mock.patch('core.services.parse_ghp', return_value=[rec]):
            process_ghp(self.project.id, self.ghp.id)
        s.refresh_from_db()
        self.assertEqual(s.delay_code, '00:30/89')

        with mock.patch('core.services.parse_ghp', return_value=[{**rec, 'delay_code': ''}]):
            process_ghp(self.project.id, self.ghp.id)
        s.refresh_from_db()
        self.assertIsNone(s.delay_code)

    def test_invalid_breakdown_becomes_warning_not_failure(self):
        self.schedule('QG484', 1)
        rec = {'flight_number': 'QG484', 'origin': 'SUB', 'destination': 'CGK', 'flight_date': '2026-09-01',
               'std': '06:00', 'atd': '06:30', 'aircraft': '320', 'delay_code': '', 'delay_code_invalid': '30 menit/89'}
        with mock.patch('core.services.parse_ghp', return_value=[rec]):
            result = process_ghp(self.project.id, self.ghp.id)
        self.assertEqual(result.matched, 1)
        self.assertTrue(any('QG484 1 Sep 2026' in w and '30 menit/89' in w for w in result.warnings()))

    def test_deleting_ghp_clears_delay_codes(self):
        # delete_source_file ikut menghapus file fisik -> pakai salinan, jangan fixture.
        tmp_dir = tempfile.mkdtemp(prefix='delay-code-test-')
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        self.ghp.file_path = shutil.copy(GHP_SEPT, tmp_dir)
        self.ghp.save()
        s = self.schedule('QG484', 1, operational_flag=True, delay_code='00:30/89')

        delete_source_file(self.ghp.id)

        s.refresh_from_db()
        self.assertIsNone(s.delay_code)
        self.assertFalse(s.operational_flag)

    def test_delay_factors_counts_every_coded_flight(self):
        flag = {'operational_flag': True}
        # Multi-kode: masuk ke tiap kode; kode sama dua kali dalam satu flight = 1 flight.
        self.schedule('QG100', 1, delay_code='00:04/63,00:19/80,00:02/63', **flag)
        # Delay < 15 menit tetap dihitung (bukan aturan OTP-15).
        self.schedule('QG101', 1, delay_code='00:03/89', std=None, **flag)
        self.schedule('QG102', 2, delay_code='00:10/89', **flag)
        # Tidak dihitung: bukan asal SUB, tidak aktif, tidak beroperasi, format rusak.
        self.schedule('QG103', 2, origin='CGK', destination='SUB', delay_code='00:50/80', **flag)
        self.schedule('QG104', 2, delay_code='00:50/80', is_active=False, **flag)
        self.schedule('QG105', 2, delay_code='00:50/80')
        self.schedule('QG106', 2, delay_code='rusak', **flag)

        data = delay_factors(self.project.id)

        self.assertEqual(data['total_flights'], 3)
        self.assertEqual(data['case_counts'], [
            {'code': '89', 'count': 2, 'minutes': 13},
            {'code': '80', 'count': 1, 'minutes': 19},
            {'code': '63', 'count': 1, 'minutes': 6},
        ])
        self.assertEqual([d['code'] for d in data['durations']], ['80', '89', '63'])

    def test_date_filter_applies(self):
        self.schedule('QG100', 1, delay_code='00:04/63', operational_flag=True)
        self.schedule('QG101', 5, delay_code='00:04/89', operational_flag=True)

        data = delay_factors(self.project.id, start_day=2, end_day=10)

        self.assertEqual([c['code'] for c in data['case_counts']], ['89'])
