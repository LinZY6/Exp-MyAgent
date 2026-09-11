# Launch Pi coding agent from this repo (Windows).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$NodeDir = Join-Path $Root ".vendor\node"
if (-not (Test-Path (Join-Path $NodeDir "node.exe"))) {
    Write-Error "Node not found at $NodeDir. Run: powershell -File scripts\bootstrap-node.ps1"
}

$env:PATH = "$NodeDir;$env:PATH"
$env:NPM_CONFIG_REGISTRY = "https://registry.npmmirror.com"

$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $i = $line.IndexOf("=")
        if ($i -lt 1) { return }
        $name = $line.Substring(0, $i).Trim()
        $val = $line.Substring($i + 1).Trim().Trim("'").Trim('"')
        [Environment]::SetEnvironmentVariable($name, $val, "Process")
    }
}

# JD gateway uses Bearer (ANTHROPIC_AUTH_TOKEN), not x-api-key.
if (-not $env:ANTHROPIC_AUTH_TOKEN -and $env:LLM_API_KEY) {
    $env:ANTHROPIC_AUTH_TOKEN = $env:LLM_API_KEY
}

function Test-RealPython([string]$exe) {
    if (-not $exe) { return $false }
    if ($exe -match "WindowsApps") { return $false }
    return Test-Path $exe
}

function Resolve-ExpmemPython {
    if (Test-RealPython $env:EXPMEM_PYTHON) { return $env:EXPMEM_PYTHON }
    $vendor = Join-Path $Root ".vendor\python\python.exe"
    if (Test-Path $vendor) { return $vendor }
    return $null
}

if (-not $env:EXPMEM_ROOT) {
    $env:EXPMEM_ROOT = Join-Path $Root "expmem_data"
}
$srcPath = Join-Path $Root "tools\expmem\src"
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $srcPath
}
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Py = Resolve-ExpmemPython
if ($Py) {
    $env:EXPMEM_PYTHON = $Py
} else {
    Write-Host "python=missing (run: powershell -File scripts\bootstrap-python.ps1)"
}

# Seed toy collections once; never overwrite user JSONL.
$Fixtures = Join-Path $Root "fixtures"
foreach ($name in @("rec_ctr", "seq_recall")) {
    $dest = Join-Path $env:EXPMEM_ROOT "$name\experiments.jsonl"
    $src = Join-Path $Fixtures "$name\experiments.jsonl"
    if (-not (Test-Path $dest) -and (Test-Path $src)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
        Copy-Item $src $dest
    }
}

$PiCli = Join-Path $Root "node_modules\@earendil-works\pi-coding-agent\dist\cli.js"
if (-not (Test-Path $PiCli)) {
    Write-Error "Pi not installed. With Node on PATH: npm install"
}

Write-Host "cwd=$Root"
Write-Host "node=$(node -v)"
Write-Host "pi=$(node $PiCli -v)"
if ($env:EXPMEM_PYTHON) {
    Write-Host "expmem_python=$env:EXPMEM_PYTHON"
}
Write-Host "expmem_root=$env:EXPMEM_ROOT"
if ($env:ANTHROPIC_AUTH_TOKEN) {
    Write-Host "auth=ANTHROPIC_AUTH_TOKEN ($($env:ANTHROPIC_AUTH_TOKEN.Length) chars)"
} elseif ($env:ANTHROPIC_API_KEY) {
    Write-Host "auth=ANTHROPIC_API_KEY ($($env:ANTHROPIC_API_KEY.Length) chars)"
} elseif ($env:OPENAI_API_KEY) {
    Write-Host "auth=OPENAI_API_KEY"
} elseif ($env:DEEPSEEK_API_KEY) {
    Write-Host "auth=DEEPSEEK_API_KEY"
} else {
    Write-Host "auth=none (copy .env.example to .env, or run /login inside Pi)"
}

# Drop a leading "--" so `powershell -File scripts\pi.ps1 -- -v` still works.
$PiArgs = @($args)
if ($PiArgs.Count -ge 1 -and $PiArgs[0] -eq "--") {
    $PiArgs = $PiArgs[1..($PiArgs.Count - 1)]
}

& node $PiCli @PiArgs
exit $LASTEXITCODE
