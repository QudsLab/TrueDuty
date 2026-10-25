; Inno Setup script for the Windows installer. CI passes /DAppVersion=... /DSrcExe=... /DOutDir=...
#ifndef AppVersion
  #define AppVersion "2.0.0"
#endif
[Setup]
AppId={{6E0B7C1E-3D52-4F3B-9A44-7A1E2D5C9B10}
AppName=TrueDuty
AppVersion={#AppVersion}
AppVerName=TrueDuty {#AppVersion}
AppPublisher=QudsLab
AppPublisherURL=https://github.com/QudsLab/TrueDuty
AppSupportURL=https://github.com/QudsLab/TrueDuty/issues
DefaultDirName={autopf}\TrueDuty
DefaultGroupName=TrueDuty
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutDir}
OutputBaseFilename=TrueDuty-Setup-{#AppVersion}-windows-x64
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\TrueDuty.exe
LicenseFile=..\..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Files]
Source: "{#SrcExe}"; DestDir: "{app}"; DestName: "TrueDuty.exe"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\TrueDuty"; Filename: "{app}\TrueDuty.exe"
Name: "{autodesktop}\TrueDuty"; Filename: "{app}\TrueDuty.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "autostart"; Description: "Start TrueDuty when I sign in to Windows"; Flags: unchecked

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "TrueDuty"; ValueData: """{app}\TrueDuty.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\TrueDuty.exe"; Description: "Start TrueDuty now"; Flags: nowait postinstall skipifsilent
