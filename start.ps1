<#
.SYNOPSIS
  Open the Cooking Assistant in seconds. Double-click start.cmd, or run .\start.ps1.

.DESCRIPTION
  - Downloads what the app needs once, and skips anything already there:
      Python 3.12 (winget, this user only)   only when no usable Python is installed
      git (winget)                           only when detection needs it and it's missing
      Python packages, models, database      through setup.ps1, which itself skips installed
                                             packages (pip dry run), models on disk and an
                                             existing database
    setup.ps1 runs only the first time, or after a requirement or detector setting changed.
    Every other start skips it and opens in seconds.
  - One server, two addresses:
      http://localhost:8000      this computer, any browser (no certificate warning)
      https://<LAN IP>:8443      phones/tablets on the same Wi-Fi (install /ca.crt once)
  - Opens the app in its own window with the camera and microphone already allowed.
    Closing the window stops the server.
  - Every start is a clean one: the previous session's server and app window are closed, and
    its leftovers (the window's browser profile, QR images, logs) are removed. Kept: the setup
    stamp (fast starts) and the certificates (a phone trusts the local CA once).
  - Prints a QR code for the phone and opens it as an image to scan from the screen.
  - Object/hand detection is on whenever it's installed.

.EXAMPLE
  .\start.cmd                  # double-click friendly
  .\start.ps1 -NoWindow        # serve only; open the links in any browser; Ctrl+C stops
  .\start.ps1 -LocalOnly       # this computer only: no LAN address, no firewall prompt
  .\start.ps1 -CheckOnly       # what is installed, what a first start would download - changes nothing
#>
[CmdletBinding()]
param(
    [switch]$NoWindow,
    [switch]$LocalOnly,
    [switch]$NoDetection,
    [switch]$CheckOnly
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

# --- 0. prerequisites, installed once: present = skipped ---

# The WindowsApps "python.exe" is only a Microsoft Store shortcut: it prints "Python was not
# found" and exits 9009. Running the candidate is the only reliable test.
function Get-PythonVersion([string]$Exe, [string[]]$Pre = @()) {
    try {
        $v = & $Exe @Pre -c "import sys; print('%d.%d' % sys.version_info[:2])" 2> $null
        if ($LASTEXITCODE -eq 0 -and $v) { return [version]("$v".Trim()) }
    } catch {}
    return $null
}

# Detection (mediapipe) has wheels for Python 3.11/3.12 only, so those win when detection is wanted.
function Find-Python([bool]$ForDetection) {
    $best = $null
    foreach ($candidate in @("py -3.12", "py -3.11", "python3.12", "python", "py")) {
        $parts = $candidate -split " "
        if (-not (Get-Command $parts[0] -ErrorAction SilentlyContinue)) { continue }
        $v = Get-PythonVersion $parts[0] @($parts | Select-Object -Skip 1)
        if (-not $v -or $v -lt [version]"3.10") { continue }
        if ($v -eq [version]"3.12" -or $v -eq [version]"3.11") { return @{ Name = $candidate; Version = $v; Detection = $true } }
        if (-not $best) { $best = @{ Name = $candidate; Version = $v; Detection = $false } }
    }
    # Installed but not on this window's PATH (installed a moment ago, or PATH was never updated).
    foreach ($dir in @("$env:LOCALAPPDATA\Programs\Python\Python312", "$env:LOCALAPPDATA\Programs\Python\Python311",
                       "$env:ProgramFiles\Python312", "$env:ProgramFiles\Python311")) {
        $exe = Join-Path $dir "python.exe"
        if ((Test-Path $exe) -and (Get-PythonVersion $exe)) {
            $env:Path = "$dir;$dir\Scripts;$env:Path"  # setup.ps1's plain "python" is now this one
            return @{ Name = "python"; Version = (Get-PythonVersion $exe); Detection = $true }
        }
    }
    return $best  # 3.10/3.13+: the base app works; detection won't install on it
}

function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user;$env:Path"
}

function Install-Once([string]$Id, [string]$What) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Warn "winget is not available to install $What."
        return
    }
    Write-Host "Installing $What (one time only, for this user - later starts skip this)..."
    # --source winget: the community repository only - the Microsoft Store source would stop
    # for its own terms prompt.
    & winget install --id $Id --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    Update-SessionPath  # the new PATH entries only reach windows opened from now on, and this one
}

$WantDetection = -not $NoDetection
$VenvPython = Get-VenvPython
$ready = $false
if (Test-Path $VenvPython) {
    & $VenvPython (Join-Path $Backend "scripts\setup_stamp.py") check
    $ready = ($LASTEXITCODE -eq 0)
}

if ($CheckOnly) {
    $py = Find-Python $WantDetection
    $git = [bool](Get-Command git -ErrorAction SilentlyContinue)
    Write-Host "Python:      $(if ($py) { "$($py.Version) ($($py.Name)) - installed, skipped" } else { 'missing - the first start installs Python 3.12 with winget' })"
    if ($py -and $WantDetection -and -not $py.Detection) { Write-Host "             detection needs 3.11/3.12 - the first start installs Python 3.12 with winget" }
    Write-Host "git:         $(if ($git) { 'installed, skipped' } elseif ($WantDetection) { 'missing - installed with winget (detection needs it)' } else { 'not needed without detection' })"
    Write-Host "Environment: $(if (Test-Path $VenvPython) { $VenvPython } else { 'missing - created on first start' })"
    Write-Host "Setup:       $(if ($ready) { 'done and up to date - nothing to download, starts skip it' } else { 'runs once on the next start (installed packages, models and the database are skipped)' })"
    exit 0
}

# --- 1. setup, only when something changed since the last successful one ---
if (-not $ready) {
    Write-Host "First start, or something changed - running setup once (later starts skip it)..."
    $py = Find-Python $WantDetection
    if (-not $py -or ($WantDetection -and -not $py.Detection)) {
        Install-Once "Python.Python.3.12" "Python 3.12"
        $py = Find-Python $WantDetection
    }
    if (-not $py) {
        Write-Warn "ERROR: no Python 3.10+ and it could not be installed. Install Python 3.12 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH') and run start again."
        exit 1
    }
    Write-Host "Python $($py.Version): ready."
    if ($WantDetection -and -not $py.Detection) {
        Write-Warn "Python $($py.Version) can't run detection (it needs 3.11/3.12) - starting without it."
        $WantDetection = $false
    }
    # One detection package (YOLOE's text encoder) installs straight from GitHub, so pip needs git.
    if ($WantDetection -and -not (Get-Command git -ErrorAction SilentlyContinue)) {
        Install-Once "Git.Git" "git"
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Write-Warn "git is still missing - starting without detection (install Git for Windows and start again to add it)."
            $WantDetection = $false
        }
    }
    & (Join-Path $Root "setup.ps1") -SkipTests -NoSummary -NoDetection:(-not $WantDetection)
    if ($LASTEXITCODE -ne 0) { exit 1 }
    $VenvPython = Get-VenvPython
} else {
    Write-Host "Setup already done - Python, packages, models and database are in place (skipped)."
}
Set-Location $Backend

$Port = "8000"
if ($env:BACKEND_PORT) { $Port = $env:BACKEND_PORT }
$LanPort = "8443"
if ($env:BACKEND_HTTPS_PORT) { $LanPort = $env:BACKEND_HTTPS_PORT }
$Health = "http://127.0.0.1:$Port/health"

# --- 2. a clean slate: this start replaces whatever an earlier one left running ---
function Get-SessionWindows {
    try {
        return @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe' OR Name='chrome.exe'" -ErrorAction Stop |
            Where-Object { $_.CommandLine -and $_.CommandLine.Contains($RunDir) })
    } catch {
        return @()
    }
}
function Get-ListenersOn([int[]]$Ports) {
    return @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $Ports -contains $_.LocalPort })
}
function Stop-PreviousSession {
    # Only this app's own processes: the app window (its profile lives in .run) and servers run by
    # this backend's venv. Anything else holding the ports is reported, never killed.
    $windows = Get-SessionWindows
    $servers = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($Backend, [StringComparison]::OrdinalIgnoreCase) -and
                       $_.CommandLine -match "serve\.py|uvicorn" })
    # An interpreter whose venv launcher is already gone still holds the port: python running
    # serve.py / uvicorn on this app's own ports is ours too.
    foreach ($l in Get-ListenersOn @([int]$Port, [int]$LanPort)) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($l.OwningProcess)" -ErrorAction SilentlyContinue
        if ($proc -and $proc.Name -like "python*" -and $proc.CommandLine -match "serve\.py|uvicorn") { $servers += $proc }
    }
    $servers = @($servers | Sort-Object ProcessId -Unique)  # the same interpreter listens on both ports
    if ($windows.Count -or $servers.Count) {
        Write-Host "Closing the previous session (server and app window)..."
    }
    foreach ($p in $windows) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    foreach ($p in $servers) { & taskkill.exe /F /T /PID $p.ProcessId *> $null }
    for ($i = 0; $i -lt 40; $i++) {
        if (-not (Get-ListenersOn @([int]$Port, [int]$LanPort)).Count -and -not (Get-SessionWindows).Count) { break }
        Start-Sleep -Milliseconds 250
    }
    # Leftovers: the window's browser profile (cache, service worker, stored settings), QR images, logs.
    Get-ChildItem $RunDir -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "app-profile*" -or $_.Name -like "*.png" -or $_.Name -like "server*.log" } |
        ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
}
Stop-PreviousSession
$blocker = Get-ListenersOn @([int]$Port, [int]$LanPort) | Select-Object -First 1
if ($blocker) {
    $name = (Get-Process -Id $blocker.OwningProcess -ErrorAction SilentlyContinue).ProcessName
    Write-Warn "ERROR: port $($blocker.LocalPort) is used by another program ($name, pid $($blocker.OwningProcess)) - close it, or set BACKEND_PORT / BACKEND_HTTPS_PORT."
    exit 1
}

# --- 3. pairing token, and this machine's LAN address + certificate (one call) ---
$lan = (& $VenvPython scripts\lan.py all | Out-String).Trim().Split("|")
if ($LASTEXITCODE -ne 0 -or $lan.Count -ne 6) { Write-Warn "ERROR: scripts\lan.py failed."; exit 1 }
$Token, $TokenState, $LanIp, $Cert, $Key, $Spki = $lan
if ($TokenState -eq "generated") { Write-Host "Generated a pairing token in backend\.env (links below carry it)." }
if ($LocalOnly) { $LanIp = "" }

$LocalUrl = "http://localhost:$Port/?token=$Token&detect=1"
$AppProfile = Join-Path $RunDir "app-profile"

# --- 4. the server: both addresses, one process, in the background ---
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
        $PhoneUrl = "https://${LanIp}:${LanPort}/?token=$Token&detect=1"
        Write-Host "  Phone/tablet on this Wi-Fi:  $PhoneUrl"
        Write-Host "      (first time on a phone: open https://${LanIp}:${LanPort}/ca.crt, install it, then no warning; Windows may ask to allow Python on private networks)"
        $Png = Join-Path $RunDir "pairing.png"
        & $VenvPython scripts\pairing_qr.py --url $PhoneUrl --png $Png
        if ($LASTEXITCODE -ne 0) {
            Write-Host "      (QR skipped - qrcode not installed; re-run setup.ps1)"
        } elseif (Test-Path $Png) {
            Start-Process $Png  # on screen, big enough for a phone camera
        }
    }
    Write-Host "  Press the big Start button and allow the camera. Detection starts by itself (first frames: 'loading model')."
    Write-Host "  Server log: .run\server.err.log"
    Write-Host ""

    if ($NoWindow) {
        Write-Host "Serving - Ctrl+C stops it."
        Wait-Process -Id $Server.Id
        exit 0
    }

    # --- 5. the app window: own profile (fresh each start), camera + microphone allowed ---
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
