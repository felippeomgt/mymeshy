# Start backend (port 8420) and frontend dev server (port 5173) in separate windows.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\backend'; & '$root\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8420"
)
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$root\frontend'; npm run dev"
)
Write-Host "Backend:  http://127.0.0.1:8420  (API docs: /docs)"
Write-Host "Frontend: http://localhost:5173"
