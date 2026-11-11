#!/bin/sh
set -eu

# Only the explicitly isolated development/staging Compose stacks enable this.
# Never run migrations implicitly if this image is reused for production.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    case "${DJANGO_ENV:-}" in
        development|staging)
            python manage.py migrate --noinput
            ;;
        *)
            echo "RUN_MIGRATIONS=1 requires DJANGO_ENV=development or staging." >&2
            exit 1
            ;;
    esac
fi

# STATIC_ROOT is a dedicated writable volume in both Compose deployments.
python manage.py collectstatic --noinput

exec "$@"
