from django.urls import path

from . import views, offer_views

app_name = 'marketplace'

urlpatterns = [
    path('', views.home, name='home'),
    path('categories/', views.categories_list, name='categories_list'),
    path('workers/', views.worker_directory_view, name='worker_directory'),
    path('api/subcategories/<int:category_id>/', views.api_subcategories, name='api_subcategories'),
    path('api/questionnaire/<int:service_id>/', views.api_questionnaire, name='api_questionnaire'),
    path('categories/<slug:slug>/', views.category_detail, name='category_detail'),
    path('cities/', views.cities_list, name='cities_list'),
    path('cities/<slug:slug>/', views.city_detail, name='city_detail'),

    path('orders/create/', views.order_create_view, name='order_create'),
    path('orders/new/', views.order_wizard_start_view, name='order_wizard_start'),
    path('orders/<int:pk>/wizard/', views.order_wizard_edit_view, name='order_wizard_edit'),
    path('orders/<int:pk>/', views.order_detail_view, name='order_detail'),
    path('orders/<int:pk>/edit/', views.order_management_edit_view, name='order_management_edit'),
    path('orders/<int:pk>/withdraw/', views.order_management_withdraw_view,
         name='order_management_withdraw'),
    path('orders/<int:pk>/duplicate/', views.order_management_duplicate_view,
         name='order_management_duplicate'),
    path('orders/photos/<int:pk>/', views.order_attachment_image_view,
         name='order_attachment_image'),
    path('orders/photos/<int:pk>/delete/', views.order_attachment_delete_view,
         name='order_attachment_delete'),
    path('orders/<int:pk>/respond/', views.order_respond_view, name='order_respond'),
    path('offers/<int:pk>/edit/', offer_views.edit_offer_view, name='offer_edit'),
    path('orders/<int:pk>/agreement/propose/', offer_views.agreement_propose_view,
         name='agreement_propose'),
    path('agreements/<int:pk>/<str:action>/', offer_views.agreement_decide_view,
         name='agreement_decide'),
    path('offers/<int:pk>/<str:action>/', offer_views.offer_action_view, name='offer_action'),
    path('orders/<int:order_id>/responses/<int:response_id>/accept/',
         views.order_accept_response_view, name='order_accept_response'),
    path('orders/<int:pk>/cancel/', views.order_cancel_view, name='order_cancel'),
    path('orders/<int:pk>/complete/', views.order_complete_view, name='order_complete'),
    path('orders/<int:pk>/review/', views.rating_create_view, name='rating_create'),

    path('worker/<int:pk>/', views.worker_public_profile_view, name='worker_public_profile'),
    path('worker/<int:pk>/favorite/', views.toggle_favorite_worker_view,
         name='toggle_favorite_worker'),
    path('worker/<int:pk>/invite/', views.worker_invitation_select_view,
         name='worker_invitation_select'),
    path('invitations/<int:pk>/', views.invitation_detail_view,
         name='invitation_detail'),
    path('invitations/<int:pk>/<str:action>/', views.invitation_action_view,
         name='invitation_action'),
    path('client/dashboard/', views.client_dashboard_view, name='client_dashboard'),
    path('worker/dashboard/', views.worker_dashboard_view, name='worker_dashboard'),
]
