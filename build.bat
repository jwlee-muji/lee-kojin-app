@echo off
chcp 65001 >nul
echo ===================================
echo LEE電力モニター - ビルドスクリプト
echo ===================================

REM venv のアクティベート
call .venv\Scripts\activate.bat

REM [1] __pycache__ を完全削除してキャッシュを排除
echo [1/5] __pycache__ を削除中...
for /d /r . %%d in (__pycache__) do (
    if exist "%%d" rmdir /s /q "%%d" 2>nul
)

REM [2] 前回のビルド成果物を完全削除
echo [2/5] 前回のビルドを削除中...
rmdir /s /q build 2>nul
rmdir /s /q dist  2>nul
del /f /q "LEE電力モニター.spec" 2>nul

REM [3] 依存関係を最新化
echo [3/5] ビルドツールを更新中...
pip install pyinstaller pyinstaller-hooks-contrib python-dotenv -q

REM [4] QRC リソースをコンパイル
echo [3.5/5] リソース(QRC)をコンパイル中...
pyside6-rcc resources.qrc -o resources_rc.py

REM [5] PyInstaller ビルド
echo [4/5] PyInstaller ビルド開始...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "LEE電力モニター" ^
  --icon "img/icon.ico" ^
  --add-data "app/ui/themes;app/ui/themes" ^
  --collect-all yfinance ^
  --collect-all google_auth_oauthlib ^
  --collect-all googleapiclient ^
  --collect-all numpy ^
  --collect-all requests ^
  --hidden-import "pyqtgraph" ^
  --hidden-import "packaging.version" ^
  --hidden-import "bs4" ^
  --hidden-import "sqlite3" ^
  --hidden-import "smtplib" ^
  --hidden-import "email.mime.text" ^
  --hidden-import "email.mime.multipart" ^
  --hidden-import "google.auth" ^
  --hidden-import "google.auth.transport.requests" ^
  --hidden-import "google.oauth2.credentials" ^
  --hidden-import "google.oauth2.service_account" ^
  --hidden-import "google_auth_oauthlib.flow" ^
  --hidden-import "googleapiclient.discovery" ^
  --hidden-import "httplib2" ^
  --hidden-import "uritemplate" ^
  main.py

if not exist "dist\LEE電力モニター.exe" (
    echo [ERROR] ビルドに失敗しました。
    pause
    exit /b 1
)

REM [6] SHA256 ハッシュを生成 (GitHub Release での整合性検証用)
echo [5/5] SHA256 ハッシュを生成中...
powershell -NoProfile -Command "(Get-FileHash 'dist\LEE電力モニター.exe' -Algorithm SHA256).Hash.ToLower()" > "dist\LEE電力モニター.sha256"
echo SHA256 ファイル: dist\LEE電力モニター.sha256

echo.
echo ===================================
echo ビルド完了！
echo   EXE : dist\LEE電力モニター.exe
echo   SHA : dist\LEE電力モニター.sha256
echo ===================================
echo GitHub Release には両ファイルをアップロードしてください。
pause
