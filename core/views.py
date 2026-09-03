import os
from django.shortcuts import render, redirect
from django.contrib import messages, admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.storage import FileSystemStorage
from django.http import JsonResponse
from core.models import Project, SourceFile
from core.services import delete_source_file
from core.ingest import ingest_uploaded_files

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
                if res['file_type'] == 'PPRP' and len(res.get('projects', [])) > 1:
                    names = ', '.join(
                        f"{MONTH_NAMES.get(int(p.split('-')[1]), p)} {p.split('-')[0]}" for p in res['projects'])
                    msg += f" Surat ini berlaku di {len(res['projects'])} bulan dan dicabut dari semuanya: {names}."
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
        
        # 2. Action: UPLOAD SourceFile — semua jenis file lewat satu pintu
        # (core.ingest), sama persis dengan tombol Upload PPRP di menu Project.
        file_type = request.POST.get('file_type')
        uploaded_files = request.FILES.getlist('file')
        project_id = request.POST.get('project_id')

        if not file_type or not uploaded_files:
            error_msg = "Pilih minimal 1 file untuk diunggah."
            if is_ajax:
                return JsonResponse({'success': False, 'message': error_msg}, status=400)
            messages.error(request, error_msg)
            return redirect('custom_upload')

        # Mode Atur Ulang: file WTT/GHP boleh menggantikan file sejenis yang
        # sudah ada (dikonfirmasi dulu di browser).
        replace = request.POST.get('replace') in ('1', 'true', 'on')

        # Untuk WTT, project tetap ditentukan dari PDF; project_id (bila ada)
        # hanya dipakai sebagai pengaman bahwa bulannya cocok.
        project = None
        if project_id:
            try:
                project = Project.objects.get(id=int(project_id))
            except (Project.DoesNotExist, ValueError):
                error_msg = "Project aktif tidak ditemukan. Muat ulang halaman lalu coba lagi."
                if is_ajax:
                    return JsonResponse({'success': False, 'message': error_msg}, status=400)
                messages.error(request, error_msg)
                return redirect('custom_upload')

        try:
            result = ingest_uploaded_files(file_type, uploaded_files, request.user,
                                           project=project, replace=replace)
        except Exception as e:
            if is_ajax:
                return JsonResponse({'success': False, 'message': str(e)}, status=400)
            messages.error(request, f"Error: {str(e)}")
            return redirect('custom_upload')

        if is_ajax:
            return JsonResponse(result.as_dict(), status=200 if result.success else 400)

        level = {'processed': messages.success, 'skipped': messages.warning, 'failed': messages.error}
        for fr in result.files:
            level[fr.status](request, f"{fr.filename}: {fr.message}")
            for w in fr.warnings:
                messages.warning(request, w)
        for msg in result.resync_messages:
            messages.info(request, msg)
        for w in result.warnings:
            messages.warning(request, w)
        return redirect('custom_upload')

    # Peta file yang sudah ada per project -> dipakai tombol Atur Ulang untuk
    # menanyakan "ganti file X dengan Y?" sebelum upload WTT/GHP.
    existing_files = {}
    for sf in SourceFile.objects.order_by('uploaded_at', 'id'):
        entry = existing_files.setdefault(str(sf.project_id), {'WTT': None, 'GHP': None, 'PPRP': []})
        name = os.path.basename(sf.file_path)
        if sf.file_type == 'PPRP':
            entry['PPRP'].append(name)
        else:
            entry[sf.file_type] = name
    project_options = [
        {'id': p.id, 'code': p.project_id, 'period_name': f"{MONTH_NAMES.get(p.month, p.month)} {p.year}"}
        for p in Project.objects.order_by('-year', '-month')
    ]

    context = admin.site.each_context(request)
    context.update({
        'projects': projects,
        'project_options': project_options,
        'existing_files': existing_files,
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


