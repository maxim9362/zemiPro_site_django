"""Additive /ru, /en, /he catalog routes; legacy URLs remain stable."""
from django.urls import path

from . import views

app_name = 'catalog_i18n'

urlpatterns = [
    path('categories/', views.categories_list, name='categories_list'),
    path('sections/<slug:slug>/', views.section_detail, name='section_detail'),
    path('categories/<slug:slug>/', views.category_detail, name='category_detail'),
    path(
        'services/<slug:category_slug>/<slug:service_slug>/',
        views.service_detail, name='service_detail',
    ),
    path('cities/', views.cities_list, name='cities_list'),
    path('cities/<slug:slug>/', views.city_detail, name='city_detail'),
]
