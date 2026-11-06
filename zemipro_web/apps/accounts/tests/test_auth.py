from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class RegistrationAndLoginTests(TestCase):
    def test_registration_creates_custom_user_and_authenticates_session(self):
        response = self.client.post(reverse('accounts:register'), {
            'username': 'new-customer',
            'password1': 'Strong-test-password-9362',
            'password2': 'Strong-test-password-9362',
        })

        self.assertRedirects(response, reverse('accounts:client_profile'))
        user = get_user_model().objects.get(username='new-customer')
        self.assertEqual(user._meta.label, 'accounts.User')
        self.assertTrue(user.check_password('Strong-test-password-9362'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_registered_custom_user_can_log_in(self):
        user = get_user_model().objects.create_user(
            username='returning-customer',
            password='Strong-login-password-9362',
        )

        response = self.client.post(reverse('accounts:login'), {
            'username': user.username,
            'password': 'Strong-login-password-9362',
        })

        self.assertRedirects(
            response,
            '/client/dashboard/',
            fetch_redirect_response=False,
        )
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_invalid_registration_does_not_create_account(self):
        response = self.client.post(reverse('accounts:register'), {
            'username': 'invalid-customer',
            'password1': 'different-password-1',
            'password2': 'different-password-2',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            get_user_model().objects.filter(username='invalid-customer').exists()
        )
