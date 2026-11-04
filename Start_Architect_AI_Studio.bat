@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  set "PY=py"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.11+ is required. Install from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
  echo Preparing local Python environment...
  %PY% -m venv .venv || goto :fail
)
echo Checking project dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
echo.
echo Open http://127.0.0.1:8000 in your browser after the server starts.
echo Keep this window open while using the application.
echo.
".venv\Scripts\python.exe" app.py
exit /b %errorlevel%
:fail
echo Setup failed. Review the error above.
pause
exit /b 1
