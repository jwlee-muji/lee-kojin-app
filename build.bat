@echo off
chcp 65001 >nul
echo ===================================
echo LEE電力モニター - ビルドスクリプト
echo ===================================

pip install pyinstaller pyinstaller-hooks-contrib

pyinstaller ^
  --onefile ^
  --windowed ^
  --name "LEE電力モニター" ^
  --add-data "version.py;." ^
  main.py

echo.
echo ビルド完了！dist フォルダを確認してください。
pause
