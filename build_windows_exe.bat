@echo off
REM ============================================================
REM  Build SEO Audit Pro into a standalone .exe
REM ============================================================
title SEO Audit Pro - Build EXE
cd /d "%~dp0"
echo Installing build + runtime dependencies...
py -m pip install -r requirements.txt pyinstaller 2>nul || python -m pip install -r requirements.txt pyinstaller
echo.
echo Building the executable (this can take a couple of minutes)...
py build_exe.py 2>nul || python build_exe.py
echo.
echo If it succeeded, your .exe is in the dist folder.
pause
