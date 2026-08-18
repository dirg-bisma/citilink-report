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

@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ['project_id', 'period', 'year', 'month', 'created_by', 'created_at', 'download_action']
    list_filter = ['year', 'month', 'period']
    search_fields = ['project_id']
    
    @display(description="Report")
    def download_action(self, obj):
        url = f"/admin/core/project/{obj.pk}/download/"
        return format_html(
            '<a class="inline-flex items-center gap-1 bg-primary-600 hover:bg-primary-700 text-white text-xs font-medium px-3 py-1.5 rounded transition-colors" href="{}" style="background-color: #006b32; color: white;">'
            '<span class="material-symbols-outlined text-[16px]">download</span> Export Excel'
            '</a>',
            url
        )
        
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:project_id>/download/', self.admin_site.admin_view(self.download_report), name='project_download'),
        ]
        return custom_urls + urls
    
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


@admin.register(ScheduleVersion)
class ScheduleVersionAdmin(ModelAdmin):
    list_display = [
        'project',
        'flight_number', 
        'display_route',
        'flight_date', 
        'display_schedule',
        'display_status',
        'display_operated',
        'version_number'
    ]
    list_filter = ['project', 'is_active', 'operational_flag', 'origin', 'destination']
    search_fields = ['flight_number', 'origin', 'destination', 'pprp_letter']
    date_hierarchy = 'flight_date'
    
    @display(description="Route")
    def display_route(self, obj):
        return f"{obj.origin} ➔ {obj.destination}"
        
    @display(description="Schedule (STD ➔ STA)")
    def display_schedule(self, obj):
        std_str = obj.std.strftime('%H:%M') if obj.std else '--:--'
        sta_str = obj.sta.strftime('%H:%M') if obj.sta else '--:--'
        return f"{std_str} ➔ {sta_str}"
        
    @display(description="Status", label=True)
    def display_status(self, obj):
        if obj.is_active:
            return "ACTIVE", "success"
        return "INACTIVE (PPRP)", "danger"
        
    @display(description="Operation", label=True)
    def display_operated(self, obj):
        if obj.operational_flag:
            return "OPERATED", "info"
        return "UNVERIFIED", "warning"

