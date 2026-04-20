$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendPath = Join-Path $projectRoot "frontend\index.html"
$pidFilePath = Join-Path $projectRoot ".hivemind-backend.pid"

function Wait-ForBackend {
    param(
        [string]$HealthUrl,
        [int]$MaxAttempts = 20
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        Start-Sleep -Milliseconds 300
        try {
            $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return $true
            }
        }
        catch {
            # Backend can still be starting up.
        }
    }
    return $false
}

function Start-HivemindBrowser {
    param(
        [string]$FrontendFilePath
    )

    $frontendUri = "file:///" + ($FrontendFilePath -replace "\\", "/")
    $browserCommand = Get-BrowserAppCommand
    if (-not $browserCommand) {
        throw "No supported app browser found. Install Microsoft Edge or Google Chrome."
    }

    $profileDir = Join-Path $env:TEMP "hivemind-browser-profile"
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    return Start-Process -FilePath $browserCommand -ArgumentList "--app=$frontendUri", "--new-window", "--user-data-dir=$profileDir" -PassThru
}

function Get-BrowserAppCommand {
    $discovered = @()

    $edgeFromPath = Get-Command "msedge.exe" -ErrorAction SilentlyContinue
    if ($edgeFromPath) {
        $discovered += $edgeFromPath.Source
    }

    $chromeFromPath = Get-Command "chrome.exe" -ErrorAction SilentlyContinue
    if ($chromeFromPath) {
        $discovered += $chromeFromPath.Source
    }

    $knownPaths = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )

    foreach ($candidate in $knownPaths) {
        if ($candidate -and (Test-Path $candidate)) {
            $discovered += $candidate
        }
    }

    $unique = $discovered | Select-Object -Unique
    if ($unique.Count -gt 0) {
        return $unique[0]
    }

    return $null
}

$backendProcess = $null
$browserProcess = $null

try {
    # Start backend in the background (no extra console window).
    $backendProcess = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $projectRoot -PassThru -WindowStyle Hidden
    Set-Content -Path $pidFilePath -Value $backendProcess.Id -Encoding ascii

    $backendReady = Wait-ForBackend -HealthUrl "http://127.0.0.1:8000/health"
    if (-not $backendReady) {
        throw "Backend failed to start in time."
    }

    $browserProcess = Start-HivemindBrowser -FrontendFilePath $frontendPath
    Wait-Process -Id $browserProcess.Id
}
finally {
    if (Test-Path $pidFilePath) {
        Remove-Item $pidFilePath -Force -ErrorAction SilentlyContinue
    }

    if ($backendProcess -and -not $backendProcess.HasExited) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
