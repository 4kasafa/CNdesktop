; Installer CNdesktop (Inno Setup 6). Satu file Setup untuk PC kasir:
; EXE -> Program Files, autostart semua user, firewall TCP 8765, uninstaller.
#define MyAppName "CNdesktop"
#define MyAppVersion "1.0.0"
#define MyAppExe "CNdesktop.exe"

[Setup]
AppId={{94E2D2C6-8AE5-47D5-9E4D-CB11B0ACA5F2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
OutputDir=..\dist
OutputBaseFilename=Setup_{#MyAppName}_{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
DisableProgramGroupPage=yes
UninstallDisplayName={#MyAppName}
CloseApplications=yes

[Files]
Source: "..\dist\{#MyAppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{commonstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"

[Run]
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""{#MyAppName}"" dir=in action=allow program=""{app}\{#MyAppExe}"" protocol=TCP localport=8765 profile=private"; Flags: runhidden; StatusMsg: "Membuka port 8765 (HP polling)..."

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""{#MyAppName}"""; Flags: runhidden; RunOnceId: "DelFwRule"
