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
    $browserCommands = Get-BrowserAppCommands
    if (-not $browserCommands -or $browserCommands.Count -eq 0) {
        throw "No supported app browser found. Install a Chromium-based browser (Edge, Chrome, Opera, or Brave)."
    }

    foreach ($browserCommand in $browserCommands) {
        try {
            $browserName = [System.IO.Path]::GetFileNameWithoutExtension($browserCommand)
            $arguments = Get-BrowserLaunchArguments -BrowserName $browserName -FrontendUri $frontendUri
            return Start-Process -FilePath $browserCommand -ArgumentList $arguments -PassThru
        }
        catch {
            # Try next discovered browser candidate.
            continue
        }
    }

    throw "Failed to start app window in detected browsers."
}

function Get-BrowserLaunchArguments {
    param(
        [string]$BrowserName,
        [string]$FrontendUri
    )

    $normalized = $BrowserName.ToLowerInvariant()

    # Opera does not behave reliably with --app for local file URLs.
    # Use a regular new window in the existing browser profile instead.
    if ($normalized -like "opera*") {
        return @("--new-window", $FrontendUri)
    }

    # Chromium-based browsers that support app mode well.
    if ($normalized -in @("msedge", "chrome", "brave")) {
        return @("--app=$FrontendUri", "--new-window")
    }

    # Safe fallback.
    return @("--new-window", $FrontendUri)
}

function Get-ExecutableFromCommandString {
    param(
        [string]$CommandText
    )

    if (-not $CommandText) {
        return $null
    }

    if ($CommandText -match '^\s*"([^"]+)"') {
        return $Matches[1]
    }

    $firstToken = ($CommandText -split "\s+")[0]
    return $firstToken.Trim('"')
}

function Get-DefaultBrowserExecutable {
    try {
        $userChoiceKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice")
        if (-not $userChoiceKey) {
            return $null
        }

        $progId = $userChoiceKey.GetValue("ProgId")
        if (-not $progId) {
            return $null
        }

        $commandKeyPath = "$progId\shell\open\command"
        $commandKey = [Microsoft.Win32.Registry]::ClassesRoot.OpenSubKey($commandKeyPath)
        if (-not $commandKey) {
            return $null
        }

        $commandText = [string]$commandKey.GetValue("")
        $executablePath = Get-ExecutableFromCommandString -CommandText $commandText
        if ($executablePath -and (Test-Path $executablePath)) {
            return $executablePath
        }
    }
    catch {
        return $null
    }

    return $null
}

function Get-BrowserAppCommands {
    $discovered = @()

    $edgeFromPath = Get-Command "msedge.exe" -ErrorAction SilentlyContinue
    if ($edgeFromPath -and $edgeFromPath.Source -and (Test-Path $edgeFromPath.Source)) {
        $discovered += $edgeFromPath.Source
    }

    $chromeFromPath = Get-Command "chrome.exe" -ErrorAction SilentlyContinue
    if ($chromeFromPath -and $chromeFromPath.Source -and (Test-Path $chromeFromPath.Source)) {
        $discovered += $chromeFromPath.Source
    }

    $operaFromPath = Get-Command "opera.exe" -ErrorAction SilentlyContinue
    if ($operaFromPath -and $operaFromPath.Source -and (Test-Path $operaFromPath.Source)) {
        $discovered += $operaFromPath.Source
    }

    $braveFromPath = Get-Command "brave.exe" -ErrorAction SilentlyContinue
    if ($braveFromPath -and $braveFromPath.Source -and (Test-Path $braveFromPath.Source)) {
        $discovered += $braveFromPath.Source
    }

    $knownPaths = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Programs\Opera GX\opera.exe",
        "$env:LOCALAPPDATA\Programs\Opera\opera.exe",
        "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe",
        "$env:ProgramFiles(x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"
    )

    foreach ($candidate in $knownPaths) {
        if ($candidate -and (Test-Path $candidate)) {
            $discovered += $candidate
        }
    }

    $defaultBrowser = Get-DefaultBrowserExecutable
    if ($defaultBrowser) {
        $discovered += $defaultBrowser
    }

    $unique = $discovered | Select-Object -Unique
    return @($unique)
}

$backendProcess = $null
$browserProcess = $null
$stopBackendOnExit = $true

try {
    # Start backend in the background (no extra console window).
    $backendProcess = Start-Process -FilePath "python" -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $projectRoot -PassThru -WindowStyle Hidden
    Set-Content -Path $pidFilePath -Value $backendProcess.Id -Encoding ascii

    $backendReady = Wait-ForBackend -HealthUrl "http://127.0.0.1:8000/health"
    if (-not $backendReady) {
        throw "Backend failed to start in time."
    }

    $browserProcess = Start-HivemindBrowser -FrontendFilePath $frontendPath

    # Some browsers hand the URL off to an already running process and exit immediately.
    # In that case we cannot track a dedicated window lifecycle reliably.
    Start-Sleep -Milliseconds 1200
    $browserStillRunning = Get-Process -Id $browserProcess.Id -ErrorAction SilentlyContinue
    if (-not $browserStillRunning) {
        $stopBackendOnExit = $false
        Write-Host "Hivemind opened in existing browser profile."
        Write-Host "Use stop_hivemind.bat when you want to stop backend."
        return
    }

    Wait-Process -Id $browserProcess.Id
}
finally {
    if ($stopBackendOnExit) {
        if (Test-Path $pidFilePath) {
            Remove-Item $pidFilePath -Force -ErrorAction SilentlyContinue
        }

        if ($backendProcess -and -not $backendProcess.HasExited) {
            Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
