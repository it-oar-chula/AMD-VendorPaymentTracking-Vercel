# 📊 Vendor Payment Tracking System v2.0

ระบบติดตามสถานะการชำระเงินให้ผู้จำหน่าย สำหรับสำนักงานวิทยทรัพยากร จุฬาลงกรณ์มหาวิทยาลัย

🌐 **Web Interface** | 🔌 **n8n Integration** | ☁️ **Vercel Deployment-Ready**

---

## 📋 สารบัญ

1. [ภาพรวมระบบ](#-ภาพรวมระบบ)
2. [ความรู้พื้นฐาน](#-ความรู้พื้นฐาน)
3. [ติดตั้ง & ตั้งค่า](#-ติดตั้ง--ตั้งค่า)
4. [รันระบบในท้องถิ่น](#-รันระบบในท้องถิ่น)
5. [API Endpoints](#-api-endpoints)
6. [n8n Integration](#-n8n-integration)
7. [Troubleshooting](#-troubleshooting)
8. [Deploy to Production](#-deploy-to-production)

---

## 🎯 ภาพรวมระบบ

### โปรเจคนี้ทำอะไร?
ดึงข้อมูลการชำระเงินจากไฟล์ Excel บน SharePoint และแสดงผลผ่าน:
- **🌐 Web Interface** - ค้นหาผ่านเว็บเบราว์เซอร์ (http://localhost:3000)
- **🔌 n8n API** - ให้ External Systems (n8n, Zapier, etc) เรียก API ด้วย Bearer Token Authentication

### 📦 โครงสร้างโปรเจค

```
.
├── api/
│   └── index.py                    # Backend API (FastAPI) - root, health, public search, n8n search
├── public/                         # Frontend (HTML/CSS/JS)
│   ├── index.html
│   ├── script.js
│   └── style.css
├── .env                            # Configuration
├── requirements.txt                # Python Dependencies
├── start-dev.ps1                   # เปิด Frontend + Backend
├── stop-dev.ps1                    # ปิด Frontend + Backend
├── vercel.json                     # Config สำหรับ Production
└── README.md                       # ไฟล์นี้เอง
```

### ✨ Features

- ✅ ค้นหาข้อมูลแบบบางส่วนจาก ชื่อผู้รับเงิน และ รายละเอียดของรายการ
- ✅ รองรับการค้นหาด้วย Invoice Number ได้ในทางปฏิบัติ หากเลขอยู่ในรายละเอียดของรายการ
- ✅ Web Interface สำหรับ End Users
- ✅ **n8n/External System Integration** ด้วย Bearer Token Authentication
- ✅ รองรับไฟล์ Excel (.xlsx, .xls) + CSV
- ✅ Azure AD Authentication สำหรับ SharePoint
- ✅ In-memory cache + fail-fast เมื่อ SharePoint/Graph API มีปัญหา
- ✅ Ready for Vercel Deployment

---

## 🔍 ความรู้พื้นฐาน

### ❓ ทำไมต้อง 2 Servers?

โปรเจคนี้มี **2 ส่วนแยกกัน**:

| ส่วน | ชื่อ | Port | Purpose |
|------|------|------|---------|
| 🎨 Frontend | `public/` | 3000 | Web Interface สำหรับ End Users |
| 🔙 Backend | `api/index.py` | 8000 | API Server สำหรับ Web + External Systems |

**เพราะ:**
- Frontend ต้องรัน Web Server (ไม่ใช่แค่เปิดไฟล์)
- Backend ต้องเป็น Process แยก เพื่อรับ requests
- 2 Port ต่าง = 2 URL ต่าง

---

## 🚀 ติดตั้ง & ตั้งค่า

### Step 1: สร้าง Virtual Environment (ทำครั้งเดียว)

```powershell
python -m venv .venv
```

### Step 2: ติดตั้ง Dependencies (ทำครั้งเดียว)

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step 3: ตั้งค่าไฟล์ `.env`

ไฟล์ `.env` ในโปรเจคให้มีค่า:

```env
# Azure AD Authentication
TENANT_ID=<ขอจากผู้ดูแล Azure>
CLIENT_ID=<ขอจากผู้ดูแล Azure>
CLIENT_SECRET=<ขอจากผู้ดูแล Azure>

# SharePoint Configuration
SHAREPOINT_SITE_NAME=<ชื่อ SharePoint Site>
SHAREPOINT_HOST=carchula.sharepoint.com
SHAREPOINT_FOLDER=<ชื่อ Folder>

# API Authentication (Bearer Token for n8n)
API_KEY=<Secret Key เดียวกับใน n8n>

# Optional
ALLOWED_ORIGINS=http://localhost:3000
CACHE_TTL_SECONDS=300
```

### 📝 หมายเหตุ:

- ❌ **ห้าม commit `.env` ไปยัง Git** (Security Risk!)
- ✅ ใส่ใน Vercel Dashboard Environment Variables สำหรับ Production

---

## 🏃 รันระบบในท้องถิ่น

### เปิด Servers

```powershell
.\start-dev.ps1
```

Script นี้จะ:
- ✅ Activate Virtual Environment
- ✅ เปิด Backend API Server (Port 8000)
- ✅ เปิด Frontend Server (Port 3000)

### ✅ ตรวจสอบว่ารันสำเร็จ

**Frontend:** http://localhost:3000

**Backend Health Check:**
```powershell
Invoke-WebRequest -Uri http://localhost:8000/api/health -UseBasicParsing | Select-Object -ExpandProperty Content
```

**ผลลัพธ์ที่คาดหวัง:**
```json
{"status":"online","message":"Backend is running","version":"2.0"}
```

### ปิด Servers

```powershell
.\stop-dev.ps1
```

---

## 📡 API Endpoints

### 1. Root

```
GET /
```

**Response:**
```json
{
  "status": "online",
  "service": "Vendor Payment Tracking API",
  "version": "2.0",
  "endpoints": [
    "/api/health",
    "/api/search",
    "/api/n8n/search"
  ]
}
```

---

### 2. Health Check

```
GET /api/health
```

**Response:**
```json
{
  "status": "online",
  "message": "Backend is running",
  "version": "2.0"
}
```

---

### 3. Website Search (ไม่ต้อง Authentication)

```
GET /api/search?q=INV001234
```

**Purpose:** ใช้จาก Frontend Web Interface

**พฤติกรรมจริงของโค้ด:**
- ค้นหาแบบ partial match
- ค้นหาเฉพาะคอลัมน์ `ชื่อผู้รับเงิน` และ `รายละเอียดของรายการ`
- ระบบสร้าง `Invoice_Number` เพิ่มจากคำแรกของ `รายละเอียดของรายการ`
- public response จะ mask เลขบัญชีธนาคารก่อนส่งกลับ

**Response:**
```json
{
  "count": 1,
  "results": [
    {
      "วันที่โอนเงินเข้าบัญชี": "2025-02-01",
      "บัญชีผู้รับเงิน": "xxx-x-xxxxx-9-0",
      "ชื่อผู้รับเงิน": "บจก. ตัวอย่าง",
      "ธนาคาร": "ธนาคารกรุงเทพ",
      "สาขาธนาคารผู้รับเงิน": "สยาม",
      "จำนวนเงิน": "5000",
      "รายละเอียดของรายการ": "INV001234 ....",
      "สถานะรายการ": "จ่ายแล้ว",
      "Invoice_Number": "INV001234"
    }
  ]
}
```

---

### 4. n8n Search (ต้อง Bearer Token)

```
GET /api/n8n/search?q=INV001234
Authorization: Bearer <API_KEY from .env>
```

**Purpose:** ใช้จาก n8n / External Systems

**Response:**
```json
{
  "success": true,
  "count": 1,
  "data": {
    "วันที่โอนเงินเข้าบัญชี": "2025-02-01",
    "ชื่อผู้รับเงิน": "บจก. ตัวอย่าง",
    "ธนาคาร": "ธนาคารกรุงเทพ",
    "บัญชีผู้รับเงิน": "xxx-xxx-6789",
    "สาขาธนาคารผู้รับเงิน": "สยาม",
    "จำนวนเงิน": "5000",
    "รายละเอียดของรายการ": "INV001234 ....",
    "สถานะรายการ": "จ่ายแล้ว",
    "Invoice_Number": "INV001234"
  },
  "message": "สำเร็จ - พบข้อมูล 1 รายการ"
}
```

---

## 🔌 n8n Integration

### วิธีใช้ใน n8n Workflow

#### Step 1: เพิ่ม HTTP Request Node

n8n → Add node → HTTP Request

#### Step 2: ตั้ง Configuration

| Field | Value |
|-------|-------|
| **Method** | GET |
| **URL** | `{{ $env.VENDOR_TRACKING_URL }}/api/n8n/search?q={{ $node["Previous Node"].json.invoice }}` |
| **Authentication** | Header |
| **Header** | `Authorization: Bearer {{ $env.API_KEY }}`<br/>`// ต้องตรงกับค่า API_KEY ใน .env` |

#### Step 3: ตั้ง Environment Variables ใน n8n

```
VENDOR_TRACKING_URL = http://localhost:8000 (Local)
                    = https://vendor-tracking.vercel.app (Production)
API_KEY = <ค่าจาก .env ของคุณ>
```

#### Step 4: Test

ส่ง request จาก n8n Workflow ไป Backend

---

## 🔐 API Authentication (Bearer Token)

### ทำไมต้อง Authentication?

```
❌ ไม่มี Auth:
- ใครๆ ก็เรียก API ได้
- ข้อมูล Payment สามารถเข้าถึงได้หมด
- Risk: Data Breach !

✅ มี Bearer Token:
- เฉพาะ n8n ที่มี API Key ถึงเรียก API ได้
- ความปลอดภัยสูงขึ้น
```

### วิธี Verify API Key

ทุก request ไปยัง `/api/n8n/*` ต้องส่ง Header:

```
Authorization: Bearer <API_KEY>
```

**💡 ที่มา:** ค่า API_KEY มาจากไฟล์ `.env` ตัวอักษรต้องตรงกันเป๊ะ

### Error Response (ถ้า Auth ผิด)

```json
{
  "detail": "Invalid API key"
}
```

---

## 🐛 Troubleshooting

### ❌ "Script ไม่ทำงาน" หรือ "Access Denied"

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\start-dev.ps1
```

---

### ❌ "ModuleNotFoundError: No module named 'pandas'"

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

### ❌ "Connection error to SharePoint"

1. ตรวจสอบ `.env` มี credentials ถูกต้องหรือไม่
2. ตรวจสอบ SharePoint Site มี Folder ตามชื่อที่กำหนด
3. ตรวจสอบ Payment_Detail_Report ไฟล์มีข้อมูลไหม

---

### ❌ "n8n API request returns 401"

```
❌ Problem:
Authorization: Bearer wrong-key

✅ Solution:
Authorization: Bearer <use value from .env>
```

---

## ☁️ Deploy to Production

### Step 1: Push code to GitHub

```powershell
git init
git add .
git commit -m "Vendor Payment Tracking v2.0"
git remote add origin https://github.com/YOUR_USERNAME/vendor-tracking.git
git branch -M main
git push -u origin main
```

### Step 2: Deploy to Vercel

1. ไปที่ https://vercel.com
2. Import Repository
3. Set Environment Variables:

```
TENANT_ID = <Azure>
CLIENT_ID = <Azure>
CLIENT_SECRET = <Azure>
SHAREPOINT_SITE_NAME = <SharePoint>
SHAREPOINT_HOST = carchula.sharepoint.com
SHAREPOINT_FOLDER = <Folder>
API_KEY = <Change this to something secure!>
ALLOWED_ORIGINS = https://your-frontend-domain.example
CACHE_TTL_SECONDS = 300
```

4. Deploy

### Step 3: Update n8n

เปลี่ยน URL ใน n8n:

```
From: http://localhost:8000
To:   https://vendor-tracking.vercel.app
```

### Step 4: Test Production

```
GET https://vendor-tracking.vercel.app/api/n8n/search?q=INV001234
Authorization: Bearer <API_KEY>
```

---

## 📚 ข้อเพิ่มเติม

### ส่วนข้อมูล (Columns) ที่บันทึก

ระบบเลือกส่งออก 8 คอลัมน์ต่อไปนี้ ถ้ามีอยู่ในไฟล์ต้นทาง:

1. **วันที่รายการมีผล** - วันที่อ้างอิงชำระ
2. **บัญชีผู้รับเงิน** - เลขบัญชีธนาคาร
3. **ชื่อผู้รับเงิน** - ชื่อผู้รับ
4. **ธนาคาร** - ชื่อธนาคาร
5. **สาขาธนาคารผู้รับเงิน** - สาขา
6. **จำนวนเงิน** - ยอด Payment
7. **รายละเอียดของรายการ** - Invoice Number + Description
8. **สถานะรายการ** - สถานะปัจจุบัน

### ไฟล์ที่เข้าใจได้

- ✅ Excel (.xlsx, .xls)
- ✅ CSV (UTF-8, ภาษาไทย)

### ชื่อไฟล์ที่อ่าน

ระบบเพียงแต่อ่านไฟล์ที่ขึ้นต้นด้วย `Payment_Detail_Report`

### หมายเหตุจากโค้ดจริง

- Backend ใช้ in-memory cache ตามค่า `CACHE_TTL_SECONDS` โดยค่า default คือ 300 วินาที
- ถ้า Graph API หรือ SharePoint ตอบกลับลักษณะ throttling/service unavailable ระบบจะเข้าสู่โหมด fail-fast ชั่วคราวประมาณ 5 นาที
- Backend จะลองอ่านไฟล์เป็น Excel ก่อน และ fallback เป็น CSV ด้วย encoding `utf-8-sig` และ `cp874`
- Endpoint `/api/search` และ `/api/n8n/search` ใช้ logic ค้นหาเดียวกัน ต่างกันที่ `/api/n8n/search` ต้องมี Bearer token

---

**Version:** 2.0  
**Last Updated:** March 18, 2026  
**Status:** ✅ Production Ready
