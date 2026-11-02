#!/bin/sh
# Runs on the EC2 every minute (axia-autodeploy.timer): when `main` on GitHub
# has a new commit, deploy it. Pull-based, so GitHub needs no way in: the
# server reads the repo with a read-only deploy key (ssh host "github-axia").
#
# A failed build or a site that doesn't come up healthy puts the previous
# code back. A `main` without experiment/deploy/ is never deployed.
set -eu

AXIA=/home/ubuntu/axia
REPO=$AXIA/repo
BRANCH=${AXIA_BRANCH:-main}
DEPLOYED=$AXIA/deployed-sha
log() { echo "$(date -u +%FT%TZ) $*"; }

exec 9>"$AXIA/.autodeploy.lock"
flock -n 9 || exit 0  # the previous run is still deploying

if [ ! -d "$REPO" ]; then
  git clone -q --branch "$BRANCH" github-axia:bayutuae/bayut-axia.git "$REPO"
fi
git -C "$REPO" fetch -q origin "$BRANCH"
SHA=$(git -C "$REPO" rev-parse "origin/$BRANCH")
[ "$SHA" = "$(cat "$DEPLOYED" 2>/dev/null || true)" ] && exit 0

if ! git -C "$REPO" cat-file -e "$SHA:experiment/deploy/docker-compose.yml" 2>/dev/null; then
  log "skip $SHA: no experiment/deploy on $BRANCH"
  exit 0
fi

log "deploying $SHA ($(git -C "$REPO" log -1 --format=%s "$SHA"))"
cd "$AXIA"
rm -rf app.new && mkdir app.new
git -C "$REPO" archive "$SHA:experiment" backend web | tar x -C app.new
for f in docker-compose.yml Caddyfile backend-start.sh web.Dockerfile autodeploy.sh; do
  git -C "$REPO" show "$SHA:experiment/deploy/$f" > "$f.new"
done
chmod +x autodeploy.sh.new
rm -rf app.prev && mv app app.prev && mv app.new app
mkdir -p prev && cp docker-compose.yml Caddyfile backend-start.sh web.Dockerfile prev/
for f in docker-compose.yml Caddyfile backend-start.sh web.Dockerfile autodeploy.sh; do mv "$f.new" "$f"; done

healthy() {
  for _ in $(seq 1 60); do
    curl -fsS -o /dev/null -H "Host: app.bayutaxia.com" http://127.0.0.1/api/health/ \
      && curl -fsS -o /dev/null -H "Host: app.bayutaxia.com" http://127.0.0.1/login && return 0
    sleep 5
  done
  return 1
}

if docker compose up -d --build --no-deps backend celery web \
  && docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile && healthy; then
  echo "$SHA" > "$DEPLOYED"
  docker image prune -f >/dev/null
  log "deployed $SHA"
else
  log "deploy of $SHA FAILED; rolling back"
  rm -rf app.failed && mv app app.failed && mv app.prev app
  cp prev/* .
  docker compose up -d --build --no-deps backend celery web
  docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile || true
  # Marked as handled so it isn't retried every minute; the previous code
  # stays live until the next commit to main.
  echo "$SHA" > "$DEPLOYED"
  exit 1
fi
