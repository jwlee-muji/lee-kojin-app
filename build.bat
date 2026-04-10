@echo off
chcp 65001 >nul
echo ===================================
echo LEE電力モニター - ビルドスクリプト
echo ===================================

pip install pyinstaller pyinstaller-hooks-contrib

rmdir /s /q build 2>nul
rmdir /s /q dist  2>nul
del /f /q "LEE電力モニター.spec" 2>nul

pyinstaller ^
  --onefile ^
  --windowed ^
  --name "LEE電力モニター" ^
  --collect-all selenium ^
  --collect-all webdriver_manager ^
  --collect-all yfinance ^
  --hidden-import "pandas" ^
  --hidden-import "pyqtgraph" ^
  --hidden-import "packaging.version" ^
  --hidden-import "sqlite3" ^
  main.py

echo.
echo ビルド完了！dist フォルダを確認してください。
pause
