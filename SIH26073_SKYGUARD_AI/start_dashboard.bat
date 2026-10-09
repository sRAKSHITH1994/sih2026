@echo off
setlocal
cd /d "%~dp0"
set "VENV_DIR=.venv"
if not exist "%VENV_DIR%\Scripts\python.exe" if exist "..\.venv\Scripts\python.exe" set "VENV_DIR=..\.venv"
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo Creating Python environment once...
  python -m venv .venv || goto :failed
  set "VENV_DIR=.venv"
)
if not exist "%VENV_DIR%\.sih26073_requirements_v5" (
  echo Installing dashboard requirements once...
  "%VENV_DIR%\Scripts\python.exe" -m pip install -r backend\requirements.txt || goto :failed
  type nul > "%VENV_DIR%\.sih26073_requirements_v5"
)
echo.
echo SIH26073 dashboard is starting...
echo Open http://127.0.0.1:8000 in your browser.
echo Keep this window open. Press Ctrl+C only when you want to stop.
"%VENV_DIR%\Scripts\python.exe" -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
goto :eof
:failed
echo.
echo Setup failed. Read START_HERE_WINDOWS.md, then run this file again.
pause
exit /b 1
