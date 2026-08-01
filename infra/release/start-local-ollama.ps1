[CmdletBinding()]
param(
    [string]$Distro = "Ubuntu",
    [string]$Model = "gemma3:4b",
    [string]$EnvironmentFile = ".env.demo",
    [switch]$SkipBuild
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

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "WSL is required. Install WSL and the Ubuntu distribution first."
}
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
Set-DotEnvValue -Path $environmentPath -Name "OLLAMA_TIMEOUT_SECONDS" -Value "300"
Set-DotEnvValue -Path $environmentPath -Name "OLLAMA_CONTEXT_TOKENS" -Value "8192"
Set-DotEnvValue -Path $environmentPath -Name "OLLAMA_MAX_OUTPUT_TOKENS" -Value "4096"
Set-DotEnvValue -Path $environmentPath -Name "OLLAMA_SCHEMA_RETRIES" -Value "1"
Set-DotEnvValue -Path $environmentPath -Name "OPENAI_API_KEY" -Value ""
Set-DotEnvValue -Path $environmentPath -Name "MODEL_INPUT_PRICE_PER_MILLION" -Value "0"
Set-DotEnvValue -Path $environmentPath -Name "MODEL_CACHED_INPUT_PRICE_PER_MILLION" -Value "0"
Set-DotEnvValue -Path $environmentPath -Name "MODEL_OUTPUT_PRICE_PER_MILLION" -Value "0"

& docker.exe info *> $null
if ($LASTEXITCODE -ne 0) {
    $desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $desktop)) {
        throw "Docker Desktop is not running and its executable was not found."
    }
    Start-Process -FilePath $desktop -WindowStyle Hidden
    $dockerReady = $false
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        Start-Sleep -Seconds 2
        & docker.exe info *> $null
        if ($LASTEXITCODE -eq 0) {
            $dockerReady = $true
            break
        }
    }
    if (-not $dockerReady) {
        throw "Docker Desktop did not become ready."
    }
}

if (-not $SkipBuild) {
    & docker.exe compose --env-file $environmentPath -f $composePath build api frontend
    if ($LASTEXITCODE -ne 0) {
        throw "The local application images did not build successfully."
    }
}
& docker.exe compose --env-file $environmentPath -f $composePath up -d --no-build
if ($LASTEXITCODE -ne 0) {
    throw "The local application stack did not start successfully."
}

& docker.exe compose --env-file $environmentPath -f $composePath exec -T worker `
    /app/.venv/bin/python -m app.ai.probe
if ($LASTEXITCODE -ne 0) {
    throw "The worker could not complete a structured Ollama probe."
}

$httpPort = "8080"
$portLine = Get-Content -LiteralPath $environmentPath | Where-Object { $_ -match "^HTTP_PORT=" } | Select-Object -First 1
if ($portLine) {
    $httpPort = $portLine.Substring("HTTP_PORT=".Length)
}
Write-Host "Local AI Project Manager is ready at http://localhost:$httpPort" -ForegroundColor Green
Write-Host "Provider: Ollama | Model: $Model | Context: 8192 tokens" -ForegroundColor Green
