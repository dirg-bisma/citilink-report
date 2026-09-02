"""
Uji pintu upload tunggal (core.ingest) memakai file contoh di docs/Source.

Jalankan:  python manage.py test tests.test_ingest
(Django membuat database uji terpisah; DB kerja tidak disentuh.)
"""
import os
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from core.ingest import ingest_uploaded_files
from core.models import Project, ScheduleVersion, SourceFile
from core.services import delete_source_file, is_charter_flight, process_ghp, process_wtt

SRC = os.path.join('docs', 'Source')
WTT_JULI = os.path.join(SRC, 'Working Time Table [WTT] Juli 2026 (1).pdf')
WTT_MARET = os.path.join(SRC, 'Working Time Table [WTT] Maret 2026.pdf')
GHP_JULI = os.path.join(SRC, 'data_master_juli_2026.xls')
GHP_MARET = os.path.join(SRC, 'data_master_maret_2026.xls')
PPRP_BPN = os.path.join(SRC, 'PPRP SUB-BPN S26 UPDATE.pdf')
PPRP_LOP = os.path.join(SRC, 'PPRP SUB-LOP S26 UPDATE 01.pdf')


def upload(path):
    with open(path, 'rb') as fh:
        return SimpleUploadedFile(os.path.basename(path), fh.read())


def upload_variant(path):
    """File yang sama isinya tapi hash-nya berbeda (byte ekor tambahan tetap
    terbaca oleh pdfplumber/xlrd) — meniru 'versi baru' dari dokumen yang sama."""
    with open(path, 'rb') as fh:
        data = fh.read() + b'\n# versi baru\n'
    base, ext = os.path.splitext(os.path.basename(path))
    return SimpleUploadedFile(f'{base} (baru){ext}', data)


class IngestTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('tester', 'tester@example.com', 'x', is_staff=True, is_superuser=True)

    def setUp(self):
        self.upload_dir = tempfile.mkdtemp(prefix='ingest-test-')

    def tearDown(self):
        shutil.rmtree(self.upload_dir, ignore_errors=True)

    def ingest(self, file_type, paths, project=None, replace=False, variant=False):
        make = upload_variant if variant else upload
        return ingest_uploaded_files(file_type, [make(p) for p in paths], self.user,
                                     project=project, upload_dir=self.upload_dir, replace=replace)

    def load_wtt(self, path, year, month):
        """Muat WTT langsung dari docs/Source (tanpa menyalin) sebagai baseline."""
        project = Project.objects.create(project_id=f'PRJ-{year}{month:02d}', period=f'{year}-{month:02d}',
                                         year=year, month=month, created_by=self.user)
        sf = SourceFile.objects.create(project=project, file_type='WTT', file_path=path,
                                       file_hash=f'wtt-{month}', uploaded_by=self.user)
        process_wtt(project.id, sf.id)
        return project


class MultiFilePprpTests(IngestTestBase):
    def test_every_selected_file_is_processed(self):
        """Regresi QG356: pilih 2 file PPRP sekaligus -> keduanya harus masuk."""
        project = self.load_wtt(WTT_JULI, 2026, 7)

        result = self.ingest('PPRP', [PPRP_BPN, PPRP_LOP], project=project)

        self.assertTrue(result.success)
        self.assertEqual([f.status for f in result.files], ['processed', 'processed'])
        self.assertEqual(SourceFile.objects.filter(project=project, file_type='PPRP').count(), 2)
        self.assertTrue(all(f.count > 0 for f in result.files))

    def test_duplicate_is_skipped_without_aborting_the_batch(self):
        project = self.load_wtt(WTT_JULI, 2026, 7)
        self.ingest('PPRP', [PPRP_BPN], project=project)

        result = self.ingest('PPRP', [PPRP_BPN, PPRP_LOP], project=project)

        self.assertEqual([f.status for f in result.files], ['skipped', 'processed'])
        self.assertIn('sudah pernah diupload', result.files[0].message.lower())
        self.assertTrue(result.success)
        self.assertEqual(SourceFile.objects.filter(project=project, file_type='PPRP').count(), 2)

    def test_letter_outside_project_month_is_rejected_with_its_range(self):
        january = Project.objects.create(project_id='PRJ-202601', period='2026-01', year=2026, month=1,
                                         created_by=self.user)

        result = self.ingest('PPRP', [PPRP_BPN], project=january)

        self.assertFalse(result.success)
        self.assertEqual(result.files[0].status, 'failed')
        self.assertIn('tidak mencakup Januari 2026', result.files[0].message)
        self.assertIn('s/d', result.files[0].message)
        # File & record tidak boleh tertinggal, supaya bisa diupload ulang ke project yang benar.
        self.assertEqual(SourceFile.objects.filter(project=january).count(), 0)
        self.assertEqual(os.listdir(self.upload_dir), [])

    def test_pprp_upload_resyncs_ghp_flags(self):
        project = self.load_wtt(WTT_JULI, 2026, 7)
        self.ingest('GHP', [GHP_JULI], project=project)
        flags_before = ScheduleVersion.objects.filter(project=project, operational_flag=True).count()

        result = self.ingest('PPRP', [PPRP_BPN], project=project)

        self.assertTrue(any('dicocokkan ulang' in m for m in result.resync_messages))
        v2_flagged = ScheduleVersion.objects.filter(project=project, version_number=2, operational_flag=True).count()
        self.assertGreater(v2_flagged, 0, 'jadwal baru dari PPRP harus langsung dapat flag GHP')
        self.assertGreaterEqual(
            ScheduleVersion.objects.filter(project=project, is_active=True, operational_flag=True).count(),
            flags_before - v2_flagged)


class GhpMatchingTests(IngestTestBase):
    def test_charter_ignored_and_unmatched_scheduled_flights_reported(self):
        project = self.load_wtt(WTT_MARET, 2026, 3)
        sf = SourceFile.objects.create(project=project, file_type='GHP', file_path=GHP_MARET,
                                       file_hash='ghp-3', uploaded_by=self.user)

        ghp = process_ghp(project.id, sf.id)

        self.assertGreater(ghp.matched, 0)
        self.assertGreater(ghp.charter_skipped, 0)
        self.assertNotIn('QG9496', ghp.unmatched, 'charter (4 digit) tidak boleh memicu peringatan')
        self.assertNotIn('QG9694', ghp.unmatched)
        # QG719 terbang tiap hari di Maret menurut GHP tapi tidak ada di WTT Maret.
        self.assertEqual(len(ghp.unmatched.get('QG719', [])), 30)
        self.assertTrue(any(w.startswith('QG719: 30 hari') for w in ghp.warnings()))
        charter_in_schedule = [fn for fn in ScheduleVersion.objects.filter(project=project)
                               .values_list('flight_number', flat=True).distinct() if is_charter_flight(fn)]
        self.assertEqual(charter_in_schedule, [], 'WTT Maret tidak memuat charter, jadi DB juga tidak boleh')

    def test_ghp_for_other_month_is_rejected(self):
        project = self.load_wtt(WTT_JULI, 2026, 7)

        result = self.ingest('GHP', [GHP_MARET], project=project)

        self.assertFalse(result.success)
        self.assertIn('bulan Maret', result.files[0].message)
        self.assertEqual(SourceFile.objects.filter(project=project, file_type='GHP').count(), 0)


class WttReuploadTests(IngestTestBase):
    def test_reuploading_wtt_restores_pprp_rows_and_ghp_flags(self):
        """Skenario 2026-09-02: hapus WTT (baris PPRP ikut terhapus), upload WTT lagi."""
        first = self.ingest('WTT', [WTT_JULI])
        self.assertTrue(first.success)
        project = first.project
        self.assertEqual((project.year, project.month), (2026, 7))

        self.ingest('PPRP', [PPRP_BPN], project=project)
        self.ingest('GHP', [GHP_JULI], project=project)
        v2_before = ScheduleVersion.objects.filter(project=project, version_number=2).count()
        flags_before = ScheduleVersion.objects.filter(project=project, operational_flag=True).count()
        self.assertGreater(v2_before, 0)
        self.assertGreater(flags_before, 0)

        wtt_file = SourceFile.objects.get(project=project, file_type='WTT')
        delete_source_file(wtt_file.id)
        self.assertLess(ScheduleVersion.objects.filter(project=project, version_number=2).count(), v2_before)

        again = self.ingest('WTT', [WTT_JULI])

        self.assertTrue(again.success)
        self.assertEqual(again.project.id, project.id)
        self.assertTrue(any('diterapkan ulang' in m for m in again.resync_messages))
        self.assertEqual(ScheduleVersion.objects.filter(project=project, version_number=2).count(), v2_before)
        self.assertEqual(ScheduleVersion.objects.filter(project=project, operational_flag=True).count(), flags_before)
        # Tidak boleh ada flight+tanggal dengan dua baris aktif setelah sinkron ulang.
        active = ScheduleVersion.objects.filter(project=project, is_active=True).values_list('flight_number', 'flight_date')
        self.assertEqual(len(active), len(set(active)))


class ReplaceFileTests(IngestTestBase):
    """Mode Atur Ulang: satu bulan = satu WTT + satu GHP; ganti harus eksplisit."""

    def test_rebuild_with_the_very_same_file_is_allowed_in_replace_mode(self):
        """Kasus nyata 2026-09-02: di mode Atur Ulang, pilih file WTT yang sama
        persis = bangun ulang bulan itu. Cek duplikat tidak boleh menghalangi."""
        project = self.ingest('WTT', [WTT_JULI]).project
        self.ingest('PPRP', [PPRP_BPN], project=project)
        self.ingest('GHP', [GHP_JULI], project=project)
        before = {
            'total': ScheduleVersion.objects.filter(project=project).count(),
            'v2': ScheduleVersion.objects.filter(project=project, version_number=2).count(),
            'flags': ScheduleVersion.objects.filter(project=project, operational_flag=True).count(),
        }

        refused = self.ingest('WTT', [WTT_JULI], project=project)
        self.assertEqual(refused.files[0].status, 'skipped')
        self.assertIn('Atur Ulang', refused.files[0].message)

        result = self.ingest('WTT', [WTT_JULI], project=project, replace=True)

        self.assertTrue(result.success, result.files[0].message)
        self.assertEqual(result.files[0].status, 'processed')
        self.assertIn('Dibangun ulang dari file yang sama', result.files[0].message)
        self.assertEqual(SourceFile.objects.filter(project=project, file_type='WTT').count(), 1)
        self.assertEqual(ScheduleVersion.objects.filter(project=project).count(), before['total'])
        self.assertEqual(ScheduleVersion.objects.filter(project=project, version_number=2).count(), before['v2'])
        self.assertEqual(ScheduleVersion.objects.filter(project=project, operational_flag=True).count(), before['flags'])

    def test_rebuild_ghp_with_the_very_same_file(self):
        project = self.load_wtt(WTT_JULI, 2026, 7)
        self.ingest('GHP', [GHP_JULI], project=project)
        flags_before = ScheduleVersion.objects.filter(project=project, operational_flag=True).count()

        result = self.ingest('GHP', [GHP_JULI], project=project, replace=True)

        self.assertTrue(result.success, result.files[0].message)
        self.assertIn('Dibangun ulang dari file yang sama', result.files[0].message)
        self.assertEqual(SourceFile.objects.filter(project=project, file_type='GHP').count(), 1)
        self.assertEqual(ScheduleVersion.objects.filter(project=project, operational_flag=True).count(), flags_before)

    def test_second_ghp_for_same_month_is_refused_without_replace(self):
        project = self.load_wtt(WTT_JULI, 2026, 7)
        self.ingest('GHP', [GHP_JULI], project=project)

        result = self.ingest('GHP', [GHP_JULI], project=project, variant=True)

        self.assertFalse(result.success)
        self.assertIn('Sudah ada file GHP untuk Juli 2026', result.files[0].message)
        self.assertIn('Atur Ulang', result.files[0].message)
        self.assertEqual(SourceFile.objects.filter(project=project, file_type='GHP').count(), 1)

    def test_replace_ghp_swaps_file_and_recomputes_flags(self):
        project = self.load_wtt(WTT_JULI, 2026, 7)
        first = self.ingest('GHP', [GHP_JULI], project=project)
        flags_before = ScheduleVersion.objects.filter(project=project, operational_flag=True).count()
        old_path = SourceFile.objects.get(id=first.files[0].source_file_id).file_path

        result = self.ingest('GHP', [GHP_JULI], project=project, replace=True, variant=True)

        self.assertTrue(result.success)
        self.assertEqual(result.files[0].replaced_filename, os.path.basename(old_path))
        self.assertIn('Menggantikan file lama', result.files[0].message)
        ghp_files = SourceFile.objects.filter(project=project, file_type='GHP')
        self.assertEqual(ghp_files.count(), 1)
        self.assertEqual(ghp_files.get().id, result.files[0].source_file_id)
        self.assertFalse(os.path.exists(old_path), 'file GHP lama harus ikut dihapus dari disk')
        self.assertEqual(ScheduleVersion.objects.filter(project=project, operational_flag=True).count(), flags_before)

    def test_replace_wtt_rebuilds_month_from_existing_pprp_and_ghp(self):
        project = self.ingest('WTT', [WTT_JULI]).project
        self.ingest('PPRP', [PPRP_BPN], project=project)
        self.ingest('GHP', [GHP_JULI], project=project)
        v2_before = ScheduleVersion.objects.filter(project=project, version_number=2).count()
        flags_before = ScheduleVersion.objects.filter(project=project, operational_flag=True).count()
        total_before = ScheduleVersion.objects.filter(project=project).count()

        refused = self.ingest('WTT', [WTT_JULI], project=project, variant=True)
        self.assertFalse(refused.success)
        self.assertIn('Sudah ada file WTT untuk Juli 2026', refused.files[0].message)

        result = self.ingest('WTT', [WTT_JULI], project=project, replace=True, variant=True)

        self.assertTrue(result.success)
        self.assertEqual(SourceFile.objects.filter(project=project, file_type='WTT').count(), 1)
        self.assertEqual(ScheduleVersion.objects.filter(project=project).count(), total_before, 'jadwal tidak boleh dobel')
        self.assertEqual(ScheduleVersion.objects.filter(project=project, version_number=2).count(), v2_before)
        self.assertEqual(ScheduleVersion.objects.filter(project=project, operational_flag=True).count(), flags_before)
        self.assertTrue(any('diterapkan ulang' in m for m in result.resync_messages))

    def test_wtt_for_other_month_than_selected_project_is_rejected(self):
        maret = self.load_wtt(WTT_MARET, 2026, 3)

        result = self.ingest('WTT', [WTT_JULI], project=maret, replace=True)

        self.assertFalse(result.success)
        self.assertIn('tidak cocok dengan project yang dipilih (Maret 2026)', result.files[0].message)
        self.assertEqual(SourceFile.objects.filter(project=maret, file_type='WTT').count(), 1)
        self.assertFalse(Project.objects.filter(year=2026, month=7).exists())


class WrongCardTests(IngestTestBase):
    """Salah kartu harus dikenali dari ISI file, bukan pesan parser mentah."""

    def test_wtt_pdf_uploaded_as_pprp(self):
        project = self.load_wtt(WTT_JULI, 2026, 7)

        result = self.ingest('PPRP', [WTT_JULI], project=project)

        self.assertFalse(result.success)
        msg = result.files[0].message
        self.assertIn('isinya dokumen WTT, bukan PPRP', msg)
        self.assertNotIn('MENJADI', msg)
        self.assertEqual(SourceFile.objects.filter(project=project, file_type='PPRP').count(), 0)

    def test_pprp_pdf_uploaded_as_wtt(self):
        result = self.ingest('WTT', [PPRP_BPN])

        self.assertFalse(result.success)
        self.assertIn('isinya dokumen PPRP, bukan WTT', result.files[0].message)
        self.assertEqual(SourceFile.objects.filter(file_type='WTT').count(), 0)

    def test_real_pprp_problem_keeps_its_own_message(self):
        """Jangan salah tuduh: file PPRP asli yang ditolak karena bulan tetap
        memberi pesan rentang suratnya."""
        january = Project.objects.create(project_id='PRJ-202601', period='2026-01', year=2026, month=1,
                                         created_by=self.user)

        result = self.ingest('PPRP', [PPRP_BPN], project=january)

        self.assertIn('tidak mencakup Januari 2026', result.files[0].message)
        self.assertNotIn('tertukar kartu', result.files[0].message)


class DeletePprpTests(IngestTestBase):
    def test_deleting_pprp_reactivates_wtt_rows_and_resyncs_ghp(self):
        project = self.load_wtt(WTT_JULI, 2026, 7)
        pprp = self.ingest('PPRP', [PPRP_BPN], project=project)
        self.ingest('GHP', [GHP_JULI], project=project)
        keys = list(ScheduleVersion.objects.filter(project=project, version_number=2)
                    .values_list('flight_number', 'flight_date'))
        self.assertTrue(keys)
        for fn, d in keys:
            self.assertFalse(ScheduleVersion.objects.get(project=project, flight_number=fn, flight_date=d,
                                                         version_number=1).is_active)

        delete_source_file(pprp.files[0].source_file_id)

        self.assertEqual(ScheduleVersion.objects.filter(project=project, version_number=2).count(), 0)
        reactivated = ScheduleVersion.objects.filter(project=project, version_number=1, is_active=True)
        for fn, d in keys:
            self.assertTrue(reactivated.filter(flight_number=fn, flight_date=d).exists(),
                            f'{fn} {d} harus kembali aktif dari WTT')
        self.assertGreater(reactivated.filter(flight_number__in=[k[0] for k in keys], operational_flag=True).count(), 0,
                           'GHP harus dicocokkan ulang ke baris WTT yang dihidupkan kembali')


class UploadEndpointsTests(IngestTestBase):
    """Kedua pintu HTTP harus memberi hasil yang sama untuk batch yang sama."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.user)
        self.project = self.load_wtt(WTT_JULI, 2026, 7)

    def _post(self, url, data):
        return self.client.post(url, data, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_upload_data_page_processes_all_files(self):
        from unittest import mock
        with mock.patch('core.ingest.UPLOAD_DIR', self.upload_dir):
            resp = self._post('/admin/upload-data/', {
                'file_type': 'PPRP', 'project_id': self.project.id,
                'file': [upload(PPRP_BPN), upload(PPRP_LOP)],
            })
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertTrue(body['success'])
        self.assertEqual([f['status'] for f in body['files']], ['processed', 'processed'])
        self.assertEqual(body['project_id'], self.project.id)

    def test_project_menu_button_processes_all_files(self):
        from unittest import mock
        with mock.patch('core.ingest.UPLOAD_DIR', self.upload_dir):
            resp = self._post(f'/admin/core/project/{self.project.id}/upload-pprp/', {
                'file': [upload(PPRP_BPN), upload(PPRP_LOP)],
            })
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual([f['status'] for f in body['files']], ['processed', 'processed'])
        self.assertEqual(SourceFile.objects.filter(project=self.project, file_type='PPRP').count(), 2)

    def test_both_upload_pages_render(self):
        resp = self.client.get('/admin/upload-data/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'formatIngestResult', resp.content)
        self.assertIn(b'file dipilih', resp.content)
        self.assertIn(b'btn-reset-mode', resp.content)
        self.assertIn(b'replace-modal', resp.content)
        self.assertIn(b'Juli 2026 (PRJ-202607)', resp.content)
        self.assertIn(b'"existing-files"', resp.content)

        resp = self.client.get('/admin/core/project/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'modal-result-notif', resp.content)
        self.assertIn(b'Tutup & Muat Ulang', resp.content)

    def test_all_duplicates_returns_400_with_reasons(self):
        from unittest import mock
        with mock.patch('core.ingest.UPLOAD_DIR', self.upload_dir):
            self._post(f'/admin/core/project/{self.project.id}/upload-pprp/', {'file': [upload(PPRP_BPN)]})
            resp = self._post(f'/admin/core/project/{self.project.id}/upload-pprp/', {'file': [upload(PPRP_BPN)]})
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertFalse(body['success'])
        self.assertEqual(body['files'][0]['status'], 'skipped')
