"""Isolated URLConf for offline allauth initiation security tests."""
from django.urls import include, path


urlpatterns = [path('oauth/', include('allauth.urls'))]
