param(
    [ValidateSet('Start', 'Stop', 'Terminal', 'Validate')][string]$Mode = 'Start',
    [string]$ConfigFile = (Join-Path $PSScriptRoot 'CareerOS.toml'),
    [ValidateSet('Backend', 'Frontend', 'Worker')][string]$Service = 'Backend'
)
$ErrorActionPreference = 'Stop'
$scriptFile = $PSCommandPath
$bootstrapPython = Join-Path (Split-Path $PSScriptRoot -Parent) 'backend\venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $bootstrapPython)) { throw "CareerOS Python environment not found: $bootstrapPython" }
$configJson = & $bootstrapPython -c 'import json,sys,tomllib; print(json.dumps(tomllib.load(open(sys.argv[1],''rb''))))' $ConfigFile
if ($LASTEXITCODE -ne 0) { throw 'Could not read CareerOS.toml.' }
$config = $configJson | ConvertFrom-Json
$project = [IO.Path]::GetFullPath($config.project_path)
$python = Join-Path $project 'backend\venv\Scripts\python.exe'
$runtime = Join-Path $project '.launcher'
$stateFile = Join-Path $runtime 'processes.json'
foreach ($port in @($config.frontend_port, $config.backend_port)) {
    if ([int]$port -lt 1024 -or [int]$port -gt 65535) { throw 'Ports must be between 1024 and 65535.' }
}
if ($config.frontend_port -eq $config.backend_port) { throw 'Frontend and backend ports must differ.' }
if ([int]$config.startup_timeout_seconds -lt 15 -or [int]$config.startup_timeout_seconds -gt 600) { throw 'Startup timeout must be 15-600 seconds.' }
foreach ($required in @($python, (Join-Path $project 'frontend\package.json'), (Join-Path $project 'docker-compose.yml'))) {
    if (!(Test-Path -LiteralPath $required)) { throw "Required file missing: $required" }
}
$backendUrl = 'http://127.0.0.1:' + $config.backend_port
$frontendUrl = 'http://127.0.0.1:' + $config.frontend_port

if ($Mode -eq 'Validate') {
    Get-Command docker.exe, npm.cmd, powershell.exe -ErrorAction Stop | Out-Null
    Write-Host "Configuration and prerequisites valid: $project"
    exit 0
}
if ($Mode -eq 'Terminal') {
    $Host.UI.RawUI.WindowTitle = "CareerOS - $Service"
    $env:PYTHONUNBUFFERED = '1'
    if ($Service -eq 'Frontend') {
        Set-Location -LiteralPath (Join-Path $project 'frontend')
        $env:NEXT_PUBLIC_CAREEROS_API_BASE = $backendUrl
        & npm.cmd run dev -- --hostname 127.0.0.1 --port $config.frontend_port
    } else {
        Set-Location -LiteralPath (Join-Path $project 'backend')
        if ($Service -eq 'Backend') {
            & $python -m uvicorn main:app --host 127.0.0.1 --port $config.backend_port --reload
        } else {
            & $python -m automation.worker
        }
    }
    exit $LASTEXITCODE
}

New-Item -ItemType Directory -Path $runtime -Force | Out-Null
$mutex = New-Object Threading.Mutex($false, 'Local\CareerOSDesktopController')
if (!$mutex.WaitOne(0)) { Write-Host 'Another CareerOS start/stop operation is already running.'; exit 1 }
try {
    function Test-Http($Url) {
        try { return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 }
        catch { return $false }
    }
    function Test-Port($Port) {
        $client = New-Object Net.Sockets.TcpClient
        try { return $client.ConnectAsync('127.0.0.1', [int]$Port).Wait(800) -and $client.Connected }
        catch { return $false }
        finally { $client.Dispose() }
    }
    function Read-State {
        if (Test-Path -LiteralPath $stateFile) {
            return @(Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json)
        }
        return @()
    }
    function Get-TrackedProcess($Entry) {
        $candidate = Get-Process -Id $Entry.pid -ErrorAction SilentlyContinue
        if ($candidate -and $candidate.StartTime.ToUniversalTime().Ticks.ToString() -eq $Entry.started_ticks) { return $candidate }
        return $null
    }
    $script:entries = @(Read-State)
    function Start-ServiceWindow($Name, $Hidden = $false) {
        $arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Mode Terminal -ConfigFile "{1}" -Service {2}' -f $scriptFile, $ConfigFile, $Name
        $options = @{ FilePath = 'powershell.exe'; ArgumentList = $arguments; PassThru = $true; WorkingDirectory = $project }
        if ($Hidden) {
            $options.WindowStyle = 'Hidden'
            $options.RedirectStandardOutput = Join-Path $runtime 'worker.log'
            $options.RedirectStandardError = Join-Path $runtime 'worker-error.log'
        } else { $options.WindowStyle = 'Normal' }
        $child = Start-Process @options
        $script:entries += [pscustomobject]@{service=$Name;pid=$child.Id;started_ticks=$child.StartTime.ToUniversalTime().Ticks.ToString()}
        ConvertTo-Json -InputObject @($script:entries) | Set-Content -LiteralPath $stateFile -Encoding UTF8
    }
    function Invoke-DockerBounded($Arguments, $Seconds = 30) {
        $options = @{FilePath='docker.exe';ArgumentList=$Arguments;WindowStyle='Hidden';PassThru=$true;
            RedirectStandardOutput=(Join-Path $runtime 'docker-command.log');RedirectStandardError=(Join-Path $runtime 'docker-command-error.log')}
        $child = Start-Process @options
        # Windows PowerShell 5.1 can lose ExitCode after the process exits unless
        # its native handle is retained before WaitForExit (PowerShell 7 differs).
        $processHandle = $child.Handle
        if (!$child.WaitForExit($Seconds * 1000)) {
            Stop-Process -Id $child.Id -ErrorAction SilentlyContinue
            return $false
        }
        # Finish draining redirected output now that the process has exited.
        $child.WaitForExit()
        return $child.ExitCode -eq 0
    }
    Set-Location -LiteralPath $project
    if ($Mode -eq 'Stop') {
        $failed = $false
        foreach ($entry in $script:entries) {
            if (Get-TrackedProcess $entry) {
                Write-Host "Stopping CareerOS $($entry.service)..."
                & taskkill.exe /PID $entry.pid /T /F | Out-Host
                if ($LASTEXITCODE -ne 0) { $failed = $true }
            }
        }
        $remaining = @($script:entries | Where-Object { Get-TrackedProcess $_ })
        ConvertTo-Json -InputObject $remaining | Set-Content -LiteralPath $stateFile -Encoding UTF8
        if (Invoke-DockerBounded 'info --format {{.ServerVersion}}' 10) {
            Write-Host 'Stopping CareerOS containers (database volumes are preserved)...'
            & docker.exe compose -f (Join-Path $project 'docker-compose.yml') stop --timeout 20
            if ($LASTEXITCODE -ne 0) { $failed = $true }
        }
        if ($config.stop_docker_desktop) {
            Write-Host 'Stopping Docker Desktop (affects all Docker projects)...'
            if (!(Invoke-DockerBounded 'desktop stop --timeout 45' 50)) {
                Write-Warning 'Docker Desktop did not confirm shutdown. See .launcher/docker-command-error.log.'
                $failed = $true
            }
        }
        foreach ($port in @($config.frontend_port, $config.backend_port)) {
            if (Test-Port $port) { Write-Warning "Port $port remains active. A separately started server was left untouched." }
        }
        if ($failed) { throw 'Some shutdown operations failed. Review the messages above.' }
        Write-Host 'CareerOS launcher-managed processes stopped.'
    } else {
        Write-Host 'Checking Docker Desktop...'
        if (!(Invoke-DockerBounded 'info --format {{.ServerVersion}}' 10)) {
            if (!(Invoke-DockerBounded 'desktop start --detach' 15)) {
                $startMessage = (Get-Content -LiteralPath (Join-Path $runtime 'docker-command-error.log') -Raw) + (Get-Content -LiteralPath (Join-Path $runtime 'docker-command.log') -Raw)
                # The desktop app can be open while its engine is still booting.
                if ($startMessage -notmatch 'already running') {
                    throw "Docker Desktop could not be started: $startMessage"
                }
            }
            $deadline = (Get-Date).AddSeconds([int]$config.startup_timeout_seconds)
            while (!(Invoke-DockerBounded 'info --format {{.ServerVersion}}' 10)) {
                if ((Get-Date) -gt $deadline) { throw 'Docker startup timed out. Open Docker Desktop to inspect its status.' }
                Start-Sleep -Seconds 3
            }
        }
        Write-Host 'Starting CareerOS database containers...'
        & docker.exe compose -f (Join-Path $project 'docker-compose.yml') up -d --wait --wait-timeout 90
        if ($LASTEXITCODE -ne 0) { throw 'CareerOS containers could not become ready.' }
        foreach ($name in @('Backend', 'Frontend')) {
            $port = if ($name -eq 'Backend') { $config.backend_port } else { $config.frontend_port }
            $url = if ($name -eq 'Backend') { $backendUrl + '/health' } else { $frontendUrl }
            if (Test-Port $port) {
                if ($name -eq 'Backend' -and !(Test-Http $url)) { throw "Port $port is occupied but the CareerOS health endpoint is unavailable." }
                Write-Host "$name port $port is already active; reusing it without restarting."
            } else {
                Write-Host "Opening CareerOS $name terminal..."
                Start-ServiceWindow $name
            }
            $deadline = (Get-Date).AddSeconds([int]$config.startup_timeout_seconds)
            while (!(Test-Http $url)) {
                if ((Get-Date) -gt $deadline) { throw "$name startup timed out. Inspect its terminal and use CareerOS-Stop if needed." }
                Start-Sleep -Seconds 2
            }
        }
        if ($config.start_worker) {
            $runningWorkers = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
                $_.ExecutablePath -and $_.ExecutablePath.Equals($python, [StringComparison]::OrdinalIgnoreCase) -and $_.CommandLine -match 'automation\.worker'
            })
            if ($runningWorkers.Count -eq 0) {
                Write-Host 'Starting background worker; logs are in .launcher.'
                Start-ServiceWindow 'Worker' $true
            } else { Write-Host 'An existing CareerOS worker is already running; leaving it unchanged.' }
        }
        if ($config.open_browser) { Start-Process $frontendUrl }
        Write-Host "CareerOS ready: $frontendUrl"
    }
} catch {
    Write-Host "CareerOS: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
