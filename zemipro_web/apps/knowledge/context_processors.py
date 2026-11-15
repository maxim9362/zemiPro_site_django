"""Only a bool: avoid exposing authoring flags or private data in navigation."""
from django.conf import settings


def public_knowledge_navigation(request):
    return {
        'knowledge_articles_enabled': bool(
            settings.ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED,
        ),
    }
