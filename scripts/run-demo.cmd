@echo off
setlocal
where python >nul 2>nul
if errorlevel 1 (
    py -3 "%~dp0manage.py" demo %*
) else (
    python "%~dp0manage.py" demo %*
)
exit /b %errorlevel%
