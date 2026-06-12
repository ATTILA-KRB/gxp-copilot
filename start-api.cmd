@echo off
title GxP Copilot - API (Ctrl+C pour arreter)
cd /d "%~dp0"
uv run uvicorn app.main:app --reload --port 8001
pause
