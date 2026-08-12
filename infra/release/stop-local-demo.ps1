[CmdletBinding()]
param(
    [string]$EnvironmentFile = ".env.demo"
)

$ErrorActionPreference = "Stop"
$env:COMPOSE_BAKE = "false"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$environmentPath = Join-Path $repositoryRoot $EnvironmentFile
$composePath = Join-Path $repositoryRoot "compose.demo.yaml"

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

if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is required and docker.exe is not on PATH."
}
if (-not (Test-Path -LiteralPath $environmentPath)) {
    Write-Host "The local environment file does not exist; the project is already stopped."
    exit 0
}

if (-not (Test-DockerReady)) {
    Write-Host "Docker Desktop is not running; the project is already stopped."
    exit 0
}

Write-Host "Stopping AI Project Manager services without deleting project data..."
& docker.exe compose --env-file $environmentPath -f $composePath stop
if ($LASTEXITCODE -ne 0) {
    throw "The local application stack did not stop successfully."
}

Write-Host "AI Project Manager is stopped. PostgreSQL data and Docker images were preserved." -ForegroundColor Green
