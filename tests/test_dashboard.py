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
