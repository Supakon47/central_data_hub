<#
.SYNOPSIS
Removes only the named Central Data Hub startup task for the current user.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$taskName = "CentralDataHubStart"

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "ลบการเปิด Central Data Hub อัตโนมัติแล้ว"
} else {
    Write-Host "ไม่พบงานเปิด Central Data Hub อัตโนมัติ"
}
