@echo off
REM reindex.bat - rebuild the Pagefind search index over docs/.
REM Run after adding/editing articles, BEFORE push.bat.
REM Optional: reindex.bat  (no args)
cd /d "%~dp0"

echo.
echo === Pagefind: rebuilding search index over docs\ ===
call pagefind --site docs

echo.
echo === Sitemap + robots.txt ===
python -X utf8 tools\build_sitemap.py

echo.
echo === Done. Now run push.bat to publish. ===
pause
