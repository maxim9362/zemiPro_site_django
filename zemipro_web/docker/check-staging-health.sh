#!/bin/sh
# On an approved staging monitor host, check the public TLS readiness endpoint.
# Log only a constant signal, never the URL or response body.
set -eu

case "${STAGING_HEALTH_URL:-}" in
    https://*/health/ready/) ;;
    *)
        echo "SAFE_ABORT: set an approved HTTPS readiness URL" >&2
        exit 2
        ;;
esac

if curl --fail --silent --max-time 8 --output /dev/null "$STAGING_HEALTH_URL"; then
    exit 0
fi

echo "ALERT: ZemiPro staging readiness failed" >&2
if command -v logger >/dev/null 2>&1; then
    logger -p user.err -t zemipro-staging "ALERT: readiness failed"
fi
exit 1
