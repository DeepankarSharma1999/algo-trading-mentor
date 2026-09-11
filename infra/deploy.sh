#!/usr/bin/env bash
# Idempotent deploy script, run ON the VM (Ubuntu). Installs Docker if missing, pulls the latest
# code, generates a real SESSION_SECRET on first run, and brings the stack up with the production
# overlay (only the web app is exposed publicly). Re-run any time to pull and redeploy.
set -euo pipefail

REPO_URL="${REPO_URL:?set REPO_URL to your git remote, e.g. https://github.com/<you>/algo-trading-mentor.git}"
APP_DIR="${APP_DIR:-$HOME/algo-trading-mentor}"

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "Docker installed. Log out and back in (or run 'newgrp docker') then re-run this script."
  exit 0
fi

if [ ! -d "$APP_DIR/.git" ]; then
  echo "==> Cloning $REPO_URL"
  git clone "$REPO_URL" "$APP_DIR"
else
  echo "==> Pulling latest"
  git -C "$APP_DIR" pull --ff-only
fi

cd "$APP_DIR/infra"

if [ ! -f .env ]; then
  echo "==> First run: generating infra/.env"
  cp .env.example .env
  SECRET="$(openssl rand -hex 32)"
  # Windows-CRLF-safe in-place edit
  sed -i "s#^SESSION_SECRET=.*#SESSION_SECRET=${SECRET}#" .env
  echo "Generated a random SESSION_SECRET. Edit infra/.env for ANTHROPIC_API_KEY etc. if wanted."
fi

echo "==> Building and starting"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo "==> Waiting for web to report healthy"
for _ in $(seq 1 40); do
  if curl -fs http://localhost:3000/api/health >/dev/null 2>&1; then
    echo "OK: web is up. Visit http://$(curl -s ifconfig.me):3000"
    exit 0
  fi
  sleep 3
done
echo "web did not become healthy in time; check: docker compose logs web" >&2
exit 1
