"""Test-only Stage 14 browser settings; never selected by ``DJANGO_ENV``."""

from .test import *  # noqa: F403


# These gates remain hard-off in every deployable configuration.  CI selects
# this module explicitly only while serving an isolated synthetic PostgreSQL.
ZEMIPRO_PILOT_CITY_SLUG = 'ashdod'
ZEMIPRO_KNOWLEDGE_QA_ENABLED = True
ZEMIPRO_KNOWLEDGE_ROLLOUT_METRICS_ENABLED = True
ZEMIPRO_PERSONAL_RECOMMENDATIONS_ENABLED = True
ZEMIPRO_PROFILE_SHARING_ENABLED = True
ZEMIPRO_RECOMMENDATION_REQUESTS_ENABLED = True
