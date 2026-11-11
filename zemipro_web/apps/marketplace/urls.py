from django.urls import path

from . import views

app_name = 'marketplace'

urlpatterns = [
    path('', views.home, name='home'),
    path('categories/', views.categories_list, name='categories_list'),
    path('api/subcategories/<int:category_id>/', views.api_subcategories, name='api_subcategories'),
    path('categories/<slug:slug>/', views.category_detail, name='category_detail'),
    path('cities/', views.cities_list, name='cities_list'),
    path('cities/<slug:slug>/', views.city_detail, name='city_detail'),

    path('orders/create/', views.order_create_view, name='order_create'),
    path('orders/<int:pk>/', views.order_detail_view, name='order_detail'),
    path('orders/<int:pk>/respond/', views.order_respond_view, name='order_respond'),
    path('orders/<int:order_id>/responses/<int:response_id>/accept/',
         views.order_accept_response_view, name='order_accept_response'),
    path('orders/<int:pk>/cancel/', views.order_cancel_view, name='order_cancel'),
    path('orders/<int:pk>/complete/', views.order_complete_view, name='order_complete'),
    path('orders/<int:pk>/review/', views.rating_create_view, name='rating_create'),

    path('worker/<int:pk>/', views.worker_public_profile_view, name='worker_public_profile'),
    path('client/dashboard/', views.client_dashboard_view, name='client_dashboard'),
    path('worker/dashboard/', views.worker_dashboard_view, name='worker_dashboard'),
]
