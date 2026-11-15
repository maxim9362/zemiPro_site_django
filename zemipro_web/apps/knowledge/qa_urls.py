"""Locale-prefixed Stage 14.6 Q&A routes."""
from django.urls import path

from . import qa_views

app_name = 'knowledge_qa'

urlpatterns = [
    path('', qa_views.question_list, name='list'),
    path('ask/', qa_views.question_create, name='create'),
    path('<str:slug>/', qa_views.question_detail, name='detail'),
    path('<str:slug>/go/<str:destination>/', qa_views.question_outbound,
         name='outbound'),
    path('<str:slug>/answers/<int:answer_id>/go/<str:destination>/',
         qa_views.question_outbound, name='answer_outbound'),
    path('<str:slug>/answer/', qa_views.answer_create, name='answer'),
    path('<str:slug>/answers/<int:answer_id>/accept/', qa_views.accept_answer,
         name='accept'),
    path('<str:slug>/answers/<int:answer_id>/helpful/', qa_views.vote_answer,
         name='vote'),
    path('<str:slug>/report/', qa_views.report_question, name='report_question'),
    path('<str:slug>/answers/<int:answer_id>/report/', qa_views.report_answer,
         name='report_answer'),
]
