# Script to stop all development servers
# Usage: PowerShell > .\stop-dev.ps1

Write-Host ""
Write-Host "================================================" -ForegroundColor Yellow
Write-Host " Vendor Payment Tracking - Stop Development" -ForegroundColor Yellow
Write-Host "================================================" -ForegroundColor Yellow
Write-Host ""

$stoppedCount = 0

# Stop Frontend Server (Port 3000)
Write-Host "1) Stopping Frontend Server (Port 3000)..." -ForegroundColor Cyan
$processes3000 = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
if ($processes3000) {
    foreach ($proc in $processes3000) {
        $process = Get-Process -Id $proc.OwningProcess -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $proc.OwningProcess -Force -ErrorAction SilentlyContinue
            Write-Host "   OK - Frontend Server stopped (PID: $($proc.OwningProcess))" -ForegroundColor Green
            $stoppedCount++
        }
    }
} else {
    Write-Host "   No process found on Port 3000" -ForegroundColor Yellow
}

Write-Host ""

# Stop Backend API Server (Port 8000)
Write-Host "2) Stopping Backend API Server (Port 8000)..." -ForegroundColor Cyan
$processes8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($processes8000) {
    foreach ($proc in $processes8000) {
        $process = Get-Process -Id $proc.OwningProcess -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $proc.OwningProcess -Force -ErrorAction SilentlyContinue
            Write-Host "   OK - Backend API Server stopped (PID: $($proc.OwningProcess))" -ForegroundColor Green
            $stoppedCount++
        }
    }
} else {
    Write-Host "   No process found on Port 8000" -ForegroundColor Yellow
}

Write-Host ""

if ($stoppedCount -eq 0) {
    Write-Host "No services were running" -ForegroundColor Yellow
} else {
    Write-Host "$stoppedCount service(s) stopped successfully!" -ForegroundColor Green
}

Write-Host ""
Write-Host "To start again: .\start-dev.ps1" -ForegroundColor Magenta
Write-Host "================================================" -ForegroundColor Yellow
Write-Host ""

Read-Host "Press Enter to close this window"
