#!/usr/bin/env bash
# Manual full redeploy on the droplet. Use after a node-v* release or any compose/
# Caddyfile/.env change. edge & adapter deploy themselves on release (CI -> SSH ->
# deploy-service.sh), so for those you don't need this — it's the all-services path.
#
#   ssh root@<droplet> 'bash /opt/emer-ai-tools/deploy/redeploy.sh'
set -euo pipefail

REPO=/opt/emer-ai-tools
COMPOSE="docker compose -f docker-compose.droplet.yaml --env-file .env"

git -C "$REPO" pull --ff-only
cd "$REPO/deploy"
$COMPOSE pull
$COMPOSE up -d --remove-orphans
# The Caddyfile is a single-file bind mount: when git pull replaces it the inode
# changes and the running container keeps the old one (a `caddy reload` would just
# re-read the stale inode). Force-recreate caddy so it re-binds the current file.
# (Static files in ../site are a directory mount and update live — no recreate.)
$COMPOSE up -d --force-recreate caddy
docker image prune -f
echo "--- status ---"
$COMPOSE ps
