# The text of the page showing in a browser window (e.g. an email open in Gmail), in
# reading order, through Windows UI Automation, as JSON. Exact words and numbers,
# unlike reading them off a screenshot. -Text picks the window whose title contains
# it (e.g. "Seaview" or "Gmail"), -Window that window handle; else the front one.
# Used by local_desktop.read_browser_window.
param([string]$Text = "", [long]$Window = 0, [int]$MaxChars = 12000)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type -Namespace HireAce -Name Win -MemberDefinition '[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();'

$A = [System.Windows.Automation.AutomationElement]
$ids = @{}
foreach ($name in "chrome", "msedge", "firefox", "brave", "opera") {
  foreach ($p in Get-Process -Name $name -ErrorAction SilentlyContinue) { $ids[[int]$p.Id] = $true }
}
$front = [int][HireAce.Win]::GetForegroundWindow()
$target = $null
foreach ($w in $A::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,
    [System.Windows.Automation.Condition]::TrueCondition)) {
  if (-not $ids.ContainsKey($w.Current.ProcessId)) { continue }
  if ($Window) {
    if ([long]$w.Current.NativeWindowHandle -eq $Window) { $target = $w; break }
  } elseif ($Text) {
    if ($w.Current.Name -like "*$Text*") { $target = $w; break }
  } elseif ([int]$w.Current.NativeWindowHandle -eq $front) {
    $target = $w; break
  }
}
if (-not $target) {
  @{ found = $false } | ConvertTo-Json -Compress
  exit 0
}

# Gmail shows a conversation with older emails folded up and quoted parts behind
# "•••": unfold them first ("Expand all", "Show trimmed content"), or the text of
# the request (e.g. its quantity table) is not on the page at all. These buttons only
# show text; nothing else is pressed.
$isButton = New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty,
  [System.Windows.Automation.ControlType]::Button)
$pressed = 0
foreach ($b in $target.FindAll([System.Windows.Automation.TreeScope]::Descendants, $isButton)) {
  $label = $b.Current.Name
  if ($label -eq "Expand all" -or $label -eq "Show trimmed content") {
    try {
      $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
      $pressed++
    } catch {}
  }
}
if ($pressed) { Start-Sleep -Milliseconds 1200 }

# The page itself (not the browser's tabs and toolbar), then its text in order
$doc = $target.FindFirst([System.Windows.Automation.TreeScope]::Descendants,
  (New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Document)))
$scope = if ($doc) { $doc } else { $target }
$isText = New-Object System.Windows.Automation.PropertyCondition($A::ControlTypeProperty,
  [System.Windows.Automation.ControlType]::Text)
$lines = New-Object System.Collections.Generic.List[string]
$length = 0
foreach ($e in $scope.FindAll([System.Windows.Automation.TreeScope]::Descendants, $isText)) {
  $line = $e.Current.Name.Trim()
  if (-not $line) { continue }
  $lines.Add($line)
  $length += $line.Length + 1
  if ($length -gt $MaxChars) { break }
}
@{
  found = $true
  title = $target.Current.Name
  text = ($lines -join "`n")
  truncated = $length -gt $MaxChars
} | ConvertTo-Json -Compress
