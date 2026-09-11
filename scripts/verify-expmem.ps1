# Probe expmem: dual-collection search, duplicate create, no n9 refs.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Test-RealPython([string]$exe) {
    if (-not $exe) { return $false }
    if ($exe -match "WindowsApps") { return $false }
    return Test-Path $exe
}

$Py = $null
if (Test-RealPython $env:EXPMEM_PYTHON) { $Py = $env:EXPMEM_PYTHON }
$vendor = Join-Path $Root ".vendor\python\python.exe"
if (-not $Py -and (Test-Path $vendor)) { $Py = $vendor }
if (-not $Py) {
    throw "No real Python. Run: powershell -File scripts\bootstrap-python.ps1"
}

$env:PYTHONUTF8 = "1"
& $Py (Join-Path $Root "scripts\verify-expmem.py")
exit $LASTEXITCODE
