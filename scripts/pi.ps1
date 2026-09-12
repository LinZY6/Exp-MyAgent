# Launch Pi coding agent from this repo (Windows).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# Classic cmd.exe mis-wraps CJK while Pi streams (looks like duplicated lines).
# Prefer Windows Terminal. Set PI_NO_WT=1 to stay in the current console.
function Get-WindowsTerminal {
    foreach ($c in @(
            (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\wt.exe"),
            (Join-Path ${env:ProgramFiles} "Windows Terminal\wt.exe")
        )) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    $cmd = Get-Command wt.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

if (-not $env:WT_SESSION -and -not $env:PI_NO_WT) {
    $wt = Get-WindowsTerminal
    if ($wt) {
        Write-Host "relaunch=Windows Terminal (avoids cmd.exe CJK wrap). PI_NO_WT=1 to stay here."
        $script = Join-Path $Root "scripts\pi.ps1"
        $wtArgs = @(
            "-d", $Root,
            "--",
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $script
        )
        if ($args.Count -gt 0) { $wtArgs += @($args) }
        & $wt @wtArgs
        exit $LASTEXITCODE
    }
    Write-Host "warn=Windows Terminal not found; Chinese TUI may wrap badly in cmd.exe."
}

try {
    cmd /c "chcp 65001 >nul"
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    [Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
} catch {
}

function Resolve-LabPath([string]$lab) {
    $lab = $lab.Trim().Trim('"').Trim("'")
    if ([string]::IsNullOrWhiteSpace($lab)) { throw "--lab needs a folder" }
    if ([IO.Path]::IsPathRooted($lab)) {
        return [IO.Path]::GetFullPath($lab)
    }
    $norm = $lab -replace '/', '\'
    if ($norm.Contains('\')) {
        return [IO.Path]::GetFullPath((Join-Path $Root $norm))
    }
    return [IO.Path]::GetFullPath((Join-Path (Join-Path $Root "experiments") $norm))
}

# Strip --lab / --empty-lab so Pi's CLI does not see them.
$LabName = $null
$EmptyLab = $false
$PiArgsList = New-Object System.Collections.ArrayList
$rawArgs = @($args)
if ($rawArgs.Count -ge 1 -and [string]$rawArgs[0] -eq "--") {
    $rawArgs = @($rawArgs[1..($rawArgs.Count - 1)])
}
for ($i = 0; $i -lt $rawArgs.Count; $i++) {
    $a = [string]$rawArgs[$i]
    if ($a -eq "--lab" -or $a -eq "-Lab") {
        if ($i + 1 -ge $rawArgs.Count) { throw "--lab needs a folder" }
        $LabName = [string]$rawArgs[++$i]
        continue
    }
    if ($a.StartsWith("--lab=")) {
        $LabName = $a.Substring(6)
        continue
    }
    if ($a -eq "--empty-lab") {
        $EmptyLab = $true
        continue
    }
    [void]$PiArgsList.Add($rawArgs[$i])
}

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

if (-not $LabName -and $env:EXPERIMENT_LAB) {
    $LabName = $env:EXPERIMENT_LAB
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

$LabPath = $null
if ($LabName) {
    if (-not $Py) { throw "Python required to init a lab. Run: powershell -File scripts\bootstrap-python.ps1" }
    $LabPath = Resolve-LabPath $LabName
    $init = Join-Path $Root "tools\fnfit\init_lab.py"
    $initArgs = @($init, "--lab", $LabPath, "--repo", $Root)
    if ($EmptyLab) { $initArgs += "--empty" }
    & $Py @initArgs
    if ($LASTEXITCODE -ne 0) { throw "init_lab failed for $LabPath" }
    $env:EXPERIMENT_LAB = $LabPath
    $env:EXPMEM_ROOT = $LabPath
    $sessionFile = Join-Path $Root ".pi\lab-session.json"
    $sessionJson = (@{ lab = $LabPath; collection = "fn_fit" } | ConvertTo-Json -Compress)
    Set-Content -Path $sessionFile -Value $sessionJson -Encoding utf8
} else {
    $sessionFile = Join-Path $Root ".pi\lab-session.json"
    if (Test-Path $sessionFile) {
        Remove-Item $sessionFile -Force
    }
    if (-not $env:EXPMEM_ROOT) {
        $env:EXPMEM_ROOT = Join-Path $Root "expmem_data"
    }
    # Seed toy collections once; never overwrite user JSONL.
    $Fixtures = Join-Path $Root "fixtures"
    foreach ($name in @("rec_ctr", "seq_recall", "fn_fit")) {
        $dest = Join-Path $env:EXPMEM_ROOT "$name\experiments.jsonl"
        $src = Join-Path $Fixtures "$name\experiments.jsonl"
        if (-not (Test-Path $dest) -and (Test-Path $src)) {
            New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
            Copy-Item $src $dest
        }
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
if ($env:EXPERIMENT_LAB) {
    Write-Host "lab=$env:EXPERIMENT_LAB"
    Write-Host "lab_code=$(Join-Path $env:EXPERIMENT_LAB 'src')"
    Write-Host "lab_jsonl=$(Join-Path $env:EXPERIMENT_LAB 'fn_fit\experiments.jsonl')"
}
if ($env:ANTHROPIC_AUTH_TOKEN) {
    Write-Host "auth=ANTHROPIC_AUTH_TOKEN ($($env:ANTHROPIC_AUTH_TOKEN.Length) chars)"
} elseif ($env:ANTHROPIC_API_KEY) {
    Write-Host "auth=ANTHROPIC_API_KEY ($($env:ANTHROPIC_API_KEY.Length) chars)"
} elseif ($env:OPENAI_API_KEY) {
    Write-Host "auth=OPENAI_API_KEY"
} elseif ($env:DEEPSEEK_API_KEY) {
    Write-Host "auth=DEEPSEEK_API_KEY ($($env:DEEPSEEK_API_KEY.Length) chars)"
} else {
    Write-Host "auth=none (copy .env.example to .env, or run /login inside Pi)"
}
if ($env:PI_MODEL) {
    Write-Host "model=$env:PI_MODEL"
}

if ($PiArgsList.Count -gt 0) {
    $PiArgs = @($PiArgsList.ToArray())
} else {
    $PiArgs = @()
}

$hasModel = $false
foreach ($a in $PiArgs) {
    if ($a -eq "--model" -or $a -eq "-m" -or ($a -is [string] -and $a.StartsWith("--model="))) {
        $hasModel = $true
        break
    }
}
if ($env:PI_MODEL -and -not $hasModel) {
    $PiArgs = @("--model", $env:PI_MODEL) + $PiArgs
}

& node $PiCli @PiArgs
exit $LASTEXITCODE
