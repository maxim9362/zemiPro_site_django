"""Stage 02.1 catalog: additive, stable IDs, trilingual and idempotent."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from apps.marketplace.models import Category, ServiceSection, Subcategory
from .factories import make_category, make_city, make_order, make_user


class Stage02CatalogSeedTests(TestCase):
    def seed(self, *args):
        call_command('seed_service_catalog', *args, stdout=StringIO())

    def test_plan_is_read_only_and_validates_all_translation_entries(self):
        self.seed('--plan')
        self.assertEqual(ServiceSection.objects.count(), 0)
        self.assertEqual(Category.objects.count(), 0)
        self.assertEqual(Subcategory.objects.count(), 0)
        with self.assertRaises(CommandError):
            self.seed('--check')

    def test_seed_twice_has_no_duplicates_or_id_changes(self):
        self.seed()
        self.assertEqual(ServiceSection.objects.count(), 12)
        self.assertEqual(Category.objects.count(), 19)
        self.assertEqual(Subcategory.objects.count(), 88)
        self.seed('--check')
        original = {
            'sections': list(ServiceSection.objects.order_by('slug').values_list('slug', 'pk')),
            'categories': list(Category.objects.order_by('slug').values_list('slug', 'pk')),
            'services': list(Subcategory.objects.order_by('category_id', 'slug').values_list(
                'category_id', 'slug', 'pk',
            )),
        }
        self.seed()
        self.assertEqual(original['sections'], list(
            ServiceSection.objects.order_by('slug').values_list('slug', 'pk')
        ))
        self.assertEqual(original['categories'], list(
            Category.objects.order_by('slug').values_list('slug', 'pk')
        ))
        self.assertEqual(original['services'], list(
            Subcategory.objects.order_by('category_id', 'slug').values_list(
                'category_id', 'slug', 'pk',
            )
        ))
        for model in (ServiceSection, Category, Subcategory):
            self.assertFalse(model.objects.filter(name_en='').exists())
            self.assertFalse(model.objects.filter(name_he='').exists())

    def test_old_repair_seed_can_run_repeatedly_without_mutating_manifest(self):
        self.seed_repair()
        self.seed_repair()
        self.assertEqual(Category.objects.count(), 8)
        self.assertEqual(Subcategory.objects.count(), 56)
        self.seed()
        self.assertEqual(Category.objects.count(), 19)
        self.assertEqual(Subcategory.objects.count(), 88)

    def seed_repair(self):
        call_command('seed_repair_categories', stdout=StringIO())

    def test_existing_orders_and_custom_admin_fields_are_preserved(self):
        city = make_city()
        owner = make_user('catalog-owner')
        old_cat = make_category(slug='plumbing', name_ru='Сантехника — редакция')
        old_cat.is_active = False
        old_cat.sort_order = 777
        old_cat.save(update_fields=['is_active', 'sort_order'])
        old_service = Subcategory.objects.create(
            category=old_cat, slug='leak-repair', name_ru='Локальный термин',
        )
        legacy_order = make_order(client=owner, category=old_cat, city=city)
        unrelated = make_category(slug='my-custom-category')
        before_ids = (old_cat.pk, old_service.pk, legacy_order.pk, unrelated.pk)

        self.seed()
        old_cat.refresh_from_db()
        old_service.refresh_from_db()
        legacy_order.refresh_from_db()
        unrelated.refresh_from_db()
        self.assertEqual(
            before_ids, (old_cat.pk, old_service.pk, legacy_order.pk, unrelated.pk)
        )
        self.assertEqual(legacy_order.category_id, old_cat.pk)
        self.assertFalse(old_cat.is_active)
        self.assertEqual(old_cat.sort_order, 777)
        self.assertEqual(old_cat.name_ru, 'Сантехника — редакция')
        self.assertEqual(old_service.name_ru, 'Локальный термин')
        self.assertEqual(old_cat.section.slug, 'repairs')
        self.assertTrue(old_cat.name_en and old_cat.name_he)
        self.assertTrue(old_cat.description)
        self.assertTrue(old_service.name_en and old_service.name_he)

        # Operator edits must not be reset by an idempotent re-run.
        old_cat.name_en = 'Custom Plumbing'
        old_cat.save(update_fields=['name_en'])
        self.seed()
        old_cat.refresh_from_db()
        self.assertEqual(old_cat.name_en, 'Custom Plumbing')

    def test_existing_category_cannot_be_silently_moved_to_another_section(self):
        self.seed()
        category = Category.objects.get(slug='plumbing')
        category.section = ServiceSection.objects.get(slug='education')
        category.save(update_fields=['section'])
        with self.assertRaises(CommandError):
            self.seed()
        category.refresh_from_db()
        self.assertEqual(category.section.slug, 'education')

    def test_duplicate_seed_slugs_fail_before_any_database_writes(self):
        from apps.marketplace.management.commands import seed_service_catalog as module
        duplicated = [*module.NEW_CATEGORIES, module.NEW_CATEGORIES[0]]
        with patch.object(module, 'NEW_CATEGORIES', duplicated):
            with self.assertRaises(CommandError):
                self.seed()
        self.assertEqual(ServiceSection.objects.count(), 0)

    def test_localized_names_fallback_and_work_modes(self):
        self.seed()
        from django.utils.translation import override
        section = ServiceSection.objects.get(slug='education')
        tutoring = Category.objects.get(slug='tutoring')
        service = Subcategory.objects.get(category=tutoring, slug='math-tutoring')
        for language, section_name, category_name in (
            ('ru', 'Образование', 'Репетиторы'),
            ('en', 'Education', 'Tutoring'),
            ('he', 'חינוך ולימודים', 'שיעורים פרטיים'),
        ):
            with override(language):
                self.assertEqual(section.localized_name, section_name)
                self.assertEqual(tutoring.localized_name, category_name)
                self.assertTrue(service.localized_name)
        self.assertEqual(tutoring.work_mode, 'both')
        section.name_he = ''
        with override('he'):
            self.assertEqual(section.localized_name, section.name_ru)


class Stage02CatalogPagesTests(TestCase):
    def setUp(self):
        call_command('seed_service_catalog', stdout=StringIO())

    def test_sections_and_categories_are_public_and_localized(self):
        url = reverse('marketplace:categories_list')
        response = self.client.get(url, HTTP_ACCEPT_LANGUAGE='he')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'חינוך ולימודים')
        self.assertContains(response, 'שיעורים פרטיים')
        self.assertContains(response, 'הרכבת רהיטים')
        self.assertContains(response, 'dir="rtl"')

    def test_inactive_section_does_not_leak_categories_or_order_form_options(self):
        section = ServiceSection.objects.get(slug='digital')
        category = Category.objects.get(slug='website-development')
        section.is_active = False
        section.save(update_fields=['is_active'])
        listing = self.client.get(reverse('marketplace:categories_list'))
        self.assertNotContains(listing, 'Разработка сайтов')
        self.assertEqual(self.client.get(
            reverse('marketplace:category_detail', args=[category.slug])
        ).status_code, 404)
        from apps.marketplace.forms import OrderCreateForm
        self.assertNotIn(category, OrderCreateForm().fields['category'].queryset)

    def test_unassigned_old_categories_remain_visible_before_seed(self):
        from apps.marketplace.models import Category
        category = Category.objects.create(name_ru='Своя услуга', slug='custom-unique')
        response = self.client.get(reverse('marketplace:categories_list'))
        self.assertContains(response, 'Своя услуга')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(category.section_id, None)

    def test_category_detail_lists_localized_subcategories_without_exposing_ids(self):
        category = Category.objects.get(slug='plumbing')
        response = self.client.get(
            reverse('marketplace:category_detail', args=[category.slug]),
            HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertContains(response, 'Plumbing')
        self.assertContains(response, 'Leak repair')
        self.assertEqual(response.status_code, 200)
