@echo off
setlocal

py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto check_python

:use_py
py -3 "%~dp0cove_api.py" %*
exit /b %errorlevel%

:check_python
python -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 goto no_python

python "%~dp0cove_api.py" %*
exit /b %errorlevel%

:no_python
echo {"ok":false,"error":{"code":"python_not_found","message":"Python 3.10 or newer was not found by the Cove wrapper."}}
exit /b 2
