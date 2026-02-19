# Script สำหรับปิด Development Servers โปรเจค Vendor Payment Tracking
# วิธีใช้: PowerShell > .\close-dev.ps1

Write-Host "Stopping Development Servers..." -ForegroundColor Yellow
Write-Host ""

# ปิด port 3000 (Frontend Server)
Write-Host "Closing Frontend Server (Port 3000)..." -ForegroundColor Cyan
$processes3000 = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
if ($processes3000) {
    foreach ($proc in $processes3000) {
        $process = Get-Process -Id $proc.OwningProcess -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $proc.OwningProcess -Force -ErrorAction SilentlyContinue
            Write-Host "OK - Frontend Server closed (PID: $($proc.OwningProcess))" -ForegroundColor Green
        }
    }
}
else {
    Write-Host "No process found on Port 3000" -ForegroundColor Yellow
}

Write-Host ""

# ปิด port 8000 (API Server)
Write-Host "Closing API Server (Port 8000)..." -ForegroundColor Cyan
$processes8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($processes8000) {
    foreach ($proc in $processes8000) {
        $process = Get-Process -Id $proc.OwningProcess -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $proc.OwningProcess -Force -ErrorAction SilentlyContinue
            Write-Host "OK - API Server closed (PID: $($proc.OwningProcess))" -ForegroundColor Green
        }
    }
}
else {
    Write-Host "No process found on Port 8000" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "All servers stopped!" -ForegroundColor Green
Write-Host ""
