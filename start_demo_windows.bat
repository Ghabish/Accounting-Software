@echo off
rem  Universal Cinemas Finance - try it on a Windows PC (demo data, no database server needed).
rem  Double-click this file. First run installs everything (a few minutes), then opens the browser.
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python 3.12 is required. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and run this file again.
  pause
  exit /b 1
)
if not exist .venv (
  echo Creating Python environment...
  py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing / checking components...
python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 ( echo Installation failed - check the internet connection. & pause & exit /b 1 )
if not exist .env (
  echo UCF_DATABASE_URL=sqlite:///./ucfin_demo.db> .env
  echo UCF_ADMIN_PASSWORD=Admin@2026pass>> .env
)
if not exist .demo_loaded (
  echo Creating the demo database ^(about one minute^)...
  python -m scripts.seed --demo --create-schema
  python -m scripts.load_demo_data
  echo done> .demo_loaded
)
echo.
echo  Universal Cinemas Finance is starting at http://localhost:8000
echo  Sign in as  cfo  /  Demo@2026pass   (admin password: Admin@2026pass)
echo  Phones / tablets on the same Wi-Fi: http://THIS-PC-IP:8000  (run "ipconfig" to see the IP)
echo  Close this window to stop the system.
echo.
start "" http://localhost:8000
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
