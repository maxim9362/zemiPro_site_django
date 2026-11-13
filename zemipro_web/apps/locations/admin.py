from django.contrib import admin

from .models import City, CityAlias, District, Neighborhood


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ('name_ru', 'name_en', 'name_he', 'slug', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('slug', 'name_ru', 'name_en', 'name_he')
    prepopulated_fields = {'slug': ('name_en',)}


class CityAliasInline(admin.TabularInline):
    model = CityAlias
    extra = 0


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ('name_ru', 'name_en', 'name_he', 'district', 'slug', 'is_active')
    list_filter = ('district', 'is_active')
    list_select_related = ('district',)
    search_fields = ('slug', 'name_ru', 'name_en', 'name_he')
    prepopulated_fields = {'slug': ('name_en',)}
    inlines = [CityAliasInline]


@admin.register(CityAlias)
class CityAliasAdmin(admin.ModelAdmin):
    list_display = ('slug', 'city')
    search_fields = ('slug', 'city__slug', 'city__name_ru')
    raw_id_fields = ('city',)


@admin.register(Neighborhood)
class NeighborhoodAdmin(admin.ModelAdmin):
    list_display = ('name_ru', 'city', 'slug', 'is_active')
    list_filter = ('city', 'is_active')
    search_fields = ('name_ru', 'name_en', 'name_he', 'slug', 'city__slug')
    raw_id_fields = ('city',)
