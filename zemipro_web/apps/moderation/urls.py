from django.urls import path

from . import views

app_name = 'moderation'

urlpatterns = [
    path('complaint/', views.complaint_create_view, name='complaint_create'),
]
