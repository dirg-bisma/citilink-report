"""Tests for processing engine"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Project, SourceFile, ScheduleVersion
from core.services import process_wtt, process_pprp, process_ghp


def test_wtt_load():
    u = User.objects.first()
    p = Project.objects.create(project_id='TEST-WTT', period='S26', year=2026, month=4, created_by=u)
    sf = SourceFile.objects.create(project=p, file_type='WTT', file_path='docs/Source/Working Time Table [WTT] April 2026.pdf', file_hash='test123', uploaded_by=u)
    count = process_wtt(p.id, sf.id)
    assert count == 842
    assert ScheduleVersion.objects.filter(project=p).count() == 842
    p.delete()
    print('[OK] WTT load')


def test_pprp_versioning():
    u = User.objects.first()
    p = Project.objects.create(project_id='TEST-PPRP', period='S26', year=2026, month=7, created_by=u)
    
    # Load WTT baseline
    sf_wtt = SourceFile.objects.create(project=p, file_type='WTT', file_path='docs/Source/Working Time Table [WTT] April 2026.pdf', file_hash='wtt1', uploaded_by=u)
    process_wtt(p.id, sf_wtt.id)
    
    # Apply PPRP
    sf_pprp = SourceFile.objects.create(project=p, file_type='PPRP', file_path='docs/Source/PPRP SUB-BPN S26 UPDATE.pdf', file_hash='pprp1', uploaded_by=u)
    process_pprp(p.id, sf_pprp.id)
    
    # Verify child rows created
    v2 = ScheduleVersion.objects.filter(project=p, version_number=2).count()
    assert v2 > 0
    p.delete()
    print('[OK] PPRP versioning')


def test_ghp_match():
    u = User.objects.first()
    p = Project.objects.filter(project_id='TEST-APR26').first()
    if not p:
        print('[SKIP] GHP match (no test project)')
        return
    
    before = ScheduleVersion.objects.filter(project=p, operational_flag=True).count()
    assert before > 0
    print(f'[OK] GHP match ({before} matched)')


if __name__ == '__main__':
    test_wtt_load()
    test_pprp_versioning()
    test_ghp_match()
    print('All processing tests pass')
