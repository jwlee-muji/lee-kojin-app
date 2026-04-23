# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [
    ('app',           'app'),           # app/ ソースをそのまま同梱 (PYZ 解析漏れの fallback)
    ('app/ui/themes', 'app/ui/themes'),
    ('img',           'img'),
]
# service_account.json が存在する場合のみ _internal/ に同梱
# (CI では GitHub Secret から生成、開発環境では gitignore 対象のためスキップ)
if os.path.exists('service_account.json'):
    datas.append(('service_account.json', '.'))
binaries = []

# app パッケージ全体を明示的に収集
hiddenimports = collect_submodules('app')

hiddenimports += [
    'pyqtgraph', 'packaging.version', 'bs4',
    'sqlite3', 'smtplib', 'ssl', '_ssl',
    'email.mime.text', 'email.mime.multipart',
    'google.auth', 'google.auth.transport.requests',
    'google.oauth2.credentials', 'google.oauth2.service_account',
    'google_auth_oauthlib.flow', 'googleapiclient.discovery',
    'httplib2', 'uritemplate',
    'concurrent.futures', 'concurrent.futures._base', 'concurrent.futures.thread',
    'calendar', 'urllib.request', 'urllib.error',
]
tmp_ret = collect_all('yfinance')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('google_auth_oauthlib')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('googleapiclient')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('numpy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('requests')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LEE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['img\\icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='LEE',
)
