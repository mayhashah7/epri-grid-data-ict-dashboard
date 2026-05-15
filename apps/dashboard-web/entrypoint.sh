#!/bin/sh
# Generates /config.js with the runtime API base URL so the SPA can reach the
# API directly via CORS (the dashboard API has corsPolicy allowedOrigins=['*']).
set -e
CONFIG_FILE=/usr/share/nginx/html/config.js
cat > "$CONFIG_FILE" <<EOF
window.__AMI_API_BASE__ = "${API_BASE_URL}";
EOF
echo "[entrypoint] Wrote $CONFIG_FILE -> API_BASE_URL='${API_BASE_URL}'"
