# Builds the Windows installer: dist\KAIRO-Setup-<version>.exe
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
# Needs: the project's .venv (with requirements.txt + requirements-build.txt) and Inno Setup 6.
$ErrorActionPreference = "Continue"  # native tools write progress to stderr; failures are checked via exit codes
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"

$version = & $py -c "import version; print(version.__version__)"
Write-Host "== KAIRO $version - Windows build ==" -ForegroundColor Cyan

Write-Host "1/5 Running tests..."
$testLog = Join-Path $env:TEMP "kairo-tests.log"
cmd /c "`"$py`" -m unittest discover -s tests -t . > `"$testLog`" 2>&1"
$testExit = $LASTEXITCODE
Get-Content $testLog -Tail 3
if ($testExit -ne 0) { throw "Tests failed - not building. See $testLog" }

Write-Host "2/5 Drawing icons..."
& $py packaging\make_icons.py | Out-Null

Write-Host "3/5 Packaging the app (PyInstaller)..."
Remove-Item -Recurse -Force build, dist\KAIRO -ErrorAction SilentlyContinue
cmd /c "`"$py`" -m PyInstaller packaging\kairo.spec --noconfirm --log-level WARN 2>&1"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

Write-Host "4/5 Self-test of the packaged app..."
$testHome = Join-Path $env:TEMP "kairo-build-selftest"
Remove-Item -Recurse -Force $testHome -ErrorAction SilentlyContinue
$env:KAIRO_HOME = $testHome
$p = Start-Process -FilePath "dist\KAIRO\KAIRO.exe" -ArgumentList "--selftest" -Wait -PassThru
Remove-Item Env:KAIRO_HOME
Get-Content (Join-Path $testHome "selftest.txt")
if ($p.ExitCode -ne 0) { throw "The packaged app failed its self-test." }

Write-Host "5/5 Building the installer (Inno Setup)..."
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 isn't installed (winget install JRSoftware.InnoSetup)." }
& $iscc /Qp "/DAppVersion=$version" packaging\windows\kairo.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

$out = Get-Item "dist\KAIRO-Setup-$version.exe"
$hash = (Get-FileHash $out -Algorithm SHA256).Hash
"$hash  $($out.Name)" | Set-Content "dist\KAIRO-Setup-$version.exe.sha256" -Encoding ascii
Write-Host ("Done: {0} ({1:N0} MB)  SHA-256 {2}" -f $out.FullName, ($out.Length / 1MB), $hash) -ForegroundColor Green
