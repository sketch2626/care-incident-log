; Inno Setup script for Care Incident Log. packaging\build.py runs it and passes the defines.
; Installs for the current user only (no admin prompt). Uninstalling never touches the
; log itself, which lives in %APPDATA%\CareIncidentLog.
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\Care Incident Log"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#define AppExe "Care Incident Log.exe"

[Setup]
AppId={{6C1B7E2A-4F0D-4B8E-9A61-3E2D5C7A9F14}
AppName=Care Incident Log
AppVersion={#AppVersion}
AppPublisher=Care Incident Log
DefaultDirName={autopf}\Care Incident Log
DefaultGroupName=Care Incident Log
PrivilegesRequired=lowest
DisableDirPage=yes
DisableProgramGroupPage=yes
WizardStyle=modern
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
OutputDir={#OutputDir}
OutputBaseFilename=CareIncidentLog-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[InstallDelete]
; Clear the previous version's program files on upgrade (data is elsewhere).
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Care Incident Log"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\Care Incident Log"; Filename: "{app}\{#AppExe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open Care Incident Log now"; Flags: nowait postinstall skipifsilent
