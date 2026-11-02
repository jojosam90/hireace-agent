# Sends one email from the Gmail signed in in the user's own browser (Edge, Chrome...)
# through Windows UI Automation. Reads JSON from stdin: browser (process name), email
# (the account), url (Gmail's compose page, already filled in), subject, files (full
# paths). Writes JSON: {sent: true} or {sent: false, reason, maybe_sent}.
# Used by gmail.py, only after the user approved this very email.
#
# Send is pressed only on the compose page showing this email's subject in this
# account, so another draft the user has open is never sent. "Attach files" takes one
# real mouse click (it cannot be pressed otherwise); the mouse goes back afterwards.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type -Namespace HireAce -Name Mouse -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern bool GetCursorPos(out System.Drawing.Point p);
[DllImport("user32.dll")] public static extern void mouse_event(int flags, int x, int y, int data, int extra);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr hwnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr hwnd, int cmd);
[DllImport("user32.dll")] public static extern bool IsIconic(System.IntPtr hwnd);
[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(System.IntPtr hwnd, System.IntPtr pid);
[DllImport("user32.dll")] public static extern bool AttachThreadInput(uint from, uint to, bool attach);
[DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
[DllImport("user32.dll")] public static extern System.IntPtr GetDlgItem(System.IntPtr dialog, int id);
[DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern System.IntPtr FindWindowEx(System.IntPtr parent, System.IntPtr after, string className, string title);
[DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern System.IntPtr SendMessage(System.IntPtr hwnd, int message, System.IntPtr wParam, string lParam);
[DllImport("user32.dll")] public static extern bool PostMessage(System.IntPtr hwnd, int message, System.IntPtr wParam, System.IntPtr lParam);
[DllImport("user32.dll")] public static extern bool IsWindow(System.IntPtr hwnd);
'@ -ReferencedAssemblies System.Drawing
[void][HireAce.Mouse]::SetProcessDPIAware()

$A = [System.Windows.Automation.AutomationElement]
$CT = [System.Windows.Automation.ControlType]
$Descendants = [System.Windows.Automation.TreeScope]::Descendants
$Children = [System.Windows.Automation.TreeScope]::Children
$job = [Console]::In.ReadToEnd() | ConvertFrom-Json
$script:sendPressed = $false
# Anything unexpected: say so, and whether Send had been pressed
trap {
  @{
    sent = $false
    maybe_sent = $script:sendPressed
    reason = "Sending stopped: $($_.Exception.Message) (line $($_.InvocationInfo.ScriptLineNumber))"
  } | ConvertTo-Json -Compress
  exit 0
}

function Finish($result) {
  $result | ConvertTo-Json -Compress
  exit 0
}
function Of-Type($type) {
  New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty, $type)
}
function Invoke-Element($element) {
  $element.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}
# The Subject box showing this email's subject, in this window
function Get-SubjectBox($window) {
  foreach ($edit in $window.FindAll($Descendants, (Of-Type $CT::Edit))) {
    if ($edit.Current.Name -ne 'Subject') { continue }
    try {
      $value = $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).Current.Value
    } catch { continue }
    if ($value -ceq $job.subject) { return $edit }
  }
  return $null
}
function Get-Button($window, [string]$namePrefix) {
  foreach ($button in $window.FindAll($Descendants, (Of-Type $CT::Button))) {
    if ($button.Current.Name -like "$namePrefix*") { return $button }
  }
  return $null
}
function Close-Tab($tab) {
  try {
    Invoke-Element $tab.FindFirst($Descendants, (Of-Type $CT::Button))
  } catch { }
}
# Windows only lets the foreground thread hand over focus: borrow its input queue
function Show-InFront([IntPtr]$handle) {
  if ([HireAce.Mouse]::IsIconic($handle)) { [void][HireAce.Mouse]::ShowWindow($handle, 9) }
  $here = [HireAce.Mouse]::GetCurrentThreadId()
  $front = [HireAce.Mouse]::GetWindowThreadProcessId([HireAce.Mouse]::GetForegroundWindow(), [IntPtr]::Zero)
  [void][HireAce.Mouse]::AttachThreadInput($here, $front, $true)
  [void][HireAce.Mouse]::SetForegroundWindow($handle)
  [void][HireAce.Mouse]::AttachThreadInput($here, $front, $false)
}
# Is this button really what is under the point (nothing covering it)?
function Test-UnderPoint($button, [int]$x, [int]$y) {
  try {
    $element = $A::FromPoint((New-Object System.Windows.Point($x, $y)))
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    for ($i = 0; $element -and $i -lt 4; $i++) {
      if ([System.Windows.Automation.Automation]::Compare($element, $button)) { return $true }
      $element = $walker.GetParent($element)
    }
  } catch { }
  return $false
}
# Not sent after all: no draft left behind, and the tab it opened closed
function Abandon($window, $tab, [string]$reason) {
  try {
    $discard = Get-Button $window 'Discard draft'
    if ($discard) { Invoke-Element $discard; Start-Sleep -Milliseconds 500 }
  } catch { }
  if ($tab) { Close-Tab $tab }
  Finish @{ sent = $false; maybe_sent = $false; reason = $reason }
}

$running = @(Get-Process -Name $job.browser -ErrorAction SilentlyContinue)
$exe = ($running | Where-Object Path | Select-Object -First 1).Path
if (-not $exe) { Finish @{ sent = $false; maybe_sent = $false; reason = "$($job.browser) is not open." } }
$ids = @{}
foreach ($p in $running) { $ids[[int]$p.Id] = $true }
# A minimized browser window shows no tabs or pages to Windows: bring it back
foreach ($w in $A::RootElement.FindAll($Children, [System.Windows.Automation.Condition]::TrueCondition)) {
  if ($ids.ContainsKey($w.Current.ProcessId) -and $w.Current.NativeWindowHandle) {
    $handle = [IntPtr]$w.Current.NativeWindowHandle
    if ([HireAce.Mouse]::IsIconic($handle)) { [void][HireAce.Mouse]::ShowWindow($handle, 9) }
  }
}
Start-Process $exe $job.url

# Gmail's compose page, loaded and showing this subject
$window = $null
$deadline = (Get-Date).AddSeconds(30)
while (-not $window -and (Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds 700
  foreach ($w in $A::RootElement.FindAll($Children, [System.Windows.Automation.Condition]::TrueCondition)) {
    if ($ids.ContainsKey($w.Current.ProcessId) -and (Get-SubjectBox $w)) { $window = $w; break }
  }
}
if (-not $window) {
  Finish @{ sent = $false; maybe_sent = $false; reason = "Gmail's compose page did not open in $($job.browser) in time." }
}
# The tab it opened: the selected one, closed again at the end
$tab = $null
foreach ($t in $window.FindAll($Descendants, (Of-Type $CT::TabItem))) {
  try {
    if ($t.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Current.IsSelected) { $tab = $t; break }
  } catch { }
}
if ($window.Current.Name -notlike "*$($job.email)*") {
  Abandon $window $tab "Gmail opened in another account, not $($job.email)."
}

foreach ($file in @($job.files)) {
  if (-not $file) { continue }
  $attach = Get-Button $window 'Attach files'
  if (-not $attach) { Abandon $window $tab "Gmail's Attach files button was not found." }
  $back = New-Object System.Drawing.Point
  [void][HireAce.Mouse]::GetCursorPos([ref]$back)
  # In front, with the button really under the cursor; Windows may need a few tries
  $clear = $false
  for ($try = 0; $try -lt 6 -and -not $clear; $try++) {
    Show-InFront ([IntPtr]$window.Current.NativeWindowHandle)
    Start-Sleep -Milliseconds 500
    $box = $attach.Current.BoundingRectangle
    $x = [int]($box.X + $box.Width / 2)
    $y = [int]($box.Y + $box.Height / 2)
    $clear = Test-UnderPoint $attach $x $y
  }
  if (-not $clear) { Abandon $window $tab "Another window is covering Gmail's Attach files button." }
  [void][HireAce.Mouse]::SetCursorPos($x, $y)
  Start-Sleep -Milliseconds 150
  [HireAce.Mouse]::mouse_event(2, 0, 0, 0, 0)
  Start-Sleep -Milliseconds 60
  [HireAce.Mouse]::mouse_event(4, 0, 0, 0, 0)
  Start-Sleep -Milliseconds 150
  [void][HireAce.Mouse]::SetCursorPos($back.X, $back.Y)

  # Windows' Open box (the same in every language: file name 1148, Open 1, Cancel 2)
  $dialogType = New-Object System.Windows.Automation.PropertyCondition($A::ClassNameProperty, '#32770')
  $dialog = $null
  $deadline = (Get-Date).AddSeconds(10)
  while (-not $dialog -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 250
    $dialog = $window.FindFirst($Children, $dialogType)
    if (-not $dialog) {
      foreach ($d in $A::RootElement.FindAll($Children, $dialogType)) {
        if ($ids.ContainsKey($d.Current.ProcessId)) { $dialog = $d; break }
      }
    }
  }
  if (-not $dialog) { Abandon $window $tab "Windows' file box did not open to attach the file." }
  # Through Windows' own messages: UI Automation sees this box's controls as blank
  # panes. The file name box is control 1148 (an Edit inside a ComboBox inside it).
  $dialogHandle = [IntPtr]$dialog.Current.NativeWindowHandle
  $nameBox = [HireAce.Mouse]::GetDlgItem($dialogHandle, 1148)
  $inner = [HireAce.Mouse]::FindWindowEx($nameBox, [IntPtr]::Zero, 'ComboBox', $null)
  if ($inner -ne [IntPtr]::Zero) { $nameBox = $inner }
  $edit = [HireAce.Mouse]::FindWindowEx($nameBox, [IntPtr]::Zero, 'Edit', $null)
  if ($edit -eq [IntPtr]::Zero) {
    [void][HireAce.Mouse]::PostMessage($dialogHandle, 0x0111, [IntPtr]2, [IntPtr]::Zero)  # Cancel
    Abandon $window $tab "Windows' file box was not as expected."
  }
  [void][HireAce.Mouse]::SendMessage($edit, 0x000C, [IntPtr]::Zero, $file)  # WM_SETTEXT
  Start-Sleep -Milliseconds 200
  [void][HireAce.Mouse]::PostMessage($dialogHandle, 0x0111, [IntPtr]1, [IntPtr]::Zero)  # WM_COMMAND, OK
  $deadline = (Get-Date).AddSeconds(10)
  while ([HireAce.Mouse]::IsWindow($dialogHandle) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 200
  }
  if ([HireAce.Mouse]::IsWindow($dialogHandle)) {
    [void][HireAce.Mouse]::PostMessage($dialogHandle, 0x0111, [IntPtr]2, [IntPtr]::Zero)  # Cancel
    Abandon $window $tab "Windows' file box did not accept $file."
  }

  # Added once Gmail shows it by name, uploaded once no bar is moving
  $fileName = Split-Path $file -Leaf
  $uploaded = $false
  $shown = $false
  $deadline = (Get-Date).AddSeconds(90)
  while (-not $uploaded -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 700
    # Inside the page only: the browser's own interface has progress bars too
    $page = $window.FindFirst($Descendants, (Of-Type $CT::Document))
    if (-not $page) { continue }
    $shown = $false
    foreach ($e in $page.FindAll($Descendants, [System.Windows.Automation.Condition]::TrueCondition)) {
      if ($e.Current.Name -like "*$fileName*") { $shown = $true; break }
    }
    $uploaded = $shown -and -not $page.FindFirst($Descendants, (Of-Type $CT::ProgressBar))
  }
  if (-not $uploaded) {
    $what = if ($shown) { 'it is still uploading' } else { 'it never appeared in the email' }
    Abandon $window $tab "Gmail did not finish attaching $fileName in time: $what."
  }
}

# Still this email, in this window: send it
$subject = Get-SubjectBox $window
$send = Get-Button $window 'Send'
if (-not $subject -or -not $send) { Abandon $window $tab "Gmail's compose page changed before sending." }
$script:sendPressed = $true
Invoke-Element $send

# Sent: the compose page has gone
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
  Start-Sleep -Milliseconds 500
  if (-not (Get-SubjectBox $window)) {
    Start-Sleep -Milliseconds 800  # Gmail finishes sending before its tab can close
    if ($tab) { Close-Tab $tab }
    Finish @{ sent = $true }
  }
}
Finish @{
  sent = $false
  maybe_sent = $true
  reason = "Gmail did not confirm sending in time. It is open in $($job.browser): check it, and Sent, before sending again."
}
