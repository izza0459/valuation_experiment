#!/bin/sh
# Ships this working copy to the EC2 and rebuilds what changed.
#   ./deploy.sh <ssh key>            backend + web
#   ./deploy.sh <ssh key> web        web only (the API keeps running)
set -e
KEY=${1:?usage: deploy.sh <ssh key> [service...]}; shift
HOST=${AXIA_HOST:-ubuntu@34.244.186.19}
cd "$(dirname "$0")/.."
SERVICES=${*:-backend celery web}

git ls-files -co --exclude-standard backend web | COPYFILE_DISABLE=1 tar --no-xattrs -czf /tmp/axia-app.tgz -T -
scp -q -i "$KEY" deploy/docker-compose.yml deploy/Caddyfile deploy/backend-start.sh deploy/web.Dockerfile "$HOST":axia/
scp -q -i "$KEY" /tmp/axia-app.tgz "$HOST":/tmp/axia-app.tgz
ssh -i "$KEY" "$HOST" "set -e; cd ~/axia
  rm -rf app.new && mkdir app.new && tar xzf /tmp/axia-app.tgz -C app.new
  rm -rf app.prev && { [ -d app ] && mv app app.prev || true; } && mv app.new app
  sudo docker compose up -d --build --no-deps $SERVICES
  sudo docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile"
