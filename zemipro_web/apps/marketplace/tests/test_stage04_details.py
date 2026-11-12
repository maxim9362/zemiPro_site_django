"""04.4: structured order values, private photo storage and access boundaries."""
from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image, PngImagePlugin

from apps.accounts.portfolio import private_portfolio_storage
from apps.locations.models import City
from apps.marketplace.models import Category, Order, OrderAttachment, Subcategory
from apps.marketplace.tests.factories import make_user
from apps.marketplace.attachment_services import (
    OrderPhotoError, validate_order_photo_batch,
)


def test_image(*, fmt='PNG', color=40, filename=None, content_type=None, marker=True):
    memory = BytesIO()
    im = Image.new('RGB', (28, 18), (color, 100, 220))
    options = {}
    if fmt == 'PNG' and marker:
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('Comment', 'GPS_SECRET_STAGE044_NEVER_PERSIST')
        options['pnginfo'] = metadata
    im.save(memory, format=fmt, **options)
    names = {'PNG': 'photo.png', 'JPEG': 'photo.jpeg', 'WEBP': 'photo.webp'}
    types = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}
    return SimpleUploadedFile(
        filename or names[fmt], memory.getvalue(),
        content_type=content_type or types[fmt],
    )


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class OrderDetailsPhotoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='044-photos', name_ru='Ремонт',
            name_en='Repair', name_he='תיקונים',
        )
        cls.service = Subcategory.objects.create(
            slug='044-repair-service', category=cls.category,
            name_ru='Покраска', name_en='Painting', name_he='צביעה',
            work_mode='onsite',
        )
        cls.owner = make_user('order-photo-owner-044')
        cls.stranger = make_user('order-photo-other-044')
        cls.worker = make_user('order-photo-worker-044')
        cls.moderator = make_user('order-photo-mod-044', is_staff=True)
        cls.moderator.user_permissions.add(Permission.objects.get(
            content_type__app_label='moderation', codename='review_complaints',
        ))

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        setting = override_settings(ZEMIPRO_PRIVATE_MEDIA_ROOT=directory.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.client.force_login(self.owner)

    def begin(self):
        root = reverse('marketplace:order_wizard_start')
        page = self.client.get(root)
        token = page.context['token']
        result = self.client.post(root, {
            'action': 'start', 'token': token,
            'category': self.category.pk, 'subcategory': self.service.pk,
        })
        self.assertEqual(result.status_code, 302)
        return Order.objects.get(wizard_token=token)

    def step(self, order, number, data=None):
        data = data or {}
        url = reverse('marketplace:order_wizard_edit', args=[order.pk])
        return self.client.post(f'{url}?step={number}', {
            'action': 'publish' if number == 8 else 'next',
            **data,
        })

    def get_to_photos(self):
        order = self.begin()
        entries = {
            2: {'questionnaire_version': ''},
            3: {'city': self.city.pk, 'mode': 'onsite', 'area': 'Central Ashdod'},
            4: {
                'preferred_date': (timezone.localdate() + timedelta(days=5)).isoformat(),
                'urgency': 'urgent',
            },
            5: {'price_type': 'range', 'amount_min': '250.20', 'amount_max': '350.50'},
        }
        for step, data in entries.items():
            response = self.step(order, step, data)
            self.assertEqual(response.status_code, 302, response.content[:300])
        return order

    def finish(self, order):
        self.assertEqual(self.step(order, 7, {
            'display_name': 'Synthetic Name', 'chat_ack': 'on',
        }).status_code, 302)
        return self.step(order, 8, {'confirm': 'on'})

    def upload(self, order, *, color=40, visibility='private', consent=False):
        return self.step(order, 6, {
            'description': 'Synthetic room painting in an approximate area.',
            'photos': [test_image(color=color)],
            'photo_visibility': visibility,
            'public_photo_consent': 'on' if consent else '',
        })

    def image_response(self, photo, *, as_user=None):
        if as_user is None:
            self.client.logout()
        else:
            self.client.force_login(as_user)
        return self.client.get(reverse('marketplace:order_attachment_image', args=[photo.pk]))

    def test_range_and_location_persist_into_order_columns_and_preserve_text(self):
        order = self.get_to_photos()
        self.assertEqual(self.step(order, 6, {
            'description': 'Synthetic work description long enough.',
        }).status_code, 302)
        self.assertEqual(self.finish(order).status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.price_kind, Order.PriceKind.RANGE)
        self.assertEqual(str(order.amount_min_ils), '250.20')
        self.assertEqual(str(order.amount_max_ils), '350.50')
        self.assertEqual(order.price, '250.20–350.50 ₪')
        self.assertEqual(order.preferred_date, timezone.localdate() + timedelta(days=5))
        self.assertEqual(order.urgency, Order.Urgency.URGENT)
        self.assertEqual(order.work_mode, Order.WorkMode.ONSITE)
        self.assertEqual(order.approximate_area, 'Central Ashdod')
        self.assertEqual(order.address, '')
        self.assertEqual(order.customer_phone, '')
        self.client.force_login(self.stranger)
        detail = self.client.get(reverse('marketplace:order_detail', args=[order.pk]))
        self.assertContains(detail, 'Central Ashdod')
        self.assertContains(detail, '250.20')
        self.assertNotContains(detail, 'Synthetic work description long enough.')

    def test_legacy_values_are_not_rewritten_or_guessed(self):
        order = Order.objects.create(
            client=self.owner, category=self.category, city=self.city,
            price='892–1050 ₪', description='Private legacy order',
            address='PRIVATE_HOME_044', customer_phone='0501234000',
        )
        order.refresh_from_db()
        self.assertEqual(order.price, '892–1050 ₪')
        self.assertEqual(order.price_kind, Order.PriceKind.LEGACY)
        self.assertIsNone(order.amount_min_ils)
        self.assertIsNone(order.amount_max_ils)
        self.assertIsNone(order.preferred_date)
        self.assertEqual(order.approximate_area, '')
        self.assertEqual(order.work_mode, Order.WorkMode.LEGACY)
        self.assertEqual(order.address, 'PRIVATE_HOME_044')

    def test_photo_sanitized_and_only_owner_sees_private_media(self):
        order = self.get_to_photos()
        self.assertEqual(self.upload(order).status_code, 302)
        photo = OrderAttachment.objects.get(order=order)
        self.assertEqual(photo.visibility, OrderAttachment.Visibility.PRIVATE)
        self.assertEqual(photo.uploaded_by_id, self.owner.pk)
        self.assertRegex(photo.file_key, r'^order-attachments/[0-9a-f]{32}\.jpg$')
        self.assertNotIn('photo.png', photo.file_key)
        self.assertLessEqual(photo.byte_size, 5 * 1024 * 1024)
        self.assertNotIn('GPS_SECRET_STAGE044_NEVER_PERSIST', (
            private_portfolio_storage().open(photo.file_key).read().decode(
                'latin1',
            )
        ))
        response = self.image_response(photo, as_user=self.owner)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow, noarchive')
        self.assertTrue(b''.join(response.streaming_content).startswith(b'\xff\xd8'))
        self.assertEqual(self.image_response(photo, as_user=self.stranger).status_code, 404)
        self.assertEqual(self.image_response(photo, as_user=self.worker).status_code, 404)
        self.assertEqual(self.image_response(photo).status_code, 404)
        self.assertEqual(self.image_response(photo, as_user=self.moderator).status_code, 200)

    def test_public_sharing_requires_explicit_consent_and_publication(self):
        order = self.get_to_photos()
        without = self.upload(order, visibility='public')
        self.assertEqual(without.status_code, 200)
        self.assertFalse(OrderAttachment.objects.filter(order=order).exists())
        self.assertEqual(self.upload(order, visibility='public', consent=True).status_code, 302)
        photo = OrderAttachment.objects.get(order=order)
        self.assertIsNotNone(photo.public_consent_at)
        self.assertEqual(self.image_response(photo).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.step(order, 7, {
            'display_name': 'Synthetic Owner', 'chat_ack': 'on',
        }).status_code, 302)
        self.assertEqual(self.step(order, 8, {'confirm': 'on'}).status_code, 302)
        self.assertEqual(self.image_response(photo).status_code, 200)

    def test_assignee_visibility_never_implies_public_access(self):
        order = self.get_to_photos()
        self.assertEqual(self.upload(order, visibility='assignee').status_code, 302)
        photo = OrderAttachment.objects.get(order=order)
        self.assertEqual(self.image_response(photo, as_user=self.worker).status_code, 404)
        self.client.force_login(self.owner)
        # Publish without assigning a worker; photo remains owner-only.
        self.assertEqual(self.step(order, 7, {
            'display_name': 'Owner', 'chat_ack': 'on',
        }).status_code, 302)
        self.assertEqual(self.step(order, 8, {'confirm': 'on'}).status_code, 302)
        self.assertEqual(self.image_response(photo, as_user=self.worker).status_code, 404)
        Order.objects.filter(pk=order.pk).update(worker=self.worker)
        self.assertEqual(self.image_response(photo, as_user=self.worker).status_code, 200)
        self.assertEqual(self.image_response(photo, as_user=self.stranger).status_code, 404)
        self.assertEqual(self.image_response(photo).status_code, 404)

    def test_image_replay_and_photo_limit(self):
        order = self.get_to_photos()
        self.assertEqual(self.upload(order, color=45).status_code, 302)
        self.assertEqual(self.upload(order, color=45).status_code, 302)
        self.assertEqual(OrderAttachment.objects.filter(order=order).count(), 1)
        for color in (46, 47, 48, 49):
            self.assertEqual(self.upload(order, color=color).status_code, 302)
        self.assertEqual(OrderAttachment.objects.filter(order=order).count(), 5)
        rejected = self.upload(order, color=50)
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(OrderAttachment.objects.filter(order=order).count(), 5)

    def test_reject_wrong_content_size_extension_and_animation(self):
        invalids = [
            SimpleUploadedFile('evil.svg', b'<svg><script>alert(1)</script></svg>',
                               content_type='image/svg+xml'),
            SimpleUploadedFile('evil.png', b'not an image', content_type='image/png'),
            SimpleUploadedFile('wrong.jpg', test_image().read(), content_type='image/jpeg'),
            SimpleUploadedFile('too-big.png', b'0' * (5 * 1024 * 1024 + 1),
                               content_type='image/png'),
        ]
        for upload in invalids:
            with self.subTest(filename=upload.name), self.assertRaises(OrderPhotoError):
                validate_order_photo_batch([upload])
        animated = BytesIO()
        Image.new('RGB', (16, 12), 'red').save(
            animated, format='WEBP', save_all=True,
            append_images=[Image.new('RGB', (16, 12), 'blue')],
            duration=100, loop=0,
        )
        with self.assertRaises(OrderPhotoError):
            validate_order_photo_batch([
                SimpleUploadedFile('animated.webp', animated.getvalue(),
                                   content_type='image/webp'),
            ])
        self.assertEqual(len(validate_order_photo_batch([test_image(fmt='WEBP')])), 1)

    def test_area_cannot_capture_home_address(self):
        order = self.begin()
        self.assertEqual(self.step(order, 2, {'questionnaire_version': ''}).status_code, 302)
        for area in ('Street 14, house 9', 'רחוב הרצל 16', 'улица Герцля, дом 3'):
            with self.subTest(area=area):
                result = self.step(order, 3, {
                    'city': self.city.pk, 'mode': 'onsite', 'area': area,
                })
                self.assertEqual(result.status_code, 200)
                self.assertIn('area', result.context['form'].errors)
                self.assertNotIn('3', Order.objects.get(pk=order.pk).wizard_data['steps'])

    def test_delete_revoke_is_owner_only_and_post_only(self):
        order = self.get_to_photos()
        self.assertEqual(self.upload(order).status_code, 302)
        photo = OrderAttachment.objects.get(order=order)
        url = reverse('marketplace:order_attachment_delete', args=[photo.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(OrderAttachment.objects.count(), 1)
        self.client.force_login(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            deleted = self.client.post(url)
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(OrderAttachment.objects.exists())
        self.assertFalse(private_portfolio_storage().exists(photo.file_key))
        self.assertEqual(self.image_response(photo).status_code, 404)

    def test_cannot_store_private_files_inside_served_media_root(self):
        with override_settings(ZEMIPRO_PRIVATE_MEDIA_ROOT=settings.MEDIA_ROOT):
            with self.assertRaises(ImproperlyConfigured):
                private_portfolio_storage()

    def test_other_user_cannot_upload_via_wizard_ownership(self):
        order = self.get_to_photos()
        self.client.force_login(self.stranger)
        forged = self.step(order, 6, {
            'description': 'Synthetic forged file submission',
            'photos': [test_image()],
        })
        self.assertEqual(forged.status_code, 404)
        self.assertEqual(OrderAttachment.objects.count(), 0)
