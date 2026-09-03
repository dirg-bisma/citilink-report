"""
Uji surat PPRP lintas bulan (2026-09-03):
- fan-out : surat yang diproses di satu bulan otomatis diterapkan ke bulan lain
            yang ada di dalam rentang berlakunya;
- adopt   : project bulan baru menarik surat lama yang mencakupnya;
- presedensi: satu flight+tanggal dipegang surat yang tanggal berlakunya
            terbaru, apa pun urutan uploadnya;
- hapus   : mencabut surat menghapusnya dari SEMUA bulan, tanggal yang
            ditinggalkan kembali ke surat lain atau ke jadwal WTT.

Jalankan:  python manage.py test tests.test_cross_month
"""
import datetime
import os

from django.test import SimpleTestCase

from core.models import ScheduleVersion, SourceFile
from core.services import delete_source_file, letter_rank
from tests.test_ingest import SRC, WTT_JULI, WTT_MARET, IngestTestBase

WTT_AGUSTUS = os.path.join(SRC, 'Working Time Table Agustus 2026 [WTT].pdf')
PPRP_UPG_JUL = os.path.join(SRC, 'PPRP SUB-UPG S26 UPDATE.pdf')       # AU.012/47/2 : QG350/352/354, 13 Jul - 24 Okt
PPRP_UPG_AUG = os.path.join(SRC, 'PPRP SUB-UPG S26 UPDATE AUG.pdf')   # AU.012/50/15: QG350/352/354 5 Agu-, QG356 14 Agu-

L_JUL = 'AU.012/47/2/DJPU-DAU-2026'
L_AUG = 'AU.012/50/15/DRJU-DAU-2026'


def letter_by_date(project, flight):
    """{tanggal: nomor surat} baris v2 aktif satu flight di satu project."""
    return {sv.flight_date: sv.pprp_letter for sv in ScheduleVersion.objects.filter(
        project=project, flight_number=flight, version_number=2, is_active=True)}


def active_v1(project, flight):
    return ScheduleVersion.objects.filter(project=project, flight_number=flight, version_number=1, is_active=True)


def letter_files(letter_path_hash):
    return SourceFile.objects.filter(file_type='PPRP', file_hash=letter_path_hash).order_by('project__month')


class LetterRankTests(SimpleTestCase):
    def test_effective_date_first_then_letter_number(self):
        older = letter_rank(datetime.date(2026, 7, 13), L_JUL)
        newer = letter_rank(datetime.date(2026, 8, 5), L_AUG)
        self.assertGreater(newer, older)
        # Tanggal sama -> nomor surat lebih tinggi menang, dibandingkan sebagai angka
        d = datetime.date(2026, 8, 5)
        self.assertGreater(letter_rank(d, L_AUG), letter_rank(d, L_JUL))
        self.assertGreater(letter_rank(d, 'AU.012/10/1/DJPU-DAU-2026'), letter_rank(d, 'AU.012/9/1/DJPU-DAU-2026'))


class FanOutTests(IngestTestBase):
    def test_letter_uploaded_to_july_is_applied_to_august_too(self):
        juli = self.load_wtt(WTT_JULI, 2026, 7)
        agu = self.load_wtt(WTT_AGUSTUS, 2026, 8)
        self.load_wtt(WTT_MARET, 2026, 3)   # di luar rentang surat -> tidak boleh kebagian

        result = self.ingest('PPRP', [PPRP_UPG_JUL], project=juli)

        self.assertTrue(result.success, [f.message for f in result.files])
        fr = result.files[0]
        self.assertEqual(fr.also_applied_to, ['Agustus 2026'])
        self.assertIn('Agustus 2026', fr.message)
        src = SourceFile.objects.get(id=fr.source_file_id)
        self.assertEqual([sf.project.month for sf in letter_files(src.file_hash)], [7, 8])
        self.assertEqual([sf.file_path for sf in letter_files(src.file_hash)], [src.file_path] * 2)

        aug = letter_by_date(agu, 'QG350')
        self.assertEqual(len(aug), 31)
        self.assertEqual(set(aug.values()), {L_JUL})
        self.assertFalse(active_v1(agu, 'QG350').exists())
        jul = letter_by_date(juli, 'QG350')
        self.assertEqual(min(jul), datetime.date(2026, 7, 13))
        self.assertEqual(len(jul), 19)

    def test_new_month_adopts_letters_uploaded_earlier(self):
        juli = self.load_wtt(WTT_JULI, 2026, 7)
        self.ingest('PPRP', [PPRP_UPG_JUL], project=juli)

        result = self.ingest('WTT', [WTT_AGUSTUS])

        self.assertTrue(result.success, [f.message for f in result.files])
        agu = result.project
        self.assertEqual((agu.year, agu.month), (2026, 8))
        self.assertEqual(SourceFile.objects.filter(project=agu, file_type='PPRP').count(), 1)
        self.assertTrue(any('diterapkan otomatis' in m and L_JUL in m for m in result.resync_messages),
                        result.resync_messages)
        self.assertEqual(set(letter_by_date(agu, 'QG352').values()), {L_JUL})
        self.assertFalse(active_v1(agu, 'QG352').exists())

    def test_pprp_without_project_lands_in_first_month_inside_its_range(self):
        agu = self.load_wtt(WTT_AGUSTUS, 2026, 8)

        result = self.ingest('PPRP', [PPRP_UPG_JUL])   # berlaku sejak 13 Jul, project Juli tidak ada

        self.assertTrue(result.success, [f.message for f in result.files])
        self.assertEqual(result.project.id, agu.id)
        self.assertEqual(len(letter_by_date(agu, 'QG354')), 31)

    def test_pprp_outside_every_month_is_refused_with_its_range(self):
        self.load_wtt(WTT_MARET, 2026, 3)

        result = self.ingest('PPRP', [PPRP_UPG_JUL])

        self.assertFalse(result.success)
        self.assertIn('13 Jul 2026 s/d 24 Okt 2026', result.files[0].message)


class PrecedenceTests(IngestTestBase):
    def assert_august_is_split_on_5_august(self, agu):
        m = letter_by_date(agu, 'QG350')
        self.assertEqual(len(m), 31)
        for d, letter in sorted(m.items()):
            self.assertEqual(letter, L_JUL if d.day < 5 else L_AUG, d)
        self.assertFalse(active_v1(agu, 'QG350').exists())
        # Setiap tanggal hanya punya SATU baris v2
        self.assertEqual(ScheduleVersion.objects.filter(project=agu, flight_number='QG350', version_number=2).count(), 31)
        # QG356 hanya ada di surat Agustus, mulai 14 Agu
        m356 = letter_by_date(agu, 'QG356')
        self.assertEqual(min(m356), datetime.date(2026, 8, 14))
        self.assertEqual(set(m356.values()), {L_AUG})

    def test_latest_effective_letter_wins_when_older_is_uploaded_first(self):
        juli = self.load_wtt(WTT_JULI, 2026, 7)
        agu = self.load_wtt(WTT_AGUSTUS, 2026, 8)
        self.ingest('PPRP', [PPRP_UPG_JUL], project=juli)
        self.ingest('PPRP', [PPRP_UPG_AUG], project=agu)

        self.assert_august_is_split_on_5_august(agu)
        # Surat Agustus tidak mencakup Juli -> Juli tetap hanya punya surat Juli
        self.assertEqual(SourceFile.objects.filter(project=juli, file_type='PPRP').count(), 1)
        self.assertEqual(set(letter_by_date(juli, 'QG350').values()), {L_JUL})

    def test_latest_effective_letter_wins_when_newer_is_uploaded_first(self):
        juli = self.load_wtt(WTT_JULI, 2026, 7)
        agu = self.load_wtt(WTT_AGUSTUS, 2026, 8)
        self.ingest('PPRP', [PPRP_UPG_AUG], project=agu)
        self.ingest('PPRP', [PPRP_UPG_JUL], project=juli)

        self.assert_august_is_split_on_5_august(agu)
        self.assertEqual(SourceFile.objects.filter(project=juli, file_type='PPRP').count(), 1)


class DeleteLetterTests(IngestTestBase):
    def test_deleting_newer_letter_hands_its_dates_back_to_older_letter(self):
        juli = self.load_wtt(WTT_JULI, 2026, 7)
        agu = self.load_wtt(WTT_AGUSTUS, 2026, 8)
        self.ingest('PPRP', [PPRP_UPG_JUL], project=juli)
        res_aug = self.ingest('PPRP', [PPRP_UPG_AUG], project=agu)

        res = delete_source_file(res_aug.files[0].source_file_id)

        self.assertEqual(res['projects'], ['2026-08'])
        m = letter_by_date(agu, 'QG350')
        self.assertEqual(len(m), 31)
        self.assertEqual(set(m.values()), {L_JUL})      # bukan kembali ke WTT
        self.assertFalse(active_v1(agu, 'QG350').exists())
        self.assertFalse(ScheduleVersion.objects.filter(project=agu, flight_number='QG356').exists())

    def test_deleting_a_letter_removes_every_copy_and_its_file(self):
        juli = self.load_wtt(WTT_JULI, 2026, 7)
        agu = self.load_wtt(WTT_AGUSTUS, 2026, 8)
        res_jul = self.ingest('PPRP', [PPRP_UPG_JUL], project=juli)
        src = SourceFile.objects.get(id=res_jul.files[0].source_file_id)
        self.assertEqual(letter_files(src.file_hash).count(), 2)
        self.assertTrue(os.path.exists(src.file_path))

        res = delete_source_file(src.id)

        self.assertEqual(res['projects'], ['2026-07', '2026-08'])
        self.assertEqual(letter_files(src.file_hash).count(), 0)
        self.assertFalse(os.path.exists(src.file_path))
        for proj in (juli, agu):
            self.assertFalse(ScheduleVersion.objects.filter(project=proj, version_number=2).exists())
            self.assertTrue(active_v1(proj, 'QG350').exists())

    def test_replacing_wtt_keeps_letters_adopted_from_other_months(self):
        juli = self.load_wtt(WTT_JULI, 2026, 7)
        self.ingest('PPRP', [PPRP_UPG_JUL], project=juli)
        agu = self.ingest('WTT', [WTT_AGUSTUS]).project

        result = self.ingest('WTT', [WTT_AGUSTUS], project=agu, replace=True)

        self.assertTrue(result.success, [f.message for f in result.files])
        self.assertEqual(SourceFile.objects.filter(project=agu, file_type='PPRP').count(), 1)
        m = letter_by_date(agu, 'QG350')
        self.assertEqual(len(m), 31)
        self.assertEqual(set(m.values()), {L_JUL})
        self.assertFalse(active_v1(agu, 'QG350').exists())
