"""Stage 14.9 explicit public-profile sharing without Meta API access."""
from urllib.parse import parse_qs, urlparse

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.marketplace.tests.factories import (
    make_category, make_city, make_user, make_worker_profile,
)


class Stage14ProfileSharingTests(TestCase):
    def setUp(self):
        self.city = make_city(slug='ashdod', name_ru='Synthetic Ashdod')
        self.category = make_category(slug='s14-profile-share')
        self.user = make_user('s14-share-worker', email='private-share@example.invalid')
        self.worker = make_worker_profile(
            self.user, city=self.city, category=self.category,
        )
        self.profile_url = reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        )
        self.share_url = reverse(
            'knowledge_share:facebook', args=[self.worker.pk],
        )

    def test_disabled_flag_hides_ui_and_route(self):
        page = self.client.get(self.profile_url)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'data-copy-profile-link')
        self.assertEqual(self.client.get(self.share_url).status_code, 404)

    @override_settings(ZEMIPRO_PROFILE_SHARING_ENABLED=True)
    def test_copy_and_facebook_are_explicit_manual_controls(self):
        page = self.client.get(self.profile_url)
        self.assertContains(page, 'data-copy-profile-link')
        self.assertContains(page, self.share_url)
        self.assertContains(page, 'profile-share.js')
        response = self.client.get(self.share_url)
        self.assertEqual(response.status_code, 302)
        target = urlparse(response['Location'])
        self.assertEqual(target.scheme, 'https')
        self.assertEqual(target.netloc, 'www.facebook.com')
        self.assertEqual(target.path, '/sharer/sharer.php')
        shared = parse_qs(target.query)['u'][0]
        self.assertEqual(urlparse(shared).path, self.profile_url)
        self.assertEqual(response['Referrer-Policy'], 'no-referrer')

    @override_settings(ZEMIPRO_PROFILE_SHARING_ENABLED=True)
    def test_unpublished_or_blocked_profile_cannot_be_shared(self):
        self.worker.is_published = False
        self.worker.save(update_fields=['is_published'])
        self.assertEqual(self.client.get(self.share_url).status_code, 404)
        self.worker.is_published = True
        self.worker.save(update_fields=['is_published'])
        self.user.is_blocked = True
        self.user.save(update_fields=['is_blocked'])
        self.assertEqual(self.client.get(self.share_url).status_code, 404)

    @override_settings(ZEMIPRO_PROFILE_SHARING_ENABLED=True)
    def test_no_facebook_login_token_or_autopost_fields_exist(self):
        page = self.client.get(self.profile_url).content.decode()
        for forbidden in (
            'access_token', 'facebook_login', 'publish_actions',
            'friend_list', 'autopost',
        ):
            self.assertNotIn(forbidden, page.lower())
        self.assertNotIn(self.user.email, page)
