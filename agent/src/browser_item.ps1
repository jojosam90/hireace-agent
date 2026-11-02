# Finds a list row on screen in an open browser window (e.g. an email in the Gmail
# inbox) by part of its text, through Windows UI Automation, and returns where to
# click it in screen pixels, as JSON. Only list rows (DataItem, TreeItem): never
# buttons, links or the text of an open email. "unread" finds the topmost unread
# email. If a browser window already shows what was asked for (the email is open),
# it says so instead ("already_open").
# Used by local_desktop.find_browser_item (the agent then double-clicks it).
param([Parameter(Mandatory = $true)][string]$Text)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# Real screen pixels, as the agent's mouse uses (not scaled by Windows display scaling)
Add-Type -Namespace HireAce -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[void][HireAce.Dpi]::SetProcessDPIAware()
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

$A = [System.Windows.Automation.AutomationElement]
$CT = [System.Windows.Automation.ControlType]
$rowTypes = @($CT::DataItem, $CT::TreeItem)
$ids = @{}
foreach ($name in "chrome", "msedge", "firefox", "brave", "opera") {
  foreach ($p in Get-Process -Name $name -ErrorAction SilentlyContinue) { $ids[[int]$p.Id] = $true }
}
$wanted = $Text.Trim()
$unread = $wanted -ieq "unread"

# The whole row: the widest match; among equally wide rows, the topmost
$best = $null
$windows = $A::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,
  [System.Windows.Automation.Condition]::TrueCondition)
foreach ($w in $windows) {
  if (-not $ids.ContainsKey($w.Current.ProcessId)) { continue }
  if (-not $unread -and $w.Current.Name -like "*$wanted*") {
    $open = @{ window = [int]$w.Current.NativeWindowHandle; title = $w.Current.Name }
    @{ found = $false; already_open = $open } | ConvertTo-Json -Depth 3 -Compress
    exit 0
  }
  foreach ($ct in $rowTypes) {
    $cond = New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty, $ct)
    foreach ($e in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)) {
      $name = $e.Current.Name
      if (-not $name -or $e.Current.IsOffscreen) { continue }
      $match = if ($unread) { $name -like "unread,*" } else { $name -like "*$wanted*" }
      if (-not $match) { continue }
      $r = $e.Current.BoundingRectangle
      if ($r.Width -lt 200 -or $r.Height -lt 10) { continue }  # a cell or checkbox, not the row
      $wider = $best -and $r.Width -gt $best.width + 50
      $higher = $best -and [Math]::Abs($r.Width - $best.width) -le 50 -and $r.Y -lt $best.top
      if (-not $best -or $wider -or $higher) {
        $best = @{
          name = $name.Substring(0, [Math]::Min(200, $name.Length))
          window = [int]$w.Current.NativeWindowHandle
          # Left of the row's middle: on the sender and subject, clear of the
          # checkbox, star and the action buttons at the right end
          x = [int]($r.X + [Math]::Min($r.Width / 2, 500))
          y = [int]($r.Y + $r.Height / 2)
          width = [int]$r.Width
          top = [int]$r.Y
        }
      }
    }
  }
}
@{ found = [bool]$best; item = $best } | ConvertTo-Json -Depth 3 -Compress
