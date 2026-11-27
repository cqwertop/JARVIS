# Builds an MSIX bundle: dist\KAIRO-<version>.msixbundle, plus dist\KAIRO.cer (the certificate it's signed with).
#   powershell -ExecutionPolicy Bypass -File packaging\build_msix.ps1 [-Rebuild]
# Uses the PyInstaller app in dist\KAIRO (from build_windows.ps1). -Rebuild (or no dist\KAIRO yet) runs
# PyInstaller first. makeappx/signtool come from Microsoft's Windows SDK BuildTools NuGet package, downloaded
# once into packaging\msix\.tools, so the Windows SDK doesn't need to be installed.
#
# Signing uses a self-signed certificate ("CN=KAIRO Project", kept in your user certificate store and reused).
# Each PC must trust KAIRO.cer (Local Machine > Trusted People) before Windows will install the bundle.
param([switch]$Rebuild)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py      = Join-Path $root ".venv\Scripts\python.exe"
$msixDir = Join-Path $PSScriptRoot "msix"
$tools   = Join-Path $msixDir ".tools"
$work    = Join-Path $root "build\msix"
$subject = "CN=KAIRO Project"   # must match Publisher in AppxManifest.xml

$version = (& $py -c "import version; print(version.__version__)").Trim()
# MSIX versions are four numbers, and a beta must sort before its final release:
#   0.10.0-beta.1 -> 0.10.0.1,  0.10.0-beta.2 -> 0.10.0.2,  0.10.0 -> 0.10.0.1000
$m = [regex]::Match($version, '^(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$')
if (-not $m.Success) { throw "version.py must look like 1.2.3 or 1.2.3-beta.4 (got '$version')." }
$revision = if ($m.Groups[4].Success) { [int]$m.Groups[4].Value } else { 1000 }
if ($m.Groups[4].Success -and $revision -ge 1000) { throw "Beta numbers must be below 1000." }
$pkgVersion = "$($m.Groups[1].Value).$($m.Groups[2].Value).$($m.Groups[3].Value).$revision"
Write-Host "== KAIRO $version - MSIX bundle ($pkgVersion) ==" -ForegroundColor Cyan

if ($Rebuild -or -not (Test-Path "dist\KAIRO\KAIRO.exe")) {
    Write-Host "Packaging the app (PyInstaller)..."
    & $py packaging\make_icons.py | Out-Null
    Remove-Item -Recurse -Force build\kairo, dist\KAIRO -ErrorAction SilentlyContinue
    cmd /c "`"$py`" -m PyInstaller packaging\kairo.spec --noconfirm --log-level WARN 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
}

$makeappx = Get-ChildItem $tools -Recurse -Filter makeappx.exe -ErrorAction SilentlyContinue |
            Where-Object FullName -match '\\x64\\' | Select-Object -First 1
if (-not $makeappx) {
    Write-Host "Downloading makeappx/signtool (Microsoft.Windows.SDK.BuildTools)..."
    New-Item -ItemType Directory -Force $tools | Out-Null
    $v = (Invoke-RestMethod https://api.nuget.org/v3-flatcontainer/microsoft.windows.sdk.buildtools/index.json).versions |
         Where-Object { $_ -notmatch '-' } | Select-Object -Last 1
    Invoke-WebRequest "https://api.nuget.org/v3-flatcontainer/microsoft.windows.sdk.buildtools/$v/microsoft.windows.sdk.buildtools.$v.nupkg" -OutFile "$tools\bt.zip"
    Expand-Archive "$tools\bt.zip" $tools -Force
    Remove-Item "$tools\bt.zip"
    $makeappx = Get-ChildItem $tools -Recurse -Filter makeappx.exe | Where-Object FullName -match '\\x64\\' | Select-Object -First 1
}
$signtool = Join-Path $makeappx.DirectoryName "signtool.exe"

Write-Host "Staging package files..."
Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
$pkg = Join-Path $work "pkg"
New-Item -ItemType Directory -Force $pkg, "$work\bundle" | Out-Null
Copy-Item -Recurse "dist\KAIRO\*" $pkg
& $py "$msixDir\make_logos.py" "$pkg\Assets"
if ($LASTEXITCODE -ne 0) { throw "Couldn't make the logos." }
(Get-Content "$msixDir\AppxManifest.xml" -Raw).Replace("__VERSION__", $pkgVersion) |
    Set-Content "$pkg\AppxManifest.xml" -Encoding utf8

$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $subject -and $_.NotAfter -gt (Get-Date) } |
        Select-Object -First 1
if (-not $cert) {
    Write-Host "Creating a self-signed signing certificate ($subject)..."
    $cert = New-SelfSignedCertificate -Type Custom -Subject $subject -KeyUsage DigitalSignature `
        -FriendlyName "KAIRO MSIX signing" -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(5) `
        -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
}

Write-Host "Packing and signing..."
$msix   = "$work\bundle\KAIRO_${pkgVersion}_x64.msix"
$bundle = Join-Path $root "dist\KAIRO-$version.msixbundle"
& $makeappx.FullName pack /o /d $pkg /p $msix | Out-Null
if ($LASTEXITCODE -ne 0) { throw "makeappx pack failed (run it without | Out-Null to see why)." }
& $signtool sign /q /fd SHA256 /sha1 $cert.Thumbprint /s My $msix
if ($LASTEXITCODE -ne 0) { throw "Signing the .msix failed." }
& $makeappx.FullName bundle /o /bv $pkgVersion /d "$work\bundle" /p $bundle | Out-Null
if ($LASTEXITCODE -ne 0) { throw "makeappx bundle failed." }
& $signtool sign /q /fd SHA256 /sha1 $cert.Thumbprint /s My $bundle
if ($LASTEXITCODE -ne 0) { throw "Signing the bundle failed." }
Export-Certificate -Cert $cert -FilePath "dist\KAIRO.cer" | Out-Null

$out = Get-Item $bundle
Write-Host ("Done: {0} ({1:N0} MB)" -f $out.FullName, ($out.Length / 1MB)) -ForegroundColor Green
Write-Host "Install: trust dist\KAIRO.cer (Local Machine > Trusted People) once, then double-click the bundle."
