<#
.SYNOPSIS
  Makes the key that signs HireAce updates. Run once.

.DESCRIPTION
  Workstations install an update only if it was signed with the private key
  (installer\release-key.xml, never committed and never on the portal), so getting into
  the portal is not enough to put code on them. The public half goes in
  release-public-key.xml, which is committed and installed on every PC.

  Back the private key up somewhere safe. A new key means PCs refuse updates until
  they get the new public key from a new installer.
#>
$ErrorActionPreference = 'Stop'
$private = Join-Path $PSScriptRoot 'release-key.xml'
$public = Join-Path (Split-Path $PSScriptRoot -Parent) 'release-public-key.xml'
if (Test-Path $private) { throw "There is already a key: $private" }

$rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider 3072
try {
  $rsa.PersistKeyInCsp = $false
  Set-Content -Path $private -Encoding ascii -Value $rsa.ToXmlString($true)
  Set-Content -Path $public -Encoding ascii -Value $rsa.ToXmlString($false)
} finally {
  $rsa.Clear()
}
Write-Host "Private key: $private (back it up, never share or commit it)" -ForegroundColor Yellow
Write-Host "Public key: $public (commit this one)"
