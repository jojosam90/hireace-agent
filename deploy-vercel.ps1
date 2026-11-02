<#
.SYNOPSIS
  Puts the HireAce web app on Vercel, to use it from a phone on any network.

.DESCRIPTION
  The agent still runs on this PC (start.ps1); the Vercel site only joins the same
  LiveKit calls, so it works from any Wi-Fi or mobile data, with no tunnel. Copies
  this PC's LiveKit settings to the Vercel project, sets the access code the site
  asks for (or none: then anyone with the link can start a call that controls this
  PC), and deploys. The site is an installable app on the phone (Add to Home screen).
  Run it again after changing the web app. The site serves every installation: each
  PC's panel shows its own phone link (?pc=<agent name>), and this script saves the
  site's address (PHONE_SITE_URL) for this PC's panel.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\deploy-vercel.ps1 -AccessCode 482915
#>
param(
  # The code the phone asks for once; asked here when not given
  [string]$AccessCode,
  # No code at all: anyone with the link can start a call that controls this PC
  [switch]$NoAccessCode
)

$ErrorActionPreference = 'Stop'
$web = Join-Path $PSScriptRoot 'agent\frontend'
# This PC's agent name, as start.ps1 makes it (made here if HireAce never started)
$nameFile = Join-Path $HOME '.hireace-agent\agent-name'
if (-not (Test-Path $nameFile)) {
  New-Item -ItemType Directory -Force (Split-Path $nameFile) | Out-Null
  'hireace-' + [guid]::NewGuid().ToString('N').Substring(0, 10) | Set-Content -Encoding ascii $nameFile
}

$code = if ($NoAccessCode) { '' } elseif ($AccessCode) { $AccessCode } else {
  Read-Host 'Access code for the site (the phone asks for it once; leave empty for no code)'
}
# The Vercel CLI writes progress and hints to its error stream. Windows PowerShell
# turns that into errors (which stop this script), so its output is read as plain
# text here and success is judged by its exit code.
function Invoke-Vercel {
  $ErrorActionPreference = 'Continue'
  $input | & vercel @args 2>&1 | ForEach-Object { "$_" }
}

Push-Location $web
try {
  # Its own Vercel project: this code was copied from an earlier project, whose link (and
  # live site) must never be deployed over
  $linked = if (Test-Path '.vercel\project.json') { (Get-Content '.vercel\project.json' -Raw | ConvertFrom-Json).projectName }
  if ($linked -ne 'hireace-agent') {
    Invoke-Vercel link --yes --project hireace-agent | Out-Host
    if ($LASTEXITCODE) { throw 'vercel link failed' }
  }

  function Set-VercelEnv([string]$name, [string]$value) {
    Invoke-Vercel env rm $name production --yes | Out-Null  # fine if it was not set
    $value | Invoke-Vercel env add $name production | Out-Null
    if ($LASTEXITCODE) { throw "vercel env add $name failed" }
    Write-Host "set $name"
  }
  $keep = '^(LIVEKIT_URL|LIVEKIT_API_KEY|LIVEKIT_API_SECRET|NEXT_PUBLIC_APP_CONFIG_ENDPOINT|SANDBOX_ID)='
  foreach ($line in Get-Content '.env.local' | Where-Object { $_ -match $keep }) {
    $name, $value = $line -split '=', 2
    Set-VercelEnv $name $value.Trim()
  }
  # No default PC: a phone controls the PC whose phone link it opened
  Invoke-Vercel env rm AGENT_NAME production --yes | Out-Null
  if ($code) {
    Set-VercelEnv 'HIREACE_ACCESS_CODE' $code.Trim()
    Invoke-Vercel env rm HIREACE_OPEN_ACCESS production --yes | Out-Null
  } else {
    Set-VercelEnv 'HIREACE_OPEN_ACCESS' 'true'
    Invoke-Vercel env rm HIREACE_ACCESS_CODE production --yes | Out-Null
  }

  $output = Invoke-Vercel deploy --prod | Tee-Object -Variable lines
  $output | Out-Host
  if ($LASTEXITCODE) { throw 'vercel deploy failed' }

  # The site's own address (the short alias, not this deployment's long one)
  $site = ($lines | Select-String -Pattern 'Aliased:\s*(https://\S+)' | Select-Object -First 1).Matches.Groups[1].Value
  if (-not $site) { $site = 'https://hireace-agent.vercel.app' }
  $site = $site.TrimEnd('/')
  # This PC's panel shows the phone link and QR code for it (after its next build)
  $settings = @(Get-Content '.env.local' | Where-Object { $_ -notmatch '^PHONE_SITE_URL=' }) + "PHONE_SITE_URL=$site"
  [IO.File]::WriteAllLines((Join-Path $web '.env.local'), [string[]]$settings, (New-Object Text.UTF8Encoding $false))
} finally {
  Pop-Location
}
$link = "$site/?pc=$((Get-Content $nameFile -Raw).Trim())"
Write-Host "This PC's phone link: $link" -ForegroundColor Green
Write-Host 'Also in the HireAce panel (Use from your phone, with a QR code) after restarting start.ps1.'
