<#
.SYNOPSIS
Registers a current-user startup task for Central Data Hub.

.DESCRIPTION
Run this once on the dedicated host computer after Docker Desktop has been
configured to start when the Windows user signs in. The task starts the local
Start-CentralDataHub.ps1 script hidden after each sign-in.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$taskName = "CentralDataHubStart"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$startScript = Join-Path $projectRoot "scripts\Start-CentralDataHub.ps1"

if (-not (Test-Path -LiteralPath $startScript -PathType Leaf)) {
    throw "ไม่พบไฟล์เริ่มระบบ: $startScript"
}

$powershellPath = Join-Path $PSHOME "powershell.exe"
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startScript`""
$action = New-ScheduledTaskAction -Execute $powershellPath -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

$taskArguments = @{
    TaskName = $taskName
    Action = $action
    Trigger = $trigger
    Settings = $settings
    Description = "Start Central Data Hub after this user signs in"
    Force = $true
}
Register-ScheduledTask @taskArguments | Out-Null

Write-Host "ติดตั้งการเปิด Central Data Hub อัตโนมัติแล้ว"
Write-Host "ตรวจสอบผลได้ที่ $projectRoot\data\logs\central-data-hub-startup.log"
