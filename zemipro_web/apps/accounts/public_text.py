"""Stage 05 public-facing contact suppression and keyword safety.

The versioned, immutable policy is shared with data migration 0016.
"""
from .contact_policy_v2 import (
    contact_shaped_query,
    contains_public_contact,
    redact_public_contact,
    searchable_public_text,
)

__all__ = [
    'contact_shaped_query',
    'contains_public_contact',
    'redact_public_contact',
    'searchable_public_text',
]
