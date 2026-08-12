# Phase 7 Complete

**Web UI with django-unfold:**
- Admin registered: Project, SourceFile, ScheduleVersion
- Process action on SourceFile: batch process WTT/PPRP/GHP
- Download link on Project: export to Excel
- Filters, search, date hierarchy on all models

**Access:** `http://localhost:8000/admin`
- Login: `admin` (set password: `python manage.py changepassword admin`)
- Test project already loaded with 842 schedules

**Usage:**
1. Create Project
2. Upload SourceFiles via admin
3. Select files → Actions → "Process selected files"
4. View ScheduleVersion to preview
5. Download report from Project detail

Run server: `python manage.py runserver`
