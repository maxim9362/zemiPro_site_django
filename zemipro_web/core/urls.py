from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

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
