<#
.SYNOPSIS
  HireAce license codes: made by new-license.ps1, checked by setup.ps1.

.DESCRIPTION
  A code looks like AS7K-JJHH-K7QD: 8 random letters and digits, then 4 that are
  worked out from them with the secret key (an HMAC), so a mistyped or made-up code
  is refused. Codes are checked on the PC, without a server. Upper or lower case,
  spaces and missing dashes do not matter. The key is in license-secret.txt (never
  committed); the installer carries a copy, so this keeps honest people honest
  rather than stopping a determined one.
#>

# No 0, O, 1 or I: easy to mix up when typed (32 characters left)
$LicenseAlphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

function Get-LicenseCheck([string]$body, [string]$secret) {
  # Trimmed: the key file ends with a line break
  $hmac = New-Object System.Security.Cryptography.HMACSHA256 (, [Text.Encoding]::UTF8.GetBytes($secret.Trim()))
  $hash = $hmac.ComputeHash([Text.Encoding]::ASCII.GetBytes($body))
  -join (0..3 | ForEach-Object { $LicenseAlphabet[$hash[$_] % $LicenseAlphabet.Length] })
}

# "as7k jjhh-k7qd" -> "AS7K-JJHH-K7QD"; "" if it is not 12 letters and digits
function Format-LicenseCode([string]$code) {
  $plain = ($code.ToUpperInvariant() -replace '[\s-]', '')
  if ($plain -notmatch '^[A-Z0-9]{12}$') { return '' }
  "$($plain.Substring(0, 4))-$($plain.Substring(4, 4))-$($plain.Substring(8, 4))"
}

function Test-LicenseCode([string]$code, [string]$secret) {
  $code = Format-LicenseCode $code
  if (-not $code -or -not $secret) { return $false }
  $plain = $code -replace '-', ''
  $plain.Substring(8, 4) -ceq (Get-LicenseCheck $plain.Substring(0, 8) $secret)
}

function New-LicenseCode([string]$secret) {
  $random = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
  $bytes = New-Object byte[] 8
  $random.GetBytes($bytes)
  $body = -join ($bytes | ForEach-Object { $LicenseAlphabet[$_ % $LicenseAlphabet.Length] })
  Format-LicenseCode ($body + (Get-LicenseCheck $body $secret))
}
