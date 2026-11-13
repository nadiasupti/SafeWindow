@echo off
REM SafeWindow admin panel: write, approve, send and cancel village alerts. Runs only on this computer.
REM The Firebase Admin key stays outside the repository. Change the path below if yours is elsewhere.
cd /d "%~dp0"
if "%GOOGLE_APPLICATION_CREDENTIALS%"=="" set GOOGLE_APPLICATION_CREDENTIALS=E:\keys\safewindow-admin.json
REM Earth Engine automation account, for the monitoring tab's "check now" button (optional)
if "%EE_SERVICE_ACCOUNT_KEY%"=="" if exist E:\keys\safewindow-ee.json set EE_SERVICE_ACCOUNT_KEY=E:\keys\safewindow-ee.json
if "%EE_PROJECT%"=="" set EE_PROJECT=safewindow-2026
if not exist "%GOOGLE_APPLICATION_CREDENTIALS%" (
    echo Admin key not found: %GOOGLE_APPLICATION_CREDENTIALS%
    echo Put the Firebase Admin key there, or set GOOGLE_APPLICATION_CREDENTIALS to its path.
    pause
    exit /b 1
)
if not exist "pwa\public\data\index.json" (
    echo Building the app data first...
    .venv\Scripts\python.exe scripts\build_pwa.py
)
echo Opening the admin panel at http://127.0.0.1:8502  (close this window to stop)
.venv\Scripts\python.exe -m streamlit run app\admin_app.py --server.address 127.0.0.1 --server.port 8502
pause
