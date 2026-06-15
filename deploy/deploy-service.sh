#!/usr/bin/env bash
# On-demand single-service rollout, invoked by CI over SSH right after it pushes a
# new image (see .github/workflows/publish-edge.yml / publish-rest-api.yml). This
# replaces the Watchtower poll: the image is pulled once, on release, instead of
# polling the registry on a timer — no rollout latency and no Docker Hub rate-limit
# cost. The systemd deploy-sync timer still reconciles config (compose/Caddyfile/
# site) on its own; this is only the image rollout for a single service.
#
#   bash /opt/emer-ai-tools/deploy/deploy-service.sh <edge|adapter>
#
# Hardening: this allowlist lets you pin the CI key to exactly this command in
# ~/.ssh/authorized_keys, e.g.
#   command="/opt/emer-ai-tools/deploy/deploy-service.sh ${SSH_ORIGINAL_COMMAND##* }",no-pty,no-port-forwarding ssh-ed25519 AAAA... ci-deploy
set -euo pipefail

svc="${1:-}"
case "$svc" in
  edge|adapter) ;;                      # never roll node/redis/caddy from CI
  *) echo "usage: deploy-service.sh <edge|adapter>" >&2; exit 2 ;;
esac

REPO=/opt/emer-ai-tools
cd "$REPO"
git pull --ff-only                      # pick up any compose/.env shipped with the release
cd "$REPO/deploy"
COMPOSE=(docker compose -f docker-compose.droplet.yaml --env-file .env)

"${COMPOSE[@]}" pull "$svc"
"${COMPOSE[@]}" up -d "$svc"
docker image prune -f
echo "deployed $svc ($("${COMPOSE[@]}" images -q "$svc" | cut -c1-12))"
