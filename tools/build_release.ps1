<#
.SYNOPSIS
  Builds the DotFlip app, the Windows 11 context-menu extension, and the installer.

.DESCRIPTION
  1. PyInstaller bundle              -> dist\DotFlip\
  2. C++ shell extension (MSVC)      -> dist\DotFlip\DotFlipMenu.dll
  3. Sparse MSIX package (signed)    -> dist\DotFlip\DotFlip.msix + DotFlip.cer
  4. Inno Setup installer            -> dist\DotFlip-Setup-<version>.exe

  Signing: by default a self-signed certificate ("CN=DotFlip") is created in your
  CurrentUser certificate store and reused. The installer trusts that certificate on the
  target machine. For public releases pass -CertThumbprint of a real code-signing certificate
  (or sign through a service such as SignPath / Azure Trusted Signing) and set -Publisher to
  that certificate's subject exactly.
#>
[CmdletBinding()]
param(
  [string]$Version = "1.0.0",
  [string]$Publisher = "CN=DotFlip",
  [string]$CertThumbprint,
  [switch]$SkipInstaller
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
$dist = Join-Path $root "dist\DotFlip"
$msixVersion = "$Version.0"

function Find-Tool($name, $dirs) {
  foreach ($d in $dirs) { $p = Join-Path $d $name; if (Test-Path $p) { return $p } }
  $c = Get-Command $name -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  throw "Cannot find $name"
}
$kits = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Directory |
  Where-Object Name -Match '^10\.' | Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName "x64" }
$makeappx = Find-Tool "makeappx.exe" $kits
$signtool = Find-Tool "signtool.exe" $kits

Write-Host "== 1/4 PyInstaller" -ForegroundColor Cyan
& $py tools\make_icons.py
$env:PYTHONPATH = "src"
& $py -m PyInstaller --noconfirm --clean --windowed --name DotFlip --icon assets\DotFlip.ico `
  --paths src --collect-all pillow_heif --collect-all resvg_py --exclude-module tkinter run.py
if ($LASTEXITCODE) { throw "PyInstaller failed" }

Write-Host "== 2/4 Shell extension" -ForegroundColor Cyan
$vcvars = Get-ChildItem "${env:ProgramFiles(x86)}\Microsoft Visual Studio", "$env:ProgramFiles\Microsoft Visual Studio" -Recurse -Filter vcvars64.bat -ErrorAction SilentlyContinue |
  Sort-Object FullName -Descending | Select-Object -First 1
if (-not $vcvars) { throw "MSVC build tools not found (install 'Desktop development with C++')" }
New-Item -ItemType Directory -Force build\shellext | Out-Null
cmd /c "`"$($vcvars.FullName)`" >nul && cl /nologo /std:c++17 /EHsc /O2 /MT /LD /W3 /DUNICODE /D_UNICODE shellext\DotFlipMenu.cpp /Fo:build\shellext\ /Fe:build\shellext\DotFlipMenu.dll /link /DEF:shellext\DotFlipMenu.def ole32.lib shlwapi.lib shell32.lib user32.lib advapi32.lib"
if ($LASTEXITCODE) { throw "Shell extension build failed" }
Copy-Item build\shellext\DotFlipMenu.dll $dist -Force

Write-Host "== 3/4 Sparse package" -ForegroundColor Cyan
if (-not $CertThumbprint) {
  $cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $Publisher -and $_.NotAfter -gt (Get-Date).AddDays(30) } | Select-Object -First 1
  if (-not $cert) {
    Write-Host "Creating self-signed certificate $Publisher"
    $cert = New-SelfSignedCertificate -Type Custom -Subject $Publisher -KeyUsage DigitalSignature -FriendlyName "dot.Flip" `
      -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(5) `
      -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
  }
  $CertThumbprint = $cert.Thumbprint
}
$cert = Get-Item "Cert:\CurrentUser\My\$CertThumbprint"
if ($cert.Subject -ne $Publisher) { throw "Certificate subject '$($cert.Subject)' must equal -Publisher '$Publisher'" }
Export-Certificate -Cert $cert -FilePath (Join-Path $dist "DotFlip.cer") -Force | Out-Null

$stage = Join-Path $root "build\msix"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$stage\Assets" | Out-Null
Copy-Item assets\*.png "$stage\Assets\"
$types = & $py -c "from dotflip.core.formats import READ_EXTENSIONS as E; print(' '.join(E))"
$itemTypes = ($types -split ' ' | ForEach-Object {
  "            <desktop5:ItemType Type=`"$_`"><desktop5:Verb Id=`"DotFlipConvert`" Clsid=`"8D3A6F52-1B47-4C0E-A9E5-6F2D7B9C3E41`" /></desktop5:ItemType>"
}) -join "`n"
(Get-Content shellext\AppxManifest.xml.in -Raw).Replace("{{VERSION}}", $msixVersion).Replace("{{PUBLISHER}}", $Publisher).Replace("{{ITEM_TYPES}}", $itemTypes) |
  Set-Content "$stage\AppxManifest.xml" -Encoding utf8
$msix = Join-Path $dist "DotFlip.msix"
Remove-Item $msix -ErrorAction SilentlyContinue
& $makeappx pack /d $stage /p $msix /nv | Out-Null
if ($LASTEXITCODE) { throw "makeappx failed" }
& $signtool sign /fd SHA256 /sha1 $CertThumbprint $msix | Out-Null
if ($LASTEXITCODE) { throw "signtool failed" }

if ($SkipInstaller) { Write-Host "Done (installer skipped)."; return }

Write-Host "== 4/4 Installer" -ForegroundColor Cyan
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
  Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup" }
& $iscc "/DAppVersion=$Version" installer\DotFlip.iss
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Write-Host "Built dist\DotFlip-Setup-$Version.exe" -ForegroundColor Green
