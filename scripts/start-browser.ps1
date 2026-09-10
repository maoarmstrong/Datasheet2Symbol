param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv/Scripts/python.exe')) { throw 'Run scripts/setup.ps1 first.' }
if (-not (Test-Path 'frontend/dist/index.html')) { throw 'Frontend build missing. Run scripts/setup.ps1 first.' }
Write-Host "Datasheet2Symbol: http://127.0.0.1:$Port"
& .venv/Scripts/python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port $Port
