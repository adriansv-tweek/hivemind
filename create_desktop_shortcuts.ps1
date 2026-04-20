$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktopPath = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell

function New-DesktopShortcut {
    param(
        [string]$ShortcutName,
        [string]$TargetPath
    )

    $shortcutPath = Join-Path $desktopPath "$ShortcutName.lnk"
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.IconLocation = "%SystemRoot%\System32\SHELL32.dll,220"
    $shortcut.Save()
}

New-DesktopShortcut -ShortcutName "Hivemind" -TargetPath (Join-Path $projectRoot "start_hivemind.bat")
New-DesktopShortcut -ShortcutName "Hivemind Stop" -TargetPath (Join-Path $projectRoot "stop_hivemind.bat")

Write-Host "Created desktop shortcuts: Hivemind, Hivemind Stop"
