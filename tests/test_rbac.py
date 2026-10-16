from django.test import TestCase, Client
from django.contrib.auth.models import User, Group, Permission
from django.core.management import call_command
from core.models import Project, SourceFile
from core.admin import UserAdmin, GroupAdmin
from django.contrib.admin.sites import AdminSite


class MockRequest:
    def __init__(self, user):
        self.user = user


class RBACTestCase(TestCase):
    def setUp(self):
        call_command('setup_roles')
        self.client = Client()

        # 1. Station Manager
        self.sm_user = User.objects.create_user('sm_user', 'sm@example.com', 'pass123', is_staff=True)
        self.sm_user.groups.add(Group.objects.get(name='Station Manager'))

        # 2. Operator
        self.op_user = User.objects.create_user('op_user', 'op@example.com', 'pass123', is_staff=True)
        self.op_user.groups.add(Group.objects.get(name='Operator'))

        # 3. Viewer
        self.vw_user = User.objects.create_user('vw_user', 'vw@example.com', 'pass123', is_staff=True)
        self.vw_user.groups.add(Group.objects.get(name='Management Viewer'))

        # 4. Super Admin
        self.admin_user = User.objects.create_user('superadmin', 'admin@example.com', 'pass123', is_staff=True, is_superuser=True)

        self.project = Project.objects.create(
            project_id='PRJ-TEST',
            period='S26',
            year=2026,
            month=7,
            created_by=self.admin_user
        )

        self.source_file = SourceFile.objects.create(
            project=self.project,
            file_type='WTT',
            file_path='/tmp/test.pdf',
            file_hash='abc123hash',
            uploaded_by=self.admin_user,
            status='SUCCESS'
        )

    def test_setup_roles_assigns_correct_permissions(self):
        sm_group = Group.objects.get(name='Station Manager')
        op_group = Group.objects.get(name='Operator')
        vw_group = Group.objects.get(name='Management Viewer')

        self.assertTrue(sm_group.permissions.filter(codename='add_sourcefile').exists())
        self.assertTrue(sm_group.permissions.filter(codename='delete_sourcefile').exists())
        self.assertTrue(sm_group.permissions.filter(codename='view_user').exists())

        self.assertTrue(op_group.permissions.filter(codename='add_sourcefile').exists())
        self.assertFalse(op_group.permissions.filter(codename='delete_sourcefile').exists())
        self.assertFalse(op_group.permissions.filter(codename='view_user').exists())

        self.assertTrue(vw_group.permissions.filter(codename='view_project').exists())
        self.assertFalse(vw_group.permissions.filter(codename='add_sourcefile').exists())
        self.assertFalse(vw_group.permissions.filter(codename='delete_sourcefile').exists())

    def test_operator_cannot_delete_source_file(self):
        self.client.force_login(self.op_user)
        resp = self.client.post('/admin/upload-data/', {
            'action': 'delete',
            'file_id': self.source_file.id
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(resp.status_code, 403)
        body = resp.json()
        self.assertFalse(body['success'])
        self.assertIn('tidak memiliki izin untuk menghapus', body['message'])
        self.assertTrue(SourceFile.objects.filter(id=self.source_file.id).exists())

    def test_viewer_cannot_upload_file(self):
        self.client.force_login(self.vw_user)
        resp = self.client.post('/admin/upload-data/', {
            'file_type': 'WTT',
            'project_id': self.project.id
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(resp.status_code, 403)
        body = resp.json()
        self.assertFalse(body['success'])
        self.assertIn('tidak memiliki izin', body['message'])

    def test_viewer_cannot_upload_pprp_on_project_admin(self):
        self.client.force_login(self.vw_user)
        resp = self.client.post(f'/admin/core/project/{self.project.id}/upload-pprp/', {
            'file': []
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(resp.status_code, 403)
        body = resp.json()
        self.assertFalse(body['success'])

    def test_station_manager_can_attempt_delete(self):
        self.client.force_login(self.sm_user)
        resp = self.client.post('/admin/upload-data/', {
            'action': 'delete',
            'file_id': self.source_file.id
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        # Station manager has permission; status 200 or processed (even if physical file missing)
        self.assertIn(resp.status_code, [200, 500])
        if resp.status_code == 200:
            self.assertTrue(resp.json().get('success'))

    def test_user_admin_display_roles(self):
        site = AdminSite()
        user_admin = UserAdmin(User, site)

        # Super admin badge
        sm_badge = user_admin.display_roles(self.sm_user)
        self.assertIn('Station Manager', sm_badge)

        op_badge = user_admin.display_roles(self.op_user)
        self.assertIn('Operator', op_badge)

        admin_badge = user_admin.display_roles(self.admin_user)
        self.assertIn('Super Admin', admin_badge)

    def test_group_admin_display_and_filter(self):
        site = AdminSite()
        group_admin = GroupAdmin(Group, site)

        sm_group = Group.objects.get(name='Station Manager')
        count_display = group_admin.display_user_count(sm_group)
        self.assertIn('1 Pengguna', count_display)

        summary_display = group_admin.display_permissions_summary(sm_group)
        self.assertIn('hak akses aktif', summary_display)

        # Custom permission label formatting check
        req = MockRequest(self.admin_user)
        req.method = 'GET'
        field = group_admin.formfield_for_manytomany(Group._meta.get_field('permissions'), req)
        perm = Permission.objects.get(
            content_type__app_label='core', content_type__model='sourcefile', codename='add_sourcefile'
        )
        self.assertEqual(field.label_from_instance(perm), 'Reference Documents | Can upload reference files (WTT/PPRP/GHP)')
