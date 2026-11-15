from django.urls import path

from . import request_views

app_name = 'knowledge_requests'

urlpatterns = [
    path('', request_views.request_list, name='list'),
    path('new/', request_views.request_create, name='create'),
    path('<str:slug>/', request_views.request_detail, name='detail'),
    path('<str:slug>/suggest/', request_views.response_create, name='respond'),
]
