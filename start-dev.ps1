# Script to start development servers
# Usage: PowerShell > .\start-dev.ps1

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host " Vendor Payment Tracking - Start Development" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""

# Check if virtual environment exists
if (-not (Test-Path ".\.venv")) {
    Write-Host "ERROR: Virtual Environment (.venv) not found" -ForegroundColor Red
    Write-Host "Please create it with: python -m venv .venv" -ForegroundColor Yellow
    exit
}

# Activate Virtual Environment
Write-Host "1) Activating virtual environment..." -ForegroundColor Cyan
& ".\.venv\Scripts\Activate.ps1"
Start-Sleep -Seconds 1

# Start Backend API Server
Write-Host "2) Starting Backend API Server (Port 8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$PWD'; .\.venv\Scripts\Activate.ps1; python api/index.py"
Start-Sleep -Seconds 3

# Verify Backend is running
Write-Host "3) Verifying Backend..." -ForegroundColor Cyan
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 3
    $json = $response.Content | ConvertFrom-Json
    Write-Host "   Status: $($json.status)" -ForegroundColor Green
    Write-Host "   Version: $($json.version)" -ForegroundColor Green
} catch {
    Write-Host "   Backend may still be starting (this is OK)..." -ForegroundColor Yellow
}

Write-Host ""

# Start Frontend Server
Write-Host "4) Starting Frontend Server (Port 3000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$PWD'; cd public; python -m http.server 3000"
Start-Sleep -Seconds 2

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host " All Services Started" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""

Write-Host "URLs:" -ForegroundColor Cyan
Write-Host "  Frontend: http://localhost:3000" -ForegroundColor White
Write-Host "  Backend: http://localhost:8000" -ForegroundColor White
Write-Host ""

Write-Host "API Endpoints:" -ForegroundColor Cyan
Write-Host "  Web Search: GET /api/search?q=INV001234" -ForegroundColor White
Write-Host "  n8n Search: GET /api/n8n/search?q=INV001234" -ForegroundColor White
Write-Host "  (n8m requires: Authorization: Bearer vendor-tracking-secret-key-12345)" -ForegroundColor Gray
Write-Host ""

Write-Host "To stop all servers: .\stop-dev.ps1" -ForegroundColor Magenta
Write-Host "================================================" -ForegroundColor Green
Write-Host ""

Read-Host "Press Enter to close this window"
