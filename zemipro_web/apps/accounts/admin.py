from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, ClientProfile, WorkerProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'phone', 'telegram_id', 'is_blocked', 'is_active')
    list_filter = ('role', 'is_blocked', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'phone', 'telegram_id')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Дополнительно', {
            'fields': ('telegram_id', 'role', 'phone', 'is_blocked'),
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
    list_display = ('user', 'city', 'is_verified', 'receive_notifications', 'created_at')
    list_filter = ('city', 'is_verified', 'receive_notifications')
    search_fields = ('user__username', 'user__email', 'contact', 'description')
    raw_id_fields = ('user', 'city')
    filter_horizontal = ('skills',)
