import os
from django.conf import settings
from django.core.management.base import BaseCommand
from core.models import SourceFile, Project


class Command(BaseCommand):
    help = "Perbaiki path file di database (migrasi dari Windows/lokal ke VPS/Docker Linux) dan cek keberadaan file fisik."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Hanya cek dan tampilkan preview perubahan tanpa mengubah database.',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        media_root = str(settings.MEDIA_ROOT)
        uploads_dir = os.path.join(media_root, 'uploads')

        self.stdout.write(self.style.MIGRATE_HEADING(f"== MEDIA_ROOT target: {media_root} =="))
        self.stdout.write(f"Folder uploads: {uploads_dir}")
        self.stdout.write(f"Folder uploads ada di disk: {os.path.exists(uploads_dir)}")
        self.stdout.write("-" * 60)

        source_files = SourceFile.objects.all().order_by('id')
        total = source_files.count()
        updated_count = 0
        missing_count = 0
        ok_count = 0

        for sf in source_files:
            original_path = sf.file_path or ''
            fname = os.path.basename(original_path.replace('\\', '/'))
            
            # Target path di lingkungan saat ini
            target_path = os.path.join(uploads_dir, fname)
            
            # Cek apakah file fisik ada di target path
            file_exists = os.path.exists(target_path)
            
            if not file_exists:
                # Coba cek di media_root langsung
                alt_path = os.path.join(media_root, fname)
                if os.path.exists(alt_path):
                    target_path = alt_path
                    file_exists = True

            needs_update = (original_path != target_path)

            if file_exists:
                ok_count += 1
                status_icon = self.style.SUCCESS("[ADA]")
            else:
                missing_count += 1
                status_icon = self.style.ERROR("[TIDAK DITEMUKAN]")

            if needs_update:
                updated_count += 1
                self.stdout.write(
                    f"{status_icon} ID {sf.id} ({sf.file_type}):\n"
                    f"   Lama: {original_path}\n"
                    f"   Baru: {target_path}"
                )
                if not dry_run:
                    sf.file_path = target_path
                    sf.save(update_fields=['file_path'])
            else:
                if not file_exists:
                    self.stdout.write(f"{status_icon} ID {sf.id} ({sf.file_type}) - {fname}")

        # Perbaiki juga template_path di Project jika ada
        projects = Project.objects.exclude(template_path='').order_by('id')
        for p in projects:
            p_fname = os.path.basename(p.template_path.replace('\\', '/'))
            p_target = os.path.join(uploads_dir, p_fname)
            if not os.path.exists(p_target):
                alt = os.path.join(media_root, p_fname)
                if os.path.exists(alt):
                    p_target = alt
            if p.template_path != p_target:
                self.stdout.write(
                    f"Project {p.project_id} template:\n"
                    f"   Lama: {p.template_path}\n"
                    f"   Baru: {p_target}"
                )
                if not dry_run:
                    p.template_path = p_target
                    p.save(update_fields=['template_path'])

        self.stdout.write("-" * 60)
        mode_str = "(DRY RUN) " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Selesai! {mode_str}Total record: {total} | "
                f"Path diperbarui: {updated_count} | "
                f"File fisik ditemukan: {ok_count} | "
                f"File fisik hilang: {missing_count}"
            )
        )
        if missing_count > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"\nPerhatian: Ada {missing_count} file belum ada di folder media server!\n"
                    f"Pastikan seluruh file dari media/uploads/ di komputer lokal sudah disalin ke server."
                )
            )
