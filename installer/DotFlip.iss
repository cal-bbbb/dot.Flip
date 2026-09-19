; Inno Setup script. Build with tools\build_release.ps1 (which runs the earlier steps first).
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{5E0B3C1A-7D42-4F96-8A1E-2C9D6B4F7A30}
AppName=dot.Flip
AppVersion={#AppVersion}
AppPublisher=dot.Flip
DefaultDirName={autopf}\dot.Flip
DefaultGroupName=dot.Flip
UninstallDisplayIcon={app}\DotFlip.exe
OutputDir=..\dist
OutputBaseFilename=DotFlip-Setup-{#AppVersion}
SetupIconFile=..\assets\DotFlip.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
; Admin is needed only to trust the package's signing certificate (Windows 11 menu). The
; per-user steps below run as the user who started setup (runasoriginaluser).
PrivilegesRequired=admin
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked
Name: "contextmenu"; Description: "Add ""Convert to"" to the right-click menu (including the Windows 11 menu)"

[Files]
Source: "..\dist\DotFlip\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Icons]
Name: "{group}\dot.Flip"; Filename: "{app}\DotFlip.exe"
Name: "{autodesktop}\dot.Flip"; Filename: "{app}\DotFlip.exe"; Tasks: desktopicon

[Run]
; Classic (Windows 10 / "Show more options") menu entries, per user.
Filename: "{app}\DotFlip.exe"; Parameters: "--register"; Flags: runasoriginaluser runhidden; Tasks: contextmenu; StatusMsg: "Adding right-click menu..."
; Windows 11 top-level menu: trust our signing certificate, then register the sparse package for the user.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Import-Certificate -FilePath '{app}\DotFlip.cer' -CertStoreLocation Cert:\LocalMachine\TrustedPeople | Out-Null"""; Flags: runhidden; Tasks: contextmenu; Check: IsWindows11; StatusMsg: "Trusting dot.Flip package..."
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Add-AppxPackage -Path '{app}\DotFlip.msix' -ExternalLocation '{app}'"""; Flags: runasoriginaluser runhidden; Tasks: contextmenu; Check: IsWindows11; StatusMsg: "Registering Windows 11 menu..."
Filename: "{app}\DotFlip.exe"; Description: "Open dot.Flip"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-AppxPackage -Name DotFlip.ContextMenu | Remove-AppxPackage"""; Flags: runhidden; RunOnceId: "RemoveSparsePackage"
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Get-ChildItem Cert:\LocalMachine\TrustedPeople | Where-Object Subject -eq 'CN=DotFlip' | Remove-Item"""; Flags: runhidden; RunOnceId: "RemoveCert"
Filename: "{app}\DotFlip.exe"; Parameters: "--unregister"; Flags: runhidden; RunOnceId: "RemoveClassicMenu"

[Code]
function IsWindows11: Boolean;
var
  V: TWindowsVersion;
begin
  GetWindowsVersionEx(V);
  Result := (V.Major = 10) and (V.Build >= 22000);
end;
