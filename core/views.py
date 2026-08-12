from django.shortcuts import render, redirect
from django.contrib.auth.models import Group, User
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
@require_POST
def quick_create_group(request):
    group_name = request.POST.get('name')
    if group_name:
        Group.objects.get_or_create(name=group_name)
    return redirect(request.META.get('HTTP_REFERER', '/admin/auth/user/'))

@staff_member_required
@require_POST
def quick_create_user(request):
    username = request.POST.get('username')
    password = request.POST.get('password')
    full_name = request.POST.get('full_name', '')
    email = request.POST.get('email', '')
    role_id = request.POST.get('role')
    
    if username and password:
        if not User.objects.filter(username=username).exists():
            user = User.objects.create_user(username=username, email=email, password=password)
            if full_name:
                parts = full_name.split(' ', 1)
                user.first_name = parts[0]
                if len(parts) > 1:
                    user.last_name = parts[1]
            if role_id:
                try:
                    group = Group.objects.get(id=role_id)
                    user.groups.add(group)
                except Group.DoesNotExist:
                    pass
            user.save()
    return redirect(request.META.get('HTTP_REFERER', '/admin/auth/user/'))
