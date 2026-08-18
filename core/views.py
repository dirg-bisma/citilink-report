import os
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.storage import FileSystemStorage
from core.models import Project, SourceFile
from core.services import process_wtt, process_pprp, process_ghp

@staff_member_required
def upload_source_file_view(request):
    projects = Project.objects.all().order_by('-created_at')
    history = SourceFile.objects.all().select_related('project', 'uploaded_by').order_by('-uploaded_at')[:50]
    
    if request.method == 'POST':
        project_id = request.POST.get('project')
        file_type = request.POST.get('file_type')
        uploaded_files = request.FILES.getlist('file')
        
        if not project_id or not file_type or not uploaded_files:
            messages.error(request, "Please fill all fields and select at least one file.")
            return redirect('custom_upload')
            
        try:
            project = Project.objects.get(id=project_id)
            success_count = 0
            
            for uploaded_file in uploaded_files:
                try:
                    # Read content for hash
                    file_content = uploaded_file.read()
                    file_hash = SourceFile.compute_hash(file_content)
                    uploaded_file.seek(0)  # Reset pointer
                    
                    if SourceFile.objects.filter(project=project, file_type=file_type, file_hash=file_hash).exists():
                        messages.warning(request, f"File {uploaded_file.name} has already been uploaded for this project. Skipped.")
                        continue
                        
                    # Save file
                    fs = FileSystemStorage(location=os.path.join('media', 'uploads'))
                    filename = fs.save(uploaded_file.name, uploaded_file)
                    file_path = fs.path(filename)
                    
                    # Create SourceFile record
                    source_file = SourceFile.objects.create(
                        project=project,
                        file_type=file_type,
                        file_path=file_path,
                        file_hash=file_hash,
                        uploaded_by=request.user,
                        status='PROCESSING'
                    )
                    
                    # Process synchronously for now
                    if file_type == 'WTT':
                        processed_count = process_wtt(project.id, source_file.id)
                    elif file_type == 'PPRP':
                        processed_count = process_pprp(project.id, source_file.id)
                    elif file_type == 'GHP':
                        processed_count = process_ghp(project.id, source_file.id)
                    elif file_type == 'TEMPLATE':
                        # Simpan path template ke project untuk dipakai saat generate report
                        project.template_path = file_path
                        project.save(update_fields=['template_path'])
                        processed_count = 0
                        source_file.status = 'SUCCESS'
                        source_file.save()
                    else:
                        processed_count = 0
                        source_file.status = 'SUCCESS'
                        source_file.save()

                        
                    success_count += 1
                    messages.success(request, f"File {uploaded_file.name} uploaded successfully! ({processed_count} records)")
                except Exception as e:
                    source_file.status = 'FAILED'
                    source_file.error_message = str(e)
                    source_file.save()
                    messages.error(request, f"Error processing {uploaded_file.name}: {str(e)}")
            
            if success_count > 1:
                messages.success(request, f"Successfully processed {success_count} files in total.")
                
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
            
        return redirect('custom_upload')
        
    context = {
        'projects': projects,
        'history': history,
        'title': 'Upload Data'
    }
    return render(request, 'admin/core/sourcefile/custom_upload.html', context)
