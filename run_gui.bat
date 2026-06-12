@echo off
rem Game QA Companion 실행 — 작업 디렉토리를 repo 루트로 고정 (configs/sessions/library 위치)
cd /d "%~dp0"
start "" ".venv\Scripts\companion-gui.exe"
