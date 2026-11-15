param([switch]$Install)
$ErrorActionPreference='Stop'
$projectPath=$PSScriptRoot
$workspacePath=Split-Path $projectPath -Parent
$pythonPath=Join-Path $workspacePath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the workspace Python environment first: python -m venv .venv, then run .\ehr-bridge\run.ps1 -Install.' }
$portableNode=Get-ChildItem -Path (Join-Path $workspacePath '.tools\node-*\node.exe') -ErrorAction SilentlyContinue | Select-Object -First 1
if ($portableNode) { $env:Path=$portableNode.Directory.FullName+';'+$env:Path }
$nodePath=(Get-Command node.exe -ErrorAction Stop).Source
$nextPath=Join-Path $projectPath 'web\node_modules\next\dist\bin\next'
if ($Install) {
    & $pythonPath -m pip install -r (Join-Path $projectPath 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    Push-Location (Join-Path $projectPath 'web')
    try { npm.cmd ci --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' } } finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath $nextPath)) { throw 'Run .\ehr-bridge\run.ps1 -Install to install frontend dependencies.' }
foreach ($port in @(8200,3200)) {
    $probe=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,$port)
    try { $probe.Start() } catch { throw "Port $port is occupied. Stop the earlier EHR Bridge process in its terminal first." } finally { $probe.Stop() }
}
Push-Location -LiteralPath $projectPath
try { & $pythonPath -m server.cli seed; if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the demo database' } } finally { Pop-Location }
$logPath=Join-Path $projectPath '.data\logs'
New-Item -ItemType Directory -Force -Path $logPath | Out-Null
$backend=Start-Process -FilePath $pythonPath -ArgumentList '-u','-m','uvicorn','server.app:app','--host','127.0.0.1','--port','8200' -WorkingDirectory $projectPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logPath 'api.log') -RedirectStandardError (Join-Path $logPath 'api-error.log') -PassThru
try {
    $ready=$false;$deadline=[DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $deadline) {
        $backend.Refresh();if ($backend.HasExited) { throw "API startup failed. Read $logPath\api-error.log" }
        try { $health=Invoke-RestMethod 'http://127.0.0.1:8200/api/health' -TimeoutSec 1; if ($health.status -eq 'ok') { $ready=$true;break } } catch { }
        Start-Sleep -Milliseconds 200
    }
    if (-not $ready) { throw "API did not become healthy. Read $logPath\api-error.log" }
    Write-Host 'EHR Bridge: http://127.0.0.1:3200 | API docs: http://127.0.0.1:8200/docs'
    Write-Host 'Keep this terminal open. Ctrl+C stops this app. Existing projects on 3000/3100 are untouched.'
    Push-Location (Join-Path $projectPath 'web')
    try { & $nodePath $nextPath dev --hostname 127.0.0.1 --port 3200 } finally { Pop-Location }
} finally { $backend.Refresh();if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -ErrorAction SilentlyContinue };$backend.Dispose() }
