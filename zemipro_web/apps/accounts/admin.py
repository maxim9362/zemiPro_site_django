from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.moderation.services import review_privacy_request

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

    # Manual blocked/status toggles bypass the audit. Only moderation actions
    # may block/unblock. User deletion risks erasing responses, notifications.
    readonly_fields = ('is_blocked', 'is_active')

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            fields.extend((
                'is_superuser', 'is_staff', 'groups', 'user_permissions',
                'role', 'active_role', 'email', 'phone',
            ))
        return tuple(dict.fromkeys(fields))


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
    readonly_fields = ('user', 'kind', 'status', 'created_at', 'reviewed_at')
    fields = readonly_fields
    actions = ('mark_processing', 'reject_request')

    def has_review_privacy_requests_permission(self, request):
        return request.user.is_staff and request.user.has_perm(
            'moderation.review_privacy_requests',
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.has_perm('moderation.review_privacy_requests'):
            actions.pop('mark_processing', None)
            actions.pop('reject_request', None)
        return actions

    @admin.action(permissions=['review_privacy_requests'], description='Передать на ручное рассмотрение')
    def mark_processing(self, request, queryset):
        count = 0
        for item in queryset.filter(status=PrivacyRequest.Status.PENDING):
            review_privacy_request(item, actor=request.user)
            count += 1
        self.message_user(request, f'Принято на рассмотрение: {count}')

    @admin.action(permissions=['review_privacy_requests'], description='Отклонить запрос')
    def reject_request(self, request, queryset):
        count = 0
        for item in queryset.filter(status=PrivacyRequest.Status.PENDING):
            review_privacy_request(item, actor=request.user, reject=True)
            count += 1
        self.message_user(request, f'Отклонено запросов: {count}')

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
