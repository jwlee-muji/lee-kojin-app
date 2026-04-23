; LEE電力モニター — Inno Setup インストールスクリプト
; バージョンはビルド時に /DMyAppVersion=x.y.z で注入する

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

#define MyAppName      "LEE電力モニター"
#define MyAppExeName   "LEE.exe"
#define MyAppPublisher "Shirokumapower"
#define MyAppURL       "https://github.com/jwlee-muji/lee-kojin-app"

[Setup]
AppId={{C4F2A8B1-3D7E-4A9C-B5F0-8E6D2C1A7F3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases

; ユーザープロファイルへのインストール (管理者権限不要)
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest

; 出力
OutputDir=dist\installer
OutputBaseFilename=LEE_Setup
SetupIconFile=img\icon.ico

; 圧縮
Compression=lzma2
SolidCompression=yes

; UI
WizardStyle=modern
WizardResizable=yes

; アップデート時の挙動: 実行中アプリを閉じて再インストール後に再起動
CloseApplications=yes
RestartApplications=yes

; アンインストール
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成"; GroupDescription: "追加タスク:"

[Files]
Source: "dist\LEE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: ".env"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\{#MyAppName}";   Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} を起動する"; Flags: nowait postinstall skipifsilent
