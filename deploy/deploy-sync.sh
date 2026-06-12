#!/usr/bin/env bash
# Pull-based auto-deploy, run on a systemd timer (~every 2 min). The droplet pulls
# main and reconciles itself to the new state — no inbound deploy channel, so the
# origin stays firewalled to Cloudflare.
#
#   site/ change                -> nothing: a directory mount, Caddy serves it live
#   Caddyfile change            -> recreate caddy (single-file mount, inode changes)
#   compose change              -> re-apply the whole stack
#   edge/adapter image changes  -> handled separately by Watchtower (on CI build)
#
# Install (once, on the droplet):
#   cp /opt/emer-ai-tools/deploy/systemd/emer-deploy-sync.* /etc/systemd/system/
#   systemctl daemon-reload && systemctl enable --now emer-deploy-sync.timer
set -euo pipefail

REPO=/opt/emer-ai-tools
cd "$REPO"

git fetch -q origin main
before=$(git rev-parse HEAD)
after=$(git rev-parse origin/main)
[ "$before" = "$after" ] && exit 0          # nothing new

if ! git merge --ff-only -q origin/main; then
  logger -t emer-deploy-sync "non-fast-forward; manual intervention needed"
  exit 1
fi

changed=$(git diff --name-only "$before" "$after")
cd "$REPO/deploy"
COMPOSE="docker compose -f docker-compose.droplet.yaml --env-file .env"

if echo "$changed" | grep -qE '^deploy/docker-compose'; then
  $COMPOSE up -d --remove-orphans
fi
# Caddyfile is a single-file bind mount: its inode changes on pull, so the running
# container keeps the old config -> force-recreate. (site/ is a directory mount and
# is served live, so site-only changes need no action.)
if echo "$changed" | grep -qE '^deploy/Caddyfile'; then
  $COMPOSE up -d --force-recreate caddy
fi

logger -t emer-deploy-sync "synced ${before:0:7} -> ${after:0:7}"
echo "synced ${before:0:7} -> ${after:0:7} (changed: $(echo "$changed" | tr '\n' ' '))"
