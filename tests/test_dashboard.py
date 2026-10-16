"""
Kartu KPI dashboard (core.analytics.otp_metric).

Jalankan:  python manage.py test tests.test_dashboard
"""
from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase

from core.analytics import otp_metric
from core.models import Project, ScheduleVersion


class GroundTimeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('tester', 'tester@example.com', 'x', is_staff=True)
        cls.project = Project.objects.create(project_id='PRJ-202609', period='2026-09', year=2026, month=9,
                                             created_by=cls.user)

    def flight(self, number, **times):
        return ScheduleVersion.objects.create(project=self.project, flight_number=number, origin='SUB',
                                              destination='CGK', flight_date=date(2026, 9, 1),
                                              operational_flag=True, **times)

    def test_no_ground_time_data_shows_dash_not_made_up_numbers(self):
        """Dulu kartu AGT/SGT menampilkan "1:45"/"1:30" saat tidak ada data — angka karangan."""
        self.flight('QG100', std=time(8, 0), atd=time(8, 5))  # tanpa ATA -> ground time tak bisa dihitung

        data = otp_metric(self.project.id)

        self.assertEqual(data['total'], 1)
        self.assertEqual(data['avg_agt'], '-')
        self.assertEqual(data['avg_sgt'], '-')

    def test_no_flights_at_all_shows_dash(self):
        data = otp_metric(self.project.id)
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['avg_agt'], '-')
        self.assertEqual(data['avg_sgt'], '-')

    def test_ground_time_is_computed_when_data_exists(self):
        self.flight('QG100', sta=time(6, 30), ata=time(6, 20), std=time(8, 0), atd=time(8, 5))

        data = otp_metric(self.project.id)

        self.assertEqual(data['avg_agt'], '1:45')  # 06:20 -> 08:05
        self.assertEqual(data['avg_sgt'], '1:30')  # 06:30 -> 08:00


class ALODTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('tester_alod', 'tester_alod@example.com', 'x', is_staff=True)
        cls.project = Project.objects.create(project_id='PRJ-202609', period='2026-09', year=2026, month=9,
                                             created_by=cls.user)

    def flight(self, number, delay_code='', **kwargs):
        return ScheduleVersion.objects.create(
            project=self.project, flight_number=number, origin='SUB', destination='CGK',
            flight_date=date(2026, 9, 1), operational_flag=True, delay_code=delay_code, **kwargs
        )

    def test_no_delay_data(self):
        from core.analytics import acceptable_level_of_delay
        self.flight('QG100', delay_code='')
        data = acceptable_level_of_delay(self.project.id)
        self.assertEqual(data['total_cases'], 0)
        self.assertEqual(data['total_flights'], 0)
        self.assertEqual(data['categories'], [])
        self.assertIsNone(data['top_category'])

    def test_alod_categories_and_percentages(self):
        from core.analytics import acceptable_level_of_delay
        # Flight 1: Code 80 (APT GOVERNMENTAL, 30 min)
        self.flight('QG101', delay_code='00:30/80')
        # Flight 2: Code 72 (WEATHER, 15 min)
        self.flight('QG102', delay_code='00:15/72')
        # Flight 3: Code 89 (APT GOVERNMENTAL, 10 min) and Code 61 (FLT OPS & CREW, 20 min)
        self.flight('QG103', delay_code='00:10/89,00:20/61')

        data = acceptable_level_of_delay(self.project.id)
        self.assertEqual(data['total_flights'], 3)
        self.assertEqual(data['total_cases'], 4)  # 2 APT + 1 WEATHER + 1 FLT OPS

        cats = {c['category']: c for c in data['categories']}
        self.assertIn('APT GOVERNMENTAL', cats)
        self.assertIn('WEATHER', cats)
        self.assertIn('FLT OPS & CREW', cats)

        # 2 / 4 = 50.0%
        self.assertEqual(cats['APT GOVERNMENTAL']['cases'], 2)
        self.assertEqual(cats['APT GOVERNMENTAL']['actual_percent'], 50.0)
        self.assertEqual(cats['APT GOVERNMENTAL']['target_percent'], 5.3)

        # 1 / 4 = 25.0%
        self.assertEqual(cats['WEATHER']['cases'], 1)
        self.assertEqual(cats['WEATHER']['actual_percent'], 25.0)
        self.assertEqual(cats['WEATHER']['target_percent'], 1.6)

        # Ordered descending by actual_percent: APT must be first
        self.assertEqual(data['categories'][0]['category'], 'APT GOVERNMENTAL')
        self.assertEqual(data['top_category']['category'], 'APT GOVERNMENTAL')

    def test_dashboard_api_returns_alod_data(self):
        self.client.force_login(self.user)
        self.flight('QG201', delay_code='00:25/80')
        resp = self.client.get(f'/admin/api/dashboard/?project_id={self.project.id}')
        self.assertEqual(resp.status_code, 200)
        json_data = resp.json()
        self.assertIn('alod_data', json_data)
        self.assertEqual(json_data['alod_data']['total_flights'], 1)
        self.assertEqual(len(json_data['alod_data']['categories']), 1)
        self.assertEqual(json_data['alod_data']['categories'][0]['category'], 'APT GOVERNMENTAL')


class PPRPPlanAchievementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('tester_pprp', 'tester_pprp@example.com', 'x', is_staff=True)
        cls.project = Project.objects.create(project_id='PRJ-202609', period='2026-09', year=2026, month=9,
                                             created_by=cls.user)

    def test_pprp_plan_achievement_calculation(self):
        from core.analytics import pprp_plan_achievement

        # Flight 1: Operated on-time (within <= 45 min)
        ScheduleVersion.objects.create(
            project=self.project, flight_number='QG101', origin='SUB', destination='CGK',
            flight_date=date(2026, 9, 1), is_active=True, operational_flag=True,
            std=time(8, 0), atd=time(8, 20)
        )
        # Flight 2: Operated out of tolerance (> 45 min)
        ScheduleVersion.objects.create(
            project=self.project, flight_number='QG102', origin='SUB', destination='DPS',
            flight_date=date(2026, 9, 1), is_active=True, operational_flag=True,
            std=time(8, 0), atd=time(8, 55)
        )
        # Flight 3: Scheduled but NOOP (operational_flag=False)
        ScheduleVersion.objects.create(
            project=self.project, flight_number='QG103', origin='SUB', destination='KNO',
            flight_date=date(2026, 9, 1), is_active=True, operational_flag=False,
            std=time(9, 0)
        )
        # Flight 4: Inactive superseded record (should be ignored)
        ScheduleVersion.objects.create(
            project=self.project, flight_number='QG101', origin='SUB', destination='CGK',
            flight_date=date(2026, 9, 1), is_active=False, operational_flag=True,
            std=time(7, 0)
        )

        res = pprp_plan_achievement(self.project.id, self.project.month)
        self.assertEqual(res['total'], 3)
        self.assertEqual(res['on_time'], 1)
        self.assertEqual(res['out_of_tolerance'], 1)
        self.assertEqual(res['noop'], 1)
        # 1 / 3 = 33.33%
        self.assertEqual(res['achievement'], 33.33)

    def test_dashboard_api_returns_pprp_plan(self):
        self.client.force_login(self.user)
        ScheduleVersion.objects.create(
            project=self.project, flight_number='QG101', origin='SUB', destination='CGK',
            flight_date=date(2026, 9, 1), is_active=True, operational_flag=True,
            std=time(8, 0), atd=time(8, 10)
        )
        resp = self.client.get(f'/admin/api/dashboard/?project_id={self.project.id}')
        self.assertEqual(resp.status_code, 200)
        json_data = resp.json()
        self.assertIn('pprp_plan', json_data)
        plan = json_data['pprp_plan']
        self.assertEqual(plan['total'], 1)
        self.assertEqual(plan['on_time'], 1)
        self.assertEqual(plan['noop'], 0)
        self.assertEqual(plan['achievement'], 100.0)


