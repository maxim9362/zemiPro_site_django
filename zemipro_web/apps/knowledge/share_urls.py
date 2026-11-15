from django.urls import path

from . import share_views

app_name = 'knowledge_share'

urlpatterns = [
    path('profile/<int:worker_id>/facebook/', share_views.facebook_share,
         name='facebook'),
]
