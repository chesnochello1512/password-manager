@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================
echo   Password Manager - сборка Windows EXE
echo ============================================
echo.

echo [1/5] Проверка Python...
set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.10 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3.10"
)
if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)
if not defined PYTHON_CMD goto no_python
%PYTHON_CMD% --version
if errorlevel 1 goto failed

echo [2/5] Виртуальное окружение...
if not exist ".venv\Scripts\python.exe" (
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto failed
)
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto failed

echo [3/5] Установка зависимостей...
python -m pip install --disable-pip-version-check --upgrade pip
if errorlevel 1 goto failed
python -m pip install --disable-pip-version-check -r requirements-dev.txt
if errorlevel 1 goto failed

if defined SKIP_TESTS goto build
echo [4/5] Автоматические тесты...
set QT_QPA_PLATFORM=offscreen
python -m pytest -q
if errorlevel 1 (
    set QT_QPA_PLATFORM=
    goto tests_failed
)
set QT_QPA_PLATFORM=

:build
echo [5/5] Сборка EXE через PyInstaller...
python -m PyInstaller --noconfirm --clean password_manager.spec
if errorlevel 1 goto failed
if not exist "dist\PasswordManager.exe" goto failed

echo.
echo ============================================
echo   Готово!
echo   EXE: %CD%\dist\PasswordManager.exe
echo ============================================
echo.
if not defined CI pause
exit /b 0

:no_python
echo.
echo ОШИБКА: Python 3.10-3.13 не найден.
echo Установите Python 3.10.8 с https://www.python.org/downloads/
echo и включите опцию "Add python.exe to PATH".
goto end_error

:tests_failed
echo.
echo ОШИБКА: автоматические тесты не прошли. Сборка остановлена.
goto end_error

:failed
echo.
echo ОШИБКА: сборка не завершена. Проверьте сообщения выше.
goto end_error

:end_error
if not defined CI pause
exit /b 1
