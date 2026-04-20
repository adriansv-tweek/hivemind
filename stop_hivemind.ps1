$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidFilePath = Join-Path $projectRoot ".hivemind-backend.pid"

if (-not (Test-Path $pidFilePath)) {
    Write-Host "No running Hivemind backend found."
    exit 0
}

$pidRaw = Get-Content $pidFilePath -ErrorAction SilentlyContinue
if (-not $pidRaw) {
    Remove-Item $pidFilePath -Force -ErrorAction SilentlyContinue
    Write-Host "No running Hivemind backend found."
    exit 0
}

$backendPid = 0
[void][int]::TryParse($pidRaw, [ref]$backendPid)
if ($backendPid -le 0) {
    Remove-Item $pidFilePath -Force -ErrorAction SilentlyContinue
    Write-Host "No running Hivemind backend found."
    exit 0
}

try {
    Stop-Process -Id $backendPid -Force -ErrorAction Stop
    Write-Host "Stopped Hivemind backend (PID $backendPid)."
}
catch {
    Write-Host "Backend was already stopped."
}
finally {
    Remove-Item $pidFilePath -Force -ErrorAction SilentlyContinue
}
