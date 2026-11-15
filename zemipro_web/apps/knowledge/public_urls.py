"""New add-only locale-prefixed article routes; no changes to legacy URLs."""
from django.urls import path

from . import public_views

app_name = 'knowledge_public'

urlpatterns = [
    path('', public_views.article_list, name='article_list'),
    path('images/<int:image_id>/', public_views.article_image, name='article_image'),
    # <str> supports safe Unicode SlugField(allow_unicode=True) in ru/he.
    path('<str:slug>/', public_views.article_detail, name='article_detail'),
]
