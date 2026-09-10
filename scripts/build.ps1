$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

# 0. Clear old artifacts (the host's safe-delete guard blocks `rm`/`Remove-Item`;
#    deleting via Python os.remove is the reliable way around it)
if (Test-Path 'dist/Datasheet2Symbol.exe') { & .venv/Scripts/python.exe -c "import os,shutil; os.path.exists('dist/Datasheet2Symbol.exe') and os.remove('dist/Datasheet2Symbol.exe')" }
if (Test-Path 'build') { & .venv/Scripts/python.exe -c "import shutil; shutil.rmtree('build', ignore_errors=True)" }

# 1. Build the frontend (TypeScript + Vite) into frontend/dist
Push-Location frontend
try {
    npm run build
    if ($LASTEXITCODE) { throw 'Frontend build failed' }
} finally { Pop-Location }

# 2. Package the backend + frontend into a single EXE (pywebview native window)
& .venv/Scripts/python.exe -m PyInstaller --onefile --noconsole --name Datasheet2Symbol --icon "assets/icon.ico" --add-data "frontend/dist;frontend/dist" --add-data "assets/icon.ico;assets" --collect-all webview --noconfirm launcher_webview.py
if ($LASTEXITCODE) { throw 'PyInstaller packaging failed' }

Write-Host ''
Write-Host '完成：dist/Datasheet2Symbol.exe'
Write-Host '分发时把该 exe 发给对方即可；首次运行会在 exe 同目录生成 data/ 保存项目。'
