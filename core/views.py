import os
from django.shortcuts import render, redirect
from django.contrib import messages, admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.storage import FileSystemStorage
from django.http import JsonResponse
from core.models import Project, SourceFile
from core.services import process_wtt, process_pprp, process_ghp, delete_source_file
from core.parsers.wtt import detect_wtt_period
from core.parsers.pprp import detect_pprp_period
from core.parsers.ghp import detect_ghp_period

MONTH_NAMES = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
    5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
    9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
}

@staff_member_required
def upload_source_file_view(request):
    projects = Project.objects.all().order_by('-created_at')
    history = SourceFile.objects.all().select_related('project', 'uploaded_by').order_by('-uploaded_at')[:50]
    
    if request.method == 'POST':
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        
        # 1. Action: DELETE SourceFile
        action = request.POST.get('action')
        if action == 'delete':
            file_id = request.POST.get('file_id')
            if not file_id:
                if is_ajax:
                    return JsonResponse({'success': False, 'message': 'File ID is required.'}, status=400)
                messages.error(request, 'File ID is required.')
                return redirect('custom_upload')
            try:
                res = delete_source_file(int(file_id))
                msg = f"File {res['file_type']} berhasil dihapus ({res['affected_count']} data terkait dibersihkan)."
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': msg,
                        'deleted_file_type': res['file_type'],
                        'deleted_file_id': res['file_id'],
                        'project_id': res['project_id'],
                    })
                messages.success(request, msg)
                return redirect('custom_upload')
            except Exception as e:
                if is_ajax:
                    return JsonResponse({'success': False, 'message': str(e)}, status=500)
                messages.error(request, f"Error deleting file: {str(e)}")
                return redirect('custom_upload')
        
        # 2. Action: UPLOAD SourceFile
        file_type = request.POST.get('file_type')
        uploaded_files = request.FILES.getlist('file')
        project_id = request.POST.get('project_id')
        
        if not file_type or not uploaded_files:
            error_msg = "Pilih minimal 1 file untuk diunggah."
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('custom_upload')
            
        try:
            for uploaded_file in uploaded_files:
                # Read content for hash
                file_content = uploaded_file.read()
                file_hash = SourceFile.compute_hash(file_content)
                uploaded_file.seek(0)  # Reset pointer
                
                # Save file temporarily to disk so parsers can read it
                fs = FileSystemStorage(location=os.path.join('media', 'uploads'))
                filename = fs.save(uploaded_file.name, uploaded_file)
                file_path = fs.path(filename)
                
                # Auto-detect period or get project
                if file_type == 'WTT':
                    month, year = detect_wtt_period(file_path)
                    project_id_str = f"PRJ-{year}{int(month):02d}"
                    period_str = f"{year}-{int(month):02d}"
                    project, created = Project.objects.get_or_create(
                        month=int(month),
                        year=int(year),
                        defaults={
                            'project_id': project_id_str,
                            'period': period_str,
                            'created_by': request.user
                        }
                    )
                else:
                    if project_id:
                        project = Project.objects.get(id=int(project_id))
                    else:
                        # Fallback to most recent project
                        project = Project.objects.order_by('-created_at').first()
                        if not project:
                            raise ValueError("Belum ada Project aktif. Silakan upload file WTT terlebih dahulu.")
                    
                    # Validate month against project
                    if file_type == 'PPRP':
                        p_month, p_year = detect_pprp_period(file_path)
                        if p_month != project.month or p_year != project.year:
                            # Remove file before raising
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            detected_name = f"{MONTH_NAMES.get(p_month, p_month)} {p_year}"
                            proj_name = f"{MONTH_NAMES.get(project.month, project.month)} {project.year}"
                            raise ValueError(f"File PPRP terdeteksi untuk periode {detected_name}, tidak cocok dengan Project aktif ({proj_name}).")
                    elif file_type == 'GHP':
                        g_month = detect_ghp_period(file_path)
                        if g_month != project.month:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            detected_name = MONTH_NAMES.get(g_month, g_month)
                            proj_name = f"{MONTH_NAMES.get(project.month, project.month)} {project.year}"
                            raise ValueError(f"File GHP terdeteksi untuk bulan {detected_name}, tidak cocok dengan Project aktif ({proj_name}).")

                # Duplicate check
                if SourceFile.objects.filter(project=project, file_type=file_type, file_hash=file_hash).exists():
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    msg = f"File {uploaded_file.name} sudah pernah diupload untuk project ini."
                    if is_ajax:
                        return JsonResponse({'success': False, 'message': msg}, status=400)
                    messages.warning(request, msg)
                    continue

                # Create SourceFile record
                source_file = SourceFile.objects.create(
                    project=project,
                    file_type=file_type,
                    file_path=file_path,
                    file_hash=file_hash,
                    uploaded_by=request.user,
                    status='PROCESSING'
                )

                # Process
                if file_type == 'WTT':
                    processed_count = process_wtt(project.id, source_file.id)
                elif file_type == 'PPRP':
                    processed_count = process_pprp(project.id, source_file.id)
                elif file_type == 'GHP':
                    processed_count = process_ghp(project.id, source_file.id)
                else:
                    processed_count = 0
                    source_file.status = 'SUCCESS'
                    source_file.save()

                # Contextual detail per file type
                detail_labels = {
                    'WTT': 'jadwal penerbangan tercreate',
                    'GHP': 'jadwal penerbangan terverifikasi (operational flag)',
                    'PPRP': 'jadwal penerbangan terdampak perubahan PPRP',
                }
                detail = detail_labels.get(file_type, 'records processed')
                msg = f"File {uploaded_file.name} berhasil diupload! ({processed_count} {detail})"

                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'message': msg,
                        'processed_count': processed_count,
                        'file_type': file_type,
                        'detail': detail,
                        'file_id': source_file.id,
                        'project_id': project.id,
                        'project_code': project.project_id,
                        'period_name': f"{MONTH_NAMES.get(project.month, project.month)} {project.year}",
                    })
                messages.success(request, msg)

        except Exception as e:
            if 'source_file' in locals() and source_file.id:
                try:
                    source_file.delete()
                except Exception:
                    pass
            if 'file_path' in locals() and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, f"Error: {str(e)}")

        if not is_ajax:
            return redirect('custom_upload')

    context = admin.site.each_context(request)
    context.update({
        'projects': projects,
        'history': history,
        'title': 'Upload Data'
    })
    return render(request, 'admin/core/sourcefile/custom_upload.html', context)


@staff_member_required
def global_dashboard_api(request):
    """API endpoint for global dashboard - returns analytics data for a given project and optional date range."""
    from core.analytics import otp_metric, pprp_achievement, delay_factors, daily_otp_trend, flight_distribution

    project_id = request.GET.get('project_id')
    start_day_raw = request.GET.get('start_day')
    end_day_raw = request.GET.get('end_day')

    start_day = int(start_day_raw) if start_day_raw and start_day_raw.isdigit() else None
    end_day = int(end_day_raw) if end_day_raw and end_day_raw.isdigit() else None

    # Build project list
    projects = Project.objects.all().order_by('-year', '-month')
    project_list = []
    for p in projects:
        project_list.append({
            'id': p.id,
            'project_id': p.project_id,
            'period': p.period,
            'year': p.year,
            'month': p.month,
            'label': f"{p.project_id} ({MONTH_NAMES.get(p.month, p.month)} {p.year})",
        })

    # If no project_id specified, pick the most recent project that has active schedules
    if not project_id and project_list:
        project_with_data = Project.objects.filter(schedules__isnull=False, schedules__origin='SUB').order_by('-year', '-month').first()
        if project_with_data:
            project_id = project_with_data.id
        else:
            project_id = project_list[0]['id']
    elif project_id:
        project_id = int(project_id)

    # Compute analytics
    otp_data = {'total': 0, 'reg_count': 0, 'chrt_count': 0, 'on_time': 0, 'delayed': 0, 'otp_percent': 0, 'otp_arr_percent': 0, 'avg_agt': '1:45', 'avg_sgt': '1:30'}
    pprp_data = {'achievement': 0, 'total': 0, 'on_time': 0}
    delay_data = {'case_counts': [], 'durations': [], 'iata_categories': []}
    daily_trend = []
    flight_dist = {'reg_count': 0, 'reg_pct': 0, 'chrt_count': 0, 'chrt_pct': 0, 'top_routes': []}

    if project_id:
        try:
            project = Project.objects.get(id=project_id)
            otp_data = otp_metric(project_id, start_day, end_day)
            pprp_data = pprp_achievement(project_id, project.month, start_day, end_day)
            delay_data = delay_factors(project_id, start_day, end_day)
            daily_trend = daily_otp_trend(project_id, start_day, end_day)
            flight_dist = flight_distribution(project_id, start_day, end_day)
        except Project.DoesNotExist:
            pass

    pprp_out = pprp_data['total'] - pprp_data['on_time']

    return JsonResponse({
        'projects': project_list,
        'selected_project_id': project_id,
        'start_day': start_day,
        'end_day': end_day,
        'otp': otp_data,
        'pprp': {
            **pprp_data,
            'out_of_tolerance': pprp_out,
        },
        'delay_data': delay_data,
        'daily_trend': daily_trend,
        'flight_dist': flight_dist,
    })


