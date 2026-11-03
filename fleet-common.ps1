# Shared by the monitor (fleet.ps1) and the updater (fleet-update.ps1).

function Write-FleetLog([string]$text) {
  try {
    $folder = Join-Path $DataDir 'logs'
    New-Item -ItemType Directory -Force $folder | Out-Null
    $file = Join-Path $folder 'fleet.log'
    if ((Test-Path $file) -and (Get-Item $file).Length -gt 1MB) { Move-Item -Force $file "$file.previous" }
    Add-Content -Path $file -Encoding utf8 -Value "$(Get-Date -Format s) $text"
  } catch { }
}

# start.ps1 reads these: it will not start while one exists
function Set-Flag([string]$name, [bool]$on, [string]$detail = '') {
  $file = Join-Path $DataDir $name
  if ($on) { Set-Content -Path $file -Encoding utf8 -Value $detail }
  elseif (Test-Path $file) { Remove-Item -Force $file }
}

# HireAce's parts: everything running from this folder and what those started, but never
# the monitor or the updater themselves
function Get-HireAceProcesses {
  $all = @(Get-CimInstance Win32_Process)
  $here = [regex]::Escape($Root)
  $found = New-Object System.Collections.Generic.HashSet[int]
  $all | Where-Object {
    $_.ProcessId -ne $PID -and $_.CommandLine -match $here -and $_.CommandLine -notmatch '\\fleet[-\w]*\.(ps1|vbs)'
  } | ForEach-Object { [void]$found.Add([int]$_.ProcessId) }
  do {
    $more = @($all | Where-Object {
      -not $found.Contains([int]$_.ProcessId) -and $found.Contains([int]$_.ParentProcessId)
    })
    $more | ForEach-Object { [void]$found.Add([int]$_.ProcessId) }
  } while ($more.Count)
  $found
}

function Stop-HireAce {
  # Twice: start.ps1 restarts a part that stops, if it gets to it first
  foreach ($round in 1, 2) {
    foreach ($id in Get-HireAceProcesses) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
  }
  # The panel: its own Chrome profile, outside this folder (see panel.ps1)
  $profilePath = Join-Path $DataDir 'panel-profile'
  Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($profilePath) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Start-HireAce {
  Start-Process (Join-Path $env:WINDIR 'System32\wscript.exe') -ArgumentList "`"$(Join-Path $Root 'hireace.vbs')`""
}

function Test-Url([string]$url) {
  try {
    Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 3 | Out-Null
    $true
  } catch {
    $false
  }
}

function Test-HireAcePart([ValidateSet('gatekeeper', 'web', 'agent')][string]$part) {
  switch ($part) {
    'gatekeeper' { Test-Url "$(if ($GatekeeperUrl) { $GatekeeperUrl } else { 'http://127.0.0.1:8080' })/healthz" }
    'web' { Test-Url 'http://127.0.0.1:3001/' }
    'agent' {
      [bool](Get-CimInstance Win32_Process -Filter "Name = 'python.exe' AND CommandLine LIKE '%src/agent.py%'" |
        Select-Object -First 1)
    }
  }
}
