<#
.SYNOPSIS
Starts Central Data Hub after Docker Desktop is ready.

.DESCRIPTION
This script is safe to run repeatedly. It does not rebuild images, delete
containers, alter source data, or expose the application to the Internet.
It starts the normal Compose stack and, when present, the local Google Sheets
override kept outside Git.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$logDirectory = Join-Path $projectRoot "data\logs"
$logPath = Join-Path $logDirectory "central-data-hub-startup.log"

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

function Write-StartupLog([string]$message) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $message" |
        Tee-Object -FilePath $logPath -Append
}

Set-Location $projectRoot
Write-StartupLog "Starting Central Data Hub."

$dockerReady = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    & docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        $dockerReady = $true
        break
    }
    Start-Sleep -Seconds 10
}

if (-not $dockerReady) {
    Write-StartupLog "Docker Desktop did not become ready within five minutes."
    throw "Docker Desktop is not ready. Open Docker Desktop, then run this script again."
}

$composeArguments = @("compose", "-f", "docker-compose.yml")
$googleOverride = Join-Path $projectRoot "docker-compose.google-sheets.yml"
if (Test-Path -LiteralPath $googleOverride -PathType Leaf) {
    $composeArguments += @("-f", "docker-compose.google-sheets.yml")
}
$composeArguments += @("up", "-d")

& docker @composeArguments
if ($LASTEXITCODE -ne 0) {
    Write-StartupLog "Docker Compose could not start Central Data Hub."
    throw "Docker Compose could not start Central Data Hub. See $logPath"
}

Write-StartupLog "Central Data Hub is running."
