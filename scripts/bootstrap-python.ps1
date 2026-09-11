# Download embeddable CPython into .vendor/python (gitignored).
# Stdlib-only; expmem has no required third-party packages.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DestDir = Join-Path $Root ".vendor"
$Ver = "3.12.10"
$Zip = Join-Path $env:TEMP "python-embed-amd64.zip"
$Urls = @(
    "https://mirrors.huaweicloud.com/python/$Ver/python-$Ver-embed-amd64.zip",
    "https://www.python.org/ftp/python/$Ver/python-$Ver-embed-amd64.zip"
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
if (-not $ok) { throw "Failed to download Python $Ver embeddable" }

$Target = Join-Path $DestDir "python"
if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Expand-Archive -Path $Zip -DestinationPath $Target -Force

$Pth = Get-ChildItem $Target -Filter "python*._pth" | Select-Object -First 1
if (-not $Pth) { throw "python._pth missing after extract" }
$lines = Get-Content $Pth.FullName
$rewritten = foreach ($line in $lines) {
    if ($line -match '^\s*#\s*import site') { "import site" }
    else { $line }
}
if ($rewritten -notcontains "import site") {
    $rewritten += "import site"
}
$SrcRel = "..\..\tools\expmem\src"
if ($rewritten -notcontains $SrcRel) {
    $rewritten += $SrcRel
}
Set-Content -Path $Pth.FullName -Value $rewritten -Encoding ascii

$Py = Join-Path $Target "python.exe"
Write-Host "python=$(& $Py -c 'import sys; print(sys.version.split()[0])')"
Write-Host "exe=$Py"
