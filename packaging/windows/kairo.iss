; KAIRO Windows installer (Inno Setup 6).
; Build:  packaging\build_windows.ps1   (runs PyInstaller first, then this script)
; Produces dist\KAIRO-Setup-<version>.exe
;
; - Installs for the current user only by default (no administrator password needed).
; - Updating installs over the old version; personal data in %LOCALAPPDATA%\KAIRO is never touched.
; - Uninstalling asks whether to also delete personal data (default: keep it).

#define AppName "KAIRO"
#ifndef AppVersion
  #define AppVersion "0.9.1"
#endif
#define AppExe "KAIRO.exe"
#define Root "..\.."

[Setup]
AppId={{62F5950B-0683-4A54-B6BD-E968E22098C7}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=KAIRO Project
AppComments=Your personal voice assistant
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; This app used to be called JARVIS (same AppId). Install to the new KAIRO folder instead of the old one;
; [InstallDelete] below removes the old JARVIS program folder and shortcuts.
UsePreviousAppDir=no
UsePreviousGroup=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#Root}\dist
OutputBaseFilename=KAIRO-Setup-{#AppVersion}
SetupIconFile={#Root}\packaging\assets\kairo.ico
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
; Ask a running KAIRO to close before files are replaced (same mutex name main.py uses; JARVIS = old name).
#ifndef TestBuild
AppMutex=Local\KAIRO_voice_assistant,Local\JARVIS_voice_assistant
#endif
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nKAIRO is a personal assistant you can talk to. After installing, a short setup guide helps you choose its AI, test your microphone and pick a voice.%n%nIt's best to close other programs before continuing.
FinishedLabel=KAIRO is installed.%n%nWhen it opens, a short setup guide will walk you through the rest. It takes about 3 minutes.

[Tasks]
Name: "desktopicon"; Description: "Put a KAIRO shortcut on my desktop"; GroupDescription: "Shortcuts:"
Name: "startatlogin"; Description: "Start KAIRO automatically when I log in"; GroupDescription: "Starting KAIRO:"; Flags: unchecked

[InstallDelete]
; Remove the previous version's program files so no stale parts are left behind (personal data lives elsewhere).
Type: filesandordirs; Name: "{app}\_internal"
; Leftovers from when this app was called JARVIS (personal data is moved over by KAIRO itself).
Type: filesandordirs; Name: "{autopf}\JARVIS"
Type: filesandordirs; Name: "{autoprograms}\JARVIS"
Type: files; Name: "{autodesktop}\JARVIS.lnk"

[Files]
Source: "{#Root}\dist\KAIRO\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\KAIRO"; Filename: "{app}\{#AppExe}"; Comment: "Start KAIRO"
Name: "{group}\KAIRO Settings"; Filename: "{app}\{#AppExe}"; Parameters: "--setup"; Comment: "Change KAIRO's AI, voice and microphone"
Name: "{group}\Uninstall KAIRO"; Filename: "{uninstallexe}"
Name: "{autodesktop}\KAIRO"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KAIRO"; ValueData: """{app}\{#AppExe}"""; Tasks: startatlogin; Flags: uninsdeletevalue
; Always clean up the start-at-login entry on uninstall, even if it was turned on later from KAIRO's own settings.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "KAIRO"; Flags: dontcreatekey uninsdeletevalue
; Upgrading from JARVIS: keep start-at-login on if it was on, and remove the old JARVIS entry.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KAIRO"; ValueData: """{app}\{#AppExe}"""; Check: OldStartAtLogin; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "JARVIS"; Flags: deletevalue dontcreatekey

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open KAIRO now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExe}"; Parameters: "--remove-user-data"; Check: WantsDataRemoved; RunOnceId: "RemoveUserData"; Flags: runhidden waituntilterminated

[Code]
var
  RemoveData: Boolean;

function OldStartAtLogin(): Boolean;
begin
  Result := RegValueExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'JARVIS');
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  RemoveData := False;
  if UninstallSilent() then
    Exit;  { silent uninstalls (and updates) always keep personal data }
  RemoveData := MsgBox('Do you also want to delete your personal KAIRO data?' + #13#10 + #13#10 +
    'This includes what KAIRO remembers about you, your tasks, reminders, notes, settings and saved API keys.' + #13#10 + #13#10 +
    'Choose No to keep them (for example, if you plan to install KAIRO again).',
    mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES;
  Result := True;
end;

function WantsDataRemoved(): Boolean;
begin
  Result := RemoveData;
end;
