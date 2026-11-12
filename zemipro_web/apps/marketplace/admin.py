from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .models import (
    Category, ServiceSection, Subcategory, Order, Response, Rating,
    ServiceQuestionnaire, QuestionnaireVersion, OrderQuestionnaireAnswer,
)
from .questionnaire_services import publish_questionnaire


@admin.register(ServiceSection)
class ServiceSectionAdmin(admin.ModelAdmin):
    list_display = ('name_ru', 'slug', 'is_active', 'sort_order')
    list_filter = ('is_active',)
    search_fields = ('name_ru', 'name_en', 'name_he', 'slug')
    prepopulated_fields = {'slug': ('name_en',)}
    ordering = ('sort_order', 'pk')


class SubcategoryInline(admin.TabularInline):
    model = Subcategory
    extra = 0
    prepopulated_fields = {'slug': ('name_en',)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name_ru', 'section', 'emoji', 'slug', 'work_mode', 'is_active', 'sort_order')
    list_filter = ('section', 'work_mode', 'is_active')
    list_select_related = ('section',)
    search_fields = ('name_ru', 'name_en', 'name_he')
    prepopulated_fields = {'slug': ('name_en',)}
    inlines = [SubcategoryInline]


@admin.register(Subcategory)
class SubcategoryAdmin(admin.ModelAdmin):
    list_display = ('name_ru', 'category', 'slug', 'work_mode', 'is_active', 'sort_order')
    list_filter = ('category', 'work_mode', 'is_active')
    search_fields = ('name_ru', 'name_en', 'name_he', 'slug')
    prepopulated_fields = {'slug': ('name_en',)}


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'customer_phone', 'client', 'worker', 'category', 'city', 'status', 'created_at')
    list_filter = ('status', 'category', 'city', 'created_at')
    search_fields = ('customer_name', 'customer_phone', 'description', 'address', 'client__username', 'worker__username')
    raw_id_fields = ('client', 'worker', 'category', 'subcategory', 'city')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'created_at'


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'worker', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('message', 'worker__username', 'worker__email', 'order__description')
    raw_id_fields = ('order', 'worker')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'worker', 'client', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('review_text', 'worker__username', 'client__username')
    raw_id_fields = ('order', 'worker', 'client')
    readonly_fields = ('created_at',)


@admin.register(ServiceQuestionnaire)
class ServiceQuestionnaireAdmin(admin.ModelAdmin):
    list_display = ('service', 'published_version', 'updated_at')
    search_fields = ('service__name_ru', 'service__category__name_ru')
    list_select_related = ('service', 'published_version')
    raw_id_fields = ('service',)
    readonly_fields = ('published_version',)
    actions = ['publish_selected']

    @admin.action(description='Опубликовать новые версии выбранных анкет')
    def publish_selected(self, request, queryset):
        published = 0
        for questionnaire in queryset:
            try:
                _, created = publish_questionnaire(questionnaire.pk)
                published += int(created)
            except ValidationError as error:
                self.message_user(
                    request, f'{questionnaire.pk}: {error}',
                    level=messages.ERROR,
                )
        self.message_user(
            request, f'Опубликовано новых версий: {published}',
            level=messages.INFO,
        )


@admin.register(QuestionnaireVersion)
class QuestionnaireVersionAdmin(admin.ModelAdmin):
    list_display = ('id', 'questionnaire', 'number', 'created_at')
    list_select_related = ('questionnaire',)
    readonly_fields = ('questionnaire', 'number', 'schema', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderQuestionnaireAnswer)
class OrderQuestionnaireAnswerAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'version', 'created_at')
    raw_id_fields = ('order',)
    readonly_fields = (
        'order', 'version', 'schema_snapshot', 'answers', 'created_at',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
