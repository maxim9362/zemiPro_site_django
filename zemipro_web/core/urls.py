from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core import health

urlpatterns = [
    path('health/live/', health.liveness, name='health_live'),
    path('health/ready/', health.readiness, name='health_ready'),
    path('admin/', admin.site.urls),
    # Pre-02.4: cookie-based language switching; public URLs remain unchanged.
    path('i18n/', include('django.conf.urls.i18n')),

    # Apps
    path('', include('apps.marketplace.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('locations/', include('apps.locations.urls')),
    path('seo/', include('apps.seo.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('moderation/', include('apps.moderation.urls')),
    path('analytics/', include('apps.analytics.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
