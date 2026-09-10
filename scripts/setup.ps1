$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv/Scripts/python.exe')) { py -3 -m venv .venv; if ($LASTEXITCODE) { throw 'Python 3.11+ required' } }
& .venv/Scripts/python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE) { throw 'Python dependency installation failed' }
Push-Location frontend
try {
 npm install
 if ($LASTEXITCODE) { throw 'Node.js 22+ and npm required; installation failed' }
 npm run build
 if ($LASTEXITCODE) { throw 'Frontend build failed' }
} finally { Pop-Location }
Write-Host 'Ready. Run ./scripts/start.ps1'
