<#
.SYNOPSIS
  Publishes the committed code as a HireAce update, ready to install from the admin portal.

.DESCRIPTION
  Packs the code (no keys, no price list), signs it with installer\release-key.xml,
  uploads it and lists it on the portal. Nothing is installed until someone chooses
  to on the portal's Releases page.

  By default the package goes to a GitHub release of this repository: the repository is
  public and the package holds only what it already holds. With -Url the package is only
  written to dist\ and you put it at that address yourself.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\installer\publish-release.ps1 -Portal https://your-portal.vercel.app -Notes "Fixes email"
#>
param(
  [Parameter(Mandatory)][string]$Portal,
  [string]$Notes = '',
  [string]$Version = '',
  # Where the package will be downloaded from, instead of a GitHub release
  [string]$Url = '',
  # The portal's RELEASE_PUBLISH_KEY; or put it in installer\release-publish-key.txt
  [string]$PublishKey = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$privateKey = Join-Path $PSScriptRoot 'release-key.xml'
if (-not (Test-Path $privateKey)) { throw 'No signing key on this PC: run installer\new-release-key.ps1 once.' }
if (-not $PublishKey) {
  $keyFile = Join-Path $PSScriptRoot 'release-publish-key.txt'
  if (Test-Path $keyFile) { $PublishKey = (Get-Content $keyFile -Raw).Trim() }
}
if (-not $PublishKey) { throw 'Give -PublishKey, or put it in installer\release-publish-key.txt' }

Push-Location $root
try {
  if (git status --porcelain) { Write-Warning 'Changes that are not committed are not in this release.' }
  $commit = git rev-parse --short HEAD
  if (-not $Version) { $Version = "$(Get-Date -Format 'yyyy.MM.dd')-$commit" }
} finally {
  Pop-Location
}

# Packed the same way as the installer: the committed files, plus which version they are
$stage = Join-Path $env:TEMP "hireace-release-$PID"
New-Item -ItemType Directory -Force $stage | Out-Null
try {
  Push-Location $root
  try {
    $files = @(Get-Content (Join-Path $PSScriptRoot 'package-files.txt'))
    git -c core.autocrlf=false archive --format=zip -o (Join-Path $stage 'code.zip') HEAD @files
    if ($LASTEXITCODE) { throw 'git archive failed' }
  } finally {
    Pop-Location
  }
  $app = Join-Path $stage 'app'
  Expand-Archive (Join-Path $stage 'code.zip') -DestinationPath $app
  Set-Content -Path (Join-Path $app 'version.txt') -Encoding ascii -Value $Version

  $dist = Join-Path $root 'dist'
  New-Item -ItemType Directory -Force $dist | Out-Null
  $name = "hireace-$Version.zip"
  $package = Join-Path $dist $name
  if (Test-Path $package) { Remove-Item $package }
  Compress-Archive -Path (Join-Path $app '*') -DestinationPath $package
} finally {
  Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
}

$sha256 = (Get-FileHash $package -Algorithm SHA256).Hash.ToLowerInvariant()
$message = [Text.Encoding]::UTF8.GetBytes("$Version`n$sha256")
$rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider
try {
  $rsa.PersistKeyInCsp = $false
  $rsa.FromXmlString((Get-Content $privateKey -Raw))
  $signature = [Convert]::ToBase64String($rsa.SignData($message, 'SHA256'))
} finally {
  $rsa.Clear()
}

# What the PCs have must accept this, or every update would fail on every PC
$check = New-Object System.Security.Cryptography.RSACryptoServiceProvider
$check.PersistKeyInCsp = $false
$check.FromXmlString((Get-Content (Join-Path $root 'release-public-key.xml') -Raw))
if (-not $check.VerifyData($message, 'SHA256', [Convert]::FromBase64String($signature))) {
  throw 'release-key.xml does not match release-public-key.xml.'
}

if (-not $Url) {
  Push-Location $root
  try {
    gh release create "v$Version" $package --title "HireAce $Version" --notes $(if ($Notes) { $Notes } else { $Version })
    if ($LASTEXITCODE) { throw 'gh release create failed' }
    $Url = gh release view "v$Version" --json assets --jq '.assets[0].url'
    if (-not $Url) { throw 'Could not read the address of the uploaded package.' }
  } finally {
    Pop-Location
  }
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$body = @{
  version = $Version; url = $Url; sha256 = $sha256; signature = $signature
  notes = $Notes; sizeBytes = (Get-Item $package).Length
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$($Portal.TrimEnd('/'))/api/releases/publish" `
  -Headers @{ Authorization = "Bearer $PublishKey" } -ContentType 'application/json' `
  -Body ([Text.Encoding]::UTF8.GetBytes($body)) | Out-Null

Write-Host "Published $Version. Install it from the portal's Releases page." -ForegroundColor Green
