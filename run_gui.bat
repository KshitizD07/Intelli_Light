@echo off
cd /d "%~dp0"
title Sentinel + Intelli-Light SUMO GUI Demo
echo ======================================================================
echo Launching Sentinel + Intelli-Light Real-Time Visual GUI Demo...
echo ======================================================================
".\venv\Scripts\python.exe" main.py sentinel-gui --delay 200 --intercept-step 35
pause
