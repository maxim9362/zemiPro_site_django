from django.contrib import admin

from .models import City


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name_ru', 'name_en', 'slug', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name_ru', 'name_en', 'name_he')
    prepopulated_fields = {'slug': ('name_en',)}
