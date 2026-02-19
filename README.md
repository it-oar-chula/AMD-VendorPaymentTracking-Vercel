# 📊 Vendor Payment Tracking System

ระบบติดตามสถานะการชำระเงินให้ผู้จำหน่าย สำหรับสำนักงานวิทยทรัพยากร จุฬาลงกรณ์มหาวิทยาลัย

---

## 🎯 ความเป็นมา

โปรเจคนี้ใช้ดึงข้อมูลการชำระเงินจากไฟล์ Excel บน SharePoint แล้วแสดงผลผ่าน Web Interface ให้ผู้ใช้ค้นหาสถานะการจ่ายเงินได้อย่างสะดวก

### 📦 โครงสร้างโปรเจค
```
.
├── api/
│   └── index.py           # Backend API (FastAPI)
├── public/
│   ├── index.html         # หน้าเว็บหลัก
│   ├── script.js          # JavaScript สำหรับการค้นหา
│   └── style.css          # CSS สไตล์เว็บ
├── .env                   # ไฟล์ Config (ต้องตั้งค่าเอง)
├── requirements.txt       # ไลบรารี่ที่ต้องใช้
├── run-dev.ps1            # Script เปิด development servers
├── vercel.json            # Config สำหรับ Vercel deployment
└── README.md              # ไฟล์นี้เอง
```

---

## � ความรู้พื้นฐาน: ทำไมต้อง Servers 2 ตัว?

### โปรเจคนี้มี 2 ส่วนที่ต่างกัน ลองเข้าใจก่อนรัน!

#### 🔙 **Backend API Server** (api/index.py - Port 8000)
- เป็น **FastAPI** ที่ดึงข้อมูลจาก SharePoint
- รับ request จาก Frontend แล้วส่งข้อมูลกลับเป็น JSON
- เปลี่ยนข้อมูล Excel เป็นตัวเลขที่จะแสดง

#### 🎨 **Frontend Server** (public/ - Port 3000)
- เป็นหน้าเว็บ HTML + CSS + JavaScript
- ต้อง run ผ่าน Web Server (แม้จะเป็น Static File)
- ส่ง request ไปยัง Backend API เพื่อขอข้อมูล

---

### ❓ ทำไมไม่เหมือน `python app.py` แบบเดิม?

**ตอบ: ขึ้นอยู่กับประเภทของแอป!**

| ประเภท | ตัวอย่าง | วิธีรัน | เหตุผล |
|--------|---------|--------|--------|
| **Simple Script** | `app.py` สั่งแสดงค่า | `python app.py` | ไม่ต้อง web server |
| **Bot/Automation** | Discord Bot | `python bot.py` | ไม่ต้อง web server |
| **Web API เพียงอย่าง** | FastAPI เล็กๆ | `python app.py` | FastAPI มี built-in server |
| **Web App สมบูรณ์** | **โปรเจคนี้** ⭐ | **ต้องเปิด 2 servers** | Frontend + Backend แยกกัน |

---

### ✅ นี่เป็นมาตรฐานหรือไม่?

**ใช่ครับ 100%** นี่คือวิธีปกติของการพัฒนา Web App:

✅ **Frontend** (HTML/CSS/JS) รันบน web server (ไม่ใช่แค่เปิด file)  
✅ **Backend** (FastAPI/Node.js) รันบน process แยก  
✅ **2 servers ต่าง port** คือสิ่ง Universal มากในการพัฒนา  

**ในสภาพจริง (Production):**
- Frontend deploy ไปที่ **Vercel / Netlify**
- Backend deploy ไปที่ **Heroku / AWS / Azure**
- 2 ตัวรับ requests ผ่าน Domain ที่ต่างกัน

---

## �🚀 วิธีเริ่มต้นการใช้งาน

### ขั้นตอนแรก: สร้าง Virtual Environment (ทำครั้งเดียว)

**ใน PowerShell (วิน + X แล้วเลือก Terminal):**

```powershell
python -m venv .venv
```

### ขั้นตอนที่สอง: ติดตั้ง Dependencies (ทำครั้งเดียว)

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### ขั้นตอนที่สาม: ตั้งค่าไฟล์ .env (สำคัญ!)

เปิดไฟล์ `.env` และใส่ค่าต่อไปนี้ (ขอจากผู้ดูแล SharePoint):

```
TENANT_ID=<Azure AD Tenant ID>
CLIENT_ID=<Azure Application ID>
CLIENT_SECRET=<Azure Application Secret>
SHAREPOINT_SITE_NAME=<ชื่อ SharePoint Site>
SHAREPOINT_HOST=<Host domain เช่น carchula.sharepoint.com>
SHAREPOINT_FOLDER=<Folder ที่เก็บ Excel>
FILE_NAME=<ชื่อไฟล์ Excel>
```

**หากไม่ทราบค่าเหล่านี้ ติดต่อผู้ดูแล Azure AD / SharePoint**

---

## 📱 วิธีรันโปรเจค

### วิธีที่ 1: ใช้ Script (ง่ายที่สุด) ⭐ **แนะนำ**

**ใน PowerShell ที่ folder โปรเจค:**

```powershell
.\run-dev.ps1
```

Script นี้จะ:
1. ✅ Activate Virtual Environment
2. ✅ เปิด API Server (Backend) บน Port 8000
3. ✅ เปิด Frontend Server บน Port 3000

จากนั้น **เปิด Browser** ไปที่:
```
http://localhost:3000
```

---

### วิธีที่ 2: เปิด Manual (ถ้า Script ไม่ทำงาน)

**Terminal 1 - เปิด API Server:**
```powershell
.\.venv\Scripts\activate
python api/index.py
```

**Terminal 2 - เปิด Frontend Server:**
```powershell
.\.venv\Scripts\activate
cd public
python -m http.server 3000
```

**Browser:**
```
http://localhost:3000
```

---

## ⏹️ วิธีปิด Servers

### วิธีที่ 1: ใช้ Script (ง่ายที่สุด) ⭐ **แนะนำ**

```powershell
.\close-dev.ps1
```

Script นี้จะปิด servers ทั้ง API และ Frontend โดยอัตโนมัติ

---

### วิธีที่ 2: ปิด Terminal ที่รัน Server (ถ้า Script ไม่ทำงาน)
ปิด 2 Terminal หน้าต่างที่รัน Servers ไปแล้ว

### วิธีที่ 3: ใช้ Ctrl+C (ถ้าต้องการให้ terminal ยังเปิดอยู่)

ในแต่ละ Terminal:
```powershell
Ctrl+C
```

กด **Y** เมื่อถามว่า "Terminate batch job"

---

## 🔄 รอบหน้าจะรันอย่างไร

ทุกครั้งที่ต้องการรัน:

1. เปิด **PowerShell** ที่ folder โปรเจค
2. พิมพ์:
   ```powershell
   .\run-dev.ps1
   ```
3. เปิด Browser ไปที่ `http://localhost:3000`
4. ทีเสร็จใช้งาน ปิด Terminal 2 ช่องที่เปิดขึ้นมา

**ตั้งแต่โปรเจคนี้ขึ้นไป คุณต้องทำให้ Servers ทำงานทุกครั้ง** ❌ ปิด VS Code ไม่ได้หมายถึงปิด Servers

---

## 🐛 แก้ไขปัญหา

### ❌ "Script ไม่ทำงาน" หรือ "Access Denied"

ในขั้นอื่นๆ ต้องมีสิทธิ์รัน PowerShell Script:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

แล้วลองรัน `.\run-dev.ps1` อีกครั้ง

### ❌ "ModuleNotFoundError: No module named 'pandas'"

ลืม `pip install -r requirements.txt` ให้รัน:

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### ❌ "Port 3000 ถูกใช้งานอยู่"

โปรแกรมอื่นกำลังใช้ port 3000 ปิดโปรแกรมนั้นได้ หรือแก้ไขคำสั่งเป็น:

```powershell
cd public
python -m http.server 3001
```

แล้วไปที่ `http://localhost:3001`

---

## � Deploy ไปยัง Vercel (ระบบ Production)

โปรเจคนี้ **ออกแบบมาให้ Deploy บน Vercel** แล้ว นี่คือวิธีการ:

### **ที่ต้องเตรียม:**
- ✅ GitHub Account (ฟรี)
- ✅ Vercel Account (ฟรี)

### **ขั้นตอนที่ 1: สร้าง GitHub Repository**

1. ไปที่ https://github.com/new
2. ตั้งชื่อ Repository: `vendor-payment-tracking`
3. เลือก **Public** (free plan)
4. คลิก **Create repository**

---

### **ขั้นตอนที่ 2: Push โค้ดขึ้น GitHub**

**ใน PowerShell ที่ folder โปรเจค:**

```powershell
# สั่งครั้งแรกเท่านั้น
git init
git add .
git commit -m "Initial commit: Vendor Payment Tracking"
git remote add origin https://github.com/YOUR_USERNAME/vendor-payment-tracking.git
git branch -M main
git push -u origin main
```

✅ ตรวจสอบ: ไปที่ GitHub จะเห็น code

---

### **ขั้นตอนที่ 3: สร้าง Vercel Account และ Deploy**

1. ไปที่ https://vercel.com
2. คลิก **Sign Up** → **Continue with GitHub**
3. Authorize Vercel
4. ไปที่ Dashboard → **Add New** → **Project**
5. เลือก Repository: **vendor-payment-tracking**
6. คลิก **Import**

---

### **ขั้นตอนที่ 4: ตั้งค่า Environment Variables (สำคัญ!)**

Vercel จะแสดงหน้ากำหนด Environment Variables:

```
TENANT_ID = <ขอจากผู้ดูแล Azure>
CLIENT_ID = <ขอจากผู้ดูแล Azure>
CLIENT_SECRET = <ขอจากผู้ดูแล Azure>
SHAREPOINT_SITE_NAME = <ชื่อ SharePoint>
SHAREPOINT_HOST = carchula.sharepoint.com
SHAREPOINT_FOLDER = Test Vendor
FILE_NAME = Payment_Detail_Report.xlsx
```

✅ **สำคัญ**: ห้ามเพิ่ม `.env` ไว้ใน GitHub (security risk) → ใส่ใน Vercel Dashboard แทน

---

### **ขั้นตอนที่ 5: Deploy**

1. คลิก **Deploy**
2. รอ 2-3 นาที
3. จะได้ URL แบบนี้: `https://vendor-payment-tracking-xxxxx.vercel.app`

---

### **ขั้นตอนที่ 6: ทดสอบ**

1. เข้าไป URL ที่ได้
2. ทดสอบค้นหาข้อมูล
3. ควรใช้งานได้เลย!

---

### **ทีหลังจะ Update Code?**

```powershell
git add .
git commit -m "Update: description"
git push origin main
```

**Vercel จะ Auto Deploy ให้เอง** ไม่ต้องทำอะไรเพิ่ม ✅

---

### **📍 ที่อยู่ของ Frontend และ Backend:**

| ส่วน | URL |
|------|-----|
| Frontend | `https://vendor-payment-tracking.vercel.app` |
| Backend API | `https://vendor-payment-tracking.vercel.app/api` |

---

### **ข้อจำกัด Free Tier:**

✅ **ฟรี:**
- Deployment ไม่จำกัด
- 160,000 requests/เดือน
- Domain vercel.app
- HTTPS ฟรี

❌ **อาจมีปัญหา:**
- ขาดทั่ว (cold start) ~1 วินาที ครั้งแรก
- Database บน SharePoint เน้ือที่ขึ้นอยู่กับ Microsoft ไม่ใช่ Vercel

---

## �📚 เทคโนโลยีที่ใช้

- **Backend:** FastAPI + Python
- **Frontend:** HTML + CSS + JavaScript
- **Database:** Excel บน SharePoint
- **Authentication:** Azure AD / MSAL

---

## 👤 ติดต่อผู้ดูแล

สำหรับปัญหาเกี่ยวกับการตั้งค่า Azure, SharePoint หรือ Credentials ติดต่อ:
- สำนักงานวิทยทรัพยากร จุฬาลงกรณ์มหาวิทยาลัย

---

**Version:** 1.0  
**Last Updated:** 19 February 2026
