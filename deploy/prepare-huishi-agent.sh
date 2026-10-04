#!/usr/bin/env bash
set -euo pipefail

AGENT_USER="${AGENT_USER:-huishi-agent}"
AGENT_GROUP="${AGENT_GROUP:-huishi-agent}"
AGENT_HOME="${AGENT_HOME:-/var/lib/huishi-agent}"
SOURCE_HOME="${AGENT_SOURCE_HOME:-/home/dashun}"
RUNTIME_DIR="${AGENT_RUNTIME_DIR:-/usr/local/lib/huishi-agent}"
CLAUDE_SOURCE="${CLAUDE_SOURCE:-$(readlink -f /usr/local/bin/claude)}"
CODEX_SCOPE_SOURCE="${CODEX_SCOPE_SOURCE:-${SOURCE_HOME}/.bun/install/global/node_modules/@openai}"
BUN_BIN="${BUN_BIN:-/opt/huishi/.bun/bin/bun}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

if ! getent passwd "${AGENT_USER}" >/dev/null; then
  adduser --system --group --home "${AGENT_HOME}" --shell /usr/sbin/nologin "${AGENT_USER}"
fi

install -d -o "${AGENT_USER}" -g "${AGENT_GROUP}" -m 700 "${AGENT_HOME}"
install -d -o root -g root -m 755 "${RUNTIME_DIR}"

if [ ! -x "${CLAUDE_SOURCE}" ]; then
  echo "Claude runtime is missing: ${CLAUDE_SOURCE}" >&2
  exit 1
fi
if [ ! -f "${CODEX_SCOPE_SOURCE}/codex/bin/codex.js" ]; then
  echo "Codex runtime is missing: ${CODEX_SCOPE_SOURCE}" >&2
  exit 1
fi
if [ ! -x "${BUN_BIN}" ]; then
  echo "Bun runtime is missing: ${BUN_BIN}" >&2
  exit 1
fi

if [ "${CLAUDE_SOURCE}" != "${RUNTIME_DIR}/claude" ]; then
  install -m 0755 -o root -g root "${CLAUDE_SOURCE}" "${RUNTIME_DIR}/claude"
fi
rm -rf "${RUNTIME_DIR}/node_modules/@openai"
install -d -o root -g root -m 755 "${RUNTIME_DIR}/node_modules"
cp -a "${CODEX_SCOPE_SOURCE}" "${RUNTIME_DIR}/node_modules/@openai"
chown -R root:root "${RUNTIME_DIR}/node_modules"
find "${RUNTIME_DIR}/node_modules" -type d -exec chmod go-w {} +
find "${RUNTIME_DIR}/node_modules" -type f -exec chmod go-w {} +

ln -sfn "${RUNTIME_DIR}/claude" /usr/local/bin/claude
cat > /usr/local/bin/codex <<EOF
#!/bin/sh
exec ${BUN_BIN} ${RUNTIME_DIR}/node_modules/@openai/codex/bin/codex.js "\$@"
EOF
chown root:root /usr/local/bin/codex
chmod 0755 /usr/local/bin/codex

rsync -a --exclude=downloads/ "${SOURCE_HOME}/.claude/" "${AGENT_HOME}/.claude/"
for state_dir in .codex .infinite-canvas; do
  if [ -d "${SOURCE_HOME}/${state_dir}" ]; then
    rsync -a "${SOURCE_HOME}/${state_dir}/" "${AGENT_HOME}/${state_dir}/"
  fi
done

chown -R "${AGENT_USER}:${AGENT_GROUP}" "${AGENT_HOME}"
find "${AGENT_HOME}" -type d -exec chmod 700 {} +
