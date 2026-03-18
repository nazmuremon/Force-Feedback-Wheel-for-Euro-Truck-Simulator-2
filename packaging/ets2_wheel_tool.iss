#define MyAppName "ETS2 DIY FFB Wheel Tool"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "DIY ETS2 Wheel Project"
#define MyAppExeName "ETS2WheelTool.exe"

[Setup]
AppId={{EAA8FE95-6E01-48EA-B6C6-2B8C29E747A4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\ETS2WheelTool
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist_installer
OutputBaseFilename=ETS2WheelToolSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
Name: "vigemdriver"; Description: "Install virtual controller driver (ViGEmBus)"; GroupDescription: "Drivers:"; Flags: checkedonce

[Files]
Source: "..\dist\ETS2WheelTool\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "msiexec.exe"; Parameters: "/i ""{app}\_internal\vgamepad\win\vigem\install\x64\ViGEmBusSetup_x64.msi"" /passive /norestart"; Description: "Install virtual controller driver"; Flags: postinstall shellexec waituntilterminated skipifsilent; Tasks: vigemdriver; Check: Is64BitInstallMode
Filename: "msiexec.exe"; Parameters: "/i ""{app}\_internal\vgamepad\win\vigem\install\x86\ViGEmBusSetup_x86.msi"" /passive /norestart"; Description: "Install virtual controller driver"; Flags: postinstall shellexec waituntilterminated skipifsilent; Tasks: vigemdriver; Check: not Is64BitInstallMode
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
