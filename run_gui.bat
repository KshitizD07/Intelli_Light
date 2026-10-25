@echo off
cd /d "%~dp0"
title Sentinel + Intelli-Light Unified Dual-View SUMO Demonstration
echo ======================================================================
echo  SENTINEL + INTELLI-LIGHT UNIFIED DUAL-VIEW SUMO DEMO
echo ======================================================================
echo  1. View #0: Global Intelli-Light Traffic Flow Overview
echo  2. View #1: Sentinel Tactical Surveillance Camera
echo.
echo  CONTROLS:
echo  - Press [SPACE] or [R] in this window anytime to DEPLOY RED-WALL!
echo  - Suspect will brake behind civilian queue and be apprehended (Option A).
echo  - Signals will turn green and normal traffic flow will resume!
echo ======================================================================
echo.
".\venv\Scripts\python.exe" main.py sentinel-gui --delay 180
pause
