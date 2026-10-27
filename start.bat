@echo off
setlocal
cd /d "%~dp0"
title QE Connect

rem ---- find Python 3.10 or newer ----
set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo.
  echo  QE Connect needs Python 3.10 or newer.
  echo  Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
  echo  then run start.bat again.
  echo.
  pause
  exit /b 1
)

rem ---- private Python environment in .venv ----
if not exist ".venv\Scripts\python.exe" (
  echo Creating QE Connect's Python environment...
  %PY% -m venv .venv || goto :fail
)

rem ---- install or update components only when the lock file changes ----
rem Every package is pinned to an exact version and checked against its published hash.
set "LOCK=backend\requirements.lock"
findstr /i "postgresql" .env >nul 2>nul && set "LOCK=backend\requirements-postgres.lock"
fc /b "%LOCK%" .venv\installed.lock >nul 2>nul || (
  echo Installing QE Connect's components. The first run takes a minute or two...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --require-hashes -r "%LOCK%" || goto :fail
  copy /y "%LOCK%" .venv\installed.lock >nul
)

cd backend
"..\.venv\Scripts\python.exe" -m app --open %*
exit /b %errorlevel%

:fail
echo.
echo  Setup didn't finish. Check your internet connection (or proxy) and run start.bat again.
echo  If it keeps failing, delete the .venv folder and try once more.
echo.
pause
exit /b 1
