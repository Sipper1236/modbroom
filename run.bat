@echo off
setlocal
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw -m modbroom %* & goto :eof)
where python  >nul 2>nul && (python -m modbroom %* & goto :eof)
echo Python 3.10+ not found. Install it from python.org (tick "Add to PATH").
pause
