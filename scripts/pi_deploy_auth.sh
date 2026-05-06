#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./scripts/pi_deploy_auth.sh <username> [display_name]
# Example:
#   ./scripts/pi_deploy_auth.sh matt "Matt"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <username> [display_name]"
  exit 1
fi

OWNER_USERNAME="$1"
OWNER_DISPLAY_NAME="${2:-$1}"

APP_DIR="${APP_DIR:-$HOME/food-log}"
SERVICE_NAME="${SERVICE_NAME:-food-log}"
PORT="${PORT:-8001}"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Error: app directory not found: $APP_DIR"
  exit 1
fi

read -rsp "Enter owner password for ${OWNER_USERNAME}: " OWNER_PASSWORD
echo

if [[ -z "$OWNER_PASSWORD" ]]; then
  echo "Error: password cannot be empty"
  exit 1
fi

cd "$APP_DIR"

BACKUP_PATH="food_log.db.backup-$(date +%Y%m%d-%H%M%S)"
if [[ -f "food_log.db" ]]; then
  cp food_log.db "$BACKUP_PATH"
  echo "Database backup created: $APP_DIR/$BACKUP_PATH"
else
  echo "No existing food_log.db found; skipping backup copy"
fi

echo "Stopping service: $SERVICE_NAME"
sudo systemctl stop "$SERVICE_NAME"

echo "Pulling latest code"
git pull --ff-only

echo "Installing dependencies"
source .venv/bin/activate
pip install -r requirements.txt

echo "Running schema migrations via init_db()"
python -c "import database; database.init_db(); print('database init complete')"

echo "Creating/updating owner user and backfilling legacy rows"
OWNER_USERNAME="$OWNER_USERNAME" OWNER_DISPLAY_NAME="$OWNER_DISPLAY_NAME" OWNER_PASSWORD="$OWNER_PASSWORD" python - <<'PY'
import os
import sqlite3
from passlib.hash import bcrypt

DB = "food_log.db"
username = os.environ["OWNER_USERNAME"]
display_name = os.environ["OWNER_DISPLAY_NAME"]
password = os.environ["OWNER_PASSWORD"]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT id FROM users WHERE username = ?", (username,))
row = cur.fetchone()
if row:
    user_id = row["id"]
    cur.execute(
        "UPDATE users SET display_name = ?, password_hash = ?, is_admin = 1, is_active = 1 WHERE id = ?",
        (display_name, bcrypt.hash(password), user_id),
    )
    created = False
else:
    cur.execute(
        "INSERT INTO users (username, display_name, password_hash, is_admin, is_active) VALUES (?, ?, ?, 1, 1)",
        (username, display_name, bcrypt.hash(password)),
    )
    user_id = cur.lastrowid
    created = True

cur.execute("UPDATE resolved_entries SET user_id = ? WHERE user_id IS NULL", (user_id,))
resolved_backfilled = cur.rowcount
cur.execute("UPDATE favorites SET user_id = ? WHERE user_id IS NULL", (user_id,))
favorites_backfilled = cur.rowcount

cur.execute(
    """
    UPDATE entry_edits
    SET user_id = (
        SELECT re.user_id FROM resolved_entries re WHERE re.id = entry_edits.entry_id
    )
    WHERE user_id IS NULL
    """
)
entry_edits_mapped = cur.rowcount

cur.execute("UPDATE entry_edits SET user_id = ? WHERE user_id IS NULL", (user_id,))
entry_edits_fallback = cur.rowcount

conn.commit()

cur.execute("SELECT COUNT(*) AS c FROM resolved_entries WHERE user_id = ?", (user_id,))
resolved_total = cur.fetchone()["c"]
cur.execute("SELECT COUNT(*) AS c FROM favorites WHERE user_id = ?", (user_id,))
favorites_total = cur.fetchone()["c"]

conn.close()

print(f"owner_user_id={user_id}")
print(f"owner_username={username}")
print(f"owner_created={created}")
print(f"backfilled_resolved_entries={resolved_backfilled}")
print(f"backfilled_favorites={favorites_backfilled}")
print(f"backfilled_entry_edits_mapped={entry_edits_mapped}")
print(f"backfilled_entry_edits_fallback={entry_edits_fallback}")
print(f"owner_total_resolved_entries={resolved_total}")
print(f"owner_total_favorites={favorites_total}")
PY

echo "Starting service: $SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"
sudo systemctl --no-pager --full status "$SERVICE_NAME" | head -n 20

echo "Health check"
curl -fsS "http://127.0.0.1:${PORT}/health" || {
  echo "Health check failed on port ${PORT}"
  exit 1
}

echo
echo "Deployment complete."
echo "Login URL: http://$(hostname -I | awk '{print $1}'):${PORT}/login"
