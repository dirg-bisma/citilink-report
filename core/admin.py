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
    list_display = ['project_id', 'period', 'year', 'month', 'created_by', 'created_at', 'pprp_action', 'view_report_action', 'download_action']
    list_filter = ['year', 'month', 'period']
    search_fields = ['project_id']
    
    @display(description="PPRP")
    def pprp_action(self, obj):
        return format_html(
            '<button type="button" onclick="openPprpModal({}, \'{}\')" class="inline-flex items-center gap-1 text-white text-xs font-medium px-3 py-1.5 rounded transition-opacity hover:opacity-90 shadow-xs cursor-pointer" style="background-color: #006b32; color: white;" title="Upload file PPRP">'
            '<span class="material-symbols-outlined text-[16px]">upload_file</span> Upload PPRP'
            '</button>',
            obj.pk,
            obj.project_id
        )
    
    @display(description="View")
    def view_report_action(self, obj):
        url = f"/admin/core/project/{obj.pk}/view-report/"
        return format_html(
            '<a class="inline-flex items-center gap-1 text-white text-xs font-medium px-3 py-1.5 rounded transition-opacity hover:opacity-90 shadow-xs" href="{}" target="_blank" style="background-color: #0284c7; color: white;" title="Buka tampilan laporan di tab baru">'
            '<span class="material-symbols-outlined text-[16px]">visibility</span> View Report'
            '</a>',
            url
        )
    
    @display(description="Report")
    def download_action(self, obj):
        url = f"/admin/core/project/{obj.pk}/download/"
        return format_html(
            '<a class="inline-flex items-center gap-1 text-white text-xs font-medium px-3 py-1.5 rounded transition-opacity hover:opacity-90 shadow-xs" href="{}" style="background-color: #006b32; color: white;">'
            '<span class="material-symbols-outlined text-[16px]">download</span> Export Excel'
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

