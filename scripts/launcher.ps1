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
$script:ManualCoreTransition = $false
$script:LastUpdateNotice = ""

$VersionFile = Join-Path $Root "VERSION"
if (Test-Path $VersionFile) {
    $script:ProjectVersion = (Get-Content -Raw $VersionFile).Trim()
}
else {
    $script:ProjectVersion = "unknown"
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

function Get-SayuriHealth {
    try {
        $health = Invoke-RestMethod -Method Get -Uri "$url/api/health" -TimeoutSec 1
        if ($null -eq $health -or $health.project -ne "Sayuri Yukishiro") {
            return $null
        }
        return $health
    }
    catch {
        return $null
    }
}

function Test-SayuriHealth {
    $health = Get-SayuriHealth
    return $null -ne $health -and $health.status -eq "ok"
}

function Get-SayuriControlToken {
    if ($null -eq (Get-SayuriHealth)) {
        return ""
    }
    try {
        $response = Invoke-RestMethod -Method Get -Uri "$url/api/session/control-token" -TimeoutSec 2
        return [string]$response.token
    }
    catch {
        return ""
    }
}

function Get-SayuriUpdateStatus {
    if ($null -eq (Get-SayuriHealth)) {
        return $null
    }
    try {
        return Invoke-RestMethod -Method Get -Uri "$url/api/update/status" -TimeoutSec 2
    }
    catch {
        return $null
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
$notify.Text = "Sayuri Yukishiro v$script:ProjectVersion"
$notify.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$openItem = $menu.Items.Add("Открыть Sayuri")
$updatesItem = $menu.Items.Add("Обновления проекта")
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

$updatesAction = {
    try {
        $token = Get-SayuriControlToken
        if (-not [string]::IsNullOrWhiteSpace($token)) {
            $headers = @{ "X-Sayuri-Control-Token" = $token }
            Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$url/api/update/check" -Headers $headers -TimeoutSec 5 | Out-Null
        }
    }
    catch {
        # Страница сама покажет состояние/ошибку проверки.
    }
    Start-Process "$url/#updates"
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

    $script:ManualCoreTransition = $true
    try {
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
    finally {
        $script:ManualCoreTransition = $false
    }
}

$exitAction = {
    [System.Windows.Forms.Application]::Exit()
}

$openItem.add_Click($openAction)
$updatesItem.add_Click($updatesAction)
$diagnosticsItem.add_Click($diagnosticsAction)
$restartItem.add_Click($restartAction)
$exitItem.add_Click($exitAction)
$notify.add_DoubleClick($openAction)
$notify.ContextMenuStrip = $menu

$watchTimer = New-Object System.Windows.Forms.Timer
$watchTimer.Interval = 1000
$watchTimer.add_Tick({
    if (-not $script:OwnsCore -or $script:ManualCoreTransition) {
        return
    }
    if ($script:CoreProcess -and -not $script:CoreProcess.HasExited) {
        return
    }

    $health = Get-SayuriHealth
    if ($null -eq $health -or -not $health.pid) {
        return
    }

    try {
        $script:CoreProcess = Get-Process -Id ([int]$health.pid) -ErrorAction Stop
        if ($health.version) {
            $script:ProjectVersion = [string]$health.version
            $notify.Text = "Sayuri Yukishiro v$script:ProjectVersion"
        }

        $updateState = Get-SayuriUpdateStatus
        if ($null -ne $updateState) {
            $noticeKey = "$($updateState.phase):$($updateState.last_update)"
            if ($noticeKey -ne $script:LastUpdateNotice) {
                if ($updateState.phase -eq "completed") {
                    $notify.ShowBalloonTip(
                        2200,
                        "Обновления проекта",
                        "Обновление успешно установлено.",
                        [System.Windows.Forms.ToolTipIcon]::Info
                    )
                    $script:LastUpdateNotice = $noticeKey
                }
                elseif ($updateState.phase -eq "rolled_back") {
                    $notify.ShowBalloonTip(
                        2600,
                        "Обновления проекта",
                        "Обновление откатилось к предыдущей версии.",
                        [System.Windows.Forms.ToolTipIcon]::Warning
                    )
                    $script:LastUpdateNotice = $noticeKey
                }
            }
        }
    }
    catch {
        # Helper ещё может выполнять проверку/перезапуск.
    }
})
$watchTimer.Start()

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
    $watchTimer.Stop()
    $watchTimer.Dispose()
    $notify.Visible = $false
    $notify.Dispose()
    Stop-SayuriCore
}
