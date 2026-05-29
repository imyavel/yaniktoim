@echo off
REM yaniktoim-cms — local editor launcher
REM Usage: double-click or `cms.bat`
cd /d "%~dp0"
echo Starting yaniktoim-cms editor on http://localhost:8765/
start "" "http://localhost:8765/"
python -X utf8 cms\server.py
