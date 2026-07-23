@echo off
REM ============================================================
REM  SEO Audit Pro - launcher
REM ============================================================
title SEO Audit Pro
cd /d "%~dp0"
py seo_audit_gui.py 2>nul
if errorlevel 1 (
    python seo_audit_gui.py
    if errorlevel 1 (
        echo.
        echo  Could not start. Run setup_windows.bat first.
        pause
    )
)
