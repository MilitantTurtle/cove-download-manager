; Inno Setup script for Cove Download Manager (Windows)
; Invoked from build-windows-wine.sh via:
;   iscc /DAppVersion=X.Y.Z /DSourceDir=<abs dist\cove-download-manager> \
;        /DOutputDir=<abs release> /DIconFile=<abs cove_icon.ico> installer.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\cove-download-manager"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif
#ifndef IconFile
  #define IconFile "..\cove_icon.ico"
#endif

[Setup]
AppId={{F5EE4E1A-6A6C-4E89-9F64-29B49D3B0F31}
AppName=Cove Download Manager
AppVersion={#AppVersion}
AppPublisher=Cove
AppPublisherURL=https://github.com/MilitantTurtle/cove-download-manager
AppSupportURL=https://github.com/MilitantTurtle/cove-download-manager/issues
AppUpdatesURL=https://github.com/MilitantTurtle/cove-download-manager/releases
DefaultDirName={autopf}\Cove Download Manager
DefaultGroupName=Cove Download Manager
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\cove-download-manager.exe
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Cove-Download-Manager-{#AppVersion}-Setup
SetupIconFile={#IconFile}
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Cove Download Manager"; Filename: "{app}\cove-download-manager.exe"
Name: "{group}\Uninstall Cove Download Manager"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Cove Download Manager"; Filename: "{app}\cove-download-manager.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\cove-download-manager.exe"; Description: "Launch Cove Download Manager"; Flags: nowait postinstall skipifsilent
