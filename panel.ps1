<#
.SYNOPSIS
  Open the floating HireAce panel (for example after closing it). HireAce itself must
  be running (start.ps1).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\panel.ps1
#>

# The floating panel: the web app in a compact Chrome app window (no tabs or address
# bar) on its own profile, so the microphone permission is remembered and it never
# mixes with your everyday Chrome or the agent's browser.
$panelProfile = Join-Path $env:USERPROFILE '.hireace-agent\panel-profile'

Add-Type -Namespace HireAce -Name Win32 -MemberDefinition @'
[DllImport("user32.dll")]
public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
[DllImport("user32.dll")]
public static extern int GetWindowLong(IntPtr hWnd, int nIndex);
[DllImport("user32.dll")]
public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")]
public static extern bool SetForegroundWindow(IntPtr hWnd);
'@

# Starts a program with no window at all, not even a terminal: on Windows 11,
# Windows Terminal shows programs started with -WindowStyle Hidden anyway
function Start-NoWindow([string]$exe, [string]$arguments, [string]$dir = $PWD.Path) {
  $info = New-Object System.Diagnostics.ProcessStartInfo $exe, $arguments
  $info.UseShellExecute = $false
  $info.CreateNoWindow = $true
  $info.WorkingDirectory = $dir
  [System.Diagnostics.Process]::Start($info)
}

function Get-PanelProcesses {
  Get-CimInstance Win32_Process -Filter "Name = 'chrome.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($panelProfile) }
}

# The panel's window (titled after the page once it has loaded), or nothing
function Get-PanelWindow {
  Get-PanelProcesses |
    ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue } |
    Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero -and $_.MainWindowTitle -like 'HireAce*' } |
    Select-Object -First 1
}

# Bring the open panel to the front (from the taskbar or the mascot too), else open it
function Show-Panel {
  $window = Get-PanelWindow
  if (-not $window) { Open-Panel; return }
  [void][HireAce.Win32]::ShowWindow($window.MainWindowHandle, 9)  # SW_RESTORE
  [void][HireAce.Win32]::SetForegroundWindow($window.MainWindowHandle)
}

function Open-Panel {
  $chrome = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
  ) | Where-Object { Test-Path $_ } | Select-Object -First 1
  if (-not $chrome) {
    Write-Warning 'Chrome not found: open http://localhost:3001 yourself.'
    return
  }

  # Top-right corner of the primary screen, above the taskbar
  Add-Type -AssemblyName System.Windows.Forms
  $area = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
  $height = [Math]::Min(860, $area.Height - 40)
  $x = $area.Right - 400
  $y = $area.Top + 20
  Start-Process $chrome -ArgumentList @(
    '--app=http://localhost:3001', "--user-data-dir=`"$panelProfile`"",
    "--window-size=380,$height", "--window-position=$x,$y",
    '--no-first-run', '--no-default-browser-check'
  )

  # Keep it above other windows; it still moves by dragging its title bar. Wait for
  # the real panel window (titled after the page, once it has loaded): Chrome may
  # show a short-lived window first, and setting that one on top does nothing.
  $deadline = (Get-Date).AddSeconds(30)
  while ((Get-Date) -lt $deadline) {
    $window = Get-PanelWindow
    if ($window) {
      # HWND_TOPMOST; SWP_NOMOVE | SWP_NOSIZE. Check it took (WS_EX_TOPMOST = 0x8).
      [void][HireAce.Win32]::SetWindowPos($window.MainWindowHandle, [IntPtr](-1), 0, 0, 0, 0, 0x0003)
      if ([HireAce.Win32]::GetWindowLong($window.MainWindowHandle, -20) -band 0x8) {
        # The little HireAce agent that floats on the desktop while the panel is
        # minimized (it quits when the panel closes)
        $bubble = Join-Path $PSScriptRoot 'bubble.ps1'
        $null = Start-NoWindow 'powershell.exe' ("-NoProfile -ExecutionPolicy Bypass -File " +
          "`"$bubble`" -Panel $($window.MainWindowHandle.ToInt64())")
        return
      }
    }
    Start-Sleep -Milliseconds 300
  }
  Write-Warning 'Could not keep the HireAce panel on top.'
}

# Run directly: show the panel. Dot-sourced by start.ps1: only define the functions.
if ($MyInvocation.InvocationName -ne '.') {
  if (Get-PanelProcesses) { Show-Panel } else { Open-Panel }
}
