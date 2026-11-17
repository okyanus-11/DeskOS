#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "DeskOS"
#define MyAppPublisher "Okyanus Bora Sevik"
#define MyAppExeName "DeskOS.exe"

[Setup]
AppId={{B7F1E2D9-5C64-4C3B-9A81-5A4F7D8C2E10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=..\assets\images\deskos.ico
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=DeskOS-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\DeskOS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\DeskOS"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall DeskOS"; Filename: "{uninstallexe}"
Name: "{autodesktop}\DeskOS"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch DeskOS"; Flags: postinstall nowait skipifsilent
