@echo off
REM ============================================================
REM  Збірка QABench у один .exe за допомогою PyInstaller (Windows)
REM ============================================================
setlocal

echo [1/3] Встановлення залежностей...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/3] Очищення попередніх збірок...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist QABench.spec del /q QABench.spec

echo [3/3] Збірка .exe...
pyinstaller --onefile --noconsole --name QABench ^
  --collect-all PySide6 ^
  --hidden-import=core ^
  --hidden-import=providers ^
  --hidden-import=ui ^
  main.py
if errorlevel 1 goto :error

echo.
echo ГОТОВО. Виконуваний файл: dist\QABench.exe
goto :eof

:error
echo.
echo ПОМИЛКА збірки. Перевірте повідомлення вище.
exit /b 1
