from django.contrib import admin
from django.contrib.auth.models import User, Group
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
from core.services import process_wtt, process_pprp, process_ghp
from core.report import generate_report
import os

admin.site.unregister(User)
admin.site.unregister(Group)

@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.http import JsonResponse
from django.core.files.storage import FileSystemStorage
from core.report import get_project_report_data, generate_report


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
    
    @display(description="View Report")
    def view_report_action(self, obj):
        url = f"/admin/core/project/{obj.pk}/view-report/"
        return format_html(
            '<a href="{}" target="_blank" class="inline-flex items-center justify-center gap-1.5 text-white text-xs font-bold px-3.5 py-2 rounded-lg shadow-sm hover:brightness-110 active:scale-95 transition-all cursor-pointer select-none" style="background-color: #006b32; color: #ffffff !important; text-decoration: none;" title="Buka tampilan laporan realisasi di tab baru">'
            '<span class="material-symbols-outlined text-[17px] text-white">visibility</span>'
            '<span>View Report</span>'
            '</a>',
            url
        )
        
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:project_id>/download/', self.admin_site.admin_view(self.download_report), name='project_download'),
            path('<int:project_id>/upload-pprp/', self.admin_site.admin_view(self.upload_pprp_view), name='project_upload_pprp'),
            path('<int:project_id>/view-report/', self.admin_site.admin_view(self.view_report_view), name='project_view_report'),
        ]
        return custom_urls + urls
        
    def view_report_view(self, request, project_id):
        project = Project.objects.get(id=project_id)
        report_data = get_project_report_data(project.id)
        context = {
            'project': project,
            'report': report_data,
            'title': f"Laporan Realisasi {project.project_id}",
        }
        return render(request, 'admin/core/project/report_view.html', context)
    
    def upload_pprp_view(self, request, project_id):
        if request.method != 'POST':
            return JsonResponse({'success': False, 'message': 'Method POST required.'}, status=405)
            
        uploaded_files = request.FILES.getlist('file')
        if not uploaded_files:
            return JsonResponse({'success': False, 'message': 'Pilih minimal 1 file PDF PPRP.'}, status=400)
            
        try:
            project = Project.objects.get(id=project_id)
            total_count = 0
            processed_files_count = 0
            skipped_files_count = 0
            
            for uploaded_file in uploaded_files:
                file_content = uploaded_file.read()
                file_hash = SourceFile.compute_hash(file_content)
                uploaded_file.seek(0)
                
                # Skip duplicate file if already uploaded for this project
                if SourceFile.objects.filter(project=project, file_type='PPRP', file_hash=file_hash).exists():
                    skipped_files_count += 1
                    continue
                    
                fs = FileSystemStorage(location=os.path.join('media', 'uploads'))
                filename = fs.save(uploaded_file.name, uploaded_file)
                file_path = fs.path(filename)
                
                source_file = SourceFile.objects.create(
                    project=project,
                    file_type='PPRP',
                    file_path=file_path,
                    file_hash=file_hash,
                    uploaded_by=request.user,
                    status='PROCESSING'
                )
                
                count = process_pprp(project.id, source_file.id)
                total_count += count
                processed_files_count += 1
                
            # Smart Re-Sync: If GHP file exists for this project, re-match operational flags!
            ghp_file = SourceFile.objects.filter(project=project, file_type='GHP', status='SUCCESS').first()
            if ghp_file:
                process_ghp(project.id, ghp_file.id)
                    
            if processed_files_count == 0 and skipped_files_count > 0:
                return JsonResponse({'success': False, 'message': 'Seluruh file yang dipilih sudah pernah diupload sebelumnya.'}, status=400)

            msg = f'Berhasil memproses {processed_files_count} file PPRP ({total_count} jadwal rute SUB terupdate).'
            if skipped_files_count > 0:
                msg += f' ({skipped_files_count} file duplikat dilewati).'

            return JsonResponse({
                'success': True,
                'message': msg,
                'count': total_count,
                'files_count': processed_files_count,
                'project_id': project.id,
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
    def download_report(self, request, project_id):
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



@admin.register(SourceFile)
class SourceFileAdmin(ModelAdmin):
    list_display = ['project', 'file_type', 'status', 'uploaded_by', 'uploaded_at']
    list_filter = ['file_type', 'status']
    search_fields = ['project__project_id']
    actions = ['process_files']
    
    @admin.action(description='Process selected files')
    def process_files(self, request, queryset):
        for sf in queryset:
            if sf.file_type == 'WTT':
                process_wtt(sf.project.id, sf.id)
            elif sf.file_type == 'PPRP':
                process_pprp(sf.project.id, sf.id)
            elif sf.file_type == 'GHP':
                process_ghp(sf.project.id, sf.id)
        self.message_user(request, f'{queryset.count()} files processed')


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
        return format_html("<strong>{}</strong> <span class='text-gray-500 text-xs'>(v{})</span>", obj.flight_number, obj.version_number)

    @display(description="Route")
    def display_route(self, obj):
        return format_html("<strong>{}</strong> ➔ <strong>{}</strong>", obj.origin, obj.destination)
        
    @display(description="Schedule (STD ➔ STA)")
    def display_schedule(self, obj):
        std_str = obj.std.strftime('%H:%M') if obj.std else '--:--'
        sta_str = obj.sta.strftime('%H:%M') if obj.sta else '--:--'
        return f"{std_str} ➔ {sta_str}"
        
    @display(description="Status", label={"ACTIVE": "success", "INACTIVE (PPRP)": "danger"})
    def display_status(self, obj):
        if obj.is_active:
            return "ACTIVE"
        return "INACTIVE (PPRP)"
        
    @display(description="Operation", label={"OPERATED": "info", "UNVERIFIED": "warning"})
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

