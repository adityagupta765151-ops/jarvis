# Puts a JARVIS button on your desktop. Run once:
#   powershell -ExecutionPolicy Bypass -File make_shortcut.ps1

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$link = Join-Path $desktop "JARVIS.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = Join-Path $here "start_jarvis.vbs"
$shortcut.WorkingDirectory = $here
$shortcut.IconLocation = Join-Path $here "jarvis.ico"
$shortcut.Description = "Start JARVIS"
$shortcut.Save()

Write-Host "Done. JARVIS is on your desktop." -ForegroundColor Cyan
Write-Host "To start it with Windows, press Win+R, type shell:startup, and copy the shortcut there."
