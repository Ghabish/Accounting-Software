# Setup and deployment

The system is one web application: a Python (FastAPI) server that serves the API under `/api` and the
pre-built web front end (in `frontend/dist`) from the same address. Users open it in any modern browser on
desktop, laptop, tablet or phone; on phones and tablets it can be installed to the home screen (PWA).
PostgreSQL 16 holds all data. Node.js is **not** needed on the server — the front end is already built.

```
browser (any device) ──HTTPS──▶ reverse proxy (IIS / nginx / cloud LB, TLS)
                                     └──▶ uvicorn: backend.main:app  ──▶ PostgreSQL 16
                                              └── attachments folder (supporting documents)
```

## 1. Requirements
| Component | Version |
|---|---|
| Python | 3.11 – 3.13 |
| PostgreSQL | 14+ (tested on 16) |
| OS | Windows Server 2019+, Ubuntu 22.04+/RHEL 9, or any Docker host / cloud VM |
| Browser | Current Chrome, Edge, Safari, Firefox (desktop and mobile) |

## 2. Database
```sql
CREATE ROLE ucfin_app LOGIN PASSWORD 'choose-a-strong-password';
CREATE DATABASE ucfin OWNER ucfin_app ENCODING 'UTF8';
```

## 3. Install (Linux)
```bash
sudo mkdir -p /opt/ucfinance /var/lib/ucfin/attachments && cd /opt/ucfinance
# copy the project here, then:
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp configuration/.env.example .env      # edit: database URL, secret key, attachment folder
alembic upgrade head                    # creates tables, constraints and integrity triggers
UCF_ADMIN_PASSWORD='...' python -m scripts.seed   # chart of accounts, sites, cost centres, tax, roles, admin user
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 4 --proxy-headers
```
Run it as a service (systemd):
```ini
[Unit]
Description=Universal Cinemas Finance
After=network.target postgresql.service
[Service]
WorkingDirectory=/opt/ucfinance
EnvironmentFile=/opt/ucfinance/.env
ExecStart=/opt/ucfinance/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 4 --proxy-headers
User=ucfin
Restart=always
[Install]
WantedBy=multi-user.target
```
Put nginx (or any TLS proxy) in front: `proxy_pass http://127.0.0.1:8000; client_max_body_size 25m;`.

## 4. Install (Windows Server)
1. Install Python 3.12 (tick *Add to PATH*) and PostgreSQL 16 (or use an existing server).
2. Copy the project to `C:\UCFinance`, open PowerShell there:
   ```powershell
   py -3.12 -m venv .venv; .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item configuration\.env.example .env   # edit with Notepad
   alembic upgrade head
   $env:UCF_ADMIN_PASSWORD='...'; python -m scripts.seed
   ```
3. Run as a Windows service with NSSM (or the Task Scheduler "at startup"):
   `nssm install UCFinance C:\UCFinance\.venv\Scripts\uvicorn.exe "backend.main:app --host 127.0.0.1 --port 8000 --workers 4"`
   and set *AppDirectory* to `C:\UCFinance`.
4. Publish through IIS with *URL Rewrite + ARR* as a reverse proxy to `http://127.0.0.1:8000`, binding an HTTPS certificate.

## 5. Docker / cloud
```bash
cat > .env <<EOT
DB_PASSWORD=choose-a-strong-password
UCF_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
UCF_ADMIN_PASSWORD=choose-initial-admin-password
EOT
docker compose up -d --build        # runs migrations and seeding automatically
```
For a cloud deployment use a managed PostgreSQL (Azure Database for PostgreSQL, AWS RDS, Google Cloud SQL),
set `UCF_DATABASE_URL` accordingly, mount persistent storage for `UCF_ATTACHMENT_DIR`, and terminate TLS at the
load balancer.

## 6. First sign-in
Sign in as `admin` with the initial password (you are asked to change it). Then, under **Administration**:
create users, assign roles and sites, review approval limits and workflow settings, rename the sample bank
accounts and enter real account numbers, confirm the tax rates flagged *to confirm*, and load opening balances
(**Planning & close → Imports & opening balances**).

## 7. Demo / training environment
```bash
python -m scripts.seed --demo --create-schema   # [DEMO] suppliers, customers, films, screens, demo users
python -m scripts.load_demo_data                # synthetic box office, F&B, settlements, bills (Oct-Nov 2026)
```
Demo users: `cfo`, `fm`, `accountant`, `ap`, `ar`, `cashier.emp`, `manager.emp`, `auditor` (password printed by the
seed). Never load demo data into the production database.

## 8. Upgrades
Back up, replace the code, `pip install -r requirements.txt`, `alembic upgrade head`, restart the service.
To rebuild the front end after changing it: `cd frontend && npm ci && npm run build`.

## 9. Multiple devices and users
The application is multi-user: every device connects to the same server and database, so all users see the
same live ledger. Sessions are per browser (bearer token, 8 hours by default). The layout adapts to phone,
tablet and desktop widths; on phones use the ☰ menu. Install on a phone: open the site in the browser →
*Add to Home screen*. Financial data is never cached on the device (the service worker caches only the
application shell).
