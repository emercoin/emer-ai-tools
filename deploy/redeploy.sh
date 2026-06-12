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
docker image prune -f
echo "--- status ---"
$COMPOSE ps
