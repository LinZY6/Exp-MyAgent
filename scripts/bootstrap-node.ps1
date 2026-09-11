# Download portable Node.js into .vendor/node (gitignored).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DestDir = Join-Path $Root ".vendor"
$Ver = "v22.22.2"
$Zip = Join-Path $env:TEMP "node-win-x64.zip"
$Urls = @(
    "https://cdn.npmmirror.com/binaries/node/$Ver/node-$Ver-win-x64.zip",
    "https://mirrors.huaweicloud.com/nodejs/$Ver/node-$Ver-win-x64.zip",
    "https://nodejs.org/dist/$Ver/node-$Ver-win-x64.zip"
)

New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
$ok = $false
foreach ($url in $Urls) {
    Write-Host "TRY $url"
    curl.exe -L --fail --connect-timeout 20 --max-time 180 -o $Zip $url
    if ($LASTEXITCODE -eq 0 -and (Test-Path $Zip) -and ((Get-Item $Zip).Length -gt 1MB)) {
        $ok = $true
        break
    }
}
if (-not $ok) { throw "Failed to download Node.js $Ver" }

$Stage = Join-Path $DestDir "node-stage"
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
Expand-Archive -Path $Zip -DestinationPath $Stage -Force
$Extracted = Get-ChildItem $Stage -Directory | Where-Object { $_.Name -like "node-v*" } | Select-Object -First 1
$Target = Join-Path $DestDir "node"
if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
Move-Item $Extracted.FullName $Target
Remove-Item -Recurse -Force $Stage
Write-Host "node=$(& (Join-Path $Target 'node.exe') -v)"
