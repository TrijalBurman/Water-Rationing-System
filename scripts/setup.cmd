@echo off
setlocal
where python >nul 2>nul
if errorlevel 1 (
    py -3 "%~dp0manage.py" setup %*
) else (
    python "%~dp0manage.py" setup %*
)
exit /b %errorlevel%
