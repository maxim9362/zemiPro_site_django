from django.urls import path

from . import recommendation_views

app_name = 'knowledge_recommendations'

urlpatterns = [
    path('', recommendation_views.recommendation_list, name='list'),
    path('worker/<int:worker_id>/new/', recommendation_views.recommendation_create,
         name='create'),
    path('<int:recommendation_id>/report/', recommendation_views.report, name='report'),
]
