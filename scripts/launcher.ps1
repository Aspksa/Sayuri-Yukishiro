param(
    [string]$Root = "",
    [switch]$PreflightOnly,
    [switch]$TrayHost,
    [switch]$SkipPreflight
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = Split-Path -Parent $PSScriptRoot
}
$Root = (Resolve-Path $Root).Path
$SourceRoot = Join-Path $Root "src"
$env:PYTHONPATH = $SourceRoot

function Resolve-SayuriPython {
    $portable = Join-Path $Root "runtime\python\python.exe"
    if (Test-Path $portable) {
        return @{ Exe = $portable; Prefix = @() }
    }

    $venv = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $venv) {
        return @{ Exe = $venv; Prefix = @() }
    }

    $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Exe = $python.Source; Prefix = @() }
    }

    $py = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($py) {
        return @{ Exe = $py.Source; Prefix = @("-3") }
    }

    throw "Python 3 was not found. Put portable Python in runtime\python or install Python 3.11+."
}

$Python = Resolve-SayuriPython

function Invoke-Sayuri {
    param([string[]]$Arguments)

    $allArgs = @($Python.Prefix) + @("-m", "sayuri_yukishiro.main") + $Arguments
    & $Python.Exe @allArgs
    return $LASTEXITCODE
}

function Start-SayuriCore {
    $allArgs = @($Python.Prefix) + @("-m", "sayuri_yukishiro.main", "--serve")
    $quoted = @()
    foreach ($arg in $allArgs) {
        $quoted += '"' + ($arg -replace '"', '\"') + '"'
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Python.Exe
    $psi.Arguments = ($quoted -join " ")
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $psi.EnvironmentVariables["PYTHONPATH"] = $SourceRoot

    return [System.Diagnostics.Process]::Start($psi)
}

$port = 8765
if ($env:SAYURI_PORT) {
    $parsedPort = 0
    if ([int]::TryParse($env:SAYURI_PORT, [ref]$parsedPort)) {
        $port = $parsedPort
    }
}
$url = "http://127.0.0.1:$port"

function Test-SayuriHealth {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "$url/api/health" -TimeoutSec 1
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

if ($PreflightOnly) {
    $code = Invoke-Sayuri -Arguments @("--preflight")
    exit $code
}

if (-not $SkipPreflight) {
    $code = Invoke-Sayuri -Arguments @("--preflight")
    if ($code -ne 0) {
        exit $code
    }
}

if (-not $TrayHost) {
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:CoreProcess = $null
$script:OwnsCore = $false

if (-not (Test-SayuriHealth)) {
    $script:CoreProcess = Start-SayuriCore
    $script:OwnsCore = $true

    $healthy = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 250
        if (Test-SayuriHealth) {
            $healthy = $true
            break
        }
        if ($script:CoreProcess.HasExited) {
            break
        }
    }

    if (-not $healthy) {
        [System.Windows.Forms.MessageBox]::Show(
            "Sayuri core did not start. Run Sayuri-Yukishiro.bat again to see diagnostics.",
            "Sayuri Yukishiro",
            "OK",
            "Error"
        ) | Out-Null
        if ($script:OwnsCore -and $script:CoreProcess -and -not $script:CoreProcess.HasExited) {
            $script:CoreProcess.Kill()
        }
        exit 1
    }
}

Start-Process $url

$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Application
$notify.Text = "Sayuri Yukishiro v0.1.0"
$notify.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$openItem = $menu.Items.Add("Открыть Sayuri")
$diagnosticsItem = $menu.Items.Add("Диагностика")
$restartItem = $menu.Items.Add("Перезапустить ядро")
$exitItem = $menu.Items.Add("Выход")

$openAction = {
    Start-Process $url
}

$diagnosticsAction = {
    $args = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $Root "scripts\launcher.ps1"),
        "-Root", $Root,
        "-PreflightOnly"
    )
    Start-Process "powershell.exe" -ArgumentList $args
}

$restartAction = {
    if ($script:OwnsCore -and $script:CoreProcess -and -not $script:CoreProcess.HasExited) {
        $script:CoreProcess.Kill()
        $script:CoreProcess.WaitForExit(5000) | Out-Null
    }
    $script:CoreProcess = Start-SayuriCore
    $script:OwnsCore = $true

    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 250
        if (Test-SayuriHealth) {
            $notify.ShowBalloonTip(1500, "Sayuri Yukishiro", "Ядро перезапущено.", [System.Windows.Forms.ToolTipIcon]::Info)
            break
        }
    }
}

$exitAction = {
    [System.Windows.Forms.Application]::Exit()
}

$openItem.add_Click($openAction)
$diagnosticsItem.add_Click($diagnosticsAction)
$restartItem.add_Click($restartAction)
$exitItem.add_Click($exitAction)
$notify.add_DoubleClick($openAction)
$notify.ContextMenuStrip = $menu
$notify.ShowBalloonTip(1200, "Sayuri Yukishiro", "Система запущена.", [System.Windows.Forms.ToolTipIcon]::Info)

try {
    [System.Windows.Forms.Application]::Run()
}
finally {
    $notify.Visible = $false
    $notify.Dispose()
    if ($script:OwnsCore -and $script:CoreProcess -and -not $script:CoreProcess.HasExited) {
        $script:CoreProcess.Kill()
        $script:CoreProcess.WaitForExit(3000) | Out-Null
    }
}
