#!/usr/bin/env bash
# Manual full redeploy on the droplet. Use after a node-v* release or any compose/
# Caddyfile/.env change. edge & adapter normally auto-update via Watchtower, so for
# those you don't need this — it's the deliberate, all-services path.
#
#   ssh root@<droplet> 'bash /opt/emer-ai-tools/deploy/redeploy.sh'
set -euo pipefail

REPO=/opt/emer-ai-tools
COMPOSE="docker compose -f docker-compose.droplet.yaml --env-file .env"

git -C "$REPO" pull --ff-only
cd "$REPO/deploy"
$COMPOSE pull
$COMPOSE up -d --remove-orphans
# Caddyfile is bind-mounted, so `up -d` won't recreate caddy on a config-only
# change — reload it explicitly (also picks up new static files in ../site).
docker exec emer-caddy caddy reload --config /etc/caddy/Caddyfile 2>/dev/null \
  || echo "caddy reload skipped (container not running yet)"
docker image prune -f
echo "--- status ---"
$COMPOSE ps
