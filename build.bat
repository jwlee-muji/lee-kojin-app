@echo off
chcp 65001 >nul
echo ===================================
echo LEE電力モニター - ビルドスクリプト
echo ===================================

REM venv のアクティベート (依存ライブラリをvenv に統一)
call .venv\Scripts\activate.bat

REM __pycache__ を完全削除して古い .pyc キャッシュを排除
echo [1/4] __pycache__ を削除中...
for /d /r . %%d in (__pycache__) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)

REM 前回のビルド成果物を削除
echo [2/4] 前回のビルドを削除中...
rmdir /s /q build 2>nul
rmdir /s /q dist  2>nul
del /f /q "LEE電力モニター.spec" 2>nul

echo [3/4] PyInstaller をインストール中...
pip install pyinstaller pyinstaller-hooks-contrib -q

echo [3.5/4] リソース(QRC)をコンパイル中...
pyside6-rcc resources.qrc -o resources_rc.py

echo [4/4] ビルド開始...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "LEE電力モニター" ^
  --icon "img/icon.ico" ^
  --add-data "app/ui/themes;app/ui/themes" ^
  --collect-all yfinance ^
  --hidden-import "pandas" ^
  --hidden-import "pyqtgraph" ^
  --hidden-import "packaging.version" ^
  --hidden-import "sqlite3" ^
  --hidden-import "smtplib" ^
  --hidden-import "email.mime.text" ^
  --hidden-import "email.mime.multipart" ^
  main.py

echo.
echo ビルド完了！dist フォルダを確認してください。
pause
