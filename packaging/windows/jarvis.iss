; JARVIS Windows installer (Inno Setup 6).
; Build:  packaging\build_windows.ps1   (runs PyInstaller first, then this script)
; Produces dist\JARVIS-Setup-<version>.exe
;
; - Installs for the current user only by default (no administrator password needed).
; - Updating installs over the old version; personal data in %LOCALAPPDATA%\JARVIS is never touched.
; - Uninstalling asks whether to also delete personal data (default: keep it).

#define AppName "JARVIS"
#ifndef AppVersion
  #define AppVersion "0.9.0"
#endif
#define AppExe "JARVIS.exe"
#define Root "..\.."

[Setup]
AppId={{62F5950B-0683-4A54-B6BD-E968E22098C7}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=JARVIS Project
AppComments=Your personal voice assistant
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#Root}\dist
OutputBaseFilename=JARVIS-Setup-{#AppVersion}
SetupIconFile={#Root}\packaging\assets\jarvis.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardSizePercent=110
WizardImageFile={#Root}\packaging\assets\wizard-large.bmp
WizardSmallImageFile={#Root}\packaging\assets\wizard-small.bmp
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; Ask a running JARVIS to close before files are replaced (same mutex name main.py uses).
#ifndef TestBuild
AppMutex=Local\JARVIS_voice_assistant
#endif
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nJARVIS is a personal assistant you can talk to. After installing, a short setup guide helps you choose its AI, test your microphone and pick a voice.%n%nIt's best to close other programs before continuing.
FinishedLabel=JARVIS is installed.%n%nWhen it opens, a short setup guide will walk you through the rest. It takes about 3 minutes.

[Tasks]
Name: "desktopicon"; Description: "Put a JARVIS shortcut on my desktop"; GroupDescription: "Shortcuts:"
Name: "startatlogin"; Description: "Start JARVIS automatically when I log in"; GroupDescription: "Starting JARVIS:"; Flags: unchecked

[InstallDelete]
; Remove the previous version's program files so no stale parts are left behind (personal data lives elsewhere).
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Root}\dist\JARVIS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\JARVIS"; Filename: "{app}\{#AppExe}"; Comment: "Start JARVIS"
Name: "{group}\JARVIS Settings"; Filename: "{app}\{#AppExe}"; Parameters: "--setup"; Comment: "Change JARVIS's AI, voice and microphone"
Name: "{group}\Uninstall JARVIS"; Filename: "{uninstallexe}"
Name: "{autodesktop}\JARVIS"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "JARVIS"; ValueData: """{app}\{#AppExe}"""; Tasks: startatlogin; Flags: uninsdeletevalue
; Always clean up the start-at-login entry on uninstall, even if it was turned on later from JARVIS's own settings.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "JARVIS"; Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open JARVIS now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "--remove-user-data"; Check: WantsDataRemoved; RunOnceId: "RemoveUserData"; Flags: runhidden waituntilterminated

[Code]
var
  RemoveData: Boolean;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  RemoveData := False;
  if UninstallSilent() then
    Exit;  { silent uninstalls (and updates) always keep personal data }
  RemoveData := MsgBox('Do you also want to delete your personal JARVIS data?' + #13#10 + #13#10 +
    'This includes what JARVIS remembers about you, your tasks, reminders, notes, settings and saved API keys.' + #13#10 + #13#10 +
    'Choose No to keep them (for example, if you plan to install JARVIS again).',
    mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  Result := True;
end;

function WantsDataRemoved(): Boolean;
begin
  Result := RemoveData;
end;
