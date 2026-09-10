param([int]$Port=8000)
$ErrorActionPreference='Stop'
$d2sTemporaryKey=$false
if (-not $env:DASHSCOPE_BASE_URL) { $env:DASHSCOPE_BASE_URL=Read-Host 'Paste your Bailian OpenAI-compatible base URL (HTTPS, ends in /v1)' }
if (-not $env:DASHSCOPE_API_KEY) {
    $d2sTemporaryKey=$true
    $d2sSecret=Read-Host 'Bailian API Key (hidden, process memory only)' -AsSecureString
    $d2sPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($d2sSecret)
    try { $env:DASHSCOPE_API_KEY=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($d2sPointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($d2sPointer) }
}
try { & "$PSScriptRoot/start.ps1" -Port $Port }
finally { if ($d2sTemporaryKey) { Remove-Item Env:DASHSCOPE_API_KEY -ErrorAction SilentlyContinue } }
