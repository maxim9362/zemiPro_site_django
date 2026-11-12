"""03.5 isolated tests: synthetic images, private bytes and owner permissions."""
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image, PngImagePlugin

from apps.accounts.models import WorkerPortfolioPhoto, WorkerProfile
from apps.accounts.portfolio import (
    MAX_UPLOAD_BYTES, PortfolioError, add_own_portfolio_photo,
    private_portfolio_storage,
    sanitize_portfolio_image,
)
from apps.locations.models import City
from apps.marketplace.models import Category


def make_image(fmt='PNG', *, filename=None, declared_type=None, exif=False):
    raw = BytesIO()
    img = Image.new('RGB', (18, 12), (210, 220, 230))
    options = {}
    if fmt == 'PNG':
        meta = PngImagePlugin.PngInfo()
        meta.add_text('Comment', 'GPS_PRIVATE_SYNTHETIC_MARKER')
        options['pnginfo'] = meta
    elif fmt == 'JPEG' and exif:
        metadata = Image.Exif()
        metadata[274] = 6
        metadata[270] = 'GPS_PRIVATE_SYNTHETIC_MARKER'
        options['exif'] = metadata
    img.save(raw, format=fmt, **options)
    names = {'PNG': 'test.png', 'JPEG': 'test.jpg', 'WEBP': 'test.webp'}
    types = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}
    return SimpleUploadedFile(
        filename or names[fmt], raw.getvalue(),
        content_type=declared_type or types[fmt],
    )


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class WorkerPortfolioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        cls.skill = Category.objects.create(
            slug='portfolio-synthetic-skill', name_ru='Синтетическая услуга',
        )

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings_ctx = override_settings(ZEMIPRO_PRIVATE_MEDIA_ROOT=self.temp.name)
        settings_ctx.enable()
        self.addCleanup(settings_ctx.disable)

        self.user = get_user_model().objects.create_user(
            username='portfolio-worker', email='secret@example.invalid',
        )
        self.other = get_user_model().objects.create_user(username='foreign-account')
        self.worker = WorkerProfile.objects.create(
            user=self.user, city=self.city, display_name='Synthetic Public Worker',
            description='Synthetic published worker for portfolio testing.',
            pricing_details='Negotiable', spoken_languages=['ru'],
            is_published=True,
        )
        self.worker.skills.add(self.skill)
        self.foreign_worker = WorkerProfile.objects.create(
            user=self.other, city=self.city, display_name='Other Worker',
            description='Synthetic published unrelated professional account.',
            pricing_details='Negotiable', spoken_languages=['ru'],
            is_published=True,
        )
        self.foreign_worker.skills.add(self.skill)
        self.list_url = reverse('accounts:worker_portfolio')
        self.add_url = reverse('accounts:worker_portfolio_add')
        self.client.force_login(self.user)

    def upload(self, *, public=False, file=None, **data):
        payload = {
            'image': file or make_image(),
            'caption': 'Synthetic example, not independently verified',
            'sort_order': '2', 'rights_confirmed': 'on',
        }
        if public:
            payload['is_public'] = 'on'
        payload.update(data)
        return self.client.post(self.add_url, payload)

    def test_normalizes_png_jpeg_webp_and_strips_source_metadata(self):
        for fmt in ('PNG', 'JPEG', 'WEBP'):
            with self.subTest(fmt=fmt):
                result = sanitize_portfolio_image(
                    make_image(fmt, exif=(fmt == 'JPEG')),
                )
                self.assertTrue(result.startswith(b'\xff\xd8\xff'))
                self.assertNotIn(b'GPS_PRIVATE_SYNTHETIC_MARKER', result)
                with Image.open(BytesIO(result)) as normalized:
                    self.assertEqual(normalized.format, 'JPEG')
                    self.assertEqual(dict(normalized.getexif()), {})
                    self.assertLessEqual(max(normalized.size), 1600)

    def test_image_upload_private_by_default_and_not_direct_media(self):
        self.assertRedirects(self.upload(), self.list_url)
        photo = WorkerPortfolioPhoto.objects.get(worker=self.worker)
        self.assertFalse(photo.is_public)
        self.assertTrue(photo.file_key.startswith('worker-portfolio/'))
        self.assertNotIn('test.png', photo.file_key)
        self.assertTrue(private_portfolio_storage().exists(photo.file_key))
        page = self.client.get(self.list_url)
        self.assertContains(page, 'Synthetic example')
        self.assertNotContains(page, photo.file_key)
        image_url = reverse('accounts:worker_portfolio_image', args=[photo.pk])
        own = self.client.get(image_url)
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own['Content-Type'], 'image/jpeg')
        self.assertEqual(own['Cache-Control'], 'private, no-store')
        self.assertEqual(own['X-Content-Type-Options'], 'nosniff')
        self.assertTrue(b''.join(own.streaming_content).startswith(b'\xff\xd8'))
        self.client.logout()
        self.assertEqual(self.client.get(image_url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse('marketplace:worker_public_profile',
                                    args=[self.worker.pk])).status_code, 200,
        )
        self.assertNotContains(
            self.client.get(reverse('marketplace:worker_public_profile',
                                    args=[self.worker.pk])), image_url,
        )
        self.assertEqual(self.client.get('/media/' + photo.file_key).status_code, 404)

    def test_public_photo_requires_both_photo_consent_and_published_worker(self):
        self.assertRedirects(self.upload(public=True), self.list_url)
        photo = WorkerPortfolioPhoto.objects.get(worker=self.worker)
        image_url = reverse('accounts:worker_portfolio_image', args=[photo.pk])
        self.client.logout()
        self.assertEqual(self.client.get(image_url).status_code, 200)
        page = self.client.get(reverse('marketplace:worker_public_profile',
                                       args=[self.worker.pk]))
        self.assertContains(page, image_url)
        self.assertContains(page, 'не подтверждает выполнение')
        self.worker.is_published = False
        self.worker.save(update_fields=['is_published'])
        self.assertEqual(self.client.get(image_url).status_code, 404)
        self.worker.is_published = True
        self.worker.save(update_fields=['is_published'])
        self.user.is_blocked = True
        self.user.save(update_fields=['is_blocked'])
        self.assertEqual(self.client.get(image_url).status_code, 404)

    def test_forged_owner_id_and_other_user_id_cannot_edit_read_or_delete(self):
        self.upload()
        photo = WorkerPortfolioPhoto.objects.get(worker=self.worker)
        self.client.force_login(self.other)
        url = reverse('accounts:worker_portfolio_image', args=[photo.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        for operation in ('worker_portfolio_edit', 'worker_portfolio_delete'):
            with self.subTest(operation=operation):
                response = self.client.post(reverse('accounts:' + operation, args=[photo.pk]), {
                    'caption': 'Forged edit',
                    'sort_order': 1, 'is_public': 'on',
                    'user_id': self.user.pk, 'worker_id': self.worker.pk,
                })
                self.assertEqual(response.status_code, 403)
        photo.refresh_from_db()
        self.assertEqual(photo.caption, 'Synthetic example, not independently verified')
        self.assertFalse(photo.is_public)
        self.assertTrue(private_portfolio_storage().exists(photo.file_key))

    def test_edit_visibility_caption_order_and_delete_on_transaction_commit(self):
        self.upload()
        photo = WorkerPortfolioPhoto.objects.get(worker=self.worker)
        self.assertEqual(self.client.post(reverse('accounts:worker_portfolio_edit',
                                                args=[photo.pk]), {
            'caption': 'New description',
            'sort_order': '9',
            'is_public': 'on',
            'worker': self.foreign_worker.pk,
        }).status_code, 302)
        photo.refresh_from_db()
        self.assertEqual((photo.caption, photo.sort_order, photo.is_public),
                         ('New description', 9, True))
        key = photo.file_key
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.assertEqual(self.client.post(reverse(
                'accounts:worker_portfolio_delete', args=[photo.pk],
            )).status_code, 302)
        self.assertEqual(len(callbacks), 1)
        self.assertFalse(WorkerPortfolioPhoto.objects.filter(pk=photo.pk).exists())
        self.assertFalse(private_portfolio_storage().exists(key))

    def test_bad_extension_mime_magic_corruption_and_oversize_rejected(self):
        files = (
            SimpleUploadedFile('x.svg', b'<svg/>', content_type='image/svg+xml'),
            SimpleUploadedFile('x.png', b'not a picture', content_type='image/png'),
            make_image('PNG', filename='wrong.jpg', declared_type='image/jpeg'),
            make_image('JPEG', filename='test.jpg', declared_type='application/pdf'),
            SimpleUploadedFile(
                'huge.png', b'x' * (MAX_UPLOAD_BYTES + 1), content_type='image/png',
            ),
        )
        for uploaded in files:
            with self.subTest(filename=uploaded.name):
                response = self.upload(file=uploaded)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(WorkerPortfolioPhoto.objects.count(), 0)

    def test_rejects_decompression_bomb_by_pixel_cap(self):
        with patch('apps.accounts.portfolio.MAX_IMAGE_PIXELS', 100):
            with self.assertRaises(PortfolioError):
                sanitize_portfolio_image(make_image('PNG'))

    def test_rights_confirmation_required_and_max_ten_photos(self):
        result = self.client.post(self.add_url, {
            'image': make_image('JPEG'), 'caption': 'No permission',
        })
        self.assertEqual(result.status_code, 400)
        self.assertFalse(WorkerPortfolioPhoto.objects.exists())
        for n in range(10):
            self.assertRedirects(self.upload(
                file=make_image('PNG'), caption=f'Image {n}',
            ), self.list_url)
        self.assertEqual(WorkerPortfolioPhoto.objects.count(), 10)
        self.assertEqual(self.upload().status_code, 400)
        self.assertEqual(WorkerPortfolioPhoto.objects.count(), 10)

    def test_csrf_method_guest_blocked_and_no_worker(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.add_url).status_code, 302)
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.user)
        self.assertEqual(guarded.post(self.add_url, {
            'image': make_image(),
            'rights_confirmed': 'on',
        }).status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.add_url).status_code, 405)
        self.user.is_blocked = True
        self.user.save(update_fields=['is_blocked'])
        self.assertEqual(self.upload().status_code, 403)
        with self.assertRaises(PermissionDenied):
            add_own_portfolio_photo(self.user, make_image(),
                                    rights_confirmed=True)

    def test_storage_never_inside_public_media_and_rejects_bad_saved_key(self):
        with override_settings(ZEMIPRO_PRIVATE_MEDIA_ROOT=settings.MEDIA_ROOT):
            # Relative path is not safe either; guard comparison to real MEDIA_ROOT.
            with self.assertRaises(ImproperlyConfigured):
                private_portfolio_storage()
        self.upload()
        photo = WorkerPortfolioPhoto.objects.get(worker=self.worker)
        WorkerPortfolioPhoto.objects.filter(pk=photo.pk).update(
            file_key='../private-copy.jpg',
        )
        self.assertEqual(self.client.get(reverse(
            'accounts:worker_portfolio_image', args=[photo.pk],
        )).status_code, 404)
