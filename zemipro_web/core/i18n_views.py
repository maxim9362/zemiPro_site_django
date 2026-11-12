"""Language switching that recognizes the *source* locale in prefixed URLs.

Django's built-in set_language() resolves the supplied next URL under
the POST request's active language. A visitor opening /he/... without a
cookie then posting from /i18n/setlang/ can have active 'ru', so its
/he/... URL doesn't resolve, and the redirect remains Hebrew even after
the new 'en' cookie is set.

Trust the source language prefix only when next is a validated local URL.
Delegate cookie, CSRF protections and redirect validation to Django itself.
"""
from urllib.parse import urlsplit

from django.utils import translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.i18n import set_language


def safe_set_language(request):
    next_url = request.POST.get('next', '') if request.method == 'POST' else ''
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        source_language = translation.get_language_from_path(
            urlsplit(next_url).path
        )
        if source_language:
            with translation.override(source_language):
                return set_language(request)
    return set_language(request)
