from django.contrib import admin
from django.core.exceptions import PermissionDenied

from .models import SeoContentPage, SeoContentRevision, SeoLegacyUrl


@admin.register(SeoLegacyUrl)
class SeoLegacyUrlAdmin(admin.ModelAdmin):
    list_display = ('path', 'decision', 'is_active', 'approved_at')
    list_filter = ('decision', 'is_active')
    search_fields = ('path', 'target_path', 'evidence_source')
    readonly_fields = ('is_active', 'approved_by', 'approved_at', 'created_at', 'updated_at')

    def has_change_permission(self, request, obj=None):
        # An active decision is an approved release artifact.  Operators must
        # deactivate it through the locked service before editing its meaning.
        if obj is not None and obj.is_active:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_active:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(SeoContentPage)
class SeoContentPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'page_type', 'language', 'status', 'version', 'updated_at')
    list_filter = ('page_type', 'language', 'status', 'quality_approved')
    search_fields = ('title', 'topic', 'source_facts')
    readonly_fields = (
        'status', 'quality_approved', 'content_fingerprint', 'version', 'reviewer',
        'reviewed_at', 'published_at', 'created_at', 'updated_at',
    )

    # All writes go through the dedicated CAS/revision/review UI.  A normal
    # ModelAdmin save would otherwise bypass immutable history and approvals.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        raise PermissionDenied(
            'SEO content writes require the versioned editorial workflow.'
        )


@admin.register(SeoContentRevision)
class SeoContentRevisionAdmin(admin.ModelAdmin):
    list_display = ('page', 'version', 'created_by', 'created_at')
    readonly_fields = ('page', 'version', 'snapshot', 'created_by', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
