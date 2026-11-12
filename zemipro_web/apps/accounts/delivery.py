"""Delivery adapters: fail closed outside explicitly isolated test mode.

Never print/send verification secrets through logs, HTTP responses or the
database. A provider adapter requires separate approval before public release.
"""
from django.conf import settings
from django.core.mail import send_mail


def deliver_contact_code(channel, destination, code):
    """Return True only when the configured transport accepts the message."""
    mode = getattr(settings, 'ZEMIPRO_CONTACT_DELIVERY_MODE', 'disabled')
    if mode == 'test-email' and getattr(settings, 'ENVIRONMENT', '') == 'test':
        if channel == 'email':
            return bool(send_mail(
                'ZemiPro contact verification',
                'Verification code: ' + code,
                'noreply@zemipro.invalid',
                [destination],
                fail_silently=False,
            ))
    return False
