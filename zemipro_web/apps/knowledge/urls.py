"""Private 14.2 URLs only; Stage 14.3 will add public reads separately."""
from django.urls import path

from . import views

app_name = 'knowledge'

urlpatterns = [
    path('articles/mine/', views.my_articles, name='my_articles'),
    path('articles/new/', views.article_create, name='article_create'),
    path('articles/<int:pk>/edit/', views.article_edit, name='article_edit'),
    path('articles/<int:pk>/submit/', views.article_submit, name='article_submit'),
    path('articles/<int:pk>/archive/', views.article_archive, name='article_archive'),
    path('articles/<int:pk>/images/add/', views.article_image_add,
         name='article_image_add'),
    path('articles/<int:pk>/images/<int:image_id>/remove/',
         views.article_image_remove, name='article_image_remove'),
    path('images/<int:image_id>/private/', views.article_image_private,
         name='article_image_private'),
    path('articles/<int:pk>/report/', views.article_report, name='article_report'),
    path('moderation/', views.moderation_queue, name='moderation_queue'),
    path('moderation/articles/<int:pk>/', views.moderation_article,
         name='moderation_article'),
    path('moderation/reports/<int:pk>/decision/', views.report_decision,
         name='report_decision'),
]
