@echo off
REM reindex.bat - rebuild the Pagefind search index over docs/.
REM Run after adding/editing articles, BEFORE push.bat.
REM Optional: reindex.bat  (no args)
cd /d "%~dp0"

echo.
echo === Pagefind: wipe stale index, then rebuild over docs\ ===
REM WIPE FIRST: pagefind does NOT delete its old hashed files, they accumulate
REM (each corpus-wide re-render stacks a fresh ~352-file generation on top).
if exist docs\pagefind rmdir /s /q docs\pagefind
call pagefind --site docs

echo.
echo === Sitemap + robots.txt ===
python -X utf8 tools\build_sitemap.py

echo.
echo === Done. Now run push.bat to publish. ===
pause
