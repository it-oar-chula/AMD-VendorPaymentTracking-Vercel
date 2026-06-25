import os
import time
import io
import secrets
import pandas as pd
import msal
import httpx
from fastapi import FastAPI, Query, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import quote
from dotenv import load_dotenv
from typing import Optional
import logging
from fastapi.concurrency import run_in_threadpool

# ตั้งค่า Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# โหลดค่าจากไฟล์ .env
load_dotenv()

class SharePointConfigError(Exception):
    """ข้อผิดพลาดจาก configuration (โฟลเดอร์ว่าง, ไม่พบไฟล์) — ไม่ใช่ SharePoint ล่ม"""
    pass

app = FastAPI(title="Vendor Tracking API")

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

# --- SharePoint Status Tracking (Fail Fast Strategy) ---
# ถ้า SharePoint โดนบล็อค → API จะ return 503 ทันที แทนที่จะรอ timeout
SHAREPOINT_DOWN = False
SHAREPOINT_DOWN_TIME = 0.0

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

# ระบบค้นหาเดิม: partial match จากชื่อผู้รับเงิน + รายละเอียดของรายการ
# ปิดไว้ก่อน แต่ไม่ลบทิ้ง: ตั้ง SEARCH_MODE=partial เมื่อต้องการกลับไปใช้
SEARCH_MODE = os.getenv("SEARCH_MODE", "strict").strip().lower()
LEGACY_PARTIAL_SEARCH_COLUMNS = [
    "ชื่อผู้รับเงิน",
    "รายละเอียดของรายการ",
]
STRICT_COMPANY_COLUMN = "ชื่อผู้รับเงิน"

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
    # ใช้ secrets.compare_digest เพื่อป้องกัน Timing Attack
    if not secrets.compare_digest(token, DEFAULT_API_KEY):
        logger.warning("❌ Invalid API key attempt detected")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return True

# MSAL Client Singleton — เก็บไว้ระดับ module เพื่อให้ MSAL token cache ทำงานได้
# บน Vercel warm instance: module-level variable จะถูก reuse → MSAL cache token ~1 ชั่วโมง
# แทนที่จะ round-trip Azure AD ทุก cache miss (ทุก 5 นาที)
_msal_app: Optional[msal.ConfidentialClientApplication] = None

def _get_msal_app() -> msal.ConfidentialClientApplication:
    global _msal_app
    if _msal_app is None:
        authority = f"https://login.microsoftonline.com/{TENANT_ID}"
        _msal_app = msal.ConfidentialClientApplication(
            CLIENT_ID, authority=authority, client_credential=CLIENT_SECRET
        )
    return _msal_app

async def get_access_token():
    """ขอ Access Token จาก Azure AD (ใช้ MSAL internal token cache)"""
    result = await run_in_threadpool(
        _get_msal_app().acquire_token_for_client,
        scopes=["https://graph.microsoft.com/.default"]
    )
    return result.get("access_token")

async def fetch_all_excel_data():
    """ดึงข้อมูลจากทุกไฟล์ Excel บน SharePoint (มี in-memory cache + Fail Fast)"""
    global SHAREPOINT_DOWN, SHAREPOINT_DOWN_TIME
    
    # ❌ ถ้า SharePoint ล่ม → return error ทันที (ไม่เรียก SharePoint)
    if SHAREPOINT_DOWN and (time.time() - SHAREPOINT_DOWN_TIME) < 300:  # 5 นาที
        age = int(time.time() - SHAREPOINT_DOWN_TIME)
        logger.warning(f"⚠️ SharePoint still down (down for {age}s) - failing fast")
        raise Exception(f"SharePoint temporarily unavailable (down for {age}s)")
    
    # ✅ Reset status ถ้า recovery time ผ่านไป
    if SHAREPOINT_DOWN and (time.time() - SHAREPOINT_DOWN_TIME) >= 300:
        logger.info("ℹ️ Attempting to recover connection to SharePoint")
        SHAREPOINT_DOWN = False
    
    # ถ้า cache ยังไม่หมดอายุ ให้ใช้ข้อมูลเดิมทันที
    if _cache["df"] is not None and (time.time() - _cache["timestamp"]) < CACHE_TTL:
        logger.info(f"⚡ Cache hit — using cached data ({len(_cache['df'])} rows, TTL {CACHE_TTL}s)")
        SHAREPOINT_DOWN = False  # Reset status on cache hit
        return _cache["df"], []

    logger.info("🔄 Cache miss — fetching from SharePoint")
    logs = []
    token = await get_access_token()
    if not token:
        logger.error("❌ Failed to get access token")
        SHAREPOINT_DOWN = True
        SHAREPOINT_DOWN_TIME = time.time()
        raise Exception("Failed to get Azure AD access token")
    
    headers = {'Authorization': f'Bearer {token}'}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # รับ Site ID
            site_url = f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_HOST}:/sites/{SHAREPOINT_SITE_NAME}"
            site_res = (await client.get(site_url, headers=headers)).json()
            
            # ❌ ตรวจสอบ error response (429 Too Many Requests, 503 Service Unavailable)
            if 'error' in site_res:
                error_code = site_res['error'].get('code', 'UNKNOWN')
                error_msg = site_res['error'].get('message', '')
                logger.error(f"🔴 SharePoint API error: {error_code} - {error_msg}")
                
                if error_code in ['throttlingException', 'serviceNotAvailable', 'generalException']:
                    SHAREPOINT_DOWN = True
                    SHAREPOINT_DOWN_TIME = time.time()
                    raise Exception(f"SharePoint {error_code}: {error_msg}")
            
            site_id = site_res.get('id')
            if not site_id:
                logger.error("❌ Cannot find SharePoint Site ID")
                SHAREPOINT_DOWN = True
                SHAREPOINT_DOWN_TIME = time.time()
                raise Exception("Cannot find SharePoint Site ID")

            # รับไฟล์ในโฟลเดอร์
            folder_path = f"{SHAREPOINT_FOLDER}".strip("/")
            encoded_folder = quote(folder_path)
            list_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{encoded_folder}:/children"
            list_res = (await client.get(list_url, headers=headers)).json()
            
            # ❌ ตรวจสอบ error response
            if 'error' in list_res:
                error_code = list_res['error'].get('code', 'UNKNOWN')
                error_msg = list_res['error'].get('message', '')
                logger.error(f"🔴 SharePoint API error: {error_code} - {error_msg}")
                
                if error_code in ['throttlingException', 'serviceNotAvailable', 'generalException']:
                    SHAREPOINT_DOWN = True
                    SHAREPOINT_DOWN_TIME = time.time()
                    raise Exception(f"SharePoint {error_code}: {error_msg}")
            
            files = list_res.get('value', [])
            if not files:
                logs.append("❌ ไม่พบไฟล์ใดๆ ใน Folder SharePoint นี้")
                raise SharePointConfigError("No files found in SharePoint folder")

            all_dataframes = []

            for file_item in files:
                file_name = file_item.get('name', '')

                # อ่านเฉพาะไฟล์ที่ขึ้นต้นด้วย "Payment_Detail_Report"
                if not file_name.startswith('Payment_Detail_Report'):
                    continue

                download_url = file_item.get('@microsoft.graph.downloadUrl')
                if not download_url:
                    continue

                # Step 1: Download (async network I/O — แยกออกมาเพื่อป้องกัน NameError)
                try:
                    response = await client.get(download_url)
                    response.raise_for_status()
                    file_content = io.BytesIO(response.content)
                except httpx.HTTPStatusError as e:
                    # 🛑 ถ้าโดนแบน (429) หรือระบบล่ม (503) ให้หยุดทันที เพื่อเข้าสู่โหมด Fail Fast
                    if e.response.status_code in [429, 503]:
                        raise e
                    # Error อื่นๆ (เช่น 404) ให้ข้ามไฟล์นี้ไป
                    logs.append(f"❌ ล้มเหลว (HTTP {e.response.status_code}): {file_name}")
                    continue
                except Exception:
                    logs.append(f"❌ ล้มเหลว (download): {file_name}")
                    continue

                # Step 2: Parse (blocking CPU/I/O → threadpool)
                try:
                    if file_name.endswith('.xlsx'):
                        df = await run_in_threadpool(pd.read_excel, file_content, engine='openpyxl', dtype=str)
                    elif file_name.endswith('.xls'):
                        df = await run_in_threadpool(pd.read_excel, file_content, engine='xlrd', dtype=str)
                    else:
                        df = await run_in_threadpool(pd.read_excel, file_content, dtype=str)
                    all_dataframes.append(df)
                    logs.append(f"✅ สำเร็จ: {file_name} ({len(df)} แถว)")
                except Exception:
                    # Excel ล้มเหลว → ลอง CSV encodings (utf-8-sig, cp874)
                    for encoding in ('utf-8-sig', 'cp874'):
                        try:
                            file_content.seek(0)
                            df = await run_in_threadpool(pd.read_csv, file_content, dtype=str, encoding=encoding)
                            all_dataframes.append(df)
                            logs.append(f"✅ สำเร็จ (CSV {encoding}): {file_name} ({len(df)} แถว)")
                            break
                        except Exception:
                            continue
                    else:
                        logs.append(f"❌ ล้มเหลว: {file_name}")

            if not all_dataframes:
                logs.append("❌ ไม่พบไฟล์ที่สามารถอ่านข้อมูลได้")
                raise SharePointConfigError("No matching files could be parsed")

            # รวมข้อมูลจากทุกไฟล์ (blocking → threadpool)
            combined_df = await run_in_threadpool(pd.concat, all_dataframes, ignore_index=True)
            combined_df.columns = combined_df.columns.astype(str).str.strip()

            # --- Data Transformation (ย้ายมาทำตรงนี้ครั้งเดียว) ---
            if 'รายละเอียดของรายการ' in combined_df.columns:
                # สร้าง Invoice_Number
                combined_df['Invoice_Number'] = combined_df['รายละเอียดของรายการ'].astype(str).str.strip().str.split().str[0]
                # สร้างตัวช่วยค้นหา (Upper Case)
                combined_df['Invoice_Number_Upper'] = combined_df['Invoice_Number'].str.upper()
            
            # ลบข้อมูลซ้ำ (blocking → threadpool)
            before_count = len(combined_df)
            combined_df = await run_in_threadpool(combined_df.drop_duplicates)
            after_count = len(combined_df)
            
            if before_count > after_count:
                logs.append(f"ℹ️ ลบข้อมูลซ้ำ: {before_count - after_count} รายการ")

            # ✅ สำเร็จ → บันทึกลง cache + reset status
            _cache["df"] = combined_df
            _cache["timestamp"] = time.time()
            SHAREPOINT_DOWN = False  # ✅ Reset status on success
            logger.info(f"✅ Cache updated — {len(combined_df)} rows, TTL {CACHE_TTL}s")

            return combined_df, logs
    
    except SharePointConfigError:
        raise  # Config errors ไม่ใช่ SharePoint ล่ม — ไม่ตั้ง SHAREPOINT_DOWN
    except Exception as e:
        logger.error(f"❌ SharePoint error: {e}", exc_info=True)
        SHAREPOINT_DOWN = True
        SHAREPOINT_DOWN_TIME = time.time()
        raise

def mask_account_number(account: str) -> str:
    """
    Mask เลขบัญชีธนาคาร โดยแสดงเฉพาะ 4 ตัวเลขสุดท้าย
    ตัวอย่าง: "123-4-56789-0" -> "xxx-x-xxxxx-89-0" ... หรือรูปแบบไทย
    รูปแบบจริง: แสดง 4 หลักสุดท้าย, แทนหลักที่เหลือด้วย x
    ตัวอย่าง: "1234567890" -> "xxxxxx7890"
              "123-4-56789-0" -> "xxx-x-xxxxx-9-0"  (4 ตัวเลขสุดท้าย = 9 กับ 0)
    """
    acc_str = str(account)
    if not acc_str or acc_str == '-':
        return acc_str
    digits = [i for i, c in enumerate(acc_str) if c.isdigit()]
    if len(digits) <= 4:
        return acc_str
    # แทนทุก digit ยกเว้น 4 ตัวสุดท้าย ด้วย 'x'
    mask_positions = set(digits[:-4])
    return ''.join('x' if i in mask_positions else c for i, c in enumerate(acc_str))


def legacy_partial_search(df_main: pd.DataFrame, query: str) -> Optional[pd.DataFrame]:
    """ระบบค้นหาเดิม: ใส่อะไรก็ค้นหาแบบ partial match ได้"""
    search_cols = [c for c in LEGACY_PARTIAL_SEARCH_COLUMNS if c in df_main.columns]
    if not search_cols:
        return None
    mask = df_main[search_cols].apply(
        lambda x: x.astype(str).str.contains(query, case=False, na=False, regex=False)
    ).any(axis=1)
    return df_main[mask].copy()


def strict_invoice_or_company_search(df_main: pd.DataFrame, query: str) -> Optional[pd.DataFrame]:
    """ระบบค้นหาปัจจุบัน: Invoice_Number หรือชื่อบริษัทต้องตรงทั้งช่องเท่านั้น"""
    masks = []
    if "Invoice_Number_Upper" in df_main.columns:
        masks.append(df_main["Invoice_Number_Upper"].astype(str).str.strip().eq(query.upper()))
    elif "Invoice_Number" in df_main.columns:
        masks.append(df_main["Invoice_Number"].astype(str).str.strip().str.upper().eq(query.upper()))
    if STRICT_COMPANY_COLUMN in df_main.columns:
        masks.append(df_main[STRICT_COMPANY_COLUMN].astype(str).str.strip().str.casefold().eq(query.casefold()))
    if not masks:
        return None

    mask = masks[0]
    for extra_mask in masks[1:]:
        mask = mask | extra_mask
    return df_main[mask].copy()


def search_dataframe(df_main: pd.DataFrame, query: str) -> Optional[pd.DataFrame]:
    if not query:
        return df_main.iloc[0:0].copy()
    if SEARCH_MODE == "partial":
        return legacy_partial_search(df_main, query)
    return strict_invoice_or_company_search(df_main, query)


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
async def search_vendor(
    request: Request,
    q: str = Query(..., description="เลข Invoice หรือชื่อผู้รับเงินแบบตรงทั้งช่อง")
):
    """
    ค้นหาข้อมูลแบบ strict match - Frontend Endpoint (Public)
    
    ตัวอย่าง: GET /api/search?q=สมชาย
    """
    logger.info(f"🔍 Public search request - Query: {q}")
    try:
        df_main, _ = await fetch_all_excel_data()
        
        if df_main.empty:
            return {"count": 0, "results": [], "message": "ตารางข้อมูลว่างเปล่า"}

        query = q.strip()
        result_df = search_dataframe(df_main, query)
        if result_df is None:
            return {"count": 0, "results": [], "message": "ไม่พบคอลัมน์สำหรับการค้นหา"}

        if result_df.empty:
            return {"count": 0, "results": [], "message": "ไม่พบข้อมูลรายการดังกล่าว"}

        # เลือกเฉพาะคอลัมน์ที่สนใจ
        valid_columns = [col for col in TARGET_COLUMNS if col in result_df.columns]
        final_data = result_df[valid_columns].copy()
        final_data['Invoice_Number'] = result_df['Invoice_Number'] if 'Invoice_Number' in result_df.columns else "-"
        
        # เปลี่ยนชื่อคอลัมน์สำหรับการแสดงผล
        final_data = final_data.rename(columns={"วันที่รายการมีผล": "วันที่โอนเงินเข้าบัญชี"})

        records = final_data.fillna("-").to_dict(orient='records')

        # Mask เลขบัญชีก่อน return สู่ public endpoint
        for record in records:
            if 'บัญชีผู้รับเงิน' in record:
                record['บัญชีผู้รับเงิน'] = mask_account_number(str(record['บัญชีผู้รับเงิน']))

        return {"count": len(records), "results": records}

    except SharePointConfigError as e:
        logger.error(f"Config error in search: {e}")
        raise HTTPException(status_code=500, detail="Data configuration error")
    except Exception as e:
        logger.error(f"Error in search: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

@app.get("/api/n8n/search")
async def n8n_search_vendor(
    request: Request,
    q: str = Query(..., description="Exact Invoice number or exact company name"),
    _: bool = Depends(verify_api_key)
):
    """
    ค้นหาข้อมูลแบบ strict match สำหรับ n8n/External API - ต้องมี Bearer Token
    
    Authentication: Bearer Token required
    
    ตัวอย่าง:
    GET /api/n8n/search?q=สมชาย
    Header: Authorization: Bearer <API_KEY>
    """
    logger.info(f"🔐 Authenticated API request - Query: {q}")
    try:
        df_main, logs = await fetch_all_excel_data()
        
        if df_main.empty:
            return {
                "success": False,
                "message": "ไม่สามารถดึงข้อมูลจาก SharePoint ได้",
                "data": None
            }

        query = q.strip()
        result_df = search_dataframe(df_main, query)
        if result_df is None:
            return {"success": False, "message": "Data structure error: Missing search columns", "data": None}
        
        if result_df.empty:
            return {
                "success": False,
                "message": f"ไม่พบข้อมูลจากคำค้นหา: {q}",
                "data": None
            }

        # เลือกคอลัมน์
        valid_columns = [col for col in TARGET_COLUMNS if col in result_df.columns]
        final_data = result_df[valid_columns].copy()
        final_data['Invoice_Number'] = result_df['Invoice_Number'] if 'Invoice_Number' in result_df.columns else "-"
        
        # เปลี่ยนชื่อคอลัมน์สำหรับการแสดงผล
        final_data = final_data.rename(columns={"วันที่รายการมีผล": "วันที่โอนเงินเข้าบัญชี"})
        
        records = final_data.fillna("-").to_dict(orient='records')
        
        # ✅ Mask เลขบัญชี (เหมือน /api/search)
        for record in records:
            if 'บัญชีผู้รับเงิน' in record:
                record['บัญชีผู้รับเงิน'] = mask_account_number(str(record['บัญชีผู้รับเงิน']))        
        logger.info(f"✅ n8n query for '{q}': Found {len(records)} record(s)")
        
        return {
            "success": True,
            "count": len(records),
            "data": records[0] if len(records) == 1 else records,
            "message": f"สำเร็จ - พบข้อมูล {len(records)} รายการ"
        }

    except HTTPException as e:
        raise e
    except SharePointConfigError as e:
        return {"success": False, "message": f"Data configuration error: {str(e)}", "data": None}
    except Exception as e:
        logger.error(f"Error in n8n search: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
