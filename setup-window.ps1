<#
.SYNOPSIS
  Set everything up, then run the whole app on this machine's network address and open it in its
  own app window (Edge/Chrome app mode: no address bar, own taskbar icon). Same as setup-window.sh.

.DESCRIPTION
  - Serves https://<this machine's LAN IP>:8443 (set BACKEND_HTTPS_PORT to change it). Phones and
    tablets on the same Wi-Fi can open the printed link. HTTPS is required: browsers only allow
    the camera on a non-localhost address over HTTPS.
  - Uses a self-signed certificate made for this LAN IP (backend\certs\, kept per IP). The app
    window trusts exactly that certificate; a phone shows a warning once - accept it.
  - Reachable from the network means protected: a pairing token is generated into backend\.env
    if none is set, and the printed links carry it.
  - Closing the app window stops the server.

.EXAMPLE
  .\setup-window.cmd                             # double-click friendly, bypasses script policy
  powershell -ExecutionPolicy Bypass -File .\setup-window.ps1
  .\setup-window.ps1 -NoDetection
#>
[CmdletBinding()]
param(
    [switch]$NoDetection
)

$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"

function Write-Warn([string]$Message) { Write-Host $Message -ForegroundColor Red }
function Quote([string]$Value) { return '"' + $Value + '"' }  # Start-Process doesn't quote for us

$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$RunDir = Join-Path $Root ".run"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

# --- 1. setup: install/verify everything (seconds when nothing changed) ---
& (Join-Path $Root "setup.ps1") -SkipTests -NoSummary -NoDetection:$NoDetection
if ($LASTEXITCODE -ne 0) { exit 1 }

Set-Location $Backend
$VenvDir = ".venv"
if ((Test-Path ".venv") -and -not (Test-Path ".venv\Scripts")) { $VenvDir = ".venv-windows" }
$VenvPython = Join-Path $Backend "$VenvDir\Scripts\python.exe"

# --- 2. LAN address, certificate for it, pairing token (scripts\lan.py - shared with the .sh) ---
$LanIp = (& $VenvPython scripts\lan.py ip | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or -not $LanIp) {
    Write-Warn "ERROR: no network connection found - connect to Wi-Fi/Ethernet first (or use .\setup.ps1 -Run for localhost)."
    exit 1
}
$Port = "8443"
if ($env:BACKEND_HTTPS_PORT) { $Port = $env:BACKEND_HTTPS_PORT }

$certInfo = (& $VenvPython scripts\lan.py cert $LanIp | Out-String).Trim().Split("|")
if ($LASTEXITCODE -ne 0 -or $certInfo.Count -ne 3) { Write-Warn "ERROR: certificate generation failed."; exit 1 }
$Cert, $Key, $Spki = $certInfo

$tokenInfo = (& $VenvPython scripts\lan.py token | Out-String).Trim().Split("|")
$Token = $tokenInfo[0]
if ($tokenInfo[1] -eq "generated") {
    Write-Host "Generated a pairing token and saved it in backend\.env (devices need it once, via the link below)."
}

# --- 3. the server's environment: backend\.env, plus what this launcher decides ---
foreach ($l in Get-Content ".env" -Encoding UTF8) {
    if ($l -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim().Trim('"').Trim("'"), "Process")
    }
}
$env:BACKEND_PAIRING_TOKEN = $Token
$env:DETECTION_ENABLED = "false"
if (-not $NoDetection) {
    & $VenvPython -c "import importlib.util as u, sys; sys.exit(0 if u.find_spec('ultralytics') and u.find_spec('mediapipe') else 1)"
    if ($LASTEXITCODE -eq 0) { $env:DETECTION_ENABLED = "true" }
}

if (Get-NetTCPConnection -LocalPort ([int]$Port) -State Listen -ErrorAction SilentlyContinue) {
    Write-Warn "ERROR: something is already listening on port $Port - close it or set BACKEND_HTTPS_PORT."
    exit 1
}

# --- 4. start the server on all interfaces, HTTPS, in the background ---
$Log = Join-Path $RunDir "server.log"
$ErrLog = Join-Path $RunDir "server.err.log"
$serverArgs = "-m uvicorn app.main:app --host 0.0.0.0 --port $Port --ssl-certfile $(Quote $Cert) --ssl-keyfile $(Quote $Key)"
Write-Host "Starting the server on https://$($LanIp):$Port (log: .run\server.err.log)..."
$Server = Start-Process -FilePath $VenvPython -ArgumentList $serverArgs -WorkingDirectory $Backend `
    -RedirectStandardOutput $Log -RedirectStandardError $ErrLog -WindowStyle Hidden -PassThru

try {
    $up = $false
    for ($i = 0; $i -lt 60; $i++) {
        & curl.exe -sk "https://127.0.0.1:$Port/health" *> $null
        if ($LASTEXITCODE -eq 0) { $up = $true; break }
        if ($Server.HasExited) { break }
        Start-Sleep -Seconds 1
    }
    if (-not $up) {
        Write-Warn "ERROR: the server did not start:"
        Get-Content $ErrLog -Tail 20 -ErrorAction SilentlyContinue
        exit 1
    }

    $AppUrl = "https://$($LanIp):$Port/?token=$Token"
    if ($env:DETECTION_ENABLED -eq "true") { $AppUrl = "$AppUrl&detect=1" }
    Write-Host ""
    Write-Host "Running." -ForegroundColor Green -NoNewline
    Write-Host " On a phone/tablet on the same network, open (accept the certificate warning once):"
    Write-Host "    $AppUrl"
    Write-Host "  (Windows may ask to allow Python through the firewall - allow it on private networks.)"
    Write-Host ""

    # --- 5. the app window: Edge/Chrome in app mode, own profile ---
    $candidates = @(
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    $Browser = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $Browser) {
        Write-Host "No Edge/Chrome found for an app window - open the link above in any browser."
        Read-Host "Press Enter to stop the server"
        exit 0
    }

    $AppProfile = Join-Path $RunDir "app-profile"
    $browserArgs = @(
        "--app=$(Quote $AppUrl)",
        "--user-data-dir=$(Quote $AppProfile)",
        "--ignore-certificate-errors-spki-list=$Spki",
        "--test-type",  # hides the "unsupported command-line flag" warning bar the line above causes
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,860"
    ) -join " "

    # Every process of the app window carries its own --user-data-dir. The first one can hand the
    # window to a process that's still around from an earlier run and exit at once, so its exit
    # means nothing - the window is open for as long as any process with this profile exists.
    function Test-AppWindowOpen {
        try {
            $procs = Get-CimInstance Win32_Process -Filter "Name='msedge.exe' OR Name='chrome.exe'" -ErrorAction Stop
        } catch {
            return $true  # the process query hiccuped - can't tell, so don't stop anyone's demo
        }
        return [bool]($procs | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($AppProfile) } | Select-Object -First 1)
    }

    # The window's own profile allows the camera and microphone for this address up front.
    & $VenvPython scripts\app_window.py grant --profile $AppProfile --origin $AppUrl
    Write-Host "Opening the app window - close it to stop the server."
    Start-Process -FilePath $Browser -ArgumentList $browserArgs | Out-Null
    for ($i = 0; $i -lt 30 -and -not (Test-AppWindowOpen); $i++) { Start-Sleep -Milliseconds 500 }
    # Closed = two checks in a row (4 s apart) find no app-window process.
    $misses = 0
    while ($misses -lt 2) {
        if (Test-AppWindowOpen) { $misses = 0 } else { $misses++ }
        Start-Sleep -Seconds 2
    }
}
finally {
    # Runs on a normal exit, an error, and Ctrl+C. /T: the venv python.exe is a launcher with a
    # child interpreter - end the whole tree.
    if ($Server -and -not $Server.HasExited) {
        & taskkill.exe /F /T /PID $Server.Id *> $null
    }
    Write-Host "Server stopped."
}
exit 0
