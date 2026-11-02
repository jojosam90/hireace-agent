<#
.SYNOPSIS
  Installs an update ordered from the admin portal. Started by the monitor (fleet.ps1).

.DESCRIPTION
  Downloads the package and checks its signature before touching anything: a package not
  signed with the private release key is refused, whatever the portal says. Then stops
  HireAce, replaces the code, reinstalls and rebuilds. If any of that fails, the PC goes back
  to the version it had. Keys, settings, the price list and the quotation template are not in
  the package, so they stay as they are.

  Progress goes to update-status.json, which the monitor passes to the portal.
#>
param(
  [Parameter(Mandatory)][string]$Root,
  [Parameter(Mandatory)][string]$DataDir,
  # For testing: no reinstall or rebuild, and HireAce is not started afterwards
  [switch]$NoStart,
  [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
. (Join-Path $Root 'fleet-common.ps1')
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.IO.Compression.FileSystem

$job = Get-Content (Join-Path $DataDir 'update-job.json') -Raw | ConvertFrom-Json
$statusFile = Join-Path $DataDir 'update-status.json'
$updateLog = Join-Path $DataDir 'logs\update.log'
$work = Join-Path $env:TEMP "hireace-update-$($job.id)"
$package = Join-Path $work 'package.zip'
$backup = Join-Path $work 'backup'
$buildFolder = Join-Path $Root 'agent\frontend\.next'
$oldBuild = "$buildFolder.previous"
$listFile = Join-Path $Root 'release-files.txt'

function Set-Status([string]$status, [string]$detail) {
  Write-FleetLog "Update $($job.version): $status $detail"
  $temporary = "$statusFile.new"
  @{ id = $job.id; status = $status; detail = $detail } | ConvertTo-Json | Set-Content -Path $temporary -Encoding utf8
  Move-Item -Force $temporary $statusFile
}

function Test-Signature {
  $keyFile = Join-Path $Root 'release-public-key.xml'
  if (-not (Test-Path $keyFile)) { throw 'This PC has no release public key.' }
  $sha256 = (Get-FileHash $package -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($sha256 -ne $job.sha256) { throw 'The download does not match the release (SHA-256).' }
  $rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider
  try {
    $rsa.PersistKeyInCsp = $false
    $rsa.FromXmlString((Get-Content $keyFile -Raw))
    $message = [Text.Encoding]::UTF8.GetBytes("$($job.version)`n$sha256")
    $signature = [Convert]::FromBase64String($job.signature)
    if (-not $rsa.VerifyData($message, 'SHA256', $signature)) { throw 'bad signature' }
  } catch {
    throw 'The release is not signed with the release key: refused.'
  } finally {
    $rsa.Clear()
  }
}

function Get-PackageFiles {
  $zip = [IO.Compression.ZipFile]::OpenRead($package)
  try {
    @($zip.Entries | Where-Object { $_.Name } | ForEach-Object { $_.FullName -replace '/', '\' })
  } finally {
    $zip.Dispose()
  }
}

# Runs a tool; its output goes to the log, and a failure stops the update
function Invoke-Tool([string]$name, [string]$folder, [string]$command) {
  Set-Status 'running' $name
  Add-Content -Path $updateLog -Encoding utf8 -Value "--- $name ($command)"
  Push-Location $folder
  try {
    $ErrorActionPreference = 'Continue'
    & cmd.exe /d /c "$command >> `"$updateLog`" 2>&1"
    $code = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = 'Stop'
    Pop-Location
  }
  if ($code) { throw "$name failed (see update.log on the PC)" }
}

function Install-Dependencies {
  $env:UV_NATIVE_TLS = 'true'
  $env:CI = 'true'
  $env:NEXT_TELEMETRY_DISABLED = '1'
  Invoke-Tool 'Installing the Python part' (Join-Path $Root 'agent') 'uv sync'
  $web = Join-Path $Root 'agent\frontend'
  Invoke-Tool 'Installing the app' $web 'pnpm.cmd install --frozen-lockfile'
  Invoke-Tool 'Building the app' $web 'pnpm.cmd build'
}

$wasRunning = $false
$touched = $false
$oldList = @()
try {
  $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $user = [Environment]::GetEnvironmentVariable('Path', 'User')
  $env:Path = "$env:USERPROFILE\.local\bin;$env:APPDATA\npm;$machine;$user"
  New-Item -ItemType Directory -Force (Split-Path $updateLog), $work | Out-Null

  # Nothing changes on this PC until the package has passed these two steps
  Set-Status 'running' 'Downloading'
  Invoke-WebRequest $job.url -UseBasicParsing -OutFile $package -TimeoutSec 600
  Set-Status 'running' 'Checking the signature'
  Test-Signature

  $newFiles = Get-PackageFiles
  if (Test-Path $listFile) { $oldList = @(Get-Content $listFile) }

  Set-Status 'running' 'Stopping HireAce'
  $wasRunning = @(Get-HireAceProcesses).Count -gt 0
  Set-Flag 'updating' $true "Updating to $($job.version)"
  Stop-HireAce

  # A copy of everything this replaces or removes, to go back to
  Set-Status 'running' 'Installing'
  $touched = $true
  foreach ($relative in @($newFiles + $oldList | Select-Object -Unique)) {
    $source = Join-Path $Root $relative
    if (Test-Path -LiteralPath $source -PathType Leaf) {
      $copy = Join-Path $backup $relative
      New-Item -ItemType Directory -Force (Split-Path $copy) | Out-Null
      Copy-Item -LiteralPath $source -Destination $copy
    }
  }
  if (Test-Path $oldBuild) { Remove-Item -Recurse -Force $oldBuild }
  if (Test-Path $buildFolder) { Move-Item $buildFolder $oldBuild }

  Expand-Archive -Path $package -DestinationPath $Root -Force
  foreach ($relative in $oldList | Where-Object { $newFiles -notcontains $_ }) {
    Remove-Item -LiteralPath (Join-Path $Root $relative) -Force -ErrorAction SilentlyContinue
  }
  Set-Content -Path $listFile -Encoding utf8 -Value $newFiles

  if (-not $SkipBuild) { Install-Dependencies }

  if (Test-Path $oldBuild) { Remove-Item -Recurse -Force $oldBuild }
  Set-Flag 'updating' $false
  if ($wasRunning -and -not $NoStart) { Start-HireAce }
  Set-Status 'done' "Installed $($job.version)"
} catch {
  $reason = $_.Exception.Message
  Write-FleetLog "Update failed: $reason"
  if ($touched) {
    try {
      # Back to the files it had, and to the packages they need
      foreach ($relative in $newFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $backup $_)) }) {
        Remove-Item -LiteralPath (Join-Path $Root $relative) -Force -ErrorAction SilentlyContinue
      }
      if (Test-Path $backup) { Copy-Item -Path (Join-Path $backup '*') -Destination $Root -Recurse -Force }
      if ($oldList) { Set-Content -Path $listFile -Encoding utf8 -Value $oldList }
      elseif (Test-Path $listFile) { Remove-Item -Force $listFile }
      if (Test-Path $oldBuild) {
        if (Test-Path $buildFolder) { Remove-Item -Recurse -Force $buildFolder }
        Move-Item $oldBuild $buildFolder
      }
      if (-not $SkipBuild) {
        $env:UV_NATIVE_TLS = 'true'
        $env:CI = 'true'
        & cmd.exe /d /c "cd /d `"$(Join-Path $Root 'agent')`" && uv sync >> `"$updateLog`" 2>&1"
        & cmd.exe /d /c "cd /d `"$(Join-Path $Root 'agent\frontend')`" && pnpm.cmd install --frozen-lockfile >> `"$updateLog`" 2>&1"
      }
      $reason = "$reason. Went back to the previous version."
    } catch {
      $reason = "$reason. Going back also failed: $($_.Exception.Message). Reinstall HireAce on this PC."
    }
  }
  Set-Flag 'updating' $false
  if ($wasRunning -and -not $NoStart) { Start-HireAce }
  Set-Status 'failed' $reason
} finally {
  Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
  Remove-Item -Force (Join-Path $DataDir 'update-job.json') -ErrorAction SilentlyContinue
}
