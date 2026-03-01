import os
import time
import pandas as pd
import msal
import requests
from fastapi import FastAPI, Query, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from urllib.parse import quote
from dotenv import load_dotenv
from typing import Optional
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ตั้งค่า Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# โหลดค่าจากไฟล์ .env
load_dotenv()

# ตั้งค่า Rate Limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute", "50/hour", "100/day"])

app = FastAPI(title="Vendor Tracking API")
app.state.limiter = limiter

# Custom Rate Limit Error Handler - Block 30 minutes
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(f"⚠️ Rate limit exceeded for IP: {get_remote_address(request)}")
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "message": "คุณได้ใช้งานเกินโควต้า กรุณารอ 30 นาทีแล้วลองใหม่อีกครั้ง",
            "retry_after": 1800  # 30 minutes in seconds
        },
        headers={"Retry-After": "1800"}
    )

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["Authorization"],
)

# --- Configuration ---
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SHAREPOINT_SITE_NAME = os.getenv("SHAREPOINT_SITE_NAME")
SHAREPOINT_HOST = os.getenv("SHAREPOINT_HOST", "carchula.sharepoint.com")
SHAREPOINT_FOLDER = os.getenv("SHAREPOINT_FOLDER", "Test Vendor")

# --- In-Memory Cache ---
# Vercel reuses warm instances → cache ทำงานได้จริงใน production
# ตั้งค่า TTL ผ่าน env var CACHE_TTL_SECONDS (default 5 นาที)
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))
_cache: dict = {"df": None, "timestamp": 0.0}

# --- API Authentication (Bearer Token) ---
# API_KEY จะต้องถูกตั้งค่าใน Environment Variables เสมอ (ทั้ง Local และ Production)
DEFAULT_API_KEY = os.getenv("API_KEY")
if not DEFAULT_API_KEY:
    raise ValueError("❌ CRITICAL: API_KEY environment variable is not set! Cannot start the application.")

# กำหนดคอลัมน์ที่สนใจ 7 คอลัมน์
TARGET_COLUMNS = [
    "วันที่รายการมีผล", 
    "บัญชีผู้รับเงิน", 
    "ชื่อผู้รับเงิน", 
    "ธนาคาร", 
    "สาขาธนาคารผู้รับเงิน", 
    "จำนวนเงิน", 
    "รายละเอียดของรายการ",
    "สถานะรายการ" 
]

# --- Dependency: Bearer Token Authentication ---
async def verify_api_key(authorization: Optional[str] = Header(None)) -> bool:
    """
    ตรวจสอบ Bearer Token
    ใช้ได้กับ n8n / external systems ที่ต้องตรวจสอบ API Key
    
    ตัวอย่าง Header:
    Authorization: Bearer vendor-tracking-secret-key-12345
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    
    # ตรวจสอบรูป "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization format. Use: Bearer <token>")
    
    token = parts[1]
    if token != DEFAULT_API_KEY:
        logger.warning(f"❌ Invalid API key attempt: {token[:10]}...")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return True

def get_access_token():
    """ขอ Access Token จาก Azure AD"""
    authority = f"https://login.microsoftonline.com/{TENANT_ID}"
    client_app = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=authority, client_credential=CLIENT_SECRET
    )
    result = client_app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return result.get("access_token")

def fetch_all_excel_data():
    """ดึงข้อมูลจากทุกไฟล์ Excel บน SharePoint (มี in-memory cache)"""
    # ถ้า cache ยังไม่หมดอายุ ให้ใช้ข้อมูลเดิมทันที
    if _cache["df"] is not None and (time.time() - _cache["timestamp"]) < CACHE_TTL:
        logger.info(f"⚡ Cache hit — using cached data ({len(_cache['df'])} rows, TTL {CACHE_TTL}s)")
        return _cache["df"], []

    logger.info("🔄 Cache miss — fetching from SharePoint")
    logs = []
    token = get_access_token()
    if not token:
        return pd.DataFrame(), ["❌ ไม่สามารถขอ Access Token จาก Azure ได้"]
    
    headers = {'Authorization': f'Bearer {token}'}
    
    # รับ Site ID
    site_url = f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_HOST}:/sites/{SHAREPOINT_SITE_NAME}"
    site_res = requests.get(site_url, headers=headers).json()
    site_id = site_res.get('id')
    if not site_id:
        return pd.DataFrame(), [f"❌ หา Site ID ไม่เจอ"]

    # รับไฟล์ในโฟลเดอร์
    folder_path = f"{SHAREPOINT_FOLDER}".strip("/")
    encoded_folder = quote(folder_path)
    list_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{encoded_folder}:/children"
    list_res = requests.get(list_url, headers=headers).json()
    
    files = list_res.get('value', [])
    if not files:
        return pd.DataFrame(), ["❌ ไม่พบไฟล์ใดๆ ใน Folder SharePoint นี้"]

    all_dataframes = []

    for file_item in files:
        file_name = file_item.get('name', '')
        
        # อ่านเฉพาะไฟล์ที่ขึ้นต้นด้วย "Payment_Detail_Report"
        if file_name.startswith('Payment_Detail_Report'):
            download_url = file_item.get('@microsoft.graph.downloadUrl')
            
            if download_url:
                try:
                    # ตรวจสอบนามสกุลไฟล์
                    if file_name.endswith('.xlsx'):
                        df = pd.read_excel(download_url, engine='openpyxl', dtype=str)
                        all_dataframes.append(df)
                        logs.append(f"✅ สำเร็จ (Excel .xlsx): {file_name} ({len(df)} แถว)")
                    elif file_name.endswith('.xls'):
                        df = pd.read_excel(download_url, engine='xlrd', dtype=str)
                        all_dataframes.append(df)
                        logs.append(f"✅ สำเร็จ (Excel .xls): {file_name} ({len(df)} แถว)")
                    else:
                        df = pd.read_excel(download_url, dtype=str)
                        all_dataframes.append(df)
                        logs.append(f"✅ สำเร็จ (Excel): {file_name} ({len(df)} แถว)")
                except Exception as e1:
                    try:
                        df = pd.read_csv(download_url, dtype=str, encoding='utf-8-sig')
                        all_dataframes.append(df)
                        logs.append(f"✅ สำเร็จ (CSV UTF-8): {file_name} ({len(df)} แถว)")
                    except Exception as e2:
                        try:
                            df = pd.read_csv(download_url, dtype=str, encoding='cp874')
                            all_dataframes.append(df)
                            logs.append(f"✅ สำเร็จ (CSV ภาษาไทย): {file_name} ({len(df)} แถว)")
                        except Exception as e3:
                            logs.append(f"❌ ล้มเหลว: {file_name}")

    if not all_dataframes:
         return pd.DataFrame(), logs + ["❌ ไม่พบไฟล์ที่สามารถอ่านข้อมูลได้"]
    
    # รวมข้อมูลจากทุกไฟล์
    combined_df = pd.concat(all_dataframes, ignore_index=True)
    combined_df.columns = combined_df.columns.astype(str).str.strip()
    
    # ลบข้อมูลซ้ำ
    before_count = len(combined_df)
    combined_df = combined_df.drop_duplicates()
    after_count = len(combined_df)
    
    if before_count > after_count:
        logs.append(f"ℹ️ ลบข้อมูลซ้ำ: {before_count - after_count} รายการ")

    # บันทึกลง cache
    _cache["df"] = combined_df
    _cache["timestamp"] = time.time()
    logger.info(f"✅ Cache updated — {len(combined_df)} rows, TTL {CACHE_TTL}s")

    return combined_df, logs

def mask_account_number(account: str) -> str:
    """
    Mask เลขบัญชีธนาคาร โดยแสดงเฉพาะ 4 ตัวเลขสุดท้าย
    ตัวอย่าง: "123-4-56789-0" -> "xxx-x-xxxxx-89-0" ... หรือรูปแบบไทย
    รูปแบบจริง: แสดง 4 หลักสุดท้าย, แทนหลักที่เหลือด้วย x
    ตัวอย่าง: "1234567890" -> "xxxxxx7890"
              "123-4-56789-0" -> "xxx-x-xxxxx-9-0"  (4 ตัวเลขสุดท้าย = 9 กับ 0)
    """
    if not account or account == '-':
        return account
    digits = [i for i, c in enumerate(account) if c.isdigit()]
    if len(digits) <= 4:
        return account
    # แทนทุก digit ยกเว้น 4 ตัวสุดท้าย ด้วย 'x'
    mask_positions = set(digits[:-4])
    return ''.join('x' if i in mask_positions else c for i, c in enumerate(account))


# --- API Endpoints ---

@app.get("/")
async def root():
    """API Root - ข้อมูลทั่วไป"""
    return {
        "status": "online",
        "service": "Vendor Payment Tracking API",
        "version": "2.0",
        "endpoints": [
            "/api/health",
            "/api/search",
            "/api/n8n/search"
        ]
    }

@app.get("/api/health")
async def health_check():
    """Health Check Endpoint"""
    return {
        "status": "online",
        "message": "Backend is running",
        "version": "2.0"
    }

@app.get("/api/search")
@limiter.limit("10/minute;50/hour;100/day")
async def search_vendor(
    request: Request,
    q: str = Query(..., description="คำค้นหา Invoice Number")
):
    """
    ค้นหาข้อมูล Invoice - Frontend Endpoint (Public, Rate Limited)
    
    Rate Limit: 10 requests/minute, 50/hour, 100/day per IP
    ถ้าเกินโค้วต้า จะถูก block 30 นาที
    
    ตัวอย่าง: GET /api/search?q=INV001234
    """
    logger.info(f"🔍 Public search request from IP: {get_remote_address(request)} - Invoice: {q}")
    try:
        df_main, _ = fetch_all_excel_data()
        
        if df_main.empty:
            return {"count": 0, "results": [], "message": "ตารางข้อมูลว่างเปล่า"}

        if 'รายละเอียดของรายการ' not in df_main.columns:
            return {"count": 0, "results": [], "message": "ไม่พบคอลัมน์ที่ต้องการ"}

        # สร้าง Invoice_Number column
        df_main['Invoice_Number'] = df_main['รายละเอียดของรายการ'].astype(str).str.strip().str.split().str[0]

        query = q.strip().upper()
        result_df = df_main[df_main['Invoice_Number'].str.upper() == query].copy()

        if result_df.empty:
            return {"count": 0, "results": [], "message": "ไม่พบข้อมูลรายการดังกล่าว"}

        # เลือกเฉพาะคอลัมน์ที่สนใจ
        valid_columns = [col for col in TARGET_COLUMNS if col in result_df.columns]
        final_data = result_df[valid_columns].copy()
        final_data['Invoice_Number'] = result_df['Invoice_Number']

        records = final_data.fillna("-").to_dict(orient='records')

        # Mask เลขบัญชีก่อน return สู่ public endpoint
        for record in records:
            if 'บัญชีผู้รับเงิน' in record:
                record['บัญชีผู้รับเงิน'] = mask_account_number(str(record['บัญชีผู้รับเงิน']))

        return {"count": len(records), "results": records}

    except Exception as e:
        logger.error(f"Error in search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/n8n/search")
@limiter.limit("100/minute;500/hour;1000/day")
async def n8n_search_vendor(
    request: Request,
    q: str = Query(..., description="Invoice Number"),
    _: bool = Depends(verify_api_key)
):
    """
    ค้นหาข้อมูl Invoice สำหรับ n8n/External API - ต้องมี Bearer Token
    
    Rate Limit: 100 requests/minute, 500/hour, 1000/day (สูงกว่า public)
    Authentication: Bearer Token required
    
    ตัวอย่าง:
    GET /api/n8n/search?q=INV001234
    Header: Authorization: Bearer <API_KEY>
    """
    logger.info(f"🔐 Authenticated API request - Invoice: {q}")
    try:
        df_main, logs = fetch_all_excel_data()
        
        if df_main.empty:
            return {
                "success": False,
                "message": "ไม่สามารถดึงข้อมูลจาก SharePoint ได้",
                "data": None
            }
            
        if 'รายละเอียดของรายการ' not in df_main.columns:
             return {
                 "success": False,
                 "message": "ไม่พบคอลัมน์ 'รายละเอียดของรายการ'",
                 "data": None
             }

        # สร้าง Invoice_Number
        df_main['Invoice_Number'] = df_main['รายละเอียดของรายการ'].astype(str).str.strip().str.split().str[0]
        
        query = q.strip().upper()
        result_df = df_main[df_main['Invoice_Number'].str.upper() == query].copy()
        
        if result_df.empty:
            return {
                "success": False,
                "message": f"ไม่พบข้อมูล Invoice: {q}",
                "data": None
            }

        # เลือกคอลัมน์
        valid_columns = [col for col in TARGET_COLUMNS if col in result_df.columns]
        final_data = result_df[valid_columns].copy()
        final_data['Invoice_Number'] = result_df['Invoice_Number']
        
        records = final_data.fillna("-").to_dict(orient='records')
        
        logger.info(f"✅ n8n query for Invoice {q}: Found {len(records)} record(s)")
        
        return {
            "success": True,
            "count": len(records),
            "data": records[0] if len(records) == 1 else records,
            "message": f"สำเร็จ - พบข้อมูล {len(records)} รายการ"
        }

    except HTTPException as e:
        # Re-raise HTTP exceptions (authentication errors)
        raise e
    except Exception as e:
        logger.error(f"Error in n8m search: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Error: {str(e)}",
            "data": None
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
