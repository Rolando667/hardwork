@echo off
REM ============================================================
REM  Збірка Telegram Agent Manager у самостійний .exe (Windows)
REM ============================================================
setlocal

echo [1/3] Створення/активація віртуального середовища...
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat

echo [2/3] Встановлення залежностей...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [3/3] Збірка exe через PyInstaller...
REM --windowed  -> без консольного вікна
REM --onefile   -> один exe
REM --add-data  -> кладемо стилі всередину (роздільник ; для Windows)
set ICON=
if exist app.ico set ICON=--icon=app.ico

pyinstaller --noconfirm --clean --onefile --windowed %ICON% ^
    --name "TelegramAgentManager" ^
    --add-data "ui/styles.qss;ui" ^
    --collect-all aiogram ^
    --collect-all anthropic ^
    --collect-submodules qasync ^
    main.py

echo.
echo Готово! Файл: dist\TelegramAgentManager.exe
endlocal
