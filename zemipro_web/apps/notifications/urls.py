from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.notification_list_view, name='notification_list'),
    path('<int:pk>/read/', views.notification_mark_read_view, name='notification_mark_read'),
    path('preferences/', views.notification_preferences_view, name='notification_preferences'),
    path('read-all/', views.notification_mark_all_read_view, name='notification_mark_all_read'),
]
