from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from apps.marketplace.models import Category
from apps.marketplace.tests.factories import make_user
from apps.seo.models import SeoContentPage, SeoContentRevision


class Stage09EditorialUiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            slug='stage09-editorial', name_ru='Редакционная категория',
            name_en='Editorial category', name_he='קטגוריית עריכה',
        )
        cls.author = make_user('stage09-editor')
        cls.reviewer = make_user('stage09-independent-reviewer', is_staff=True)
        cls.stranger = make_user('stage09-editorial-stranger')
        permissions = Permission.objects.filter(codename__in={
            'add_seocontentpage', 'view_seocontentpage', 'change_seocontentpage',
        })
        cls.author.user_permissions.add(*permissions)
        cls.reviewer.user_permissions.add(*Permission.objects.filter(codename__in={
            'view_seocontentpage', 'change_seocontentpage',
            'review_seo_content', 'publish_seo_content',
        }))

    def content_data(self):
        return {
            'page_type': SeoContentPage.PageType.CATEGORY,
            'language': 'ru', 'section': '', 'category': self.category.pk,
            'service': '', 'city': '', 'topic': 'Безопасный выбор услуги',
            'title': 'Безопасный выбор услуги в Ашдоде',
            'meta_description': (
                'Проверенный редакционный материал о выборе услуги без ложных обещаний.'
            ),
            'summary': (
                'Краткое объяснение безопасного выбора и оформления заявки в ZemiPro.'
            ),
            'body': (
                'Материал объясняет границы услуги и рекомендует описывать задачу через '
                'защищённую форму. Он не публикует контакты, не придумывает цены, рейтинги '
                'или гарантии и ссылается только на актуальный Django-каталог и реальные '
                'опубликованные анкеты в пределах пилота Ашдода.'
            ),
            'source_facts': 'Django catalog schema and owner-approved Ashdod pilot.',
        }

    def test_full_brief_review_publish_unpublish_flow_with_history(self):
        self.client.force_login(self.author)
        created = self.client.post(reverse('seo:editorial_create'), self.content_data())
        page = SeoContentPage.objects.get()
        self.assertRedirects(created, reverse('seo:editorial_detail', args=[page.pk]))
        self.assertEqual(page.status, SeoContentPage.Status.BRIEF)

        submitted = self.client.post(reverse(
            'seo:editorial_action', args=[page.pk, 'submit'],
        ), {'expected_version': 1})
        self.assertEqual(submitted.status_code, 302)
        page.refresh_from_db()
        self.assertEqual(page.status, SeoContentPage.Status.REVIEW)

        # The author cannot approve their own content and has no review permission.
        self.client.post(reverse(
            'seo:editorial_action', args=[page.pk, 'approve'],
        ), {'expected_version': page.version})
        page.refresh_from_db()
        self.assertEqual(page.status, SeoContentPage.Status.REVIEW)

        self.client.force_login(self.reviewer)
        self.client.post(reverse(
            'seo:editorial_action', args=[page.pk, 'approve'],
        ), {'expected_version': page.version})
        page.refresh_from_db()
        self.assertEqual(page.status, SeoContentPage.Status.APPROVED)
        self.assertEqual(page.reviewer, self.reviewer)
        self.client.post(reverse(
            'seo:editorial_action', args=[page.pk, 'publish'],
        ), {'expected_version': page.version})
        page.refresh_from_db()
        self.assertEqual(page.status, SeoContentPage.Status.PUBLISHED)
        self.assertEqual(SeoContentRevision.objects.filter(page=page).count(), 3)
        self.client.post(reverse(
            'seo:editorial_action', args=[page.pk, 'unpublish'],
        ), {'expected_version': page.version})
        page.refresh_from_db()
        self.assertEqual(page.status, SeoContentPage.Status.APPROVED)
        self.assertIsNone(page.published_at)
        self.assertEqual(SeoContentRevision.objects.filter(page=page).count(), 4)

    def test_object_permissions_noindex_csrf_and_method_guards(self):
        page = SeoContentPage.objects.create(
            author=self.author, **{
                key: value for key, value in self.content_data().items()
                if key not in {'section', 'category', 'service', 'city'}
            }, category=self.category,
        )
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(reverse('seo:editorial_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse(
            'seo:editorial_detail', args=[page.pk],
        )).status_code, 403)

        self.client.force_login(self.author)
        detail = self.client.get(reverse('seo:editorial_detail', args=[page.pk]))
        self.assertContains(detail, 'noindex,follow')
        self.assertNotContains(detail, self.stranger.username)
        self.assertEqual(self.client.put(reverse(
            'seo:editorial_detail', args=[page.pk],
        )).status_code, 405)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.author)
        self.assertEqual(csrf_client.post(reverse(
            'seo:editorial_action', args=[page.pk, 'submit'],
        ), {'expected_version': page.version}).status_code, 403)

    def test_quality_gate_rejects_thin_approval(self):
        page = SeoContentPage.objects.create(
            page_type='category', language='ru', category=self.category,
            topic='Thin', title='Thin', meta_description='Too short',
            summary='Too short', body='Too short', source_facts='Synthetic.',
            status=SeoContentPage.Status.REVIEW, author=self.author,
        )
        self.client.force_login(self.reviewer)
        self.client.post(reverse(
            'seo:editorial_action', args=[page.pk, 'approve'],
        ), {'expected_version': page.version})
        page.refresh_from_db()
        self.assertEqual(page.status, SeoContentPage.Status.REVIEW)
        self.assertFalse(page.quality_approved)

    def test_django_admin_cannot_bypass_editorial_workflow(self):
        page = SeoContentPage.objects.create(
            author=self.author, **{
                key: value for key, value in self.content_data().items()
                if key not in {'section', 'category', 'service', 'city'}
            }, category=self.category,
        )
        administrator = make_user(
            'stage09-admin-bypass', is_staff=True, is_superuser=True,
        )
        administrator.set_password('Synthetic-admin-password-9362!')
        administrator.save(update_fields=['password'])
        self.client.force_login(administrator)
        response = self.client.post(reverse(
            'admin:seo_seocontentpage_change', args=[page.pk],
        ), {'title': 'Admin bypass attempt'})
        self.assertEqual(response.status_code, 403)
        page.refresh_from_db()
        self.assertEqual(page.version, 1)
        self.assertFalse(page.revisions.exists())

    def test_staff_without_seo_permissions_cannot_read_or_edit_foreign_draft(self):
        page = SeoContentPage.objects.create(
            author=self.author, **{
                key: value for key, value in self.content_data().items()
                if key not in {'section', 'category', 'service', 'city'}
            }, category=self.category,
        )
        staff = make_user('stage09-unprivileged-staff', is_staff=True)
        self.client.force_login(staff)
        url = reverse('seo:editorial_detail', args=[page.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {
            **self.content_data(), 'expected_version': page.version,
        }).status_code, 403)
        page.refresh_from_db()
        self.assertEqual(page.title, self.content_data()['title'])
        self.assertEqual(page.version, 1)
