# ========================================
# Test Script สำหรับ Production API
# https://vendor-payment-tracking.vercel.app/api/n8n/search
# ========================================

# โหลด API_KEY จากไฟล์ .env
$envFile = ".\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "❌ ไม่พบไฟล์ .env ในโฟลเดอร์ปัจจุบัน" -ForegroundColor Red
    exit 1
}

# อ่านค่า API_KEY จาก .env
$apiKey = $null
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^API_KEY\s*=\s*(.+)$') {
        $apiKey = $matches[1].Trim('"').Trim("'")
    }
}

if (-not $apiKey) {
    Write-Host "❌ ไม่พบ API_KEY ในไฟล์ .env" -ForegroundColor Red
    exit 1
}

Write-Host "✅ โหลด API_KEY สำเร็จ" -ForegroundColor Green
Write-Host ""

# ขอให้ผู้ใช้กรอก Invoice Number
$invoiceNumber = Read-Host "📝 กรุณากรอกเลข Invoice ที่ต้องการค้นหา"

if ([string]::IsNullOrWhitespace($invoiceNumber)) {
    Write-Host "❌ ไม่ได้กรอก Invoice Number" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "🔍 กำลังค้นหา Invoice: $invoiceNumber" -ForegroundColor Cyan
Write-Host ""

# ส่ง Request ไปยัง Production API
$apiUrl = "https://vendor-payment-tracking.vercel.app/api/n8n/search"
$headers = @{
    "Authorization" = "Bearer $apiKey"
    "Content-Type"  = "application/json"
}

try {
    $response = Invoke-WebRequest -Uri "$apiUrl?q=$invoiceNumber" `
                                  -Headers $headers `
                                  -UseBasicParsing
    
    $result = $response.Content | ConvertFrom-Json
    
    Write-Host "✅ ได้รับตอบกลับจาก API สำเร็จ" -ForegroundColor Green
    Write-Host ""
    
    if ($result.success) {
        Write-Host "📊 ผลลัพธ์:" -ForegroundColor Green
        Write-Host "===============================================" -ForegroundColor Green
        Write-Host "ค้นหาสำเร็จ - Found: $($result.count) record(s)" -ForegroundColor Green
        Write-Host "===============================================" -ForegroundColor Green
        Write-Host ""
        
        # แสดงข้อมูล
        if ($result.data -is [System.Collections.IEnumerable] -and $result.data -isnot [string]) {
            # ข้อมูลหลายแถว
            $result.data | Format-Table -AutoSize
        } else {
            # ข้อมูลชิ้นเดียว
            $result.data | Format-List
        }
        
        Write-Host ""
        Write-Host "📌 ข้อความ: $($result.message)" -ForegroundColor Yellow
    } else {
        Write-Host "❌ ค้นหาไม่พบข้อมูล" -ForegroundColor Yellow
        Write-Host "ข้อความ: $($result.message)" -ForegroundColor Yellow
    }
    
} catch {
    $statusCode = $_.Exception.Response.StatusCode
    
    Write-Host "❌ เกิดข้อผิดพลาด" -ForegroundColor Red
    
    if ($statusCode -eq 401) {
        Write-Host "Status Code: 401 - Unauthorized" -ForegroundColor Red
        Write-Host "ตรวจสอบ API_KEY ใน .env ว่าถูกต้องหรือไม่" -ForegroundColor Yellow
    } elseif ($statusCode -eq 400) {
        Write-Host "Status Code: 400 - Bad Request" -ForegroundColor Red
        Write-Host "ตรวจสอบรูปแบบ Invoice Number" -ForegroundColor Yellow
    } elseif ($statusCode -eq 500) {
        Write-Host "Status Code: 500 - Server Error" -ForegroundColor Red
        Write-Host "เซิร์ฟเวอร์มีข้อผิดพลาด กรุณาลองใหม่" -ForegroundColor Yellow
    } else {
        Write-Host "Status Code: $statusCode" -ForegroundColor Red
        Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "================================" -ForegroundColor Gray
Write-Host "📋 API Information:" -ForegroundColor Gray
Write-Host "  URL: $apiUrl" -ForegroundColor Gray
Write-Host "  Method: GET" -ForegroundColor Gray
Write-Host "  Query: ?q=<INVOICE_NUMBER>" -ForegroundColor Gray
Write-Host "  Auth: Bearer Token (from .env)" -ForegroundColor Gray
Write-Host "================================" -ForegroundColor Gray
