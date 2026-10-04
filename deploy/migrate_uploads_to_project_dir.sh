#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/huishi}"
SOURCE_DIR="${SOURCE_DIR:-/var/lib/docker/volumes/huishi_uploads/_data}"
TARGET_DIR="${TARGET_DIR:-/opt/huishi/data/uploads}"
UPLOAD_UID="${UPLOAD_UID:-10001}"
UPLOAD_GID="${UPLOAD_GID:-10001}"
PYTHON="${PYTHON:-${APP_DIR}/.venv/bin/python}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root so Docker volume files can be read and target ownership can be set." >&2
  exit 1
fi

if [ ! -d "${SOURCE_DIR}" ]; then
  echo "Upload source does not exist: ${SOURCE_DIR}" >&2
  exit 1
fi

install -d -o "${UPLOAD_UID}" -g "${UPLOAD_GID}" -m 0750 "${TARGET_DIR}"
"${PYTHON}" "${APP_DIR}/tools/upload_storage_cli.py" migrate-local \
  --source "${SOURCE_DIR}" \
  --target "${TARGET_DIR}"
chown -R "${UPLOAD_UID}:${UPLOAD_GID}" "${TARGET_DIR}"
find "${TARGET_DIR}" -type d -exec chmod 0750 {} +
find "${TARGET_DIR}" -type f -exec chmod 0640 {} +
