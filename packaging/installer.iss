; Inno Setup script for the Engineering Stamp Placer.
;
; Produces a single per-user installer (no administrator rights required) that
; installs the PyInstaller distribution and creates Start Menu / desktop
; shortcuts. Build the PyInstaller output first, then compile this script:
;
;     python -m PyInstaller packaging\EngineeringStampPlacer.spec --noconfirm --clean
;     iscc packaging\installer.iss
;
; The result is dist\EngineeringStampPlacer-Setup.exe.

#define MyAppName "Engineering Stamp Placer"
#define MyAppVersion "1.2.1"
#define MyAppPublisher "RnD-AS-02"
#define MyAppExeName "EngineeringStampPlacer.exe"

[Setup]
AppId={{8B5F1C2E-7E2A-4E8B-9C3D-1A2B3C4D5E6F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\EngineeringStampPlacer
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#SourcePath}\..\dist
OutputBaseFilename=EngineeringStampPlacer-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "{#SourcePath}\..\dist\EngineeringStampPlacer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
