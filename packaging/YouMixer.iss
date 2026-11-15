; YouMixer's Windows installer (Inno Setup 6). It is built by packaging\build.py, which passes
; AppVersion, SourceDir (the folder PyInstaller produced) and OutputDir.
;
; It installs for the current user only (no administrator rights), asks for the language, how to
; open YouMixer and the optional keys, and writes the answers to %APPDATA%\YouMixer\config.json.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\YouMixer"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
; Never change AppId: it is how upgrades and the uninstaller recognise YouMixer
AppId={{8F3B1C52-6D7A-4E39-9B1F-2A5C7D0E4B66}
AppName=YouMixer
AppVersion={#AppVersion}
AppPublisher=Orteku
AppPublisherURL=https://github.com/Orteku/YouMixer
AppSupportURL=https://github.com/Orteku/YouMixer/issues
AppUpdatesURL=https://github.com/Orteku/YouMixer/releases
DefaultDirName={autopf}\YouMixer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=YouMixer-Setup-{#AppVersion}
SetupIconFile=..\build\icon.ico
UninstallDisplayIcon={app}\YouMixer.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
en.ModeTitle=How should YouMixer open?
en.ModeSub=You can change this later in Settings.
en.ModeIntro=YouMixer is a web page that runs on your PC. Choose where it opens:
en.ModeBrowser=In my browser (recommended)
en.ModeWindow=In its own window, without an address bar (needs Microsoft Edge or Google Chrome)
en.KeysTitle=Optional keys
en.KeysSub=YouMixer works fine without them.
en.KeysIntro=Two keys improve YouMixer a little. You don't need either of them: leave the fields empty and press Next to skip this step. You can add them later in Settings.
en.KeysLastfm=Last.fm key: helps find artists similar to the ones you like, for better discoveries.
en.KeysYoutube=YouTube Data API key: a backup for reading public playlists if the usual way fails.
en.KeysGetLastfm=Get a Last.fm key
en.KeysGetYoutube=How to get a YouTube key
en.KeysLastfmField=Last.fm key
en.KeysYoutubeField=YouTube Data API key
en.DeleteData=Do you also want to delete your YouMixer data (lists, history, what it learned and your settings)?%n%nThis cannot be undone.
en.AutoLaunch=Start YouMixer
es.ModeTitle=¿Cómo quieres que se abra YouMixer?
es.ModeSub=Puedes cambiarlo después en Ajustes.
es.ModeIntro=YouMixer es una página web que funciona en tu PC. Elige dónde se abre:
es.ModeBrowser=En mi navegador (recomendado)
es.ModeWindow=En su propia ventana, sin barra de direcciones (necesita Microsoft Edge o Google Chrome)
es.KeysTitle=Claves opcionales
es.KeysSub=YouMixer funciona bien sin ellas.
es.KeysIntro=Dos claves mejoran un poco YouMixer. No necesitas ninguna: deja los campos vacíos y pulsa Siguiente para omitir este paso. Puedes añadirlas después en Ajustes.
es.KeysLastfm=Clave de Last.fm: ayuda a encontrar artistas parecidos a los que te gustan, para descubrir mejor.
es.KeysYoutube=Clave de YouTube Data API: un respaldo para leer playlists públicas si la vía habitual falla.
es.KeysGetLastfm=Conseguir una clave de Last.fm
es.KeysGetYoutube=Cómo conseguir una clave de YouTube
es.KeysLastfmField=Clave de Last.fm
es.KeysYoutubeField=Clave de YouTube Data API
es.DeleteData=¿Quieres borrar también tus datos de YouMixer (listas, historial, lo aprendido y tus ajustes)?%n%nNo se puede deshacer.
es.AutoLaunch=Abrir YouMixer

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\YouMixer"; Filename: "{app}\YouMixer.exe"
Name: "{autodesktop}\YouMixer"; Filename: "{app}\YouMixer.exe"; Tasks: desktopicon

[Registry]
; The youmixer:// link: it is how the page's power key starts YouMixer when it is off
Root: HKCU; Subkey: "Software\Classes\youmixer"; ValueType: string; ValueData: "URL:YouMixer"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\youmixer"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\youmixer\shell\open\command"; ValueType: string; ValueData: """{app}\YouMixer.exe"" --no-browser ""%1"""

[Run]
Filename: "{app}\YouMixer.exe"; Description: "{cm:AutoLaunch}"; Flags: nowait postinstall skipifsilent

[Code]
var
  ModePage: TInputOptionWizardPage;
  KeysPage: TWizardPage;
  LastfmEdit, YoutubeEdit: TNewEdit;

function DataFolder: String;
begin
  Result := ExpandConstant('{userappdata}\YouMixer');
end;

function ConfigPath: String;
begin
  Result := DataFolder + '\config.json';
end;

// Turns off a YouMixer that is running, so its files can be replaced or removed
procedure QuitRunning(Folder: String);
var
  Exe: String;
  Code: Integer;
begin
  Exe := Folder + '\YouMixer.exe';
  if FileExists(Exe) then
    Exec(Exe, '--quit', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

procedure OpenLink(Url: String);
var
  Code: Integer;
begin
  ShellExec('open', Url, '', '', SW_SHOWNORMAL, ewNoWait, Code);
end;

procedure GetLastfmClick(Sender: TObject);
begin
  OpenLink('https://www.last.fm/api/account/create');
end;

procedure GetYoutubeClick(Sender: TObject);
begin
  OpenLink('https://developers.google.com/youtube/v3/getting-started');
end;

function AddText(Page: TWizardPage; Text: String; Top: Integer; Height: Integer): TNewStaticText;
begin
  Result := TNewStaticText.Create(Page);
  Result.Parent := Page.Surface;
  Result.Left := 0;
  Result.Top := Top;
  Result.Width := Page.SurfaceWidth;
  Result.AutoSize := False;
  Result.WordWrap := True;
  Result.Height := Height;
  Result.Caption := Text;
end;

function AddEdit(Page: TWizardPage; Top: Integer): TNewEdit;
begin
  Result := TNewEdit.Create(Page);
  Result.Parent := Page.Surface;
  Result.Left := 0;
  Result.Top := Top;
  Result.Width := Page.SurfaceWidth;
end;

function AddButton(Page: TWizardPage; Caption: String; Top: Integer; OnClick: TNotifyEvent): TNewButton;
begin
  Result := TNewButton.Create(Page);
  Result.Parent := Page.Surface;
  Result.Left := 0;
  Result.Top := Top;
  Result.Width := ScaleX(230);
  Result.Height := ScaleY(23);
  Result.Caption := Caption;
  Result.OnClick := OnClick;
end;

procedure InitializeWizard;
var
  Top: Integer;
begin
  ModePage := CreateInputOptionPage(wpSelectTasks, CustomMessage('ModeTitle'), CustomMessage('ModeSub'),
    CustomMessage('ModeIntro'), True, False);
  ModePage.Add(CustomMessage('ModeBrowser'));
  ModePage.Add(CustomMessage('ModeWindow'));
  ModePage.Values[0] := True;

  KeysPage := CreateCustomPage(ModePage.ID, CustomMessage('KeysTitle'), CustomMessage('KeysSub'));
  AddText(KeysPage, CustomMessage('KeysIntro'), 0, ScaleY(44));
  Top := ScaleY(48);
  AddText(KeysPage, CustomMessage('KeysLastfm'), Top, ScaleY(28));
  AddButton(KeysPage, CustomMessage('KeysGetLastfm'), Top + ScaleY(30), @GetLastfmClick);
  LastfmEdit := AddEdit(KeysPage, Top + ScaleY(58));
  Top := ScaleY(136);
  AddText(KeysPage, CustomMessage('KeysYoutube'), Top, ScaleY(28));
  AddButton(KeysPage, CustomMessage('KeysGetYoutube'), Top + ScaleY(30), @GetYoutubeClick);
  YoutubeEdit := AddEdit(KeysPage, Top + ScaleY(58));
end;

// When upgrading there is already a config.json: its answers are kept and these pages are not shown again
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := ((PageID = ModePage.ID) or (PageID = KeysPage.ID)) and FileExists(ConfigPath);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  QuitRunning(ExpandConstant('{app}'));
  Result := '';
end;

function JsonText(Value: String): String;
begin
  Result := Trim(Value);
  StringChangeEx(Result, '\', '', True);
  StringChangeEx(Result, '"', '', True);
end;

procedure SaveConfig;
var
  Json, Mode: String;
begin
  if FileExists(ConfigPath) then Exit;
  Mode := 'browser';
  if ModePage.Values[1] then Mode := 'window';
  Json := '{' + #13#10 + '  "language": "' + ActiveLanguage + '",' + #13#10 + '  "open_mode": "' + Mode + '"';
  if JsonText(LastfmEdit.Text) <> '' then
    Json := Json + ',' + #13#10 + '  "lastfm_key": "' + JsonText(LastfmEdit.Text) + '"';
  if JsonText(YoutubeEdit.Text) <> '' then
    Json := Json + ',' + #13#10 + '  "youtube_key": "' + JsonText(YoutubeEdit.Text) + '"';
  Json := Json + #13#10 + '}' + #13#10;
  ForceDirectories(DataFolder);
  SaveStringToFile(ConfigPath, Json, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then SaveConfig;
end;

function InitializeUninstall: Boolean;
begin
  QuitRunning(ExpandConstant('{app}'));
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // Data is kept unless the user says otherwise; a silent uninstall never deletes it
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) and DirExists(DataFolder) then
    if MsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(DataFolder, True, True, True);
end;
