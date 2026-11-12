from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.SafeLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('client/profile/', views.client_profile_view, name='client_profile'),
    path('worker/profile/', views.worker_profile_view, name='worker_profile'),
    path('switch-role/', views.switch_role_view, name='switch_role'),
    path('verification/', views.contact_verification_view, name='contact_verification'),
    path('verification/request/', views.request_verification_view, name='request_verification'),
    path('verification/confirm/', views.confirm_verification_view, name='confirm_verification'),
    path('password-reset/', views.VerifiedPasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html',
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html',
        success_url=reverse_lazy('accounts:password_reset_complete'),
    ), name='password_reset_confirm'),
    path('reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html',
    ), name='password_reset_complete'),
]
