"""
Susun ulang data turunan setiap bulan dari file-file sumbernya (idempoten):

    python manage.py sync_pprp            # semua bulan
    python manage.py sync_pprp --month 2026-08

Per bulan: surat PPRP dari bulan lain yang mencakup bulan itu ditarik (adopt),
semua surat diterapkan ulang dengan aturan presedensi (surat berlaku terbaru
menang), baris WTT tanpa pengganti dihidupkan, lalu GHP dicocokkan ulang.
Dipakai a.l. untuk backfill setelah aturan surat lintas bulan diberlakukan
(2026-09-03) — sebelumnya surat hanya tercatat di bulan tempat ia diupload.
"""
from django.core.management.base import BaseCommand, CommandError

from core.ingest import period_name, resync_project
from core.models import Project


class Command(BaseCommand):
    help = 'Terapkan ulang surat PPRP (termasuk lintas bulan) dan cocokkan ulang GHP untuk tiap bulan.'

    def add_arguments(self, parser):
        parser.add_argument('--month', help='Hanya bulan ini, format YYYY-MM (default: semua bulan).')

    def handle(self, *args, **options):
        projects = Project.objects.order_by('year', 'month')
        if options.get('month'):
            try:
                y, m = (int(x) for x in options['month'].split('-'))
            except ValueError:
                raise CommandError('Format --month harus YYYY-MM, contoh 2026-08.')
            projects = projects.filter(year=y, month=m)
            if not projects.exists():
                raise CommandError(f'Tidak ada project untuk {period_name(y, m)}.')

        for proj in projects:
            self.stdout.write(self.style.MIGRATE_HEADING(f'== {period_name(proj.year, proj.month)} ({proj.project_id})'))
            messages, warnings = resync_project(proj)
            for msg in messages or ['tidak ada yang berubah.']:
                self.stdout.write(f'   {msg}')
            for w in warnings:
                self.stdout.write(self.style.WARNING(f'   ! {w}'))
        self.stdout.write(self.style.SUCCESS('Selesai.'))
