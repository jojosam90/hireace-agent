<#
.SYNOPSIS
  The HireAce monitor: tells the admin portal how this PC is, and carries out its orders.

.DESCRIPTION
  Runs from Windows sign-in with no window (fleet.vbs), whether or not HireAce is open, so
  the portal can tell "this PC is offline" from "HireAce is closed" and can still restart or
  update it. A PC behind a router cannot be reached from the internet, so it calls out: it
  checks in every minute, and the answer carries any order. Its only other work is a few
  local checks, so it is idle almost all the time.

  Sends: PC and Windows user name, HireAce version, which parts are running, whether a call is
  on, free memory and disk, and token counts. Never the conversations, screens or emails.

.PARAMETER Once
  Check in one time and stop (for testing).
#>
param(
  [string]$Root = $PSScriptRoot,
  [string]$DataDir = (Join-Path $env:USERPROFILE '.hireace-agent'),
  [string]$PortalUrl = '',
  [switch]$Once,
  # For testing: never start HireAce
  [switch]$NoStart
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
. (Join-Path $Root 'fleet-common.ps1')
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$single = New-Object System.Threading.Mutex($false, 'Local\HireAceMonitor')
try { $first = $single.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $first = $true }
if (-not $first) { exit 3 }

function Get-EnvValue([string]$file, [string]$name) {
  if (-not (Test-Path $file)) { return '' }
  $line = Get-Content $file | Where-Object { $_ -match "^\s*$name\s*=" } | Select-Object -First 1
  if ($line) { ($line -split '=', 2)[1].Trim() } else { '' }
}

if (-not $PortalUrl) { $PortalUrl = Get-EnvValue (Join-Path $Root 'agent\.env.local') 'HIREACE_PORTAL_URL' }
if (-not $PortalUrl) { exit 4 }
$PortalUrl = $PortalUrl.TrimEnd('/')
New-Item -ItemType Directory -Force $DataDir | Out-Null

$identityFile = Join-Path $DataDir 'fleet.json'
$statusFile = Join-Path $DataDir 'update-status.json'
$spool = Join-Path $DataDir 'usage.jsonl'
$sending = Join-Path $DataDir 'usage.sending'
$script:results = New-Object System.Collections.ArrayList
$script:interval = 60
$monitorScript = Join-Path $Root 'fleet.ps1'
$startedFrom = (Get-Item $monitorScript).LastWriteTimeUtc

function Read-Text([string]$file) {
  if (Test-Path $file) { (Get-Content $file -Raw).Trim() } else { '' }
}

function Send-Portal([string]$path, $body, [string]$token = '') {
  $headers = @{}
  if ($token) { $headers.Authorization = "Bearer $token" }
  Invoke-RestMethod -Method Post -Uri "$PortalUrl$path" -Headers $headers -ContentType 'application/json' -TimeoutSec 30 `
    -Body ([Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 6 -Compress)))
}

function Get-Identity {
  if (Test-Path $identityFile) { return Get-Content $identityFile -Raw | ConvertFrom-Json }
  $license = Read-Text (Join-Path $DataDir 'license.txt')
  if (-not $license) { throw 'No license code on this PC.' }
  $identity = Send-Portal '/api/agent/enroll' @{
    license = $license
    hostname = $env:COMPUTERNAME
    windowsUser = $env:USERNAME
    agentName = Read-Text (Join-Path $DataDir 'agent-name')
    version = Read-Text (Join-Path $Root 'version.txt')
  }
  $identity | ConvertTo-Json | Set-Content -Path $identityFile -Encoding ascii
  Write-FleetLog "Joined the portal as $($identity.deviceId)"
  $identity
}

function Test-InCall {
  $token = Get-EnvValue (Join-Path $Root 'agent\.env') 'GATEKEEPER_TOKEN'
  if (-not $token) { return $false }
  try {
    $answer = Invoke-RestMethod 'http://127.0.0.1:8080/v1/calls' -Headers @{ 'X-Gatekeeper-Token' = $token } -TimeoutSec 3
    [bool]$answer.room
  } catch {
    $false
  }
}

# Token counts the voice agent wrote since the last check-in, added up per day and model. The
# file is moved aside and kept until the portal has it; its contents name the batch, so one
# sent twice (the answer got lost) is counted once.
function Get-UsageBatch {
  if (-not (Test-Path $sending)) {
    if (-not (Test-Path $spool)) { return $null }
    try { Move-Item $spool $sending } catch { return $null }  # being written just now
  }
  $totals = @{}
  foreach ($line in Get-Content $sending) {
    try { $row = $line | ConvertFrom-Json } catch { continue }
    if (-not $row.day) { continue }
    $key = "$($row.day)|$($row.model)"
    if (-not $totals[$key]) {
      $totals[$key] = @{
        day = $row.day; model = $row.model; inText = 0; inAudio = 0; inImage = 0
        cachedText = 0; cachedAudio = 0; outText = 0; outAudio = 0
      }
    }
    foreach ($field in 'inText', 'inAudio', 'inImage', 'cachedText', 'cachedAudio', 'outText', 'outAudio') {
      $totals[$key][$field] += [double]$row.$field
    }
  }
  if (-not $totals.Count) {
    Remove-Item -Force $sending
    return $null
  }
  @{ batchId = (Get-FileHash $sending -Algorithm SHA256).Hash; items = @($totals.Values) }
}

function Get-Report {
  $os = Get-CimInstance Win32_OperatingSystem
  $disk = New-Object IO.DriveInfo ([IO.Path]::GetPathRoot($Root))
  $report = @{
    hostname = $env:COMPUTERNAME
    windowsUser = $env:USERNAME
    agentName = Read-Text (Join-Path $DataDir 'agent-name')
    version = Read-Text (Join-Path $Root 'version.txt')
    parts = @{
      gatekeeper = Test-HireAcePart 'gatekeeper'
      agent = Test-HireAcePart 'agent'
      web = Test-HireAcePart 'web'
    }
    uptimeSeconds = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalSeconds)
    memoryFreeMb = [math]::Round($os.FreePhysicalMemory / 1024)
    memoryTotalMb = [math]::Round($os.TotalVisibleMemorySize / 1024)
    diskFreeGb = [math]::Round($disk.AvailableFreeSpace / 1GB, 1)
  }
  $report.inCall = $report.parts.gatekeeper -and (Test-InCall)

  # What the updater has to say
  if (Test-Path $statusFile) {
    try {
      $status = Get-Content $statusFile -Raw | ConvertFrom-Json
      [void]$script:results.Add(@{ id = $status.id; status = $status.status; detail = $status.detail })
    } catch { }
  }
  $report.results = @($script:results)
  $usage = Get-UsageBatch
  if ($usage) { $report.usage = $usage }
  $report
}

function Invoke-Restart($command) {
  Write-FleetLog 'Restarting HireAce'
  Stop-HireAce
  if ($NoStart) {
    [void]$script:results.Add(@{ id = $command.id; status = 'done'; detail = 'Stopped (test run)' })
    return
  }
  Start-HireAce
  # The web app can need a rebuild first: give it time, and say how it ended
  $deadline = (Get-Date).AddSeconds(180)
  while ((Get-Date) -lt $deadline) {
    if ((Test-HireAcePart 'gatekeeper') -and (Test-HireAcePart 'web')) {
      [void]$script:results.Add(@{ id = $command.id; status = 'done'; detail = 'Restarted' })
      return
    }
    Start-Sleep -Seconds 5
  }
  [void]$script:results.Add(@{ id = $command.id; status = 'failed'; detail = 'Did not come back within 3 minutes' })
}

function Start-Update($command) {
  if ($command.version -eq (Read-Text (Join-Path $Root 'version.txt'))) {
    [void]$script:results.Add(@{ id = $command.id; status = 'done'; detail = "Already on $($command.version)" })
    return
  }
  # Its own process: this one keeps checking in, and is itself replaced by the update
  $job = Join-Path $DataDir 'update-job.json'
  $command | ConvertTo-Json | Set-Content -Path $job -Encoding ascii
  $arguments = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', "`"$(Join-Path $Root 'fleet-update.ps1')`"",
    '-Root', "`"$Root`"", '-DataDir', "`"$DataDir`""
  )
  if ($NoStart) { $arguments += '-NoStart' }
  Start-Process powershell.exe -ArgumentList $arguments -WindowStyle Hidden
  [void]$script:results.Add(@{ id = $command.id; status = 'running'; detail = 'Starting the update' })
}

function Apply-Answer($answer) {
  $script:interval = [math]::Max(30, [int]$answer.intervalSeconds)
  Set-Flag 'usage-limit' ([bool]$answer.limitReached) 'The monthly usage limit was reached.'
  Set-Flag 'deactivated' (-not $answer.active) 'Deactivated from the admin portal.'
  # Also if someone starts it by hand or removes the flag: the portal decides
  if (-not $answer.active -and @(Get-HireAceProcesses).Count) {
    Write-FleetLog 'Deactivated: stopping HireAce'
    Stop-HireAce
  }
  $command = $answer.command
  if (-not $command) { return }
  try {
    switch ($command.type) {
      'restart' { Invoke-Restart $command }
      'update' { Start-Update $command }
      default { [void]$script:results.Add(@{ id = $command.id; status = 'failed'; detail = "Unknown order: $($command.type)" }) }
    }
  } catch {
    Write-FleetLog "Order failed: $($_.Exception.Message)"
    [void]$script:results.Add(@{ id = $command.id; status = 'failed'; detail = $_.Exception.Message })
  }
}

function Invoke-CheckIn {
  $identity = Get-Identity
  $report = Get-Report
  try {
    $answer = Send-Portal '/api/agent/heartbeat' $report $identity.token
  } catch {
    $code = 0
    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    if ($code -eq 401) {
      # Removed from the portal: it joins as new at the next start, if it still runs then
      Write-FleetLog 'The portal no longer knows this PC'
      Remove-Item -Force $identityFile -ErrorAction SilentlyContinue
      exit 4
    }
    throw
  }
  # The portal has them now
  $script:results.Clear()
  if ($report.usage -and (Test-Path $sending)) { Remove-Item -Force $sending }
  if ($report.results | Where-Object { $_.status -ne 'running' -and (Test-Path $statusFile) }) {
    Remove-Item -Force $statusFile -ErrorAction SilentlyContinue
  }
  Apply-Answer $answer
}

while ($true) {
  try {
    # Again at once if an order was just carried out: the portal hears how it ended now,
    # not a minute later, and not never if this monitor stops first
    do { Invoke-CheckIn } while ($script:results.Count)
  } catch {
    Write-FleetLog "Check-in failed: $($_.Exception.Message)"
  }
  if ($Once) { break }
  # An update replaced this script: start again on the new one (fleet.vbs does it)
  if ((Test-Path $monitorScript) -and (Get-Item $monitorScript).LastWriteTimeUtc -ne $startedFrom) { exit 0 }
  Start-Sleep -Seconds $script:interval
  [GC]::Collect()
}
