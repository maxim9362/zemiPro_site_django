"""14.3 public projections. Never query or render unmoderated article source.

This is deliberately independent of the Stage14.2 authoring switch:
publication/read access is allowed only by its separate owner-gated flag.
"""
from django.conf import settings
from django.db.models import Exists, F, OuterRef, Q

from apps.accounts.client_favorites import public_worker_queryset
from .models import ExpertArticle, ExpertArticleDecision, ExpertArticleImage


def public_articles():
    """The SINGLE fail-closed public eligibility predicate for all consumers.

    The account/worker availability is shared with real public profiles.
    The fixed city constraint applies even in multi-city test configurations.
    """
    articles = ExpertArticle.objects.none()
    if not settings.ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED:
        return articles
    approved = ExpertArticleDecision.objects.filter(
        article_id=OuterRef('pk'), version=OuterRef('content_version'),
        kind=ExpertArticleDecision.Kind.APPROVE,
    )
    workers = public_worker_queryset().filter(
        city__slug='ashdod', city__is_active=True,
    ).values('pk')
    return (
        ExpertArticle.objects.filter(
            status=ExpertArticle.Status.PUBLISHED,
            public_content_safe=True,
            public_title__gt='', public_body__gt='',
            approved_version=F('content_version'),
            published_at__isnull=False,
            moderated_by__isnull=False,
            rights_confirmed_at__isnull=False,
            category__is_active=True,
            author_id__in=workers,
            author__skills__pk=F('category_id'),
            # Stage14.4: opt-in plus individually moderated pilot whitelist.
            # A mistaken global flag change alone must never publish all articles.
            author__knowledge_pilot_enrollment__consent_version=1,
            author__knowledge_pilot_enrollment__consented_at__isnull=False,
            author__knowledge_pilot_enrollment__revoked_at__isnull=True,
            author__knowledge_pilot_enrollment__accepted_by_id=F('author__user_id'),
            pilot_selection__selected_at__isnull=False,
            pilot_selection__revoked_at__isnull=True,
            pilot_selection__approved_version=F('content_version'),
            pilot_selection__selected_by__is_staff=True,
            pilot_selection__selected_by__is_active=True,
            pilot_selection__selected_by__is_blocked=False,
        ).filter(
            Q(category__section__isnull=True) | Q(category__section__is_active=True),
        ).filter(
            Q(subcategory__isnull=True) |
            Q(subcategory__is_active=True, subcategory__category_id=F('category_id')),
        ).alias(approved_evidence=Exists(approved)).filter(
            approved_evidence=True,
        ).select_related(
            'author', 'author__city', 'category', 'subcategory',
        ).defer('title', 'excerpt', 'body')
    )


def public_article_images(article):
    """Return image metadata ONLY, never raw bytes in template/queryset."""
    return ExpertArticleImage.objects.filter(
        article_id=article.pk,
        approved_version=article.content_version,
        rights_confirmed_at__isnull=False,
    ).defer('jpeg_data').order_by('pk')


def public_article_image(image_id):
    """Byte access must recheck the FULL parent gate for every request."""
    return ExpertArticleImage.objects.filter(
        pk=image_id,
        article_id__in=public_articles().values('pk'),
        approved_version=F('article__content_version'),
        rights_confirmed_at__isnull=False,
    ).only('pk', 'jpeg_data', 'public_caption', 'article_id').first()
