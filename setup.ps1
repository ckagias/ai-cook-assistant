<#
.SYNOPSIS
  One-command setup for Windows PowerShell - the same as setup.sh: creates/repairs the venv,
  installs everything (base + object/hand detection + models), prepares .env and the recipe
  database, runs the tests, prints next steps.

.DESCRIPTION
  Safe to re-run: packages already installed at the required version are not downloaded again.
  A package whose required version changed gets the new version, and the old one's wheel is
  kept in .wheelhouse\ (never deleted). Models are only ever added to backend\models\.
  An existing environment is never deleted: one that is broken or belonged to a moved project
  is renamed aside and rebuilt from .wheelhouse\.

.EXAMPLE
  .\setup.cmd                                    # double-click friendly, bypasses script policy
  powershell -ExecutionPolicy Bypass -File .\setup.ps1
  .\setup.ps1 -NoDetection -SkipTests -Run
#>
[CmdletBinding()]
param(
    [switch]$NoDetection,  # skip the ~1 GB detection stack (torch, ultralytics, mediapipe) and models
    [switch]$SkipTests,    # don't run the test suite at the end
    [switch]$Run,          # start the server on localhost afterwards (see also setup-window.ps1)
    [switch]$NoSummary     # skip the closing "what it does / how to use it" summary
)

$ErrorActionPreference = "Continue"  # native tools report through exit codes, checked explicitly
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PYTHONIOENCODING = "utf-8"

function Write-Warn([string]$Message) { Write-Host $Message -ForegroundColor Red }

$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
Set-Location $Backend

# --- 1. Python: detection needs 3.11/3.12 (mediapipe has no 3.13+ wheels yet), so prefer those ---
function Test-Python([string[]]$Command) {
    $exe = $Command[0]
    $pre = @($Command | Select-Object -Skip 1)
    try {
        & $exe @pre -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$Python = $null
foreach ($candidate in @("py -3.12", "py -3.11", "python3.12", "python", "py")) {
    $parts = $candidate -split " "
    if (-not (Get-Command $parts[0] -ErrorAction SilentlyContinue)) { continue }
    if (Test-Python $parts) { $Python = $parts; break }
}
if (-not $Python) {
    Write-Warn "ERROR: no Python 3.10+ found. Install Python 3.12 from https://www.python.org/downloads/ and re-run."
    exit 1
}
$PyExe = $Python[0]
$PyPre = @($Python | Select-Object -Skip 1)
$info = & $PyExe @PyPre -c "import sys; print(sys.executable, sys.version.split()[0])"
Write-Host "Using Python: $info"

# --- 2. which venv: .venv, or .venv-windows when .venv was made by another OS (e.g. WSL) ---
$VenvDir = ".venv"
if ((Test-Path ".venv") -and -not (Test-Path ".venv\Scripts")) {
    $VenvDir = ".venv-windows"
    Write-Host "backend\.venv belongs to another operating system - using backend\$VenvDir for Windows."
}
$VenvPython = Join-Path $Backend "$VenvDir\Scripts\python.exe"

function Set-Aside([string]$Reason) {
    # Renames, never deletes: the old environment stays on disk.
    $aside = "$VenvDir.$Reason-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    Rename-Item -Path $VenvDir -NewName $aside
    Write-Warn "Moved the old environment to backend\$aside (delete it yourself once the new one works)."
}

# --- 3. a venv whose project moved, or whose Python no longer starts, is set aside and rebuilt ---
if (Test-Path "$VenvDir\pyvenv.cfg") {
    $line = Select-String -Path "$VenvDir\pyvenv.cfg" -Pattern "^command = " | Select-Object -First 1
    $recorded = ""
    if ($line) { $recorded = ($line.Line -replace ".*-m venv ", "").Trim() }
    $starts = $false
    if (Test-Path $VenvPython) {
        & $VenvPython -c "import sys" *> $null
        $starts = ($LASTEXITCODE -eq 0)
    }
    if ($recorded -and -not (Test-Path $recorded)) {
        Write-Warn "WARNING: $VenvDir was created at '$recorded', which no longer exists (the project was moved or copied)."
        Set-Aside "moved"
    } elseif (-not $starts) {
        Write-Warn "WARNING: $VenvDir's Python no longer starts."
        Set-Aside "broken"
    }
}

# --- 4. create the venv if missing, install what's missing or at the wrong version ---
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment ($VenvDir)..."
    & $PyExe @PyPre -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Write-Warn "ERROR: could not create the virtual environment."; exit 1 }
}

$WithDetection = -not $NoDetection
if ($WithDetection) {
    & $VenvPython -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3, 11), (3, 12)) else 1)"
    if ($LASTEXITCODE -ne 0) {
        $ver = & $VenvPython -c "import sys; print(sys.version.split()[0])"
        Write-Warn "WARNING: $VenvDir uses Python $ver - detection needs 3.11 or 3.12 (mediapipe). Installing the base app only; install Python 3.12 and rename backend\$VenvDir to get detection."
        $WithDetection = $false
    }
}

# pip >= 23 for 'install --dry-run --report', which is how already-installed packages are skipped.
& $VenvPython -m pip install -q "pip>=23"

$Requirements = @("requirements.txt")
if ($WithDetection) { $Requirements += "requirements-detect.txt" }
Write-Host "Checking dependencies ($($Requirements -join ' '))..."
& $VenvPython scripts\sync_deps.py @Requirements
if ($LASTEXITCODE -ne 0) { Write-Warn "Dependency install failed - see above."; exit 1 }

# --- 5. .env from .env.example, plus a warning for a missing provider key ---
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

function Read-DotEnv([string]$Path) {
    $values = @{}
    if (Test-Path $Path) {
        foreach ($l in Get-Content $Path -Encoding UTF8) {
            if ($l -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
                $values[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
            }
        }
    }
    return $values
}

$envValues = Read-DotEnv ".env"
$keyVars = @{ "anthropic" = @("ANTHROPIC_API_KEY"); "openai" = @("OPENAI_API_KEY"); "gemini" = @("GEMINI_API_KEY", "GOOGLE_API_KEY") }
$provider = $envValues["VISION_PROVIDER"]
if ($provider -and $keyVars.ContainsKey($provider)) {
    $hasKey = $false
    foreach ($k in $keyVars[$provider]) { if ($envValues[$k]) { $hasKey = $true } }
    if (-not $hasKey) { Write-Warn "WARNING: VISION_PROVIDER=$provider but $($keyVars[$provider] -join ' or ') is empty in .env" }
}

# --- 6. models for the configured detector (download/export once; nothing is ever deleted) ---
if ($WithDetection) {
    Write-Host "Checking detection models..."
    & $VenvPython scripts\fetch_models.py
    if ($LASTEXITCODE -ne 0) { Write-Warn "WARNING: model download/export failed - /detect will retry on first use." }
}

# --- 7. local recipe database (created + seeded from data\recipes.json on first run) ---
& $VenvPython scripts\db_init.py
if ($LASTEXITCODE -ne 0) { Write-Warn "WARNING: database setup failed - see above." }

# --- 8. tests ---
if (-not $SkipTests) {
    Write-Host "Running tests..."
    & $VenvPython -m pytest tests -q -p no:warnings -p no:cacheprovider | Select-Object -Last 3
    if ($LASTEXITCODE -ne 0) { Write-Warn "Tests failed (exit code $LASTEXITCODE) - see above." } else { Write-Host "Tests passed." }
}

# --- what the system does, where to open it, how to use it, and this install's status ---
if (-not $NoSummary) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8  # the summary has Greek button names
    & $VenvPython scripts\usage.py --shell ps --python "backend\$VenvDir\Scripts\python.exe"
}

# --- 9. -Run: the server on localhost, in the foreground, with .env loaded into its environment ---
if ($Run) {
    foreach ($entry in (Read-DotEnv ".env").GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
    }
    $bindHost = "127.0.0.1"
    if ($env:BACKEND_HOST) { $bindHost = $env:BACKEND_HOST }
    $port = "8000"
    if ($env:BACKEND_PORT) { $port = $env:BACKEND_PORT }
    $url = "http://localhost:$port/"
    if ($env:BACKEND_PAIRING_TOKEN) { $url = "$url" + "?token=$env:BACKEND_PAIRING_TOKEN" }
    Write-Host "Starting the server - open $url  (Ctrl+C stops it)"
    & $VenvPython -m uvicorn app.main:app --host $bindHost --port $port
    exit $LASTEXITCODE
}
exit 0
