[CmdletBinding()]
param(
    [string]$Distro = "Ubuntu",
    [string]$Model = "llama3.1:8b",
    [string]$EnvironmentFile = ".env.demo",
    [ValidateRange(1, 16)]
    [int]$WorkerReplicas = 4,
    [switch]$SkipBuild,
    [switch]$PreferCachedImages,
    [switch]$SkipProviderProbe,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$env:COMPOSE_BAKE = "false"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$environmentPath = Join-Path $repositoryRoot $EnvironmentFile
$environmentExample = Join-Path $repositoryRoot ".env.demo.example"
$composePath = Join-Path $repositoryRoot "compose.demo.yaml"

function Set-DotEnvValue {
    param([string]$Path, [string]$Name, [string]$Value)

    $lines = [System.Collections.Generic.List[string]]::new()
    if (Test-Path $Path) {
        foreach ($line in Get-Content -LiteralPath $Path) {
            $lines.Add($line)
        }
    }
    $pattern = "^$([regex]::Escape($Name))="
    $updated = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match $pattern) {
            $lines[$index] = "$Name=$Value"
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $lines.Add("$Name=$Value")
    }
    Set-Content -LiteralPath $Path -Value $lines -Encoding utf8
}

function Test-DockerReady {
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & docker.exe info *> $null
        return $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Test-DockerImage {
    param([string]$Image)

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & docker.exe image inspect $Image *> $null
        return $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "WSL is required. Install WSL and the Ubuntu distribution first."
}

Write-Host "[1/6] Checking local Ollama..."
if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is required and docker.exe is not on PATH."
}

& wsl.exe -d $Distro --exec test -x /usr/local/bin/ollama
if ($LASTEXITCODE -ne 0) {
    throw "Ollama is not installed in the '$Distro' WSL distribution."
}

# A foreground WSL client prevents the distro from stopping while Docker uses its Ollama service.
& wsl.exe -d $Distro --exec pgrep -f "^sleep infinity$" *> $null
if ($LASTEXITCODE -ne 0) {
    Start-Process -FilePath "wsl.exe" -WindowStyle Hidden -ArgumentList @(
        "-d", $Distro, "--exec", "sleep", "infinity"
    )
}

$ollamaReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 2
        $ollamaReady = $true
        break
    }
    catch {
        # The systemd-managed Ollama service can need a few seconds after WSL starts.
    }
}
if (-not $ollamaReady) {
    throw "Ollama did not become ready at http://127.0.0.1:11434."
}

$installedModels = (Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 10).models
if ($Model -notin @($installedModels | ForEach-Object { $_.name })) {
    throw "The Ollama model '$Model' is not installed. Run: wsl -d $Distro -- ollama pull $Model"
}

if (-not (Test-Path -LiteralPath $environmentPath)) {
    Copy-Item -LiteralPath $environmentExample -Destination $environmentPath
}
Set-DotEnvValue -Path $environmentPath -Name "AI_PROVIDER" -Value "ollama"
Set-DotEnvValue -Path $environmentPath -Name "OLLAMA_BASE_URL" -Value "http://host.docker.internal:11434"
Set-DotEnvValue -Path $environmentPath -Name "OLLAMA_MODEL" -Value $Model
Set-DotEnvValue -Path $environmentPath -Name "OLLAMA_TIMEOUT_SECONDS" -Value "1800"
Set-DotEnvValue -Path $environmentPath -Name "OLLAMA_CONTEXT_TOKENS" -Value "8192"
Set-DotEnvValue -Path $environmentPath -Name "OLLAMA_MAX_OUTPUT_TOKENS" -Value "4096"
Set-DotEnvValue -Path $environmentPath -Name "PLANNING_RUN_DEFAULT_TOKEN_BUDGET" -Value "100000"
Set-DotEnvValue -Path $environmentPath -Name "DEMO_WORKER_REPLICAS" -Value $WorkerReplicas.ToString()
Set-DotEnvValue -Path $environmentPath -Name "OLLAMA_SCHEMA_RETRIES" -Value "1"
Set-DotEnvValue -Path $environmentPath -Name "OLLAMA_FAST_PLANNING" -Value "true"
Set-DotEnvValue -Path $environmentPath -Name "OPENAI_API_KEY" -Value ""
Set-DotEnvValue -Path $environmentPath -Name "MODEL_INPUT_PRICE_PER_MILLION" -Value "0"
Set-DotEnvValue -Path $environmentPath -Name "MODEL_CACHED_INPUT_PRICE_PER_MILLION" -Value "0"
Set-DotEnvValue -Path $environmentPath -Name "MODEL_OUTPUT_PRICE_PER_MILLION" -Value "0"

$httpPort = "8080"
$portLine = Get-Content -LiteralPath $environmentPath | Where-Object { $_ -match "^HTTP_PORT=" } | Select-Object -First 1
if ($portLine) {
    $httpPort = $portLine.Substring("HTTP_PORT=".Length)
}
Set-DotEnvValue -Path $environmentPath -Name "DEMO_ORIGIN" -Value "http://localhost:$httpPort"

Write-Host "[2/6] Checking Docker Desktop..."
if (-not (Test-DockerReady)) {
    $desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $desktop)) {
        throw "Docker Desktop is not running and its executable was not found."
    }
    Start-Process -FilePath $desktop -WindowStyle Hidden
    $dockerReady = $false
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        Start-Sleep -Seconds 2
        if (Test-DockerReady) {
            $dockerReady = $true
            break
        }
    }
    if (-not $dockerReady) {
        throw "Docker Desktop did not become ready."
    }
}

$buildRequired = -not $SkipBuild
if ($PreferCachedImages -and -not $SkipBuild) {
    $appVersion = "0.13.0"
    $versionLine = Get-Content -LiteralPath $environmentPath | Where-Object { $_ -match "^APP_VERSION=" } | Select-Object -First 1
    if ($versionLine) {
        $appVersion = $versionLine.Substring("APP_VERSION=".Length)
    }
    $backendImageExists = Test-DockerImage -Image "ai-project-manager-backend:$appVersion"
    $frontendImageExists = Test-DockerImage -Image "ai-project-manager-university-demo-frontend:latest"
    $buildRequired = -not ($backendImageExists -and $frontendImageExists)
}

if ($buildRequired) {
    Write-Host "[3/6] Building application images (first launch may take several minutes)..."
    & docker.exe compose --env-file $environmentPath -f $composePath build api frontend
    if ($LASTEXITCODE -ne 0) {
        throw "The local application images did not build successfully."
    }
}
else {
    Write-Host "[3/6] Using cached application images."
}

Write-Host "[4/6] Starting database, API, workers, and frontend..."
& docker.exe compose --env-file $environmentPath -f $composePath up -d --no-build
if ($LASTEXITCODE -ne 0) {
    throw "The local application stack did not start successfully."
}

if (-not $SkipProviderProbe) {
    Write-Host "[5/6] Verifying structured AI output..."
    & docker.exe compose --env-file $environmentPath -f $composePath exec -T worker `
        /app/.venv/bin/python -m app.ai.probe
    if ($LASTEXITCODE -ne 0) {
        throw "The worker could not complete a structured Ollama probe."
    }
}
else {
    Write-Host "[5/6] Ollama endpoint and model are ready."
}

Write-Host "[6/6] Waiting for the application health check..."
$applicationUrl = "http://localhost:$httpPort"
$applicationReady = $false
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "$applicationUrl/api/v1/health/ready" -TimeoutSec 5
        if ($health.status -eq "ready") {
            $applicationReady = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $applicationReady) {
    throw "The application did not become ready at $applicationUrl."
}

Write-Host "Local AI Project Manager is ready at $applicationUrl" -ForegroundColor Green
Write-Host "Provider: Ollama | Model: $Model | Context: 8192 tokens | Workers: $WorkerReplicas" -ForegroundColor Green
if ($OpenBrowser) {
    Start-Process $applicationUrl
}
