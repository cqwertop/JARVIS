@echo off
rem Starts JARVIS. Uses your Claude plan through Claude Code unless ANTHROPIC_API_KEY is set.
rem Extra options are passed through, e.g.  start_jarvis.bat --text   or   start_jarvis.bat --mic 2
cd /d "%~dp0"
".venv\Scripts\python.exe" main.py %*
pause
