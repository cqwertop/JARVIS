# Builds an MSIX bundle: dist\JARVIS-<version>.msixbundle, plus dist\JARVIS.cer (the certificate it's signed with).
#   powershell -ExecutionPolicy Bypass -File packaging\build_msix.ps1 [-Rebuild]
# Uses the PyInstaller app in dist\JARVIS (from build_windows.ps1). -Rebuild (or no dist\JARVIS yet) runs
# PyInstaller first. makeappx/signtool come from Microsoft's Windows SDK BuildTools NuGet package, downloaded
# once into packaging\msix\.tools, so the Windows SDK doesn't need to be installed.
#
# Signing uses a self-signed certificate ("CN=JARVIS Project", kept in your user certificate store and reused).
# Each PC must trust JARVIS.cer (Local Machine > Trusted People) before Windows will install the bundle.
param([switch]$Rebuild)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py      = Join-Path $root ".venv\Scripts\python.exe"
$msixDir = Join-Path $PSScriptRoot "msix"
$tools   = Join-Path $msixDir ".tools"
$work    = Join-Path $root "build\msix"
$subject = "CN=JARVIS Project"   # must match Publisher in AppxManifest.xml

$version = (& $py -c "import version; print(version.__version__)").Trim()
$pkgVersion = (($version -split '[^0-9]+' | Where-Object { $_ }) + @("0", "0", "0", "0"))[0..3] -join "."
Write-Host "== JARVIS $version - MSIX bundle ($pkgVersion) ==" -ForegroundColor Cyan

if ($Rebuild -or -not (Test-Path "dist\JARVIS\JARVIS.exe")) {
    Write-Host "Packaging the app (PyInstaller)..."
    & $py packaging\make_icons.py | Out-Null
    Remove-Item -Recurse -Force build\jarvis, dist\JARVIS -ErrorAction SilentlyContinue
    cmd /c "`"$py`" -m PyInstaller packaging\jarvis.spec --noconfirm --log-level WARN 2>&1"
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
Copy-Item -Recurse "dist\JARVIS\*" $pkg
& $py "$msixDir\make_logos.py" "$pkg\Assets"
if ($LASTEXITCODE -ne 0) { throw "Couldn't make the logos." }
(Get-Content "$msixDir\AppxManifest.xml" -Raw).Replace("__VERSION__", $pkgVersion) |
    Set-Content "$pkg\AppxManifest.xml" -Encoding utf8

$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $subject -and $_.NotAfter -gt (Get-Date) } |
        Select-Object -First 1
if (-not $cert) {
    Write-Host "Creating a self-signed signing certificate ($subject)..."
    $cert = New-SelfSignedCertificate -Type Custom -Subject $subject -KeyUsage DigitalSignature `
        -FriendlyName "JARVIS MSIX signing" -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(5) `
        -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
}

Write-Host "Packing and signing..."
$msix   = "$work\bundle\JARVIS_${pkgVersion}_x64.msix"
$bundle = Join-Path $root "dist\JARVIS-$version.msixbundle"
& $makeappx.FullName pack /o /d $pkg /p $msix | Out-Null
if ($LASTEXITCODE -ne 0) { throw "makeappx pack failed (run it without | Out-Null to see why)." }
& $signtool sign /q /fd SHA256 /sha1 $cert.Thumbprint /s My $msix
if ($LASTEXITCODE -ne 0) { throw "Signing the .msix failed." }
& $makeappx.FullName bundle /o /bv $pkgVersion /d "$work\bundle" /p $bundle | Out-Null
if ($LASTEXITCODE -ne 0) { throw "makeappx bundle failed." }
& $signtool sign /q /fd SHA256 /sha1 $cert.Thumbprint /s My $bundle
if ($LASTEXITCODE -ne 0) { throw "Signing the bundle failed." }
Export-Certificate -Cert $cert -FilePath "dist\JARVIS.cer" | Out-Null

$out = Get-Item $bundle
Write-Host ("Done: {0} ({1:N0} MB)" -f $out.FullName, ($out.Length / 1MB)) -ForegroundColor Green
Write-Host "Install: trust dist\JARVIS.cer (Local Machine > Trusted People) once, then double-click the bundle."
