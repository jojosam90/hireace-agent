<#
.SYNOPSIS
  Installs HireAce on this PC (run by HireAceSetup.exe).

.DESCRIPTION
  Asks for the license code (every install, the last one filled in; see
  license.ps1), installs what is
  missing (uv for Python, Node.js, pnpm), copies HireAce to
  %LOCALAPPDATA%\HireAce, builds the app and puts a "HireAce" shortcut on the
  desktop. Email is set up afterwards in the app: Settings (the gear icon) > Open
  Gmail, and sign in once. Running it again updates an existing installation and keeps
  its settings (they live in %USERPROFILE%\.hireace-agent).
  Progress shows in a small window with a progress bar; every step's output goes
  to %TEMP%\HireAceSetup.log.
#>
param(
  [string]$Package = (Join-Path $PSScriptRoot 'hireace.zip'),
  # For a test run without questions or windows: install here, with this license
  [string]$Destination = (Join-Path $env:LOCALAPPDATA 'HireAce'),
  [string]$LicenseCode = '',
  [switch]$Unattended
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName Microsoft.VisualBasic, System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$title = 'HireAce setup'
$dest = $Destination
$log = Join-Path $env:TEMP 'HireAceSetup.log'
Set-Content -Path $log -Value "HireAce setup $(Get-Date -Format s) on $env:PROCESSOR_ARCHITECTURE"

# --- Progress window -------------------------------------------------------------
# Every step: its share of the overall bar, its line in the checklist and its title
$steps = [ordered]@{
  license  = @{ Weight = 1;  Name = 'License';          Title = 'Activating your license' }
  check    = @{ Weight = 2;  Name = 'Check this PC';    Title = 'Checking this PC' }
  uv       = @{ Weight = 6;  Name = 'uv (runs Python)'; Title = 'Installing uv (runs the Python part)' }
  node     = @{ Weight = 12; Name = 'Node.js';          Title = 'Installing Node.js (Windows may ask for permission)' }
  pnpm     = @{ Weight = 3;  Name = 'pnpm';             Title = 'Installing pnpm' }
  copy     = @{ Weight = 4;  Name = 'Copy HireAce';     Title = 'Copying HireAce' }
  python   = @{ Weight = 30; Name = 'Python part';      Title = 'Installing the Python part' }
  packages = @{ Weight = 18; Name = 'App packages';     Title = 'Installing the app' }
  build    = @{ Weight = 23; Name = 'Build the app';    Title = 'Building the app' }
  shortcut = @{ Weight = 2;  Name = 'Desktop icon';     Title = 'Adding HireAce to the desktop and Start menu' }
}
$totalWeight = ($steps.Values | ForEach-Object { $_.Weight } | Measure-Object -Sum).Sum

$font = New-Object System.Drawing.Font('Segoe UI', 9)
$boldFont = New-Object System.Drawing.Font('Segoe UI', 9, [System.Drawing.FontStyle]::Bold)
$form = New-Object System.Windows.Forms.Form -Property @{
  Text = $title; ClientSize = New-Object System.Drawing.Size(460, (190 + 22 * $steps.Count))
  FormBorderStyle = 'FixedDialog'; MaximizeBox = $false; StartPosition = 'CenterScreen'
  Font = $font
}
$stepLabel = New-Object System.Windows.Forms.Label -Property @{
  Location = New-Object System.Drawing.Point(20, 18); Size = New-Object System.Drawing.Size(360, 22)
  Font = New-Object System.Drawing.Font('Segoe UI', 10, [System.Drawing.FontStyle]::Bold)
  Text = 'Starting...'
}
$percentLabel = New-Object System.Windows.Forms.Label -Property @{
  Location = New-Object System.Drawing.Point(380, 18); Size = New-Object System.Drawing.Size(60, 22)
  TextAlign = 'TopRight'; Text = '0%'
}
$bar = New-Object System.Windows.Forms.ProgressBar -Property @{
  Location = New-Object System.Drawing.Point(20, 46); Size = New-Object System.Drawing.Size(420, 22)
  Maximum = 1000; Style = 'Continuous'
}
$stepNow = New-Object System.Windows.Forms.Label -Property @{
  Location = New-Object System.Drawing.Point(20, 78); Size = New-Object System.Drawing.Size(360, 18)
  ForeColor = [System.Drawing.Color]::DimGray; Text = 'This step'
}
$stepPercent = New-Object System.Windows.Forms.Label -Property @{
  Location = New-Object System.Drawing.Point(380, 78); Size = New-Object System.Drawing.Size(60, 18)
  TextAlign = 'TopRight'; ForeColor = [System.Drawing.Color]::DimGray; Text = ''
}
$stepBar = New-Object System.Windows.Forms.ProgressBar -Property @{
  Location = New-Object System.Drawing.Point(20, 98); Size = New-Object System.Drawing.Size(420, 10)
  Maximum = 1000; Style = 'Continuous'
}
$form.Controls.AddRange(@($stepLabel, $percentLabel, $bar, $stepNow, $stepPercent, $stepBar))
# The checklist: one line per step
$y = 122
foreach ($key in $steps.Keys) {
  $line = New-Object System.Windows.Forms.Label -Property @{
    Location = New-Object System.Drawing.Point(20, $y); Size = New-Object System.Drawing.Size(420, 20)
    ForeColor = [System.Drawing.Color]::Gray; Text = "$([char]0x25CB)   $($steps[$key].Name)"
  }
  $steps[$key].Line = $line
  $form.Controls.Add($line)
  $y += 22
}
$note = New-Object System.Windows.Forms.Label -Property @{
  Location = New-Object System.Drawing.Point(20, ($y + 8)); Size = New-Object System.Drawing.Size(420, 50)
  ForeColor = [System.Drawing.Color]::DimGray
  Text = "The first install takes about 5-10 minutes. You can keep using your PC; this window tells you when it is done."
}
$form.Controls.Add($note)
$script:finished = $false
$script:cancel = $false
$form.Add_FormClosing({
  param($sender, $e)
  if ($script:finished) { return }
  $e.Cancel = $true
  $stop = [System.Windows.Forms.MessageBox]::Show('Stop installing HireAce?', $title, 'YesNo', 'Question')
  if ($stop -eq 'Yes') { $script:cancel = $true }
})
if (-not $Unattended) { $form.Show() }

$script:doneWeight = 0
$script:current = $null
function Set-Bar([double]$weight) {
  # 1.0, not 1: [math]::Min(1, x) compares whole numbers, so the bar showed 0%
  # until halfway and then jumped to 100%
  $share = [math]::Min(1.0, $weight / $totalWeight)
  $bar.Value = [int](1000 * $share)
  $percentLabel.Text = "$([int](100 * $share))%"
}
function Set-StepBar([double]$share) {
  $share = [math]::Max(0.0, [math]::Min(1.0, $share))
  $stepBar.Value = [int](1000 * $share)
  $stepPercent.Text = "$([int](100 * $share))%"
}
function Wait-Ui {
  [System.Windows.Forms.Application]::DoEvents()
  if ($script:cancel) { Stop-Setup 'Setup was stopped. Run HireAceSetup.exe again to finish it.' }
}
# Checklist marks: done, running, failed (characters, so the file stays plain ASCII)
$markDone = [char]0x2713
$markNow = [char]0x25B6
$markFailed = [char]0x2717
function Start-Step([string]$key) {
  $script:current = $key
  $step = $steps[$key]
  $stepLabel.Text = $step.Title
  $stepNow.Text = "This step: $($step.Name)"
  $step.Line.Text = "$markNow   $($step.Name)"
  $step.Line.ForeColor = [System.Drawing.Color]::Black
  $step.Line.Font = $boldFont
  Set-StepBar 0
  "`r`n== $($step.Title)`r`n" | Add-Content -Path $log
  Wait-Ui
}
function Complete-Step([string]$note = '') {
  $step = $steps[$script:current]
  $script:doneWeight += $step.Weight
  $step.Line.Text = "$markDone   $($step.Name)$note"
  $step.Line.ForeColor = [System.Drawing.Color]::ForestGreen
  $step.Line.Font = $font
  Set-StepBar 1
  Set-Bar $script:doneWeight
  Wait-Ui
}
# A step this PC does not need (e.g. Node.js is already installed)
function Skip-Step([string]$key) {
  Start-Step $key
  Complete-Step ' (already installed)'
}
function Stop-Setup([string]$message) {
  $script:finished = $true
  if ($script:current) {
    $steps[$script:current].Line.Text = "$markFailed   $($steps[$script:current].Name)"
    $steps[$script:current].Line.ForeColor = [System.Drawing.Color]::Firebrick
  }
  $form.Close()
  if (-not $Unattended) { [void][System.Windows.Forms.MessageBox]::Show($message, $title, 'OK', 'Error') }
  Write-Host $message
  exit 1
}
# Starts a program with no window at all, not even a terminal: on Windows 11,
# Windows Terminal shows programs started with -WindowStyle Hidden anyway
function Start-NoWindow([string]$exe, [string]$arguments, [string]$dir = $PWD.Path) {
  $info = New-Object System.Diagnostics.ProcessStartInfo $exe, $arguments
  $info.UseShellExecute = $false
  $info.CreateNoWindow = $true
  $info.WorkingDirectory = $dir
  [System.Diagnostics.Process]::Start($info)
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

function Update-Path {
  # Pick up tools installed during this setup without opening a new window
  $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $user = [Environment]::GetEnvironmentVariable('Path', 'User')
  $env:Path = "$env:USERPROFILE\.local\bin;$env:APPDATA\npm;$machine;$user"
}

# Runs a command hidden, its output into the log (by cmd: through PowerShell it was
# garbled and could stop the app build), while the bar moves on towards the step's
# usual duration.
function Invoke-Step([string]$key, [int]$seconds, [string]$commandLine) {
  Start-Step $key
  $what = $steps[$key].Title
  $weight = $steps[$key].Weight
  $p = Start-NoWindow 'cmd.exe' "/d /c `"$commandLine >> `"$log`" 2>&1`""
  $null = $p.Handle  # keeps the exit code readable after it ends
  $started = Get-Date
  while (-not $p.HasExited) {
    if ($script:cancel) { & taskkill.exe /T /F /PID $p.Id | Out-Null }
    $elapsed = ((Get-Date) - $started).TotalSeconds
    $share = 0.95 * (1 - [math]::Exp(-$elapsed / $seconds))
    Set-StepBar $share
    Set-Bar ($script:doneWeight + $weight * $share)
    Wait-Ui
    Start-Sleep -Milliseconds 150
  }
  if ($p.ExitCode) {
    Stop-Setup "$what failed (exit code $($p.ExitCode)).`n`nDetails are in $log - send that file to the person who gave you HireAce."
  }
  Complete-Step
}

try {
  # --- License -------------------------------------------------------------------
  # Asked on every install. The code used last time on this PC is filled in, so an
  # update only needs OK (or another code typed over it).
  . (Join-Path $PSScriptRoot 'license.ps1')
  $licenseSecret = Get-Content (Join-Path $PSScriptRoot 'license.secret') -Raw -ErrorAction SilentlyContinue
  $licenseFile = Join-Path $env:USERPROFILE '.hireace-agent\license.txt'
  $saved = if (Test-Path $licenseFile) { (Get-Content $licenseFile -Raw).Trim() } else { '' }
  Start-Step 'license'
  if ($Unattended) {
    # A test run: the code given, else the one used last time
    $code = if ($LicenseCode) { $LicenseCode } else { $saved }
    if (-not (Test-LicenseCode $code $licenseSecret)) { Stop-Setup 'The license code is not valid.' }
  } else {
    $code = if ($LicenseCode) { $LicenseCode } else { Format-LicenseCode $saved }
    $prompt = "Enter your HireAce license code.`n`nIt looks like ABCD-EFGH-JKLM (letters and digits). You got it from whoever gave you HireAce."
    if (Test-LicenseCode $code $licenseSecret) {
      $prompt = "Enter your HireAce license code.`n`nThe code used last time on this PC is filled in: press OK to keep it, or type another one."
    }
    $form.Hide()
    while ($true) {
      $code = [Microsoft.VisualBasic.Interaction]::InputBox($prompt, $title, $code).Trim()
      if (-not $code) { Stop-Setup 'Setup was cancelled: a license code is needed to install HireAce.' }
      if (Test-LicenseCode $code $licenseSecret) { break }
      $prompt = "That license code is not valid. Check it and try again.`n`nIt looks like ABCD-EFGH-JKLM (letters and digits)."
    }
    $form.Show()
  }
  New-Item -ItemType Directory -Force (Split-Path $licenseFile) | Out-Null
  Format-LicenseCode $code | Set-Content -Encoding ascii $licenseFile
  Complete-Step ' (activated)'

  # --- Requirements ------------------------------------------------------------
  Start-Step 'check'
  $chrome = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
  ) | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $chrome) {
    Stop-Setup "Google Chrome is needed. Install it from https://www.google.com/chrome and run this setup again."
  }
  $office = Test-Path 'Registry::HKEY_CLASSES_ROOT\Word.Application'
  Complete-Step

  # --- Tools ---------------------------------------------------------------------
  Update-Path
  if (Get-Command uv -ErrorAction SilentlyContinue) { Skip-Step 'uv' } else {
    Invoke-Step 'uv' 30 `
      'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"'
    Update-Path
  }
  if (Get-Command node -ErrorAction SilentlyContinue) { Skip-Step 'node' } else {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
      Stop-Setup 'Node.js is needed. Install the LTS version from https://nodejs.org and run this setup again.'
    }
    Invoke-Step 'node' 90 `
      'winget install --id OpenJS.NodeJS.LTS -e --silent --accept-source-agreements --accept-package-agreements'
    Update-Path
  }
  if (Get-Command pnpm.cmd -ErrorAction SilentlyContinue) { Skip-Step 'pnpm' } else {
    Invoke-Step 'pnpm' 30 'npm install -g pnpm@9.15.9'
    Update-Path
  }

  # --- Files ---------------------------------------------------------------------
  Start-Step 'copy'
  # An update: stop everything running from here first (its files are in use, and
  # parts left running hold the ports the new HireAce needs): start.ps1, the
  # gatekeeper, the agent, the web app, and what they started
  if (Test-Path $dest) {
    foreach ($id in Get-ProcessesFrom $dest) {
      Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
  }
  New-Item -ItemType Directory -Force $dest | Out-Null
  Expand-Archive -Path $Package -DestinationPath $dest -Force
  $agentDir = Join-Path $dest 'agent'
  Set-StepBar 0.7

  # --- Settings ------------------------------------------------------------------
  # A random secret shared by the parts of HireAce on this PC (kept on updates)
  $envFile = Join-Path $agentDir '.env'
  # (Test-Path first: on a new PC there is no .env yet, and Select-String would stop setup)
  if (-not ((Test-Path $envFile) -and (Select-String -Path $envFile -Pattern '^GATEKEEPER_TOKEN=' -Quiet))) {
    "GATEKEEPER_TOKEN=$([guid]::NewGuid().ToString('N'))" | Set-Content -Path $envFile -Encoding ascii
  }
  Complete-Step

  # --- Install and build -------------------------------------------------------------
  Push-Location $agentDir
  try {
    # Always 64-bit Intel/AMD Python 3.12: some of HireAce's voice packages exist only
    # for it. ARM laptops (e.g. Snapdragon) run it through Windows' emulation, and a
    # Python already on the PC is left alone.
    'cpython-3.12-windows-x86_64-none' | Set-Content -Encoding ascii '.python-version'
    # Trust this PC's certificates: antivirus or company networks that inspect HTTPS
    $env:UV_NATIVE_TLS = 'true'
    Invoke-Step 'python' 120 'uv sync'
  } finally {
    Pop-Location
  }

  Push-Location (Join-Path $agentDir 'frontend')
  try {
    $env:CI = 'true'  # no interactive questions from pnpm
    Invoke-Step 'packages' 90 'pnpm.cmd install --frozen-lockfile'
    Invoke-Step 'build' 150 'pnpm.cmd build'
  } finally {
    Pop-Location
  }

  if ($Unattended) {
    $script:finished = $true
    $form.Close()
    Write-Host "Installed in $dest"
    exit 0
  }

  # --- Shortcut ------------------------------------------------------------------
  Start-Step 'shortcut'
  $shell = New-Object -ComObject WScript.Shell
  $places = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('Programs')
  )
  foreach ($place in $places) {
    $link = $shell.CreateShortcut((Join-Path $place 'HireAce.lnk'))
    # No window of its own, not even a terminal (hireace.vbs): the panel is
    # HireAce's window
    $link.TargetPath = Join-Path $env:WINDIR 'System32\wscript.exe'
    $link.Arguments = "`"$dest\hireace.vbs`""
    $link.WorkingDirectory = $dest
    $link.IconLocation = "$dest\hireace.ico,0"
    $link.Description = 'Start HireAce'
    $link.Save()
  }
  Complete-Step
  $stepLabel.Text = 'Done: HireAce is on your desktop'
  $stepNow.Text = 'All steps finished'
  Wait-Ui
  Start-Sleep -Milliseconds 800

  $script:finished = $true
  $form.Close()
  $officeNote = if ($office) { '' } else {
    "`n`nNote: Microsoft Office (desktop) was not found, so HireAce can browse and search but not edit Word, Excel or PowerPoint files."
  }
  $answer = [System.Windows.Forms.MessageBox]::Show(
    "HireAce is installed.$officeNote`n`nStart it any time with the 'HireAce' shortcut on your desktop. It opens as a small panel; minimize it to keep HireAce on standby, close it to quit HireAce.`n`nStart it now?",
    $title, 'YesNo', 'Information')
  if ($answer -eq 'Yes') {
    Start-Process (Join-Path $env:WINDIR 'System32\wscript.exe') -ArgumentList "`"$dest\hireace.vbs`""
  }
} catch {
  Stop-Setup "Setup stopped: $($_.Exception.Message)`n`nDetails are in $log"
}
