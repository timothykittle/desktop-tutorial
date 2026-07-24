@echo off
REM ============================================================
REM  SEO Audit Pro - one-time Windows setup
REM  Installs the required Python packages.
REM ============================================================
title SEO Audit Pro - Setup
echo.
echo  Checking for Python...
py --version >nul 2>&1
if errorlevel 1 (
    python --version >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  Python is not installed.
        echo  Download it from https://www.python.org/downloads/
        echo  IMPORTANT: tick "Add python.exe to PATH" during install,
        echo  then run this setup again.
        echo.
        pause
        exit /b 1
    )
    set PYCMD=python
) else (
    set PYCMD=py
)
echo  Installing required packages (requests, beautifulsoup4)...
%PYCMD% -m pip install --upgrade pip >nul
%PYCMD% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo  Package install failed - check your internet connection.
    pause
    exit /b 1
)
echo.
echo  Installing optional extras (drag-and-drop + AI copy)...
echo  (These are optional - the app still works if they fail.)
%PYCMD% -m pip install tkinterdnd2 anthropic
echo.
echo.
echo  Setup complete! Double-click run_windows.bat to launch SEO Audit Pro.
echo.
pause
