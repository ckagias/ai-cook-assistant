<#
.SYNOPSIS
    Puts the Cooking Assistant on Google Cloud Run at one fixed public address, and writes the one
    QR code that always opens it: qr\main-app.png.

.DESCRIPTION
    The address is https://<service>-<project number>.<region>.run.app. It never changes: every
    redeploy lands on it, from any network, so the QR code (and the slide that shows it) keeps working.
    Phones need nothing installed - Cloud Run serves real HTTPS.

    First time only: sign in with the event account (gcloud auth login) and accept the Google Cloud
    terms of service once at https://console.cloud.google.com.

    What it does:
      1. turns on Cloud Run, Cloud Build, Artifact Registry and Secret Manager in the project;
      2. keeps two secrets in Secret Manager, read from backend\.env and never printed:
         the OpenAI key and the cloud pairing token (CLOUD_PAIRING_TOKEN, created once);
      3. builds backend\ into a container with Docker here (Windows or WSL; only what
         backend\.dockerignore lets through - never .env or certs, checked), pushes it to the project
         and deploys it: at most 2 instances, detection off (it needs the laptop's CPU and models).
         -UseCloudBuild builds in Google Cloud instead (backend\.gcloudignore), where the project allows it;
      4. checks /health on the fixed address and writes qr\main-app.png.

.EXAMPLE
    .\deploy-cloud.ps1              # deploy or redeploy
    .\deploy-cloud.ps1 -QrOnly      # just (re)write qr\main-app.png - the address is known before the first deploy
#>
param(
    [string]$Project = "a11y-hack26ath-266",
    [string]$Region = "europe-west1",
    [string]$Service = "readycheck",
    [switch]$QrOnly,
    [switch]$UseCloudBuild  # build in Google Cloud instead of here (needs the Cloud Run Builder role on the project)
)

$ErrorActionPreference = "Continue"  # gcloud reports progress on stderr; failures are checked by exit code
$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$EnvFile = Join-Path $Backend ".env"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
$QrPng = Join-Path $Root "qr\main-app.png"

$g = (Get-Command gcloud -ErrorAction SilentlyContinue).Source
if (-not $g) { $g = Join-Path $env:LOCALAPPDATA "google-cloud-sdk\bin\gcloud.cmd" }
if (-not (Test-Path $g)) { Write-Host "gcloud not found. Install the Google Cloud CLI first." -ForegroundColor Red; exit 1 }

function Invoke-Gcloud {
    & $g @args
    if ($LASTEXITCODE -ne 0) { throw "gcloud $($args[0..2] -join ' ') failed (exit $LASTEXITCODE)" }
}

function Get-EnvValue([string]$Name) {
    if (-not (Test-Path $EnvFile)) { return $null }
    $line = Get-Content $EnvFile -Encoding UTF8 | Where-Object { $_ -match "^$Name=(.+)$" } | Select-Object -First 1
    if ($line) { return ($line -replace "^$Name=", "").Trim() }
    return $null
}

# The cloud copy's own pairing token: made once, kept in backend\.env (gitignored), inside the QR code.
$CloudToken = Get-EnvValue "CLOUD_PAIRING_TOKEN"
if (-not $CloudToken) {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $CloudToken = [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
    $text = if (Test-Path $EnvFile) { [IO.File]::ReadAllText($EnvFile) } else { "" }
    $sep = if ($text -and -not $text.EndsWith("`n")) { "`n" } else { "" }
    [IO.File]::AppendAllText($EnvFile, "$sep# Pairing token of the Cloud Run copy (deploy-cloud.ps1); it is inside qr\main-app.png`nCLOUD_PAIRING_TOKEN=$CloudToken`n")
    Write-Host "Created CLOUD_PAIRING_TOKEN in backend\.env"
}

try {
    $Number = (& $g projects describe $Project --format="value(projectNumber)" 2>$null | Out-String).Trim()
    if (-not $Number) { throw "can't read project $Project - signed in with the event account? (gcloud auth login)" }
    $BaseUrl = "https://$Service-$Number.$Region.run.app"
    $AppUrl = "$BaseUrl/?token=$CloudToken"

    if (-not $QrOnly) {
        Invoke-Gcloud config set project $Project --quiet
        Write-Host "1/4 Services (Cloud Run, Cloud Build, Artifact Registry, Secret Manager)..."
        & $g services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com --project $Project --quiet
        if ($LASTEXITCODE -ne 0) {
            throw "services not enabled. If the error says 'terms of service': open https://console.cloud.google.com as the event account, accept the terms, run this again."
        }

        Write-Host "2/4 Secrets..."
        $OpenAiKey = Get-EnvValue "OPENAI_API_KEY"
        if (-not $OpenAiKey) { throw "OPENAI_API_KEY is not set in backend\.env" }
        $RuntimeSa = "$Number-compute@developer.gserviceaccount.com"
        $secrets = [ordered]@{ "openai-api-key" = $OpenAiKey; "cloud-pairing-token" = $CloudToken }
        foreach ($name in $secrets.Keys) {
            $tmp = [IO.Path]::GetTempFileName()
            try {
                [IO.File]::WriteAllText($tmp, $secrets[$name], (New-Object Text.UTF8Encoding($false)))  # no newline
                & $g secrets describe $name --project $Project --format="value(name)" 2>$null | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    Invoke-Gcloud secrets create $name --project $Project --replication-policy=automatic --data-file=$tmp --quiet
                } else {
                    $current = (& $g secrets versions access latest --secret=$name --project $Project 2>$null | Out-String).Trim()
                    if ($current -ne $secrets[$name]) {
                        Invoke-Gcloud secrets versions add $name --project $Project --data-file=$tmp --quiet
                    }
                }
            } finally {
                Remove-Item $tmp -ErrorAction SilentlyContinue
            }
            Invoke-Gcloud secrets add-iam-policy-binding $name --project $Project --member="serviceAccount:$RuntimeSa" --role="roles/secretmanager.secretAccessor" --quiet | Out-Null
        }

        $runArgs = @("--project", $Project, "--region", $Region, "--allow-unauthenticated", "--max-instances", "2",
            "--memory", "1Gi", "--cpu", "1", "--timeout", "120",
            "--set-env-vars", "VISION_PROVIDER=openai,DETECTION_ENABLED=false",
            "--set-secrets", "OPENAI_API_KEY=openai-api-key:latest,BACKEND_PAIRING_TOKEN=cloud-pairing-token:latest", "--quiet")
        if ($UseCloudBuild) {
            Write-Host "3/4 Build (Cloud Build) and deploy..."
            Invoke-Gcloud run deploy $Service --source $Backend @runArgs
        } else {
            # The event projects don't let Cloud Build's account read the upload, so the image is built
            # here (Docker on Windows, or in WSL) and pushed to the project's own repository.
            Write-Host "3/4 Build here with Docker, push, deploy (a few minutes the first time)..."
            $Image = "$Region-docker.pkg.dev/$Project/cloud-run-source-deploy/${Service}:latest"
            $winDocker = (Get-Command docker -ErrorAction SilentlyContinue).Source
            if ($winDocker) {
                $dock = { & $winDocker @args }
                $context = $Backend
            } else {
                $dock = { & wsl.exe -e docker @args }
                $context = (& wsl.exe -e wslpath -a ($Backend -replace '\\', '/')).Trim()
            }
            & $g artifacts repositories describe cloud-run-source-deploy --location $Region --project $Project --format="value(name)" 2>$null | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Invoke-Gcloud artifacts repositories create cloud-run-source-deploy --repository-format=docker --location $Region --project $Project --quiet
            }
            $tokenFile = Join-Path $env:TEMP "gcloud-ar-token.txt"
            try {
                $accessToken = (& $g auth print-access-token 2>$null | Out-String).Trim()
                [IO.File]::WriteAllText($tokenFile, $accessToken, (New-Object Text.UTF8Encoding($false)))
                $registry = "https://$Region-docker.pkg.dev"
                if ($winDocker) {
                    Get-Content $tokenFile -Raw | & $winDocker login -u oauth2accesstoken --password-stdin $registry
                } else {
                    $wslToken = (& wsl.exe -e wslpath -a ($tokenFile -replace '\\', '/')).Trim()
                    & wsl.exe -e sh -c "docker login -u oauth2accesstoken --password-stdin $registry < '$wslToken'"
                }
                if ($LASTEXITCODE -ne 0) { throw "docker login to $registry failed" }
            } finally {
                Remove-Item $tokenFile -ErrorAction SilentlyContinue
            }
            & $dock build --platform linux/amd64 -t $Image $context
            if ($LASTEXITCODE -ne 0) { throw "docker build failed" }
            # Nothing secret may be in the image: .dockerignore keeps .env out - check it.
            & $dock run --rm --entrypoint sh $Image -c "test ! -e /app/.env && test ! -d /app/.venv && test ! -d /app/certs"
            if ($LASTEXITCODE -ne 0) { throw "the image contains .env, .venv or certs - check backend\.dockerignore" }
            & $dock push $Image
            if ($LASTEXITCODE -ne 0) { throw "docker push failed" }
            Invoke-Gcloud run deploy $Service --image $Image @runArgs
        }

        Write-Host "4/4 Checking $BaseUrl/health ..."
        $ok = $false
        for ($i = 0; $i -lt 10 -and -not $ok; $i++) {
            try { $ok = (Invoke-WebRequest "$BaseUrl/health" -UseBasicParsing -TimeoutSec 20).StatusCode -eq 200 } catch { Start-Sleep -Seconds 3 }
        }
        if (-not $ok) { throw "$BaseUrl/health does not answer yet" }
    }

    New-Item -ItemType Directory -Force (Split-Path $QrPng) | Out-Null
    & $VenvPython (Join-Path $Backend "scripts\pairing_qr.py") --url $AppUrl --png $QrPng
    Write-Host ""
    Write-Host "The app's fixed address:  $BaseUrl" -ForegroundColor Green
    Write-Host "The one QR code:          $QrPng  (the same after every redeploy)"
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
