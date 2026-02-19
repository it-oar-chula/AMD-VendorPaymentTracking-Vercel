# Script for opening Development Servers
# Usage: PowerShell > .\run-dev.ps1

# Check if virtual environment exists
if (-not (Test-Path ".\.venv")) {
    Write-Host "ERROR: Virtual Environment (.venv) not found" -ForegroundColor Red
    Write-Host "Please create it with: python -m venv .venv" -ForegroundColor Yellow
    exit
}

Write-Host "Starting Development Servers..." -ForegroundColor Green
Write-Host ""

# Activate Virtual Environment
Write-Host "1. Activating Virtual Environment..." -ForegroundColor Cyan
& ".\.venv\Scripts\Activate.ps1"

# Open first Terminal for API Server (Backend)
Write-Host "2. Starting API Server (Port 8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python api/index.py"

# Wait a moment for API server to start
Start-Sleep -Seconds 2

# Open second Terminal for Frontend Server
Write-Host "3. Starting Frontend Server (Port 3000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD\public'; python -m http.server 3000"

Write-Host ""
Write-Host "READY: Both servers are running!" -ForegroundColor Green
Write-Host ""
Write-Host "Open in browser: http://localhost:3000" -ForegroundColor Yellow
Write-Host "API Server: http://localhost:8000" -ForegroundColor Yellow
Write-Host ""
Write-Host "To close servers: Use .\close-dev.ps1 or close both terminal windows" -ForegroundColor Yellow
