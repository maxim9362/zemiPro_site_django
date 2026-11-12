from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    User, ClientProfile, WorkerProfile, PrivacyRequest, WorkerPortfolioPhoto,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'active_role', 'phone', 'telegram_id', 'is_blocked', 'is_active')
    list_filter = ('role', 'active_role', 'is_blocked', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'phone', 'telegram_id')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Дополнительно', {
            'fields': ('telegram_id', 'role', 'active_role', 'phone', 'is_blocked'),
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Дополнительно', {
            'fields': ('telegram_id', 'role', 'phone'),
        }),
    )


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'contact', 'created_at')
    list_filter = ('city',)
    search_fields = ('user__username', 'user__email', 'contact')
    raw_id_fields = ('user', 'city')


@admin.register(WorkerProfile)
class WorkerProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'display_name', 'provider_type', 'is_published',
        'city', 'offers_remote', 'is_verified',
        'receive_notifications', 'created_at',
    )
    list_filter = ('city', 'provider_type', 'is_published', 'offers_remote',
                   'is_verified', 'receive_notifications')
    readonly_fields = ('is_published', 'published_at')
    search_fields = ('user__username', 'user__email', 'contact', 'description')
    raw_id_fields = ('user', 'city')
    filter_horizontal = ('skills', 'service_cities')


@admin.register(PrivacyRequest)
class PrivacyRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'kind', 'status', 'created_at', 'reviewed_at')
    list_filter = ('kind', 'status')
    search_fields = ('user__username',)
    readonly_fields = ('user', 'kind', 'created_at')
    fields = ('user', 'kind', 'status', 'created_at', 'reviewed_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(WorkerPortfolioPhoto)
class WorkerPortfolioPhotoAdmin(admin.ModelAdmin):
    """Metadata only. Uploaded images are not exposed from Django admin."""

    list_display = ('id', 'worker', 'is_public', 'sort_order', 'created_at')
    list_filter = ('is_public',)
    raw_id_fields = ('worker',)
    readonly_fields = (
        'worker', 'file_key', 'caption', 'sort_order', 'is_public',
        'rights_confirmed_at', 'created_at',
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
