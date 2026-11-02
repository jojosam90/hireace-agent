# Lists the tabs of every open browser window (Chrome, Edge, Firefox, Brave, Opera)
# through Windows UI Automation, as JSON. With -Select, also switches to the first
# tab whose name contains that text and returns it as "selected".
# Used by local_desktop.find_browser_tab (one call instead of many screen steps).
param([string]$Select = "")

$ErrorActionPreference = "Stop"
# Tab names can hold any character: write UTF-8, not the console's code page
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

$browsers = "chrome", "msedge", "firefox", "brave", "opera"
$root = [System.Windows.Automation.AutomationElement]::RootElement
$isTab = New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
  [System.Windows.Automation.ControlType]::TabItem)

$windows = @()
$selected = $null
$ids = @{}
foreach ($name in $browsers) {
  foreach ($p in Get-Process -Name $name -ErrorAction SilentlyContinue) { $ids[[int]$p.Id] = $name }
}

$top = $root.FindAll([System.Windows.Automation.TreeScope]::Children,
  [System.Windows.Automation.Condition]::TrueCondition)
foreach ($w in $top) {
  $procId = $w.Current.ProcessId
  if (-not $ids.ContainsKey($procId) -or -not $w.Current.Name) { continue }
  $tabs = @()
  foreach ($t in $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, $isTab)) {
    $tabName = $t.Current.Name
    if (-not $tabName) { continue }
    $tabs += $tabName
    if ($Select -and -not $selected -and $tabName -like "*$Select*") {
      try {
        $t.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
      } catch {
        try { $t.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() } catch {}
      }
      $selected = @{ browser = $ids[$procId]; window = [int]$w.Current.NativeWindowHandle; tab = $tabName }
    }
  }
  $windows += @{
    browser = $ids[$procId]
    window = [int]$w.Current.NativeWindowHandle
    title = $w.Current.Name
    tabs = $tabs
  }
}
@{ windows = $windows; selected = $selected } | ConvertTo-Json -Depth 4 -Compress
