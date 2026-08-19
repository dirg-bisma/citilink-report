from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from core.views import upload_source_file_view

urlpatterns = [
    path('', RedirectView.as_view(url='/admin/', permanent=False), name='index'),
    path('admin/upload-data/', upload_source_file_view, name='custom_upload'),
    path('admin/', admin.site.urls),
]
