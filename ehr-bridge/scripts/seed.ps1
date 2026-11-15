param([int]$Patients=8)
$ErrorActionPreference='Stop'
$projectPath=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath=Join-Path (Split-Path $projectPath -Parent) '.venv\Scripts\python.exe'
Push-Location -LiteralPath $projectPath
try { & $pythonPath -m server.cli seed --patients $Patients; if ($LASTEXITCODE -ne 0) { throw 'Seed failed' } } finally { Pop-Location }
