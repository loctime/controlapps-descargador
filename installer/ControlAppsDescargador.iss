#define MyAppName "ControlApps Descargador"
#define MyAppVersion "2.3.2"
#define MyAppPublisher "ControlApps"
#define MyAppExeName "ControlApps Descargador.exe"
#define MyHostExeName "ControlApps Descargador Host.exe"

[Setup]
AppId={{B5A49EE7-6DC8-429A-AFB7-07348CD1E6B6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\ControlApps\Descargador
DefaultGroupName=ControlApps
UninstallDisplayName={#MyAppName}
OutputDir=..\release
OutputBaseFilename=ControlApps-Descargador-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\dist\ControlApps Descargador\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\ControlApps Descargador Host\*"; DestDir: "{app}\host"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ControlApps\Descargador"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\ControlApps Descargador"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\host\{#MyHostExeName}"; Parameters: "--register"; Flags: runhidden
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir ControlApps Descargador"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\host\{#MyHostExeName}"; Parameters: "--unregister"; Flags: runhidden; RunOnceId: "QuitarHostNavegador"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\host"
