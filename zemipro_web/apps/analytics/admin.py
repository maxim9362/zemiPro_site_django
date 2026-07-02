from django.contrib import admin

from .models import GlobalStats, CategoryStats


@admin.register(GlobalStats)
class GlobalStatsAdmin(admin.ModelAdmin):
    list_display = ('metric_name', 'count', 'updated_at')
    search_fields = ('metric_name',)


@admin.register(CategoryStats)
class CategoryStatsAdmin(admin.ModelAdmin):
    list_display = ('category', 'completed_count', 'updated_at')
    search_fields = ('category__name_ru',)
