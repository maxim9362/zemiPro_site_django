"""Stage 03.7: Django accounts work without Telegram or a bot runtime."""
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.test import TestCase
from django.urls import reverse

from apps.accounts.admin import UserAdmin
from apps.notifications.models import Notification
from apps.notifications.services import create_notification, get_user_notifications


class TelegramIndependentDjangoTests(TestCase):
    def test_legacy_identifier_absent_from_model_and_admin(self):
        User = get_user_model()
        with self.assertRaises(FieldDoesNotExist):
            User._meta.get_field('telegram_id')
        self.assertNotIn('telegram_id', str(UserAdmin.fieldsets))
        self.assertNotIn('telegram_id', str(UserAdmin.add_fieldsets))
        self.assertNotIn('telegram_id', UserAdmin.list_display)
        self.assertNotIn('telegram_id', UserAdmin.search_fields)

    def test_registration_and_login_work_without_telegram(self):
        result = self.client.post(reverse('accounts:register'), {
            'username': 's037-new',
            'email': 'stage037@example.invalid',
            'password1': 'Synthetic-Pass-9362',
            'password2': 'Synthetic-Pass-9362',
        })
        self.assertRedirects(result, reverse('accounts:contact_verification'))
        User = get_user_model()
        user = User.objects.get(username='s037-new')
        self.assertTrue(user.check_password('Synthetic-Pass-9362'))
        self.assertTrue(user.email_verification_required)
        self.client.post(reverse('accounts:logout'))
        login = self.client.post(reverse('accounts:login'), {
            'username': user.username, 'password': 'Synthetic-Pass-9362',
        })
        self.assertEqual(login.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_in_app_notifications_do_not_need_bot_channel(self):
        user = get_user_model().objects.create_user(
            username='s037-notified', password='Synthetic-Pass-9362',
        )
        note = create_notification(
            user, 'Synthetic event', 'Synthetic event message',
            notification_type='system',
        )
        self.assertEqual(note.recipient_id, user.pk)
        self.assertEqual(get_user_notifications(user).count(), 1)
        self.assertEqual(Notification.objects.count(), 1)

    def test_bot_routes_are_not_exposed(self):
        for path in (
            '/accounts/telegram/login/',
            '/accounts/telegram/callback/',
            '/telegram/webhook/',
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_forged_bot_identifier_never_binds_identity(self):
        result = self.client.post(reverse('accounts:register'), {
            'username': 's037-forged',
            'email': 'forged037@example.invalid',
            'password1': 'Synthetic-Pass-9362',
            'password2': 'Synthetic-Pass-9362',
            'telegram_id': '9876543210',
            'is_staff': '1',
        })
        self.assertEqual(result.status_code, 302)
        user = get_user_model().objects.get(username='s037-forged')
        self.assertFalse(user.is_staff)
        self.assertNotIn('telegram_id', (f.name for f in user._meta.fields))
