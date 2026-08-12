from django.contrib import admin
from django.shortcuts import redirect, render
from django.urls import path
from django.http import FileResponse, HttpResponse
from unfold.admin import ModelAdmin
from core.models import Project, SourceFile, ScheduleVersion
from core.services import process_wtt, process_pprp, process_ghp
from core.report import generate_report
import os


@admin.register(Project)
class ProjectAdmin(ModelAdmin):
    list_display = ['project_id', 'period', 'year', 'month', 'created_by', 'created_at']
    list_filter = ['year', 'month', 'period']
    search_fields = ['project_id']
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:project_id>/download/', self.admin_site.admin_view(self.download_report), name='project_download'),
        ]
        return custom_urls + urls
    
    def download_report(self, request, project_id):
        output_path = f'report_{project_id}.xlsx'
        generate_report(project_id, '', output_path)
        return FileResponse(open(output_path, 'rb'), as_attachment=True, filename=f'report_{project_id}.xlsx')


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
    list_display = ['flight_number', 'origin', 'destination', 'flight_date', 'version_number', 'is_active', 'operational_flag']
    list_filter = ['is_active', 'operational_flag', 'origin', 'destination']
    search_fields = ['flight_number']
    date_hierarchy = 'flight_date'

