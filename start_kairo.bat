@echo off
rem Starts KAIRO. Uses your Claude plan through Claude Code unless ANTHROPIC_API_KEY is set.
rem Extra options are passed through, e.g.  start_kairo.bat --text   or   start_kairo.bat --mic 2
cd /d "%~dp0"
".venv\Scripts\python.exe" main.py %*
pause
