<#
.SYNOPSIS
  Open the Cooking Assistant in seconds. Double-click start.cmd, or run .\start.ps1.

.DESCRIPTION
  - Runs setup.ps1 only the first time, or after a requirement or detector setting changed.
    Every other start skips it.
  - One server, two addresses:
      http://localhost:8000      this computer, any browser (no certificate warning)
      https://<LAN IP>:8443      phones/tablets on the same Wi-Fi (accept the certificate once)
  - Opens the app in its own window with the camera and microphone already allowed.
    Closing the window stops the server.
  - Object/hand detection is on whenever it's installed.

.EXAMPLE
  .\start.cmd                  # double-click friendly
  .\start.ps1 -NoWindow        # serve only; open the links in any browser; Ctrl+C stops
  .\start.ps1 -LocalOnly       # this computer only: no LAN address, no firewall prompt
#>
[CmdletBinding()]
param(
    [switch]$NoWindow,
    [switch]$LocalOnly,
    [switch]$NoDetection
)

$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Warn([string]$Message) { Write-Host $Message -ForegroundColor Red }
function Quote([string]$Value) { return '"' + $Value + '"' }  # Start-Process doesn't quote for us

$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$RunDir = Join-Path $Root ".run"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
$Started = Get-Date

function Get-VenvPython {
    $dir = ".venv"
    if ((Test-Path (Join-Path $Backend ".venv")) -and -not (Test-Path (Join-Path $Backend ".venv\Scripts"))) { $dir = ".venv-windows" }
    return (Join-Path $Backend "$dir\Scripts\python.exe")
}

# --- 1. setup, only when something changed since the last successful one ---
$VenvPython = Get-VenvPython
$ready = $false
if (Test-Path $VenvPython) {
    & $VenvPython (Join-Path $Backend "scripts\setup_stamp.py") check
    $ready = ($LASTEXITCODE -eq 0)
}
if (-not $ready) {
    Write-Host "First start, or something changed - running setup once (later starts skip it)..."
    & (Join-Path $Root "setup.ps1") -SkipTests -NoSummary -NoDetection:$NoDetection
    if ($LASTEXITCODE -ne 0) { exit 1 }
    $VenvPython = Get-VenvPython
}
Set-Location $Backend

$Port = "8000"
if ($env:BACKEND_PORT) { $Port = $env:BACKEND_PORT }
$LanPort = "8443"
if ($env:BACKEND_HTTPS_PORT) { $LanPort = $env:BACKEND_HTTPS_PORT }
$Health = "http://127.0.0.1:$Port/health"

# --- 2. pairing token, and this machine's LAN address + certificate (one call) ---
$lan = (& $VenvPython scripts\lan.py all | Out-String).Trim().Split("|")
if ($LASTEXITCODE -ne 0 -or $lan.Count -ne 6) { Write-Warn "ERROR: scripts\lan.py failed."; exit 1 }
$Token, $TokenState, $LanIp, $Cert, $Key, $Spki = $lan
if ($TokenState -eq "generated") { Write-Host "Generated a pairing token in backend\.env (links below carry it)." }
if ($LocalOnly) { $LanIp = "" }

$LocalUrl = "http://localhost:$Port/?token=$Token&detect=1"
$AppProfile = Join-Path $RunDir "app-profile"

# Already running (a second double-click): just bring up a window.
& curl.exe -s -o NUL $Health
if ($LASTEXITCODE -eq 0) {
    Write-Host "Already running - opening the app window."
    & $VenvPython scripts\app_window.py open --url $LocalUrl --profile $AppProfile
    exit 0
}

# --- 3. the server: both addresses, one process, in the background ---
$Log = Join-Path $RunDir "server.log"
$ErrLog = Join-Path $RunDir "server.err.log"
$serverArgs = "scripts\serve.py --port $Port"
if ($LanIp) { $serverArgs += " --lan-port $LanPort --cert $(Quote $Cert) --key $(Quote $Key)" }
if ($NoDetection) { $serverArgs += " --detection off" }
$env:BACKEND_PAIRING_TOKEN = $Token
$Server = Start-Process -FilePath $VenvPython -ArgumentList $serverArgs -WorkingDirectory $Backend `
    -RedirectStandardOutput $Log -RedirectStandardError $ErrLog -WindowStyle Hidden -PassThru

try {
    $up = $false
    for ($i = 0; $i -lt 240; $i++) {
        & curl.exe -s -o NUL $Health
        if ($LASTEXITCODE -eq 0) { $up = $true; break }
        if ($Server.HasExited) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not $up) {
        Write-Warn "ERROR: the server did not start (is port $Port or $LanPort already in use?):"
        Get-Content $ErrLog -Tail 20 -ErrorAction SilentlyContinue
        exit 1
    }
    $secs = [math]::Round(((Get-Date) - $Started).TotalSeconds, 1)

    Write-Host ""
    Write-Host "Cooking Assistant is running ($secs s)." -ForegroundColor Green
    Write-Host "  This computer, any browser:  $LocalUrl"
    if ($LanIp) {
        Write-Host "  Phone/tablet on this Wi-Fi:  https://$($LanIp):$LanPort/?token=$Token&detect=1"
        Write-Host "      (accept the certificate warning once; Windows may ask to allow Python on private networks)"
    }
    Write-Host "  Press the big Start button and allow the camera. Detection starts by itself (first frames: 'loading model')."
    Write-Host "  Server log: .run\server.err.log"
    Write-Host ""

    if ($NoWindow) {
        Write-Host "Serving - Ctrl+C stops it."
        Wait-Process -Id $Server.Id
        exit 0
    }

    # --- 4. the app window: own profile, camera + microphone allowed for localhost ---
    & $VenvPython scripts\app_window.py open --url $LocalUrl --profile $AppProfile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "No Edge/Chrome for an app window - open the link above in any browser. Ctrl+C stops the server."
        Wait-Process -Id $Server.Id
        exit 0
    }

    # Every process of the app window carries its own --user-data-dir. The first one can hand the
    # window to a process that's still around and exit at once, so its exit means nothing - the
    # window is open for as long as any process with this profile exists.
    function Test-AppWindowOpen {
        try {
            $procs = Get-CimInstance Win32_Process -Filter "Name='msedge.exe' OR Name='chrome.exe'" -ErrorAction Stop
        } catch {
            return $true  # the process query hiccuped - can't tell, so don't stop anyone's demo
        }
        return [bool]($procs | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($AppProfile) } | Select-Object -First 1)
    }
    Write-Host "Close the app window to stop the server (links above keep working until then)."
    for ($i = 0; $i -lt 30 -and -not (Test-AppWindowOpen); $i++) { Start-Sleep -Milliseconds 500 }
    # Closed = two checks in a row (4 s apart) find no app-window process.
    $misses = 0
    while ($misses -lt 2) {
        if (Test-AppWindowOpen) { $misses = 0 } else { $misses++ }
        Start-Sleep -Seconds 2
    }
}
finally {
    # Normal exit, error, and Ctrl+C. /T: the venv python.exe is a launcher with a child
    # interpreter - end the whole tree.
    if ($Server -and -not $Server.HasExited) {
        & taskkill.exe /F /T /PID $Server.Id *> $null
    }
    Write-Host "Server stopped."
}
exit 0
