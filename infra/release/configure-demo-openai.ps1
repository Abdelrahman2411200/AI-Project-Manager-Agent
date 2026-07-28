[CmdletBinding()]
param(
    [string]$EnvironmentFile = ".env.demo",
    [switch]$ProbeOnly
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$environmentPath = if ([IO.Path]::IsPathRooted($EnvironmentFile)) {
    [IO.Path]::GetFullPath($EnvironmentFile)
} else {
    [IO.Path]::GetFullPath((Join-Path $repositoryRoot $EnvironmentFile))
}
$examplePath = Join-Path $repositoryRoot ".env.demo.example"
$composePath = Join-Path $repositoryRoot "compose.demo.yaml"

if ($ProbeOnly) {
    if (-not (Test-Path -LiteralPath $environmentPath -PathType Leaf)) {
        throw "The environment file does not exist. Configure the demo before probing it."
    }
} else {
    if (-not (Test-Path -LiteralPath $environmentPath -PathType Leaf)) {
        Copy-Item -LiteralPath $examplePath -Destination $environmentPath
    }

    $secureKey = Read-Host "Enter the OpenAI API key for the local demo (input is hidden)" -AsSecureString
    $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $plainKey = $null

    try {
        $plainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
        if ([string]::IsNullOrWhiteSpace($plainKey) -or $plainKey.Length -lt 20) {
            throw "The API key is empty or unexpectedly short."
        }
        if ($plainKey -match "\s") {
            throw "The API key must not contain whitespace."
        }

        $updatedLines = [Collections.Generic.List[string]]::new()
        $keyWritten = $false
        foreach ($line in [IO.File]::ReadAllLines($environmentPath)) {
            if ($line -match "^OPENAI_API_KEY=") {
                if (-not $keyWritten) {
                    $updatedLines.Add("OPENAI_API_KEY=$plainKey")
                    $keyWritten = $true
                }
                continue
            }
            $updatedLines.Add($line)
        }
        if (-not $keyWritten) {
            $updatedLines.Add("OPENAI_API_KEY=$plainKey")
        }

        [IO.File]::WriteAllLines(
            $environmentPath,
            $updatedLines,
            [Text.UTF8Encoding]::new($false)
        )
    } finally {
        if ($keyPointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
        }
        $plainKey = $null
        $secureKey = $null
    }

    & docker compose --env-file $environmentPath -f $composePath up -d --force-recreate `
        api worker frontend
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose could not restart the API, worker, and frontend."
    }

    & docker compose --env-file $environmentPath -f $composePath exec -T api `
        /app/.venv/bin/python -c `
        "from app.core.config import get_settings; raise SystemExit(0 if get_settings().openai_api_key else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw "The restarted API did not load OPENAI_API_KEY."
    }
}

& docker compose --env-file $environmentPath -f $composePath exec -T worker `
    /app/.venv/bin/python -m app.ai.probe
$probeExitCode = $LASTEXITCODE

switch ($probeExitCode) {
    0 {
        Write-Host "OpenAI planning is ready. The live structured provider probe succeeded."
    }
    2 {
        throw "OPENAI_API_KEY is not configured in the worker."
    }
    3 {
        throw (
            "The API key is installed, but its OpenAI API account has no available quota. " +
            "Add API credits at https://platform.openai.com/settings/organization/billing/overview, " +
            "wait a few minutes, then rerun this command with -ProbeOnly."
        )
    }
    default {
        throw (
            "The live OpenAI structured provider probe failed safely. Review the typed probe output " +
            "above, correct the provider account or network issue, then rerun with -ProbeOnly."
        )
    }
}
