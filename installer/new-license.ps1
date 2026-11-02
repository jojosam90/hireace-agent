<#
.SYNOPSIS
  Makes HireAce license codes to give to customers.

.DESCRIPTION
  Prints new codes (like AS7K-JJHH-K7QD) and adds them, with the date and who they
  are for, to issued-licenses.csv next to this script. The first run makes the
  secret key (license-secret.txt); keep that file safe and never share or commit it:
  every installer built with it accepts the codes made with it, and a new key makes
  all earlier codes invalid for new installers.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\installer\new-license.ps1 -Count 3 -For "Consap"
#>
param(
  [int]$Count = 1,
  # Who the codes are for (kept in issued-licenses.csv)
  [string]$For = ''
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'license.ps1')

$secretFile = Join-Path $PSScriptRoot 'license-secret.txt'
if (-not (Test-Path $secretFile)) {
  $bytes = New-Object byte[] 32
  (New-Object System.Security.Cryptography.RNGCryptoServiceProvider).GetBytes($bytes)
  ($bytes | ForEach-Object { $_.ToString('x2') }) -join '' | Set-Content -Encoding ascii $secretFile
  Write-Host "Made a new secret key: $secretFile (keep it safe, never share or commit it)" -ForegroundColor Yellow
}
$secret = (Get-Content $secretFile -Raw).Trim()

$issued = Join-Path $PSScriptRoot 'issued-licenses.csv'
if (-not (Test-Path $issued)) { 'code,issued,for' | Set-Content -Encoding utf8 $issued }
1..$Count | ForEach-Object {
  $code = New-LicenseCode $secret
  "$code,$(Get-Date -Format 'yyyy-MM-dd'),$($For -replace ',', ' ')" | Add-Content -Encoding utf8 $issued
  $code
}
