from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from core import health
from core.i18n_views import safe_set_language

urlpatterns = [
    path('health/live/', health.liveness, name='health_live'),
    path('health/ready/', health.readiness, name='health_ready'),
    path('admin/', admin.site.urls),
    # Language switch must stay UNPREFIXED even when public catalog uses i18n_patterns.
    path('i18n/setlang/', safe_set_language, name='set_language'),

    # Apps
    path('', include('apps.marketplace.urls')),
    path('accounts/', include('apps.accounts.urls')),
    path('locations/', include('apps.locations.urls')),
    path('seo/', include('apps.seo.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('moderation/', include('apps.moderation.urls')),
    path('analytics/', include('apps.analytics.urls')),
]

if settings.ZEMIPRO_GOOGLE_LOGIN_ENABLED:
    # Dedicated prefix avoids allauth's local signup/password URLs shadowing Django.
    urlpatterns.append(path('oauth/', include('allauth.urls')))

# Additive catalog routes only. Never wrap legacy marketplace/auth/health routes
# in i18n_patterns: existing URLs, SEO/PSEO links and external clients stay valid.
urlpatterns += i18n_patterns(
    path('', include('apps.marketplace.localized_urls')),
    prefix_default_language=True,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
