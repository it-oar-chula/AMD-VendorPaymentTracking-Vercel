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
_cache: dict = {"payment_df": None, "tax_df": None, "timestamp": 0.0}

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

PAYMENT_FILE_PREFIX = "payment_detail_report"
TAX_FILE_PREFIX = "tax-id"
TAX_ID_COLUMN = "เลขที่ภาษี 3"
TAX_DOCUMENT_COLUMN = "เลขเอกสาร"
PAYMENT_REFERENCE_COLUMN = "เลขที่อ้างอิงผู้รับเงิน"

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
    if _cache["payment_df"] is not None and _cache["tax_df"] is not None and (time.time() - _cache["timestamp"]) < CACHE_TTL:
        logger.info(
            f"⚡ Cache hit — using cached data "
            f"({len(_cache['payment_df'])} payment rows, {len(_cache['tax_df'])} tax rows, TTL {CACHE_TTL}s)"
        )
        SHAREPOINT_DOWN = False  # Reset status on cache hit
        return _cache["payment_df"], _cache["tax_df"], []

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

            payment_dataframes = []
            tax_dataframes = []

            for file_item in files:
                file_name = file_item.get('name', '')

                file_name_lower = file_name.lower()
                is_payment_file = file_name_lower.startswith(PAYMENT_FILE_PREFIX)
                is_tax_file = file_name_lower.startswith(TAX_FILE_PREFIX)

                # อ่านเฉพาะไฟล์ Payment_Detail_Report* และ tax-id*
                if not is_payment_file and not is_tax_file:
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
                    if file_name_lower.endswith('.xlsx'):
                        df = await run_in_threadpool(pd.read_excel, file_content, engine='openpyxl', dtype=str)
                    elif file_name_lower.endswith('.xls'):
                        df = await run_in_threadpool(pd.read_excel, file_content, engine='xlrd', dtype=str)
                    else:
                        df = await run_in_threadpool(pd.read_excel, file_content, dtype=str)
                    if is_payment_file:
                        payment_dataframes.append(df)
                    else:
                        tax_dataframes.append(df)
                    logs.append(f"✅ สำเร็จ: {file_name} ({len(df)} แถว)")
                except Exception:
                    # Excel ล้มเหลว → ลอง CSV encodings (utf-8-sig, cp874)
                    for encoding in ('utf-8-sig', 'cp874'):
                        try:
                            file_content.seek(0)
                            df = await run_in_threadpool(pd.read_csv, file_content, dtype=str, encoding=encoding)
                            if is_payment_file:
                                payment_dataframes.append(df)
                            else:
                                tax_dataframes.append(df)
                            logs.append(f"✅ สำเร็จ (CSV {encoding}): {file_name} ({len(df)} แถว)")
                            break
                        except Exception:
                            continue
                    else:
                        logs.append(f"❌ ล้มเหลว: {file_name}")

            if not payment_dataframes:
                logs.append("❌ ไม่พบไฟล์ Payment_Detail_Report ที่สามารถอ่านข้อมูลได้")
                raise SharePointConfigError("No Payment_Detail_Report files could be parsed")
            if not tax_dataframes:
                logs.append("❌ ไม่พบไฟล์ tax-id ที่สามารถอ่านข้อมูลได้")
                raise SharePointConfigError("No tax-id files could be parsed")

            # รวมข้อมูลจากทุกไฟล์ (blocking → threadpool)
            combined_df = await run_in_threadpool(pd.concat, payment_dataframes, ignore_index=True)
            combined_df.columns = combined_df.columns.astype(str).str.strip()
            tax_df = await run_in_threadpool(pd.concat, tax_dataframes, ignore_index=True)
            tax_df.columns = tax_df.columns.astype(str).str.strip()

            # --- Data Transformation (ย้ายมาทำตรงนี้ครั้งเดียว) ---
            if PAYMENT_REFERENCE_COLUMN in combined_df.columns:
                combined_df["Payment_Document_Number"] = (
                    combined_df[PAYMENT_REFERENCE_COLUMN].astype(str).str.strip().str.split("/").str[-1].str.strip()
                )
                combined_df["Payment_Document_Number_Normalized"] = combined_df["Payment_Document_Number"].apply(normalize_identifier)

            if TAX_ID_COLUMN in tax_df.columns:
                tax_df["Tax_ID_Normalized"] = tax_df[TAX_ID_COLUMN].apply(normalize_identifier)
            if TAX_DOCUMENT_COLUMN in tax_df.columns:
                tax_df["Tax_Document_Number"] = tax_df[TAX_DOCUMENT_COLUMN].astype(str).str.strip()
                tax_df["Tax_Document_Number_Normalized"] = tax_df["Tax_Document_Number"].apply(normalize_identifier)
            
            # ลบข้อมูลซ้ำ (blocking → threadpool)
            before_count = len(combined_df)
            combined_df = await run_in_threadpool(combined_df.drop_duplicates)
            tax_df = await run_in_threadpool(tax_df.drop_duplicates)
            after_count = len(combined_df)
            
            if before_count > after_count:
                logs.append(f"ℹ️ ลบข้อมูลซ้ำ: {before_count - after_count} รายการ")

            # ✅ สำเร็จ → บันทึกลง cache + reset status
            _cache["payment_df"] = combined_df
            _cache["tax_df"] = tax_df
            _cache["timestamp"] = time.time()
            SHAREPOINT_DOWN = False  # ✅ Reset status on success
            logger.info(f"✅ Cache updated — {len(combined_df)} payment rows, {len(tax_df)} tax rows, TTL {CACHE_TTL}s")

            return combined_df, tax_df, logs
    
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


def normalize_identifier(value: object) -> str:
    """เก็บเฉพาะตัวเลข สำหรับเทียบ tax id/document id ที่อาจมี space หรือ hyphen"""
    return "".join(c for c in str(value).strip() if c.isdigit())


def clean_tax_id_input(value: object) -> str:
    """ลบเฉพาะ whitespace จาก input ผู้ใช้ แต่ไม่ลบขีด/ตัวอักษรเพื่อให้ validate ได้ตรงไปตรงมา"""
    return "".join(c for c in str(value).strip() if not c.isspace())


def validate_tax_id_query(value: object) -> tuple[Optional[str], Optional[str]]:
    tax_id = clean_tax_id_input(value)
    if not tax_id:
        return None, "กรุณาระบุเลขประจำตัวผู้เสียภาษี 13 หลัก"
    if not tax_id.isdigit():
        return None, "เลขประจำตัวผู้เสียภาษีต้องเป็นตัวเลข 13 หลักเท่านั้น"
    if len(tax_id) < 13:
        return None, f"เลขประจำตัวผู้เสียภาษียังไม่ครบ ต้องมี 13 หลัก ตอนนี้มี {len(tax_id)} หลัก"
    if len(tax_id) > 13:
        return None, f"เลขประจำตัวผู้เสียภาษีเกิน ต้องมี 13 หลัก ตอนนี้มี {len(tax_id)} หลัก"
    return tax_id, None


def tax_id_payment_search(payment_df: pd.DataFrame, tax_df: pd.DataFrame, query: str) -> Optional[pd.DataFrame]:
    """ค้นหาด้วยเลขประจำตัวผู้เสียภาษี แล้ว map เลขเอกสารไปหา payment row"""
    required_payment_cols = {"Payment_Document_Number_Normalized"}
    required_tax_cols = {"Tax_ID_Normalized", "Tax_Document_Number_Normalized", TAX_ID_COLUMN, TAX_DOCUMENT_COLUMN}
    if not required_payment_cols.issubset(payment_df.columns) or not required_tax_cols.issubset(tax_df.columns):
        return None

    query_tax_id = clean_tax_id_input(query)
    if not query_tax_id:
        return payment_df.iloc[0:0].copy()

    matched_tax = tax_df[tax_df["Tax_ID_Normalized"].eq(query_tax_id)].copy()
    if matched_tax.empty:
        return payment_df.iloc[0:0].copy()

    document_numbers = set(matched_tax["Tax_Document_Number_Normalized"].dropna())
    result_df = payment_df[payment_df["Payment_Document_Number_Normalized"].isin(document_numbers)].copy()
    if result_df.empty:
        return result_df

    tax_lookup = matched_tax.drop_duplicates("Tax_Document_Number_Normalized")[
        ["Tax_Document_Number_Normalized", TAX_ID_COLUMN, TAX_DOCUMENT_COLUMN]
    ]
    return result_df.merge(
        tax_lookup,
        left_on="Payment_Document_Number_Normalized",
        right_on="Tax_Document_Number_Normalized",
        how="left",
    )


def payment_records(result_df: pd.DataFrame, query: str) -> list[dict]:
    valid_columns = [col for col in TARGET_COLUMNS if col in result_df.columns]
    final_data = result_df[valid_columns].copy()
    final_data["เลขประจำตัวผู้เสียภาษี"] = result_df[TAX_ID_COLUMN] if TAX_ID_COLUMN in result_df.columns else normalize_identifier(query)
    final_data["เลขเอกสาร"] = (
        result_df["Tax_Document_Number_Normalized"]
        if "Tax_Document_Number_Normalized" in result_df.columns
        else "-"
    )

    # เปลี่ยนชื่อคอลัมน์สำหรับการแสดงผล
    final_data = final_data.rename(columns={"วันที่รายการมีผล": "วันที่โอนเงินเข้าบัญชี"})

    records = final_data.fillna("-").to_dict(orient="records")
    for record in records:
        if "บัญชีผู้รับเงิน" in record:
            record["บัญชีผู้รับเงิน"] = mask_account_number(str(record["บัญชีผู้รับเงิน"]))
    return records


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
    q: str = Query(..., description="เลขประจำตัวผู้เสียภาษี")
):
    """
    ค้นหาข้อมูลด้วยเลขประจำตัวผู้เสียภาษี - Frontend Endpoint (Public)
    
    ตัวอย่าง: GET /api/search?q=3100200097940
    """
    logger.info(f"🔍 Public search request - Query: {q}")
    try:
        query, validation_error = validate_tax_id_query(q)
        if validation_error:
            raise HTTPException(status_code=400, detail=validation_error)

        payment_df, tax_df, _ = await fetch_all_excel_data()
        
        if payment_df.empty or tax_df.empty:
            return {"count": 0, "results": [], "message": "ตารางข้อมูลว่างเปล่า"}

        result_df = tax_id_payment_search(payment_df, tax_df, query)
        if result_df is None:
            return {"count": 0, "results": [], "message": "ไม่พบคอลัมน์สำหรับการค้นหา"}

        if result_df.empty:
            return {"count": 0, "results": [], "message": "ไม่พบข้อมูลรายการดังกล่าว"}

        records = payment_records(result_df, query)
        return {"count": len(records), "results": records}

    except SharePointConfigError as e:
        logger.error(f"Config error in search: {e}")
        raise HTTPException(status_code=500, detail="Data configuration error")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error in search: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

@app.get("/api/n8n/search")
async def n8n_search_vendor(
    request: Request,
    q: str = Query(..., description="Tax ID"),
    _: bool = Depends(verify_api_key)
):
    """
    ค้นหาข้อมูลด้วยเลขประจำตัวผู้เสียภาษี สำหรับ n8n/External API - ต้องมี Bearer Token
    
    Authentication: Bearer Token required
    
    ตัวอย่าง:
    GET /api/n8n/search?q=3100200097940
    Header: Authorization: Bearer <API_KEY>
    """
    logger.info(f"🔐 Authenticated API request - Query: {q}")
    try:
        query, validation_error = validate_tax_id_query(q)
        if validation_error:
            raise HTTPException(status_code=400, detail=validation_error)

        payment_df, tax_df, logs = await fetch_all_excel_data()
        
        if payment_df.empty or tax_df.empty:
            return {
                "success": False,
                "message": "ไม่สามารถดึงข้อมูลจาก SharePoint ได้",
                "data": None
            }

        result_df = tax_id_payment_search(payment_df, tax_df, query)
        if result_df is None:
            return {"success": False, "message": "Data structure error: Missing search columns", "data": None}
        
        if result_df.empty:
            return {
                "success": False,
                "message": f"ไม่พบข้อมูลจากคำค้นหา: {q}",
                "data": None
            }

        records = payment_records(result_df, query)
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
