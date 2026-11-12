"""Audited moderation through explicit staff-only Django admin actions."""
from django.contrib import admin

from .models import Complaint, ModerationEvent
from .services import resolve_complaint, dismiss_complaint, block_user, unblock_user


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'reporter', 'target_user', 'target_order',
        'reason', 'status', 'created_at',
    )
    list_filter = ('status', 'reason', 'created_at')
    search_fields = (
        'message', 'reporter__username', 'target_user__username', 'admin_note',
    )
    raw_id_fields = ('reporter', 'target_user', 'target_order', 'target_rating')
    readonly_fields = (
        'reporter', 'target_user', 'target_order', 'target_rating',
        'reason', 'message', 'status', 'admin_note', 'created_at', 'resolved_at',
    )
    fields = readonly_fields
    actions = [
        'action_resolve', 'action_dismiss',
        'action_block_target', 'action_unblock_target',
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.has_perm('moderation.review_complaints'):
            actions.pop('action_resolve', None)
            actions.pop('action_dismiss', None)
        if not request.user.has_perm('moderation.moderate_accounts'):
            actions.pop('action_block_target', None)
            actions.pop('action_unblock_target', None)
        return actions

    @admin.action(description='Рассмотреть жалобы')
    def action_resolve(self, request, queryset):
        count = 0
        for complaint in queryset.filter(status=Complaint.Status.PENDING):
            resolve_complaint(complaint, actor=request.user)
            count += 1
        self.message_user(request, f'Рассмотрено жалоб: {count}')

    @admin.action(description='Отклонить жалобы')
    def action_dismiss(self, request, queryset):
        count = 0
        for complaint in queryset.filter(status=Complaint.Status.PENDING):
            dismiss_complaint(complaint, actor=request.user)
            count += 1
        self.message_user(request, f'Отклонено жалоб: {count}')

    @admin.action(description='Заблокировать пользователей')
    def action_block_target(self, request, queryset):
        count = 0
        for complaint in queryset.filter(target_user__isnull=False):
            if block_user(complaint.target_user, actor=request.user,
                          complaint=complaint):
                count += 1
        self.message_user(request, f'Заблокировано пользователей: {count}')

    @admin.action(description='Разблокировать пользователей')
    def action_unblock_target(self, request, queryset):
        count = 0
        for complaint in queryset.filter(target_user__isnull=False):
            if unblock_user(complaint.target_user, actor=request.user,
                            complaint=complaint):
                count += 1
        self.message_user(request, f'Разблокировано пользователей: {count}')


@admin.register(ModerationEvent)
class ModerationEventAdmin(admin.ModelAdmin):
    """Read-only audit; PostgreSQL additionally rejects UPDATE and DELETE."""

    list_display = ('id', 'actor', 'target_user', 'action', 'occurred_at')
    list_filter = ('action', 'occurred_at')
    readonly_fields = (
        'actor', 'target_user', 'complaint',
        'privacy_request', 'action', 'occurred_at',
    )
    fields = readonly_fields
    search_fields = ('actor__username', 'target_user__username')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
