from django.contrib import admin
from django.urls import path
from core.views import quick_create_group, quick_create_user

urlpatterns = [
    path('admin/quick-create-group/', quick_create_group, name='quick_create_group'),
    path('admin/quick-create-user/', quick_create_user, name='quick_create_user'),
    path('admin/', admin.site.urls),
]
