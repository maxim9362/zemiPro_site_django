"""Only a bool: avoid exposing authoring flags or private data in navigation."""
from django.conf import settings


def public_knowledge_navigation(request):
    return {
        'knowledge_articles_enabled': bool(
            settings.ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED,
        ),
        'knowledge_authoring_enabled': bool(
            settings.ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED,
        ),
        'personal_recommendations_enabled': bool(
            settings.ZEMIPRO_PERSONAL_RECOMMENDATIONS_ENABLED,
        ),
        'profile_sharing_enabled': bool(
            settings.ZEMIPRO_PROFILE_SHARING_ENABLED,
        ),
        'knowledge_qa_enabled': bool(settings.ZEMIPRO_KNOWLEDGE_QA_ENABLED),
        'recommendation_requests_enabled': bool(
            settings.ZEMIPRO_RECOMMENDATION_REQUESTS_ENABLED,
        ),
        'external_worker_invites_enabled': bool(
            settings.ZEMIPRO_EXTERNAL_WORKER_INVITES_ENABLED,
        ),
    }
