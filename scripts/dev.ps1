param([switch]$Install)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $repoPath
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { python -m venv .venv }
$pythonPath = Join-Path $repoPath '.venv\Scripts\python.exe'
$portableNode = Get-ChildItem -LiteralPath (Join-Path $repoPath '.tools') -Filter node.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($portableNode) { $env:Path = $portableNode.Directory.FullName + ';' + $env:Path }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22+ or add it to PATH.' }
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$nextPath = Join-Path $repoPath 'frontend\node_modules\next\dist\bin\next'
if ($Install) {
    & $pythonPath -m pip install -r backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed' }
    Push-Location frontend
    try { npm.cmd ci --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' } }
    finally { Pop-Location }
}
if (Test-Path -LiteralPath '.env') {
    $dotenvJson = & $pythonPath (Join-Path $PSScriptRoot 'read_env.py')
    if ($LASTEXITCODE -ne 0) { throw 'Could not load the local environment configuration.' }
    $dotenvValues = $dotenvJson | ConvertFrom-Json
    foreach ($property in $dotenvValues.PSObject.Properties) { [Environment]::SetEnvironmentVariable($property.Name, [string]$property.Value, 'Process') }
}
if (-not (Test-Path -LiteralPath $nextPath)) { throw 'Frontend dependencies are missing. Run .\scripts\dev.ps1 -Install.' }

# Fail before migrations/startup instead of silently starting on a different port.
foreach ($port in @(8000, 3000)) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    try { $listener.Start() }
    catch { throw "Port $port is already in use. Stop the existing EHR Bridge server in its terminal, then run this launcher again." }
    finally { $listener.Stop() }
}

& $pythonPath -m backend.app.cli migrate
if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
& $pythonPath -m backend.app.cli seed
if ($LASTEXITCODE -ne 0) { throw 'Seed failed' }
$logDirectory = Join-Path $repoPath '.data\logs'
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$apiLog = Join-Path $logDirectory 'backend.log'
$apiErrorLog = Join-Path $logDirectory 'backend-error.log'
$apiProcess = Start-Process -FilePath $pythonPath -ArgumentList '-u','-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $repoPath -WindowStyle Hidden -RedirectStandardOutput $apiLog -RedirectStandardError $apiErrorLog -PassThru
try {
    Write-Host 'Waiting for the EHR Bridge API on port 8000...'
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    $apiReady = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        $apiProcess.Refresh()
        if ($apiProcess.HasExited) {
            $apiProcess.WaitForExit()
            Get-Content -LiteralPath $apiErrorLog -Tail 25 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
            throw "Backend exited during startup (exit code $($apiProcess.ExitCode)). See $apiErrorLog"
        }
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 1
            if ($health.status -eq 'ok' -and $health.synthetic_only -eq $true) { $apiReady = $true; break }
        } catch { } # Startup connection refusals are expected until uvicorn is ready.
        Start-Sleep -Milliseconds 200
    }
    if (-not $apiReady) { throw "Backend did not become ready within 30 seconds. See $apiErrorLog" }
    Write-Host 'EHR Bridge: http://127.0.0.1:3000 | API docs: http://127.0.0.1:8000/docs'
    Write-Host "Backend logs: $apiLog and $apiErrorLog"
    Write-Host 'Keep this terminal open. Press Ctrl+C to stop both servers.'
    Push-Location frontend
    # Direct node invocation avoids cmd.exe's "Terminate batch job" prompt.
    try {
        & $nodePath $nextPath dev --hostname 127.0.0.1 --port 3000
        if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1073741510) { throw "Frontend exited with code $LASTEXITCODE. Backend logs: $apiErrorLog" }
    } finally { Pop-Location }
} finally {
    $apiProcess.Refresh()
    if (-not $apiProcess.HasExited) { Stop-Process -Id $apiProcess.Id -ErrorAction SilentlyContinue }
    $apiProcess.Dispose()
}
