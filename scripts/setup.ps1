# MyMeshy one-time setup. Run from the repo root:  .\scripts\setup.ps1
# Installs uv (if missing), creates a Python 3.11 venv, installs base backend
# deps + MCP deps, and installs frontend npm packages.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# --- uv (manages its own Python toolchains; system Python version is irrelevant)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host ">> Installing uv..." -ForegroundColor Cyan
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

# --- backend venv (Python 3.11 — the ML ecosystem's sweet spot)
Write-Host ">> Creating backend venv (Python 3.11)..." -ForegroundColor Cyan
uv venv --python 3.11 "$root\.venv"
uv pip install --python "$root\.venv\Scripts\python.exe" -r "$root\backend\requirements.txt"
uv pip install --python "$root\.venv\Scripts\python.exe" -r "$root\mcp\requirements.txt"

# --- frontend
Write-Host ">> Installing frontend packages..." -ForegroundColor Cyan
Push-Location "$root\frontend"
npm install
Pop-Location

Write-Host ""
Write-Host "Setup complete. Start the app with: .\scripts\dev.ps1" -ForegroundColor Green
Write-Host "The app runs in MOCK mode until you install real models (README: 'Installing real models')." -ForegroundColor Yellow
