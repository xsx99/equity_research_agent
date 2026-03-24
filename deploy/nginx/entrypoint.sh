#!/bin/sh
set -e

CERT_DIR=/etc/nginx/certs
KEY="$CERT_DIR/server.key"
CRT="$CERT_DIR/server.crt"

if [ ! -f "$CRT" ] || [ ! -f "$KEY" ]; then
    echo "Generating self-signed TLS certificate..."
    apk add --no-cache openssl >/dev/null 2>&1
    openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
        -keyout "$KEY" \
        -out "$CRT" \
        -subj "/CN=insider-tracker"
    echo "Certificate generated."
fi

exec nginx -g "daemon off;"
