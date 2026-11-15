from django.contrib import admin

from .models import SeoContentPage, SeoContentRevision, SeoLegacyUrl


@admin.register(SeoLegacyUrl)
class SeoLegacyUrlAdmin(admin.ModelAdmin):
    list_display = ('path', 'decision', 'is_active', 'approved_at')
    list_filter = ('decision', 'is_active')
    search_fields = ('path', 'target_path', 'evidence_source')
    readonly_fields = ('is_active', 'approved_by', 'approved_at', 'created_at', 'updated_at')


@admin.register(SeoContentPage)
class SeoContentPageAdmin(admin.ModelAdmin):
    list_display = ('title', 'page_type', 'language', 'status', 'version', 'updated_at')
    list_filter = ('page_type', 'language', 'status', 'quality_approved')
    search_fields = ('title', 'topic', 'source_facts')
    readonly_fields = (
        'status', 'quality_approved', 'content_fingerprint', 'version', 'reviewer',
        'reviewed_at', 'published_at', 'created_at', 'updated_at',
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
