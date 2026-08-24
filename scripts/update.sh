#!/usr/bin/env bash
set -euo pipefail

# Routine, non-destructive deploy: pull latest code from GitHub onto the Pi,
# run schema migrations, and restart the service. Never touches users,
# passwords, or logged data. For rotating the owner login itself, use
# scripts/pi_deploy_auth.sh instead.
#
# Usage (run on the Pi, in the app directory):
#   ./scripts/update.sh
# Or from your Mac:
#   ssh companionpi 'cd ~/food-log && ./scripts/update.sh'

APP_DIR="${APP_DIR:-$HOME/food-log}"
SERVICE_NAME="${SERVICE_NAME:-food-log}"
PORT="${PORT:-8001}"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Error: app directory not found: $APP_DIR"
  exit 1
fi

cd "$APP_DIR"

echo "Fetching latest from origin"
git fetch origin

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse '@{u}')"

if [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]]; then
  echo "Already up to date at $LOCAL_SHA. Nothing to deploy."
  exit 0
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Error: working tree has uncommitted changes. Refusing to deploy."
  echo "Resolve or stash them on the Pi first, then re-run."
  exit 1
fi

echo "Current commit: $LOCAL_SHA"
echo "Deploying to:   $REMOTE_SHA"

BACKUP_PATH="food_log.db.backup-$(date +%Y%m%d-%H%M%S)"
if [[ -f "food_log.db" ]]; then
  cp food_log.db "$BACKUP_PATH"
  echo "Database backup created: $APP_DIR/$BACKUP_PATH"
else
  echo "No existing food_log.db found; skipping backup copy"
fi

echo "Stopping service: $SERVICE_NAME"
sudo systemctl stop "$SERVICE_NAME"

echo "Pulling latest code (fast-forward only)"
git pull --ff-only

echo "Installing dependencies"
source .venv/bin/activate
pip install -r requirements.txt

echo "Running schema migrations via init_db() (additive only, never drops data)"
python -c "import database; database.init_db(); print('database init complete')"

echo "Starting service: $SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"
sudo systemctl --no-pager --full status "$SERVICE_NAME" | head -n 20

echo "Health check"
if ! curl -fsS "http://127.0.0.1:${PORT}/health"; then
  echo
  echo "Health check FAILED on port ${PORT}."
  echo "Service is running the new code but did not report healthy."
  echo "Rollback:"
  echo "  sudo systemctl stop $SERVICE_NAME"
  echo "  git reset --hard $LOCAL_SHA"
  echo "  cp $BACKUP_PATH food_log.db   # only if you suspect data was affected"
  echo "  sudo systemctl start $SERVICE_NAME"
  exit 1
fi

echo
echo "Deploy complete: $LOCAL_SHA -> $REMOTE_SHA"
echo "Rollback if needed: sudo systemctl stop $SERVICE_NAME && git reset --hard $LOCAL_SHA && sudo systemctl start $SERVICE_NAME"
