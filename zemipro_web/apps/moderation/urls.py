from django.urls import path

from . import views

app_name = 'moderation'

urlpatterns = [
    path('complaint/', views.complaint_create_view, name='complaint_create'),
    path('queue/', views.moderator_queue_view, name='queue'),
    path('queue/<int:pk>/decision/', views.moderator_decision_view, name='decision'),
    path('complaint/<int:pk>/appeal/', views.complaint_appeal_view, name='appeal'),
    path('appeals/<int:pk>/decision/', views.moderator_appeal_decision_view,
         name='appeal_decision'),
]
