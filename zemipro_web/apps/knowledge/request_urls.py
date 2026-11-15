from django.urls import path

from . import request_views

app_name = 'knowledge_requests'

urlpatterns = [
    path('', request_views.request_list, name='list'),
    path('new/', request_views.request_create, name='create'),
    path('<str:slug>/', request_views.request_detail, name='detail'),
    path('<str:slug>/suggest/', request_views.response_create, name='respond'),
    path('<str:slug>/report/', request_views.report_request, name='report_request'),
    path('<str:slug>/responses/<int:response_id>/report/',
         request_views.report_response, name='report_response'),
]
