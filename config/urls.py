from django.contrib import admin
from django.urls import path
from core.views import upload_source_file_view

urlpatterns = [
    path('admin/upload-data/', upload_source_file_view, name='custom_upload'),
    path('admin/', admin.site.urls),
]
