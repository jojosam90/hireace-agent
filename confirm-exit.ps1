<#
.SYNOPSIS
  Asks whether to exit HireAce. Exit code 6 is Yes, 7 is No. Started by panel.ps1.
#>

Add-Type -AssemblyName System.Windows.Forms

# An invisible always-on-top owner, so the question is in front of whatever is open
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = 'None'
$owner.Opacity = 0
$owner.Size = New-Object System.Drawing.Size 1, 1
$owner.StartPosition = 'CenterScreen'
$owner.Show()
$owner.Activate()

# Nobody answers in under a third of a second: a box that closed by itself is asked again
$answer = [System.Windows.Forms.DialogResult]::No
foreach ($try in 1..3) {
  $asked = Get-Date
  $answer = [System.Windows.Forms.MessageBox]::Show(
    $owner,
    "Exit HireAce?`n`nIt will stop until you start it again from the desktop icon.",
    'HireAce',
    [System.Windows.Forms.MessageBoxButtons]::YesNo,
    [System.Windows.Forms.MessageBoxIcon]::Question,
    [System.Windows.Forms.MessageBoxDefaultButton]::Button2)
  if (((Get-Date) - $asked).TotalMilliseconds -ge 300) { break }
  $answer = [System.Windows.Forms.DialogResult]::No
}
$owner.Close()
exit [int]$answer  # DialogResult's Yes and No are 6 and 7
