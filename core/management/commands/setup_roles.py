"""
Inisialisasi atau sinkronisasi peran grup (roles) dan privilege default:

    python manage.py setup_roles

Peran yang dibuat:
1. Station Manager: Pengelolaan proyek, upload/delete file acuan, sinkronisasi ulang, download laporan, kelola staf.
2. Operator: Upload file acuan (WTT/PPRP/GHP), lihat jadwal, preview & download laporan, lihat dashboard.
3. Management Viewer: Akses read-only ke dashboard, jadwal, dan laporan.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


ROLE_PERMISSIONS = {
    'Station Manager': {
        'description': 'Supervisor operasional: kelola proyek, upload & hapus data, sinkronisasi, dan kelola staf operator.',
        'permissions': [
            # Core
            ('core', 'project', 'view_project'),
            ('core', 'project', 'add_project'),
            ('core', 'project', 'change_project'),
            ('core', 'sourcefile', 'view_sourcefile'),
            ('core', 'sourcefile', 'add_sourcefile'),
            ('core', 'sourcefile', 'change_sourcefile'),
            ('core', 'sourcefile', 'delete_sourcefile'),
            ('core', 'scheduleversion', 'view_scheduleversion'),
            ('core', 'scheduleversion', 'change_scheduleversion'),
            # Auth
            ('auth', 'user', 'view_user'),
            ('auth', 'user', 'change_user'),
            ('auth', 'group', 'view_group'),
        ],
    },
    'Operator': {
        'description': 'Staf operasional: unggah file sumber, pantau jadwal penerbangan, dan unduh laporan.',
        'permissions': [
            ('core', 'project', 'view_project'),
            ('core', 'sourcefile', 'view_sourcefile'),
            ('core', 'sourcefile', 'add_sourcefile'),
            ('core', 'scheduleversion', 'view_scheduleversion'),
        ],
    },
    'Management Viewer': {
        'description': 'Akses peninjau eksekutif / manajemen: lihat dashboard analitik, jadwal, dan laporan (read-only).',
        'permissions': [
            ('core', 'project', 'view_project'),
            ('core', 'sourcefile', 'view_sourcefile'),
            ('core', 'scheduleversion', 'view_scheduleversion'),
        ],
    },
}


class Command(BaseCommand):
    help = 'Inisialisasi peran grup (Group) dan permissions bawaan sistem Citilink AVIOR.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('== Menyiapkan Role dan Privilege Pengguna Citilink AVIOR =='))

        for role_name, config in ROLE_PERMISSIONS.items():
            group, created = Group.objects.get_or_create(name=role_name)
            action_label = 'Dibuat' if created else 'Diperbarui'

            perms_to_set = []
            for app_label, model, codename in config['permissions']:
                try:
                    perm = Permission.objects.get(
                        content_type__app_label=app_label,
                        content_type__model=model,
                        codename=codename,
                    )
                    perms_to_set.append(perm)
                except Permission.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'   ! Permission tidak ditemukan: {app_label}.{codename}'))

            group.permissions.set(perms_to_set)
            self.stdout.write(
                self.style.SUCCESS(f'[OK] [{action_label}] Grup "{role_name}" ({len(perms_to_set)} hak akses)')
            )
            self.stdout.write(f'   Deskripsi: {config["description"]}')

        self.stdout.write(self.style.SUCCESS('\nSemua peran berhasil disinkronkan.'))
