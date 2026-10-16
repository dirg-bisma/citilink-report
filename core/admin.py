from django.contrib import admin
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.shortcuts import redirect, render
from django.urls import path
from django.http import FileResponse, HttpResponse
from django.utils.html import format_html
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from core.models import Project, SourceFile, ScheduleVersion
from core.ingest import ingest_uploaded_files, resync_project
from core.report import generate_report
import os

admin.site.unregister(User)
admin.site.unregister(Group)

from django.utils.safestring import mark_safe

# Custom permission display labels for Citilink AVIOR RBAC
PERMISSION_DISPLAY_LABELS = {
    # Reference Documents (core.sourcefile)
    ('core', 'sourcefile', 'view_sourcefile'): 'Reference Documents | Can view uploaded files history',
    ('core', 'sourcefile', 'add_sourcefile'): 'Reference Documents | Can upload reference files (WTT/PPRP/GHP)',
    ('core', 'sourcefile', 'change_sourcefile'): 'Reference Documents | Can resynchronize flight schedules (Resync)',
    ('core', 'sourcefile', 'delete_sourcefile'): 'Reference Documents | Can delete uploaded files',

    # Flight Schedules (core.scheduleversion)
    ('core', 'scheduleversion', 'view_scheduleversion'): 'Flight Schedules | Can view flight schedule & OTP records',
    ('core', 'scheduleversion', 'change_scheduleversion'): 'Flight Schedules | Can edit flight schedule records',
    ('core', 'scheduleversion', 'add_scheduleversion'): 'Flight Schedules | Can add raw flight schedule records',
    ('core', 'scheduleversion', 'delete_scheduleversion'): 'Flight Schedules | Can delete raw flight schedule records',

    # Flight Periods (core.project)
    ('core', 'project', 'view_project'): 'Flight Periods | Can view flight periods & OTP reports',
    ('core', 'project', 'add_project'): 'Flight Periods | Can create new flight period',
    ('core', 'project', 'change_project'): 'Flight Periods | Can edit flight period details',
    ('core', 'project', 'delete_project'): 'Flight Periods | Can delete flight period',

    # User Accounts (auth.user)
    ('auth', 'user', 'view_user'): 'User Accounts | Can view staff accounts',
    ('auth', 'user', 'add_user'): 'User Accounts | Can create new staff account',
    ('auth', 'user', 'change_user'): 'User Accounts | Can edit staff accounts & permissions',
    ('auth', 'user', 'delete_user'): 'User Accounts | Can delete staff account',

    # User Roles (auth.group)
    ('auth', 'group', 'view_group'): 'User Roles | Can view user roles & groups',
    ('auth', 'group', 'add_group'): 'User Roles | Can create new user role',
    ('auth', 'group', 'change_group'): 'User Roles | Can edit user roles & permissions',
    ('auth', 'group', 'delete_group'): 'User Roles | Can delete user role',
}


def format_permission_label(perm):
    key = (perm.content_type.app_label, perm.content_type.model, perm.codename)
    if key in PERMISSION_DISPLAY_LABELS:
        return PERMISSION_DISPLAY_LABELS[key]
    model_name = perm.content_type.model.replace('_', ' ').title()
    return f"{model_name} | {perm.name}"


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_display = ['username', 'email', 'first_name', 'last_name', 'display_roles', 'is_staff', 'is_active']
    list_filter = ['groups', 'is_staff', 'is_active', 'is_superuser']
    actions = ['assign_operator', 'assign_station_manager', 'assign_viewer']

    @display(description="Role / Grup")
    def display_roles(self, obj):
        badges = []
        if obj.is_superuser:
            badges.append(
                '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-900 dark:bg-amber-950/50 dark:text-amber-300 mr-1">'
                'Super Admin</span>'
            )
        groups = list(obj.groups.all())
        if not groups and not obj.is_superuser:
            return mark_safe(
                '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300">'
                'Tanpa Role</span>'
            )
        for g in groups:
            if g.name == 'Station Manager':
                color_class = "bg-green-100 text-[#006b32] dark:bg-green-950/50 dark:text-green-300 border border-green-200 dark:border-green-800"
            elif g.name == 'Operator':
                color_class = "bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300 border border-blue-200 dark:border-blue-800"
            elif g.name == 'Management Viewer':
                color_class = "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border border-slate-200 dark:border-slate-700"
            else:
                color_class = "bg-purple-100 text-purple-800 dark:bg-purple-950/50 dark:text-purple-300 border border-purple-200"
            badges.append(
                f'<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold {color_class} mr-1">{g.name}</span>'
            )
        return mark_safe(''.join(badges))

    @admin.action(description="Tetapkan role terpilih sebagai Operator")
    def assign_operator(self, request, queryset):
        grp = Group.objects.filter(name='Operator').first()
        if grp:
            for u in queryset:
                u.groups.add(grp)
            self.message_user(request, f"{queryset.count()} pengguna berhasil ditetapkan sebagai Operator.")

    @admin.action(description="Tetapkan role terpilih sebagai Station Manager")
    def assign_station_manager(self, request, queryset):
        grp = Group.objects.filter(name='Station Manager').first()
        if grp:
            for u in queryset:
                u.groups.add(grp)
            self.message_user(request, f"{queryset.count()} pengguna berhasil ditetapkan sebagai Station Manager.")

    @admin.action(description="Tetapkan role terpilih sebagai Management Viewer")
    def assign_viewer(self, request, queryset):
        grp = Group.objects.filter(name='Management Viewer').first()
        if grp:
            for u in queryset:
                u.groups.add(grp)
            self.message_user(request, f"{queryset.count()} pengguna berhasil ditetapkan sebagai Management Viewer.")

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "user_permissions":
            kwargs["queryset"] = Permission.objects.filter(
                content_type__app_label__in=['core', 'auth']
            ).exclude(content_type__model='permission').select_related('content_type')
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "user_permissions" and field:
            field.label_from_instance = format_permission_label
            field.help_text = "Pilih hak akses di kolom kiri dan klik tombol panah (>) untuk menambahkan, atau pilih di kolom kanan dan klik panah (<) untuk menghapus."
        return field


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    list_display = ['name', 'display_user_count', 'display_permissions_summary']

    @display(description="Jumlah Pengguna")
    def display_user_count(self, obj):
        count = obj.user_set.count()
        return format_html(
            '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-base-100 text-font-important-light dark:bg-base-800 dark:text-font-important-dark">{} Pengguna</span>',
            count
        )

    @display(description="Ringkasan Privilege")
    def display_permissions_summary(self, obj):
        count = obj.permissions.count()
        core_count = obj.permissions.filter(content_type__app_label='core').count()
        auth_count = obj.permissions.filter(content_type__app_label='auth').count()
        return f"{count} hak akses aktif ({core_count} Operasional, {auth_count} Administrasi)"

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "permissions":
            kwargs["queryset"] = Permission.objects.filter(
                content_type__app_label__in=['core', 'auth']
            ).exclude(content_type__model='permission').select_related('content_type')
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "permissions" and field:
            field.label_from_instance = format_permission_label
            field.help_text = "Pilih hak akses di kolom kiri dan klik tombol panah (>) untuk menambahkan, atau pilih di kolom kanan dan klik panah (<) untuk menghapus."
        return field


from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.http import JsonResponse
from core.report import get_project_report_data, generate_report, generate_rekap_report, INDONESIAN_MONTHS


# Tombol baris tabel (Upload PPRP / Lihat Laporan / Detail) sengaja dibiarkan
# bergaya lama (hijau solid, #006b32 inline) atas permintaan pemilik 2026-09-15;
# versi kelas Unfold sempat dicoba dan dinilai jelek.
@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ['project_id', 'period', 'year', 'month', 'created_by', 'created_at', 'pprp_action', 'view_report_action']
    list_filter = ['year', 'month', 'period']
    search_fields = ['project_id']
    
    @display(description="Upload PPRP")
    def pprp_action(self, obj):
        return format_html(
            '<button type="button" onclick="openPprpModal({}, \'{}\')" class="inline-flex items-center justify-center gap-1.5 text-white text-xs font-bold px-3.5 py-2 rounded-lg shadow-sm hover:brightness-110 active:scale-95 transition-all cursor-pointer select-none" style="background-color: #006b32; color: #ffffff !important; text-decoration: none;" title="Upload dokumen surat izin PPRP untuk project ini">'
            '<span class="material-symbols-outlined text-[17px] text-white">cloud_upload</span>'
            '<span>Upload PPRP</span>'
            '</button>',
            obj.pk,
            obj.project_id
        )

    @display(description="Laporan")
    def view_report_action(self, obj):
        url = f"/admin/core/project/{obj.pk}/view-report/"
        return format_html(
            '<a href="{}" target="_blank" class="inline-flex items-center justify-center gap-1.5 text-white text-xs font-bold px-3.5 py-2 rounded-lg shadow-sm hover:brightness-110 active:scale-95 transition-all cursor-pointer select-none" style="background-color: #006b32; color: #ffffff !important; text-decoration: none;" title="Buka tampilan laporan realisasi di tab baru">'
            '<span class="material-symbols-outlined text-[17px] text-white">visibility</span>'
            '<span>Lihat Laporan</span>'
            '</a>',
            url
        )
        
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('download-rekap/', self.admin_site.admin_view(self.download_rekap_view), name='project_download_rekap'),
            path('<int:project_id>/download/', self.admin_site.admin_view(self.download_report), name='project_download'),
            path('<int:project_id>/upload-pprp/', self.admin_site.admin_view(self.upload_pprp_view), name='project_upload_pprp'),
            path('<int:project_id>/view-report/', self.admin_site.admin_view(self.view_report_view), name='project_view_report'),
        ]
        return custom_urls + urls
        
    def view_report_view(self, request, project_id):
        project = Project.objects.get(id=project_id)

        # Dua tahap: penyusunan laporan makan beberapa detik, sedangkan tombol
        # View membuka tab baru — tanpa ini tab tsb kosong selama proses.
        # Tahap 1 mengirim layar progres (tanpa query berat); layar itu menarik
        # laporan aslinya lewat ?data=1 lalu menggantikan isi halaman.
        if request.GET.get('data') != '1':
            return render(request, 'admin/core/project/report_loading.html', {
                'project': project,
                'month_name': INDONESIAN_MONTHS.get(project.month, ''),
                'title': f"Menyusun Laporan {project.project_id}",
            })

        report_data = get_project_report_data(project.id)
        context = {
            'project': project,
            'report': report_data,
            'title': f"Laporan Realisasi {project.project_id}",
        }
        return render(request, 'admin/core/project/report_view.html', context)
    
    def upload_pprp_view(self, request, project_id):
        # Pintu yang sama dengan halaman Upload Data (core.ingest): semua file
        # diproses satu per satu, hasil per file dilaporkan, GHP disinkronkan ulang.
        if not request.user.has_perm('core.add_sourcefile'):
            return JsonResponse({'success': False, 'message': 'Anda tidak memiliki izin untuk mengunggah file PPRP.'}, status=403)

        if request.method != 'POST':
            return JsonResponse({'success': False, 'message': 'Method POST required.'}, status=405)

        uploaded_files = request.FILES.getlist('file')
        if not uploaded_files:
            return JsonResponse({'success': False, 'message': 'Pilih minimal 1 file PDF PPRP.'}, status=400)

        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Project tidak ditemukan.'}, status=404)

        try:
            result = ingest_uploaded_files('PPRP', uploaded_files, request.user, project=project)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

        return JsonResponse(result.as_dict(), status=200 if result.success else 400)

    def download_report(self, request, project_id):
        if not request.user.has_perm('core.view_project'):
            self.message_user(request, "Anda tidak memiliki izin untuk mengunduh laporan ini.", level='error')
            from django.shortcuts import redirect
            return redirect('/admin/core/project/')
        import tempfile
        try:
            project = Project.objects.get(id=project_id)
            # Simpan ke file sementara
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
                output_path = tmp.name
            count = generate_report(project_id, project.template_path, output_path)
            filename = f"Report_{project.project_id}_{project.year}-{project.month:02d}.xlsx"
            response = FileResponse(
                open(output_path, 'rb'),
                as_attachment=True,
                filename=filename
            )
            return response
        except FileNotFoundError as e:
            self.message_user(request, str(e), level='error')
            from django.shortcuts import redirect
            return redirect(f'/admin/core/project/')
        except Exception as e:
            self.message_user(request, f"Gagal generate report: {e}", level='error')
            from django.shortcuts import redirect
            return redirect(f'/admin/core/project/')

    def download_rekap_view(self, request):
        if not request.user.has_perm('core.view_project'):
            self.message_user(request, "Anda tidak memiliki izin untuk mengunduh laporan rekap.", level='error')
            from django.shortcuts import redirect
            return redirect('/admin/core/project/')
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
                output_path = tmp.name
            count = generate_rekap_report(output_path)
            filename = f"Report_Rekap_Satu_Musim.xlsx"
            response = FileResponse(
                open(output_path, 'rb'),
                as_attachment=True,
                filename=filename
            )
            return response
        except ValueError as e:
            self.message_user(request, str(e), level='warning')
            from django.shortcuts import redirect
            return redirect(f'/admin/core/project/')
        except Exception as e:
            self.message_user(request, f"Gagal generate rekap: {e}", level='error')
            from django.shortcuts import redirect
            return redirect(f'/admin/core/project/')



@admin.register(SourceFile)
class SourceFileAdmin(ModelAdmin):
    list_display = ['project', 'file_type', 'status', 'uploaded_by', 'uploaded_at']
    list_filter = ['file_type', 'status']
    search_fields = ['project__project_id']
    actions = ['resync_months']

    @admin.action(description='Sinkronkan ulang bulan file terpilih (surat PPRP + GHP)')
    def resync_months(self, request, queryset):
        if not request.user.has_perm('core.change_sourcefile'):
            self.message_user(request, "Anda tidak memiliki izin untuk melakukan sinkronisasi ulang data.", level='error')
            return
        # Dulu aksi ini memanggil parser langsung ("Process selected files")
        # tanpa validasi dan tanpa sinkronisasi turunan — pintu ketiga yang
        # bisa membuat jadwal dobel. Sekarang memakai jalur yang sama dengan
        # halaman Upload Data: susun ulang bulan dari file-file sumbernya.
        projects = {sf.project for sf in queryset.select_related('project')}
        for proj in sorted(projects, key=lambda p: (p.year, p.month)):
            messages_, warnings = resync_project(proj)
            for m in messages_ or [f"{proj}: tidak ada yang perlu disinkronkan."]:
                self.message_user(request, m)
            for w in warnings:
                self.message_user(request, w, level='WARNING')


from unfold.contrib.filters.admin import DropdownFilter


class MonthDropdownFilter(DropdownFilter):
    title = "Bulan"
    parameter_name = "month"

    def lookups(self, request, model_admin):
        return [
            ("1", "Januari"),
            ("2", "Februari"),
            ("3", "Maret"),
            ("4", "April"),
            ("5", "Mei"),
            ("6", "Juni"),
            ("7", "Juli"),
            ("8", "Agustus"),
            ("9", "September"),
            ("10", "Oktober"),
            ("11", "November"),
            ("12", "Desember"),
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(flight_date__month=self.value())
        return queryset


class YearDropdownFilter(DropdownFilter):
    title = "Tahun"
    parameter_name = "year"

    def lookups(self, request, model_admin):
        years = [str(y) for y in range(2024, 2029)]
        return [(y, y) for y in years]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(flight_date__year=self.value())
        return queryset


@admin.register(ScheduleVersion)
class ScheduleVersionAdmin(ModelAdmin):
    list_display = [
        'display_project',
        'display_flight_number', 
        'display_route',
        'flight_date', 
        'display_schedule',
        'display_status',
        'display_operated',
        'detail_action',
    ]
    list_filter = [
        MonthDropdownFilter,
        YearDropdownFilter,
        'project',
        'is_active',
        'operational_flag',
        'origin',
        'destination',
    ]
    list_filter_options = {
        'month': {
            'horizontal': True,
        },
        'year': {
            'horizontal': True,
        },
    }
    search_fields = ['flight_number']
    list_per_page = 50
    
    @display(description="Project")
    def display_project(self, obj):
        return obj.project.project_id

    @display(description="Flight")
    def display_flight_number(self, obj):
        return format_html(
            '<strong>{}</strong> <span class="text-xs text-font-subtle-light dark:text-font-subtle-dark">(v{})</span>',
            obj.flight_number, obj.version_number)

    @display(description="Rute")
    def display_route(self, obj):
        return f"{obj.origin} → {obj.destination}"

    @display(description="Jadwal (STD → STA)")
    def display_schedule(self, obj):
        std_str = obj.std.strftime('%H:%M') if obj.std else '--:--'
        sta_str = obj.sta.strftime('%H:%M') if obj.sta else '--:--'
        return f"{std_str} → {sta_str}"

    @display(description="Status", label={"ACTIVE": "success", "INACTIVE (PPRP)": "danger"})
    def display_status(self, obj):
        if obj.is_active:
            return "ACTIVE"
        return "INACTIVE (PPRP)"

    # Warna sama dengan badge OPERATED/NO OPS di kartu rincian: hijau/merah,
    # tanpa biru (satu warna aksen, docs/ui-cleanup.md §2).
    @display(description="Operasi", label={"OPERATED": "success", "UNVERIFIED": "danger"})
    def display_operated(self, obj):
        if obj.operational_flag:
            return "OPERATED"
        return "UNVERIFIED"

    @display(description="Aksi")
    def detail_action(self, obj):
        return format_html(
            '<button type="button" onclick="openScheduleDetailModal({})" class="inline-flex items-center justify-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-md bg-green-50 text-[#006b32] dark:bg-green-950/30 dark:text-green-400 border border-green-200 dark:border-green-800 hover:bg-[#006b32] hover:text-white dark:hover:bg-[#006b32] dark:hover:text-white shadow-2xs transition-all cursor-pointer" title="Lihat rincian lengkap verifikasi data">'
            '<span class="material-symbols-outlined text-[15px]">info</span> Detail'
            '</button>',
            obj.pk
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:object_id>/detail-json/', self.admin_site.admin_view(self.detail_json_view), name='scheduleversion_detail_json'),
        ]
        return custom_urls + urls

    def detail_json_view(self, request, object_id):
        try:
            s = ScheduleVersion.objects.select_related('project', 'source_wtt', 'source_pprp').get(id=object_id)
            
            # GHP Source file if any
            ghp_sf = SourceFile.objects.filter(project=s.project, file_type='GHP', status='SUCCESS').first()
            ghp_filename = os.path.basename(ghp_sf.file_path) if ghp_sf else 'Belum ada file GHP'
            
            wtt_filename = os.path.basename(s.source_wtt.file_path) if s.source_wtt else '-'
            pprp_filename = os.path.basename(s.source_pprp.file_path) if s.source_pprp else '-'
            
            # Determine reason
            if s.operational_flag:
                ops_status_desc = "Penerbangan terkonfirmasi beroperasi (Ditemukan catatan pergerakan pada log aktual GHP)"
            else:
                if not s.is_active:
                    ops_status_desc = "Jadwal lama tidak aktif karena telah digantikan oleh penetapan izin PPRP baru"
                else:
                    ops_status_desc = "Penerbangan tidak ditemukan pada data GHP yang diunggah (Batal / Tidak Beroperasi / No Ops)"
            
            indonesian_months = {
                1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni",
                7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November", 12: "Desember"
            }
            d = s.flight_date
            flight_date_str = f"{d.day:02d} {indonesian_months.get(d.month, '')} {d.year}"
            pprp_date_str = f"{s.pprp_date.day:02d} {indonesian_months.get(s.pprp_date.month, '')} {s.pprp_date.year}" if s.pprp_date else '-'
            
            c = s.created_at
            if c:
                created_at_str = f"{c.day:02d} {indonesian_months.get(c.month, '')} {c.year}, {c.strftime('%H:%M')} WIB"
            else:
                created_at_str = '-'

            data = {
                'id': s.id,
                'project_id': s.project.project_id,
                'flight_number': s.flight_number,
                'version_number': s.version_number,
                'flight_date': flight_date_str,
                'created_at': created_at_str,
                'origin': s.origin,
                'destination': s.destination,
                'std': s.std.strftime('%H:%M') if s.std else '--:--',
                'sta': s.sta.strftime('%H:%M') if s.sta else '--:--',
                'atd': s.atd.strftime('%H:%M') if s.atd else '--:--',
                'ata': s.ata.strftime('%H:%M') if s.ata else '--:--',
                'is_active': s.is_active,
                'operational_flag': s.operational_flag,
                'pprp_letter': s.pprp_letter or '-',
                'pprp_date': pprp_date_str,
                'source_wtt': wtt_filename,
                'source_pprp': pprp_filename,
                'source_ghp': ghp_filename,
                'ops_status_desc': ops_status_desc,
            }
            return JsonResponse({'success': True, 'data': data})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=404)

