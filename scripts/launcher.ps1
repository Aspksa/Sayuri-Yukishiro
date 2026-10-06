param(
    [string]$Root = "",
    [switch]$PreflightOnly,
    [switch]$TrayHost,
    [switch]$SkipPreflight,
    [switch]$NoUpdate
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = Split-Path -Parent $PSScriptRoot
}
$Root = (Resolve-Path $Root).Path
$SourceRoot = Join-Path $Root "src"
$env:PYTHONPATH = $SourceRoot
$script:SayuriExitCode = 0
$script:ShutdownToken = ""

$VersionFile = Join-Path $Root "VERSION"
if (Test-Path $VersionFile) {
    $ProjectVersion = (Get-Content -Raw $VersionFile).Trim()
}
else {
    $ProjectVersion = "unknown"
}

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
    $script:SayuriExitCode = $LASTEXITCODE
}

function Start-SayuriCore {
    $script:ShutdownToken = [guid]::NewGuid().ToString("N")
    $processArgs = @($Python.Prefix) + @("-m", "sayuri_yukishiro.main", "--serve")
    $quoted = @()
    foreach ($item in $processArgs) {
        $quoted += '"' + ($item -replace '"', '\"') + '"'
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Python.Exe
    $psi.Arguments = ($quoted -join " ")
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $psi.EnvironmentVariables["PYTHONPATH"] = $SourceRoot
    $psi.EnvironmentVariables["SAYURI_SHUTDOWN_TOKEN"] = $script:ShutdownToken

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

function Stop-SayuriCore {
    if (-not $script:OwnsCore -or -not $script:CoreProcess -or $script:CoreProcess.HasExited) {
        return
    }

    $stopped = $false
    if (-not [string]::IsNullOrWhiteSpace($script:ShutdownToken)) {
        try {
            $headers = @{ "X-Sayuri-Shutdown-Token" = $script:ShutdownToken }
            Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$url/api/shutdown" -Headers $headers -TimeoutSec 2 | Out-Null
            $stopped = $script:CoreProcess.WaitForExit(5000)
        }
        catch {
            $stopped = $false
        }
    }

    if (-not $stopped -and -not $script:CoreProcess.HasExited) {
        $script:CoreProcess.Kill()
        $script:CoreProcess.WaitForExit(3000) | Out-Null
    }
}

function Run-Preflight {
    $cliArgs = @("--preflight")
    if ($NoUpdate) {
        $cliArgs += "--no-update"
    }
    Invoke-Sayuri -Arguments $cliArgs
}

if ($PreflightOnly) {
    Run-Preflight
    exit $script:SayuriExitCode
}

if (-not $SkipPreflight) {
    Run-Preflight
    if ($script:SayuriExitCode -ne 0) {
        exit $script:SayuriExitCode
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
        Stop-SayuriCore
        exit 1
    }
}

Start-Process $url

$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Application
$notify.Text = "Sayuri Yukishiro v$ProjectVersion"
$notify.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$openItem = $menu.Items.Add("Открыть Sayuri")
$diagnosticsItem = $menu.Items.Add("Диагностика")
$restartItem = $menu.Items.Add("Перезапустить ядро")
$exitItem = $menu.Items.Add("Выход")

if (-not $script:OwnsCore) {
    $restartItem.Enabled = $false
    $restartItem.ToolTipText = "Это окно трея не запускало текущее ядро."
}

$openAction = {
    Start-Process $url
}

$diagnosticsAction = {
    $cliArgs = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $Root "scripts\launcher.ps1"),
        "-PreflightOnly",
        "-NoUpdate"
    )
    Start-Process "powershell.exe" -ArgumentList $cliArgs
}

$restartAction = {
    if (-not $script:OwnsCore) {
        return
    }

    Stop-SayuriCore
    $script:CoreProcess = Start-SayuriCore

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

    if ($healthy) {
        $notify.ShowBalloonTip(
            1500,
            "Sayuri Yukishiro",
            "Ядро перезапущено.",
            [System.Windows.Forms.ToolTipIcon]::Info
        )
    }
    else {
        [System.Windows.Forms.MessageBox]::Show(
            "Sayuri core did not restart. Run diagnostics.",
            "Sayuri Yukishiro",
            "OK",
            "Error"
        ) | Out-Null
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
$notify.ShowBalloonTip(
    1200,
    "Sayuri Yukishiro",
    "Система запущена.",
    [System.Windows.Forms.ToolTipIcon]::Info
)

try {
    [System.Windows.Forms.Application]::Run()
}
finally {
    $notify.Visible = $false
    $notify.Dispose()
    Stop-SayuriCore
}
