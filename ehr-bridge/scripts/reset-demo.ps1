param([int]$Patients=8)
$ErrorActionPreference='Stop'
$projectPath=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath=Join-Path (Split-Path $projectPath -Parent) '.venv\Scripts\python.exe'
Push-Location -LiteralPath $projectPath
try { & $pythonPath -m server.cli reset --confirm RESET-DEMO --patients $Patients; if ($LASTEXITCODE -ne 0) { throw 'Reset failed; stop the app first' } } finally { Pop-Location }
