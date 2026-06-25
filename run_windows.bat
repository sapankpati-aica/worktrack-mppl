@echo off
title WorkTrack Pro - MPPL Office
cd /d "%~dp0"
echo.
echo ============================================================
echo   WorkTrack Pro - starting local server
echo   Open http://127.0.0.1:5000 in your browser
echo   Login: admin@office.local / admin123
echo   Press Ctrl+C to stop
echo ============================================================
echo.
python app.py
pause
