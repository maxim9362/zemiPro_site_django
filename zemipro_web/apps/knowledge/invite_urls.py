from django.urls import path

from . import invite_views

app_name = 'knowledge_invites'

urlpatterns = [
    path('worker/<str:token>/', invite_views.landing, name='landing'),
]
