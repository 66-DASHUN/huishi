#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/huishi}"
APP_USER="${APP_USER:-huishi}"
APP_GROUP="${APP_GROUP:-huishi}"
AGENT_USER="${AGENT_USER:-huishi-agent}"
AGENT_GROUP="${AGENT_GROUP:-huishi-agent}"
AGENT_HOME="${AGENT_HOME:-/var/lib/huishi-agent}"
AGENT_SOURCE_HOME="${AGENT_SOURCE_HOME:-/home/dashun}"
DB_NAME="${DB_NAME:-huishi_staging}"
DB_USER="${DB_USER:-huishi}"
DOMAIN="${DOMAIN:-huishi.local}"
CANVAS_DOMAIN="${CANVAS_DOMAIN:-canvas.huishi.local}"
VM_IP="${VM_IP:-192.168.13.129}"
WORKERS="${WORKERS:-4}"

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root: sudo bash $0" >&2
    exit 1
  fi
}

random_secret() {
  openssl rand -base64 36 | tr -d '\n'
}

random_urlsafe_password() {
  openssl rand -hex 24 | tr -d '\n'
}

require_root

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  acl \
  curl \
  git \
  nginx \
  openssl \
  postgresql \
  postgresql-contrib \
  python3 \
  python3-pip \
  python3-venv \
  redis-server \
  unzip

systemctl enable --now postgresql redis-server

if ! getent passwd "${APP_USER}" >/dev/null; then
  adduser --system --group --home "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

if ! getent passwd "${AGENT_USER}" >/dev/null; then
  adduser --system --group --home "${AGENT_HOME}" --shell /usr/sbin/nologin "${AGENT_USER}"
fi

mkdir -p "${APP_DIR}" /var/lib/huishi/uploads /var/lib/huishi/canvas-cache /var/log/huishi /var/backups/huishi/postgres /var/backups/huishi/code /etc/ssl/huishi
chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
chown -R "${APP_USER}:${APP_GROUP}" /var/lib/huishi /var/log/huishi /var/backups/huishi/postgres
setfacl -m u:www-data:--x /var/lib/huishi
setfacl -m u:www-data:r-x /var/lib/huishi/uploads
setfacl -m d:u:www-data:r-x /var/lib/huishi/uploads
chown root:"${APP_GROUP}" /var/backups/huishi
chmod 750 /var/backups/huishi /var/backups/huishi/postgres
chown -R root:root /var/backups/huishi/code
chmod 750 /var/backups/huishi/code
install -d -o "${AGENT_USER}" -g "${AGENT_GROUP}" -m 700 "${AGENT_HOME}"

DB_PASSWORD="${DB_PASSWORD:-$(random_urlsafe_password)}"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
  ELSE
    ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';
  END IF;
END
\$\$;
SQL

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  sudo -u postgres createdb -O "${DB_USER}" "${DB_NAME}"
fi

cd "${APP_DIR}"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

ENCRYPTION_KEY="$("./.venv/bin/python" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")"
SECRET_KEY="${HUISHI_SECRET_KEY:-$(random_secret)}"
ADMIN_PASSWORD="${HUISHI_ADMIN_PASSWORD:-$(random_secret)}"

cat > "${APP_DIR}/.env" <<ENV
HUISHI_ENV=production
HUISHI_SECRET_KEY=${SECRET_KEY}
HUISHI_ADMIN_PASSWORD=${ADMIN_PASSWORD}
HUISHI_ENCRYPTION_KEY=${ENCRYPTION_KEY}

DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@127.0.0.1:5432/${DB_NAME}
HUISHI_REQUIRE_POSTGRES=1
HUISHI_OUTPUT_DIR=/var/lib/huishi/uploads
HUISHI_LOG_DIR=/var/log/huishi
HUISHI_BACKUP_DIR=/var/backups/huishi/postgres
HUISHI_BACKUP_KEEP=14
HUISHI_CANVAS_APP_URL=https://${CANVAS_DOMAIN}

HUISHI_GENERATION_QUEUE_BACKEND=rq
HUISHI_REDIS_URL=redis://127.0.0.1:6379/0
HUISHI_RQ_QUEUE_NAME=huishi-generation
HUISHI_RQ_JOB_TIMEOUT_SECONDS=1200
HUISHI_RQ_RESULT_TTL_SECONDS=60
HUISHI_RQ_FAILURE_TTL_SECONDS=86400
HUISHI_APP_IMPORT_PATH=app:create_app

HUISHI_UPSTREAM_MAX_CONCURRENCY=240
HUISHI_UPSTREAM_RPM_LIMIT=300
HUISHI_GENERATION_LIMIT_WAIT_TIMEOUT_SECONDS=840
HUISHI_GENERATION_LIMIT_WAIT_SLEEP_SECONDS=1
HUISHI_GENERATION_TASK_STALE_SECONDS=1080
HUISHI_RATE_LIMIT_NAMESPACE=huishi
HUISHI_REQUIRE_REDIS_LIMITS=1

HUISHI_MAX_GENERATION_COUNT=10
HUISHI_MAX_ACTIVE_GENERATION_TASKS_PER_USER=2
HUISHI_MAX_REFERENCE_IMAGES=16
HUISHI_MAX_REFERENCE_IMAGE_BYTES=12M
HUISHI_MAX_CONTENT_LENGTH=64M

HUISHI_STORAGE_ORPHAN_RETENTION_DAYS=7
HUISHI_STORAGE_HIDDEN_RETENTION_DAYS=14
HUISHI_STORAGE_MAX_BYTES=200G
HUISHI_STORAGE_SWEEP_MAX_DELETE_FILES=20000
HUISHI_STORAGE_SWEEP_MIN_AGE_SECONDS=300
HUISHI_IMAGE_OPTIMIZE_ENABLED=1
HUISHI_IMAGE_JPEG_QUALITY=88
HUISHI_IMAGE_WEBP_QUALITY=86
HUISHI_IMAGE_PNG_COMPRESS_LEVEL=9
ENV

chown "${APP_USER}:${APP_GROUP}" "${APP_DIR}/.env"
chmod 600 "${APP_DIR}/.env"

openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /etc/ssl/huishi/huishi.local.key \
  -out /etc/ssl/huishi/huishi.local.crt \
  -subj "/CN=${DOMAIN}" \
  -addext "subjectAltName=DNS:${DOMAIN},DNS:${CANVAS_DOMAIN},IP:${VM_IP}"
chmod 600 /etc/ssl/huishi/huishi.local.key

if [ ! -x "${APP_DIR}/.bun/bin/bun" ]; then
  sudo -u "${APP_USER}" bash -lc "curl -fsSL https://bun.sh/install | BUN_INSTALL=${APP_DIR}/.bun bash"
fi

if [ -d "${APP_DIR}/infinite-canvas/web" ]; then
  cd "${APP_DIR}/infinite-canvas/web"
  sudo -u "${APP_USER}" env CANVAS_PARENT_ORIGINS="https://${DOMAIN}" "${APP_DIR}/.bun/bin/bun" install --frozen-lockfile
  sudo -u "${APP_USER}" env CANVAS_PARENT_ORIGINS="https://${DOMAIN}" "${APP_DIR}/.bun/bin/bun" run build
  rm -rf .next/standalone/.next/static .next/standalone/public
  mkdir -p .next/standalone/.next
  cp -a .next/static .next/standalone/.next/static
  if [ -d public ]; then
    cp -a public .next/standalone/public
  fi
  rm -rf .next/standalone/.next/cache
  ln -s /var/lib/huishi/canvas-cache .next/standalone/.next/cache
fi

cd "${APP_DIR}"
cp deploy/huishi.service /etc/systemd/system/huishi.service
cp deploy/huishi-worker@.service /etc/systemd/system/huishi-worker@.service
cp deploy/huishi-canvas.service /etc/systemd/system/huishi-canvas.service
cp deploy/huishi-canvas-agent.service /etc/systemd/system/huishi-canvas-agent.service
cp deploy/huishi-backup.service /etc/systemd/system/huishi-backup.service
cp deploy/huishi-backup.timer /etc/systemd/system/huishi-backup.timer
cp deploy/huishi-storage-sweep.service /etc/systemd/system/huishi-storage-sweep.service
cp deploy/huishi-storage-sweep.timer /etc/systemd/system/huishi-storage-sweep.timer
cp deploy/nginx-huishi.local.conf /etc/nginx/sites-available/huishi
ln -sf /etc/nginx/sites-available/huishi /etc/nginx/sites-enabled/huishi
rm -f /etc/nginx/sites-enabled/default
nginx -t

bash deploy/prepare-huishi-agent.sh

chown -R root:root "${APP_DIR}"
chown root:"${APP_GROUP}" "${APP_DIR}/.env"
chmod 640 "${APP_DIR}/.env"
find "${APP_DIR}" -type d -exec chmod go-w {} +
find "${APP_DIR}" -type f -exec chmod go-w {} +

systemctl daemon-reload

sudo -u "${APP_USER}" env $(grep -v '^#' "${APP_DIR}/.env" | xargs) "${APP_DIR}/.venv/bin/python" tools/db_smoke.py

systemctl enable --now huishi
if [ -d "${APP_DIR}/infinite-canvas/web" ]; then
  systemctl enable --now huishi-canvas
fi
if [ -d "${APP_DIR}/infinite-canvas/canvas-agent" ]; then
  systemctl enable --now huishi-canvas-agent
fi
for i in $(seq 1 "${WORKERS}"); do
  systemctl enable --now "huishi-worker@${i}"
done
systemctl enable --now huishi-storage-sweep.timer
systemctl enable --now huishi-backup.timer
systemctl reload nginx

cat <<EOF
VM staging bootstrap finished.

Add these entries to Windows hosts if not already present:
${VM_IP} ${DOMAIN}
${VM_IP} ${CANVAS_DOMAIN}

Open:
https://${DOMAIN}

Generated admin password:
${ADMIN_PASSWORD}

Generated PostgreSQL password is stored in ${APP_DIR}/.env.
EOF
