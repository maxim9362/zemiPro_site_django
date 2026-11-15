from django.test import TestCase, override_settings

from apps.accounts.models import WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import Category, Subcategory
from apps.marketplace.tests.factories import make_user
from apps.seo.catalog import public_pilot_city, service_workers


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class Stage09CatalogProjectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ashdod = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.other = City.objects.create(
            slug='haifa-stage09', name_ru='Хайфа', name_en='Haifa', name_he='חיפה',
        )
        cls.category = Category.objects.create(
            slug='stage09-repair', name_ru='Ремонт', name_en='Repair', name_he='תיקון',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='stage09-paint', name_ru='Покраска',
            name_en='Painting', name_he='צביעה',
        )

    def make_worker(self, username, city, *, declare_service=True, published=True):
        profile = WorkerProfile.objects.create(
            user=make_user(username), city=city, display_name=username,
            description='Synthetic public profile without contacts.',
            pricing_details='By agreement', is_published=published,
        )
        profile.skills.add(self.category)
        if declare_service:
            profile.services.add(self.service)
        return profile

    def test_only_real_declared_ashdod_supply_is_returned(self):
        eligible = self.make_worker('seo-eligible', self.ashdod)
        self.make_worker('seo-no-service', self.ashdod, declare_service=False)
        self.make_worker('seo-other-city', self.other)
        self.make_worker('seo-draft', self.ashdod, published=False)
        self.assertEqual(list(service_workers(self.service, self.ashdod)), [eligible])
        self.assertFalse(service_workers(self.service, self.other).exists())

    def test_pilot_city_is_server_side_ashdod(self):
        self.assertEqual(public_pilot_city(), self.ashdod)
