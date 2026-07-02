from django.contrib import admin, messages
from django.utils import timezone

from .models import Complaint
from .services import resolve_complaint, dismiss_complaint, block_user, unblock_user


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('id', 'reporter', 'target_user', 'target_order', 'reason', 'status', 'created_at')
    list_filter = ('status', 'reason', 'created_at')
    search_fields = ('message', 'reporter__username', 'target_user__username', 'admin_note')
    raw_id_fields = ('reporter', 'target_user', 'target_order', 'target_rating')
    readonly_fields = ('created_at', 'resolved_at')
    actions = ['action_resolve', 'action_dismiss', 'action_block_target', 'action_unblock_target']

    @admin.action(description='Рассмотреть жалобы')
    def action_resolve(self, request, queryset):
        count = 0
        for complaint in queryset.filter(status=Complaint.Status.PENDING):
            resolve_complaint(complaint)
            count += 1
        self.message_user(request, f'Рассмотрено жалоб: {count}')

    @admin.action(description='Отклонить жалобы')
    def action_dismiss(self, request, queryset):
        count = 0
        for complaint in queryset.filter(status=Complaint.Status.PENDING):
            dismiss_complaint(complaint)
            count += 1
        self.message_user(request, f'Отклонено жалоб: {count}')

    @admin.action(description='Заблокировать пользователей')
    def action_block_target(self, request, queryset):
        count = 0
        for complaint in queryset.filter(target_user__isnull=False):
            if complaint.target_user:
                block_user(complaint.target_user)
                count += 1
        self.message_user(request, f'Заблокировано пользователей: {count}')

    @admin.action(description='Разблокировать пользователей')
    def action_unblock_target(self, request, queryset):
        count = 0
        for complaint in queryset.filter(target_user__isnull=False):
            if complaint.target_user:
                unblock_user(complaint.target_user)
                count += 1
        self.message_user(request, f'Разблокировано пользователей: {count}')
