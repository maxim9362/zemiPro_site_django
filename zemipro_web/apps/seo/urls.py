from django.urls import path

from . import views


app_name = 'seo'

urlpatterns = [
    path('editorial/', views.editorial_list, name='editorial_list'),
    path('editorial/new/', views.editorial_create, name='editorial_create'),
    path('editorial/<int:pk>/', views.editorial_detail, name='editorial_detail'),
    path(
        'editorial/<int:pk>/<str:action>/',
        views.editorial_action, name='editorial_action',
    ),
]
