from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.authentication.urls')),
    path('api/', include('apps.exams.urls')),
    path('api/', include('apps.attempts.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
