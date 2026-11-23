#!/usr/bin/env bash
# Universal Cinemas Finance - try it on a Mac or Linux computer (demo data, no database server needed).
#   chmod +x start_demo.sh && ./start_demo.sh
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
command -v "$PY" >/dev/null || { echo "Python 3.11+ is required (https://www.python.org/downloads/)"; exit 1; }
[ -d .venv ] || "$PY" -m venv .venv
. .venv/bin/activate
python -m pip install -q --disable-pip-version-check -r requirements.txt
if [ ! -f .env ]; then
  printf 'UCF_DATABASE_URL=sqlite:///./ucfin_demo.db\nUCF_ADMIN_PASSWORD=Admin@2026pass\n' > .env
fi
if [ ! -f .demo_loaded ]; then
  echo "Creating the demo database (about one minute)..."
  python -m scripts.seed --demo --create-schema
  python -m scripts.load_demo_data
  echo done > .demo_loaded
fi
echo
echo " Universal Cinemas Finance: http://localhost:8000"
echo " Sign in as  cfo / Demo@2026pass   (admin password: Admin@2026pass)"
echo " Phones / tablets on the same Wi-Fi: http://<this computer's IP>:8000"
echo " Press Ctrl+C to stop."
echo
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
