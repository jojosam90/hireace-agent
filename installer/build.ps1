<#
.SYNOPSIS
  Builds dist\HireAceSetup.exe, the installer to give to testers.

.DESCRIPTION
  Packs the committed code plus this PC's API keys (agent\.env.local and
  agent\frontend\.env.local) into a zip, and wraps it with installer\setup.ps1
  into a self-extracting HireAceSetup.exe using IExpress (built into Windows).

  WARNING: the installer contains your OpenAI, LiveKit and Resend keys. Anyone with
  it can extract them and their usage is billed to you. Give it only to people you
  trust, and replace the keys when testing is over.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\installer\build.ps1
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$dist = Join-Path $root 'dist'
# Staged in a temp folder: IExpress fails on paths with spaces ("HireAce Agent")
$stage = Join-Path $env:TEMP 'hireace-installer-build'

# The key license codes are checked with (made by new-license.ps1)
$licenseSecret = Join-Path $PSScriptRoot 'license-secret.txt'
if (-not (Test-Path $licenseSecret)) {
  throw 'No license key yet: run installer\new-license.ps1 once (it makes the key and a first code).'
}
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage | Out-Null

# 1. The committed code only (no node_modules, .venv, builds or local data)
Push-Location $root
try {
  # autocrlf off: files keep their committed LF endings (the app's lint rejects CRLF)
  $files = @(Get-Content (Join-Path $PSScriptRoot 'package-files.txt'))
  git -c core.autocrlf=false archive --format=zip -o (Join-Path $stage 'code.zip') HEAD @files
  if ($LASTEXITCODE) { throw 'git archive failed' }
} finally {
  Pop-Location
}
$app = Join-Path $stage 'app'
Expand-Archive (Join-Path $stage 'code.zip') -DestinationPath $app
# Which version this is, for the admin portal
$version = "$(Get-Date -Format 'yyyy.MM.dd')-$(git -C $root rev-parse --short HEAD)"
Set-Content -Path (Join-Path $app 'version.txt') -Encoding ascii -Value $version

# 2. The keys. Not this PC's gatekeeper secret (setup makes a new one); each user
#    signs in to their own Gmail in their browser.
$keep = '^(LIVEKIT_URL|LIVEKIT_API_KEY|LIVEKIT_API_SECRET|OPENAI_API_KEY|EMAIL_SIGNATURE|OPENAI_VOICE|OPENAI_REALTIME_MODEL|HIREACE_PORTAL_URL)='
$keys = [string[]](Get-Content (Join-Path $root 'agent\.env.local') | Where-Object { $_ -match $keep })
# UTF-8 without a byte-order mark: a BOM would hide the first setting from the app
[IO.File]::WriteAllLines((Join-Path $app 'agent\.env.local'), $keys, (New-Object Text.UTF8Encoding $false))
Copy-Item (Join-Path $root 'agent\frontend\.env.local') (Join-Path $app 'agent\frontend\.env.local')
# The company's price list and quotation template: on this PC only, never committed
foreach ($file in 'agent\price_list.json', 'agent\templates\quotation.xlsx') {
  $source = Join-Path $root $file
  if (Test-Path $source) {
    New-Item -ItemType Directory -Force (Split-Path (Join-Path $app $file)) | Out-Null
    Copy-Item $source (Join-Path $app $file)
  } else {
    Write-Warning "$file is missing: quotations will not work in this installer."
  }
}

$package = Join-Path $stage 'hireace.zip'
Compress-Archive -Path (Join-Path $app '*') -DestinationPath $package
Copy-Item (Join-Path $PSScriptRoot 'setup.ps1') $stage
# The license check and its secret key (codes from new-license.ps1)
Copy-Item (Join-Path $PSScriptRoot 'license.ps1') $stage
Copy-Item $licenseSecret (Join-Path $stage 'license.secret')
Set-Content -Path (Join-Path $stage 'install.cmd') -Encoding ascii -Value @'
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0setup.ps1"
'@

# 3. Self-extracting installer: extracts to a temp folder and runs install.cmd
#    (ShowInstallProgramWindow=1: no black window; setup shows its own progress window)
$exe = Join-Path $stage 'HireAceSetup.exe'
$sed = Join-Path $stage 'hireace.sed'
Set-Content -Path $sed -Encoding ascii -Value @"
[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName=$exe
FriendlyName=HireAce setup
AppLaunched=cmd.exe /c install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles
[Strings]
FILE0="install.cmd"
FILE1="setup.ps1"
FILE2="hireace.zip"
FILE3="license.ps1"
FILE4="license.secret"
[SourceFiles]
SourceFiles0=$stage\
[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
%FILE3%=
%FILE4%=
"@
Start-Process "$env:WINDIR\System32\iexpress.exe" -ArgumentList '/N', '/Q', $sed -Wait
if (-not (Test-Path $exe)) { throw 'IExpress did not produce HireAceSetup.exe' }

New-Item -ItemType Directory -Force $dist | Out-Null
$final = Join-Path $dist 'HireAceSetup.exe'
Copy-Item $exe $final -Force
Remove-Item -Recurse -Force $stage  # it held the keys in plain files
$size = [math]::Round((Get-Item $final).Length / 1MB, 1)
Write-Host "Built $final ($size MB)" -ForegroundColor Green
Write-Host 'It contains your API keys: share it only with people you trust.' -ForegroundColor Yellow
