@echo off
title J.A.R.V.I.S V3 - Dependency Setup
echo [SYSTEM] Downloading & Installing Multimodal Drivers...
cd d:\JARVIS_V3
pip install --upgrade pip
pip install -r requirements.txt
echo [SUCCESS] Environment ready! Launch start_jarvis.bat to begin.
pause
