# VM Staging Deployment

目标：VM staging 与正式上线版本保持同一运行形态。两者都使用 Linux、PostgreSQL、Redis/RQ、Gunicorn、Nginx HTTPS、systemd 和 `HUISHI_ENV=production`。区别只允许是数据库名、域名、密钥、API key 和业务数据。

当前 VM：

```text
VMware VM IP: 192.168.13.129
VM network: NAT
Domains for browser testing: huishi.local, canvas.huishi.local
```

## Naming

```text
Linux user: huishi
Code: /opt/huishi
Uploads: /var/lib/huishi/uploads
Logs: /var/log/huishi
Backups: /var/backups/huishi
PostgreSQL user: huishi
VM database: huishi_staging
Production database: huishi_prod
Redis namespace: huishi
Web service: huishi.service
Worker service: huishi-worker@.service
```

## Host Preparation

On Windows, add this to `C:\Windows\System32\drivers\etc\hosts` as Administrator:

```text
192.168.13.129 huishi.local
192.168.13.129 canvas.huishi.local
```

The VM must run SSH before Codex can deploy into it:

```bash
sudo apt update
sudo apt install -y openssh-server
sudo systemctl enable --now ssh
```

## VM Bootstrap

Install server dependencies:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip postgresql postgresql-contrib redis-server nginx openssl
sudo systemctl enable --now postgresql redis-server
```

Create the Linux user and directories:

```bash
sudo adduser --system --group --home /opt/huishi --shell /usr/sbin/nologin huishi
sudo mkdir -p /opt/huishi /var/lib/huishi/uploads /var/log/huishi /var/backups/huishi /etc/ssl/huishi
sudo chown -R huishi:huishi /opt/huishi /var/lib/huishi /var/log/huishi /var/backups/huishi
```

Create PostgreSQL staging database:

```bash
sudo -u postgres createuser huishi
sudo -u postgres createdb -O huishi huishi_staging
sudo -u postgres psql -c "ALTER USER huishi WITH PASSWORD 'REPLACE_WITH_STRONG_DB_PASSWORD';"
```

Generate a local TLS certificate for `huishi.local`:

```bash
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /etc/ssl/huishi/huishi.local.key \
  -out /etc/ssl/huishi/huishi.local.crt \
  -subj "/CN=huishi.local" \
  -addext "subjectAltName=DNS:huishi.local,DNS:canvas.huishi.local,IP:192.168.13.129"
sudo chmod 600 /etc/ssl/huishi/huishi.local.key
```

## App Deployment

Copy the repository contents to `/opt/huishi`, then:

```bash
cd /opt/huishi
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

Create `/opt/huishi/.env` from `deploy/env.vm-staging.example`, replace all placeholders, then:

```bash
sudo chown huishi:huishi /opt/huishi/.env
sudo chmod 600 /opt/huishi/.env
```

Generate `HUISHI_ENCRYPTION_KEY`:

```bash
/opt/huishi/.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Install Bun and build the canvas frontend:

```bash
sudo -u huishi bash -lc 'curl -fsSL https://bun.sh/install | bash'
cd /opt/huishi/infinite-canvas/web
sudo -u huishi env CANVAS_PARENT_ORIGINS=https://huishi.local /opt/huishi/.bun/bin/bun install --frozen-lockfile
sudo -u huishi env CANVAS_PARENT_ORIGINS=https://huishi.local /opt/huishi/.bun/bin/bun run build
```

Install service files:

```bash
sudo cp /opt/huishi/deploy/huishi.service /etc/systemd/system/huishi.service
sudo cp /opt/huishi/deploy/huishi-worker@.service /etc/systemd/system/huishi-worker@.service
sudo cp /opt/huishi/deploy/huishi-canvas.service /etc/systemd/system/huishi-canvas.service
sudo cp /opt/huishi/deploy/nginx-huishi.local.conf /etc/nginx/sites-available/huishi
sudo ln -sf /etc/nginx/sites-available/huishi /etc/nginx/sites-enabled/huishi
sudo nginx -t
sudo systemctl daemon-reload
```

## Verification Gate

Run database smoke twice:

```bash
cd /opt/huishi
sudo -u huishi env $(grep -v '^#' .env | xargs) ./.venv/bin/python tools/db_smoke.py
sudo -u huishi env $(grep -v '^#' .env | xargs) ./.venv/bin/python tools/db_smoke.py
```

Run tests:

```bash
sudo -u huishi env $(grep -v '^#' .env | xargs) ./.venv/bin/python -m pytest -q
```

Start services:

```bash
sudo systemctl enable --now huishi
sudo systemctl enable --now huishi-canvas
for i in $(seq 1 4); do sudo systemctl enable --now huishi-worker@$i; done
sudo systemctl reload nginx
```

Check runtime:

```bash
systemctl status huishi --no-pager
systemctl status huishi-canvas --no-pager
systemctl status huishi-worker@1 --no-pager
curl -k -I https://huishi.local/
curl -k -I https://canvas.huishi.local/canvas
redis-cli ping
redis-cli llen rq:queue:huishi-generation
```

Manual smoke:

- Admin login through `https://huishi.local`
- Configure image provider and text/agent provider
- User generation
- Canvas generation
- Invite create/redeem
- Points ledger
- `flask --app wsgi:app storage-sweep` dry-run

## Backup Gate

PostgreSQL backup must use `pg_dump`, not SQLite `.backup`:

```bash
sudo -u postgres pg_dump -Fc huishi_staging > /var/backups/huishi/huishi_staging-$(date +%F-%H%M%S).dump
```

VM staging is not production approval. Production is approved only after the same gate passes on the real Ubuntu server against `huishi_prod`.
