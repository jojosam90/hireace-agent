<#
.SYNOPSIS
  Start HireAce on this PC: the gatekeeper, the voice agent and the web app.

.DESCRIPTION
  The agent controls this computer's real mouse and keyboard and its own Chrome
  window, so everything runs directly on Windows. Ctrl+C stops all three.

  Emergency stop while the agent is working: slam the mouse into any screen corner.

.PARAMETER Lan
  Also serve the web app to your local network, to watch from a phone. Anyone on
  that network can then open it and approve actions: use only on a trusted network.

.PARAMETER SkipBuild
  Never rebuild the web app. Without it, the web app is rebuilt only when its
  source changed since the last build.

.PARAMETER NoPanel
  Do not open the floating HireAce panel (open http://localhost:3001 yourself).

.PARAMETER Background
  How the desktop icon starts it: with no window of its own. What each part prints
  goes to log files in %USERPROFILE%\.hireace-agent\logs, and closing the panel stops
  HireAce (minimizing it shows the little HireAce agent instead).

  Only one HireAce runs at a time: starting it again shows the open panel.

.EXAMPLE
  .\start.ps1
  .\start.ps1 -Lan
#>
param([switch]$Lan, [switch]$SkipBuild, [switch]$NoPanel, [switch]$Background)

$ErrorActionPreference = 'Stop'

# Turned off from the admin portal, or being updated from it (see fleet.ps1)
$dataDir = Join-Path $env:USERPROFILE '.hireace-agent'
foreach ($hold in @(
    @('deactivated', 'HireAce has been turned off by your administrator.'),
    @('updating', 'HireAce is being updated. Try again in a few minutes.'))) {
  if (Test-Path (Join-Path $dataDir $hold[0])) {
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($hold[1], 'HireAce', 'OK', 'Information')
    exit 0
  }
}

# The monitor that reports to the admin portal: already running after Windows sign-in;
# this covers a PC where it stopped. It exits at once if it is running or no portal is set.
$monitor = Join-Path $PSScriptRoot 'fleet.vbs'
if (Test-Path $monitor) { Start-Process (Join-Path $env:WINDIR 'System32\wscript.exe') -ArgumentList "`"$monitor`"" }

# One HireAce at a time (e.g. the desktop icon clicked twice): a second start shows
# the open panel instead; two would fight over the same ports
$single = New-Object System.Threading.Mutex($false, 'Local\HireAce')
try { $first = $single.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $first = $true }
if (-not $first) {
  . (Join-Path $PSScriptRoot 'panel.ps1')
  Show-Panel
  exit 0
}
$agentDir = Join-Path $PSScriptRoot 'agent'
$webDir = Join-Path $agentDir 'frontend'

# In the background, what each part prints goes to its own log (the last run's
# log is kept as *.previous.log, e.g. to see why a part stopped). With no window to
# show it, a failed start says why in a message and in start.log.
$logs = Join-Path $env:USERPROFILE '.hireace-agent\logs'
if ($Background) {
  New-Item -ItemType Directory -Force $logs | Out-Null
  Start-Transcript -Path (Join-Path $logs 'start.log') -Force | Out-Null
  trap {
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show(
      "HireAce could not start: $($_.Exception.Message)`n`nDetails are in $logs\start.log",
      'HireAce', 'OK', 'Error')
    break
  }
}

# Every process running from $folder (its path on the command line), and everything
# those started: the real Python behind the .venv one names no folder of its own
function Get-ProcessesFrom([string]$folder) {
  $all = @(Get-CimInstance Win32_Process)
  $here = [regex]::Escape($folder)
  $found = New-Object System.Collections.Generic.HashSet[int]
  $all | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match $here } |
    ForEach-Object { [void]$found.Add([int]$_.ProcessId) }
  do {
    $more = @($all | Where-Object { -not $found.Contains([int]$_.ProcessId) -and $found.Contains([int]$_.ParentProcessId) })
    $more | ForEach-Object { [void]$found.Add([int]$_.ProcessId) }
  } while ($more.Count)
  $found
}

# Parts of this HireAce still running without it (after a crash or a forced stop):
# they hold its ports, so a new start would fail without a word
function Stop-LeftoverParts {
  foreach ($id in Get-ProcessesFrom $agentDir) {
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
  }
}
Stop-LeftoverParts

# Shared secret between the agent, the gatekeeper and the web app's Approve buttons
$token = Get-Content (Join-Path $agentDir '.env') -ErrorAction SilentlyContinue |
  Where-Object { $_ -match '^\s*GATEKEEPER_TOKEN\s*=' } |
  ForEach-Object { ($_ -split '=', 2)[1].Trim() } |
  Select-Object -First 1
if (-not $token) { throw 'Set GATEKEEPER_TOKEN=<random string> in agent\.env' }

$env:GATEKEEPER_TOKEN = $token
$env:GATEKEEPER_URL = 'http://127.0.0.1:8080'
# Each installation answers only its own calls: one agent name per PC, made once.
# (All installations share the LiveKit project, which would otherwise hand a call
# to any HireAce agent, possibly on someone else's PC.)
$nameFile = Join-Path (Join-Path $env:USERPROFILE '.hireace-agent') 'agent-name'
if (-not (Test-Path $nameFile)) {
  New-Item -ItemType Directory -Force (Split-Path $nameFile) | Out-Null
  'hireace-' + [guid]::NewGuid().ToString('N').Substring(0, 10) | Set-Content -Encoding ascii $nameFile
}
$env:AGENT_NAME = (Get-Content $nameFile -Raw).Trim()
$env:ALLOW_LOCAL_TOKEN_ROUTE = 'true'
$env:NEXT_TELEMETRY_DISABLED = '1'

# The floating panel (also runnable on its own: .\panel.ps1)
. (Join-Path $PSScriptRoot 'panel.ps1')

function Start-Part([string]$name, [string]$exe, [string[]]$arguments, [string]$dir) {
  if (-not $Background) {
    return Start-Process $exe -ArgumentList $arguments -WorkingDirectory $dir -NoNewWindow -PassThru
  }
  $file = $name -replace ' ', '-'
  foreach ($kind in 'log', 'errors.log') {
    $log = Join-Path $logs "$file.$kind"
    if (Test-Path $log) { Move-Item -Force $log (Join-Path $logs "$file.previous.$kind") }
  }
  # Through cmd, which writes the output to the logs; no window for either
  $command = "`"$exe`" $($arguments -join ' ') > `"$(Join-Path $logs "$file.log")`" " +
    "2> `"$(Join-Path $logs "$file.errors.log")`""
  Start-NoWindow 'cmd.exe' "/d /s /c `"$command`"" $dir
}

$uv = (Get-Command uv).Source
# The .cmd shim: Start-Process cannot launch pnpm's PowerShell shim (pnpm.ps1)
$pnpm = (Get-Command pnpm.cmd).Source
# The web app runs on Node directly: through pnpm it took a second Node process
# (about 80 MB) that only waited
$node = (Get-Command node).Source
$next = Join-Path $webDir 'node_modules\next\dist\bin\next'

# A build takes about 2 minutes: only rebuild when a source file is newer than it
$buildId = Join-Path $webDir '.next\BUILD_ID'
$needsBuild = -not (Test-Path $buildId)
if (-not $needsBuild) {
  $builtAt = (Get-Item $buildId).LastWriteTime
  $changed = Get-ChildItem $webDir -Force |
    Where-Object { $_.Name -notin 'node_modules', '.next' } |
    ForEach-Object { if ($_.PSIsContainer) { Get-ChildItem $_.FullName -Recurse -File } else { $_ } } |
    Where-Object { $_.Name -notin 'tsconfig.tsbuildinfo', 'next-env.d.ts' -and $_.LastWriteTime -gt $builtAt } |
    Select-Object -First 1
  $needsBuild = $null -ne $changed
}

if ($needsBuild -and -not $SkipBuild) {
  Write-Host 'Building the web app (about 2 minutes, only after it changed)...'
  Push-Location $webDir
  try {
    if ($Background) { & $pnpm build *> (Join-Path $logs 'build.log') } else { & $pnpm build }
    if ($LASTEXITCODE) { throw 'The web app build failed.' }
  } finally {
    Pop-Location
  }
}

$webHost = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
# Each part and how to start it. If one stops (for example the agent gives up
# after the internet dropped while the PC slept), it is started again.
$parts = [ordered]@{
  gatekeeper = { Start-Part 'gatekeeper' $uv @('run', 'src/gatekeeper.py') $agentDir }
  agent      = { Start-Part 'agent' $uv @('run', 'src/agent.py', 'start') $agentDir }
  'web app'  = { Start-Part 'web app' $node @("`"$next`"", 'start', '-p', '3001', '-H', $webHost) $webDir }
}
$running = @{}
try {
  foreach ($name in $parts.Keys) { $running[$name] = & $parts[$name] }

  Write-Host ''
  Write-Host 'HireAce is running: http://localhost:3001   (Ctrl+C to stop)' -ForegroundColor Green
  if ($Lan) {
    Write-Host 'On your phone, open http://<this PC''s IP address>:3001 and tap "My PC" during a call.'
  }
  Write-Host 'Emergency stop: slam the mouse into any screen corner.' -ForegroundColor Yellow

  if (-not $NoPanel) {
    # Wait for the web app before opening the panel on it
    $deadline = (Get-Date).AddSeconds(60)
    while ((Get-Date) -lt $deadline) {
      try {
        Invoke-WebRequest 'http://127.0.0.1:3001' -UseBasicParsing -TimeoutSec 2 | Out-Null
        break
      } catch {
        Start-Sleep -Milliseconds 500
      }
    }
    Open-Panel
  }

  $panelIds = @()
  $tick = 0
  while ($true) {
    Start-Sleep -Seconds 2
    # In the background the panel is HireAce's only window: closing it stops HireAce.
    # Watched by its Chrome process, which is cheap; looking for it (a system-wide
    # process query) only until it is found, every 10 s
    if ($Background -and -not $NoPanel) {
      if (-not $panelIds) {
        if ($tick++ % 5 -eq 0) {
          $panelIds = @(Get-PanelProcesses | Where-Object { $_.CommandLine -notlike '*--type=*' } |
            ForEach-Object { $_.ProcessId })
        }
      } elseif (-not (Get-Process -Id $panelIds -ErrorAction SilentlyContinue)) {
        break
      }
    }
    foreach ($name in @($running.Keys)) {
      if ($running[$name].HasExited) {
        Write-Warning "The $name stopped; restarting it in 10 seconds."
        Start-Sleep -Seconds 10
        $running[$name] = & $parts[$name]
      }
    }
  }
} finally {
  foreach ($process in $running.Values) {
    if (-not $process.HasExited) { taskkill /T /F /PID $process.Id | Out-Null }
  }
  # Anything a part left behind (e.g. a child that outlived its parent)
  Stop-LeftoverParts
  # The panel has nothing to talk to once the agent is gone
  # The main Chrome process only: /T takes its helpers (--type=...) with it
  foreach ($panel in Get-PanelProcesses | Where-Object { $_.CommandLine -notlike '*--type=*' }) {
    try { taskkill /T /F /PID $panel.ProcessId 2>$null | Out-Null } catch { }
  }
}
