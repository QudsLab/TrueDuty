; Inno Setup script for the Windows installer. CI passes /DAppVersion=... /DSrcDir=<standalone folder> /DOutDir=... /DArch=x64|arm64
#ifndef Arch
  #define Arch "x64"
#endif
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
OutputBaseFilename=TrueDuty-Setup-{#AppVersion}-windows-{#Arch}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\TrueDuty.exe
LicenseFile=..\..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
#if Arch == "arm64"
ArchitecturesAllowed=arm64
ArchitecturesInstallIn64BitMode=arm64
#else
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#endif
VersionInfoVersion={#AppVersion}
VersionInfoCompany=QudsLab
VersionInfoDescription=TrueDuty installer
VersionInfoCopyright=Copyright (c) QudsLab. MIT License.
SignedUninstaller=no
CloseApplications=yes

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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
