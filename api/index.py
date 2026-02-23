import os
import pandas as pd
import msal
import requests
from fastapi import FastAPI, Query, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import quote
from dotenv import load_dotenv
from typing import Optional
import logging

# ตั้งค่า Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# โหลดค่าจากไฟล์ .env
load_dotenv()

app = FastAPI(title="Vendor Tracking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration ---
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SHAREPOINT_SITE_NAME = os.getenv("SHAREPOINT_SITE_NAME")
SHAREPOINT_HOST = os.getenv("SHAREPOINT_HOST", "carchula.sharepoint.com")
SHAREPOINT_FOLDER = os.getenv("SHAREPOINT_FOLDER", "Test Vendor")

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
    """ดึงข้อมูลจากทุกไฟล์ Excel บน SharePoint"""
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
    
    return combined_df, logs

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
async def search_vendor(q: str = Query(..., description="คำค้นหา Invoice Number")):
    """
    ค้นหาข้อมูล Invoice - ใช้จากเว็บ Frontend
    ไม่ต้องมี Authentication
    
    ตัวอย่าง: GET /api/search?q=INV001234
    """
    try:
        df_main, logs = fetch_all_excel_data()
        
        if df_main.empty:
            return {
                "count": 0,
                "results": [],
                "message": "ตารางข้อมูลว่างเปล่า",
                "logs": logs
            }
            
        if 'รายละเอียดของรายการ' not in df_main.columns:
             return {
                 "count": 0,
                 "results": [],
                 "message": "ไม่พบคอลัมน์ที่ต้องการ",
                 "logs": logs
             }

        # สร้าง Invoice_Number column
        df_main['Invoice_Number'] = df_main['รายละเอียดของรายการ'].astype(str).str.strip().str.split().str[0]
        
        query = q.strip().upper()
        result_df = df_main[df_main['Invoice_Number'].str.upper() == query].copy()
        
        if result_df.empty:
            return {
                "count": 0,
                "results": [],
                "message": "ไม่พบข้อมูลรายการดังกล่าว",
                "logs": logs
            }

        # เลือกเฉพาะคอลัมน์ที่สนใจ
        valid_columns = [col for col in TARGET_COLUMNS if col in result_df.columns]
        final_data = result_df[valid_columns].copy()
        final_data['Invoice_Number'] = result_df['Invoice_Number']
        
        records = final_data.fillna("-").to_dict(orient='records')
        
        return {
            "count": len(records),
            "results": records,
            "logs": logs
        }

    except Exception as e:
        logger.error(f"Error in search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/n8n/search")
async def n8n_search_vendor(
    q: str = Query(..., description="Invoice Number"),
    _: bool = Depends(verify_api_key)
):
    """
    ค้นหาข้อมูล Invoice สำหรับ n8n - ต้องมี Bearer Token Authentication
    
    ตัวอย่าง:
    GET /api/n8n/search?q=INV001234
    Header: Authorization: Bearer API_KEY
    """
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
