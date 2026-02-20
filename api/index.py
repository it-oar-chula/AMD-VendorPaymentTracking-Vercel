import os
from typing import Optional
import pandas as pd
import msal
import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import quote
from dotenv import load_dotenv

# 1. โหลดค่าจากไฟล์ .env
load_dotenv()

app = FastAPI(title="Vendor Tracking API")

# 2. ตั้งค่า CORS เพื่อให้ Frontend (index.html) เรียกใช้งานได้
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ในใช้งานจริงควรระบุ URL ของเว็บเราเพื่อความปลอดภัย
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Configuration จาก Environment Variables ---
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SHAREPOINT_SITE_NAME = os.getenv("SHAREPOINT_SITE_NAME")
SHAREPOINT_HOST = os.getenv("SHAREPOINT_HOST", "carchula.sharepoint.com")
SHAREPOINT_FOLDER = os.getenv("SHAREPOINT_FOLDER", "Test Vendor")
FILE_NAME = os.getenv("FILE_NAME", "Payment_Detail_Report.xlsx")

# --- Helper Functions ---

def get_access_token():
    """ขอ Access Token จาก Microsoft Graph API"""
    authority = f"https://login.microsoftonline.com/{TENANT_ID}"
    client_app = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=authority, client_credential=CLIENT_SECRET
    )
    result = client_app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return result.get("access_token")

def fetch_excel_data():
    """ดึงข้อมูลจาก SharePoint และส่งคืนเป็น DataFrame"""
    token = get_access_token()
    if not token:
        raise Exception("ไม่สามารถขอ Access Token ได้")
    
    headers = {'Authorization': f'Bearer {token}'}
    
    # หา Site ID
    site_url = f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_HOST}:/sites/{SHAREPOINT_SITE_NAME}"
    site_res = requests.get(site_url, headers=headers).json()
    site_id = site_res.get('id')
    
    if not site_id:
        raise Exception("หา Site ID ไม่เจอ")

    # หาไฟล์และดึง Download URL
    file_path = f"{SHAREPOINT_FOLDER}/{FILE_NAME}".strip("/")
    encoded_path = quote(file_path)
    file_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{encoded_path}"
    file_res = requests.get(file_url, headers=headers).json()
    
    download_url = file_res.get('@microsoft.graph.downloadUrl')
    if not download_url:
        raise Exception("หาไฟล์ไม่เจอหรือไม่มีสิทธิ์เข้าถึง")
    
    # อ่านข้อมูล 2 Sheets
    # ระบุ dtype เพื่อป้องกันตัวเลขรหัสต่างๆ เพี้ยน
    dtype_spec = {
        'เลขที่อ้างอิงรายการ': str,
        'บัญชีหักเงิน': str,
        'บัญชีผู้รับเงิน': str,
        'รหัสธนาคาร': str,
        'เลขประจำตัวผู้เสียภาษี': str
    }
    
    df_main = pd.read_excel(download_url, sheet_name='Payment_Detail_Report', dtype=dtype_spec)
    df_show = pd.read_excel(download_url, sheet_name='Show_Column')
    
    return df_main, df_show

# --- API Endpoints ---

@app.get("/api/search")
async def search_vendor(q: str = Query(..., description="คำค้นหา (ชื่อหรือเลขประจำตัวผู้เสียภาษี)")):
    try:
        # 1. ดึงข้อมูลล่าสุด
        df_main, df_show = fetch_excel_data()
        
        # 2. จัดการเรื่องคอลัมน์ที่จะแสดงผล (Logic เดิมที่คุณ Art ต้องการ)
        columns_to_show = df_show[df_show['Show'].str.upper() == 'YES']['Name'].tolist()
        # กรองเฉพาะคอลัมน์ที่มีอยู่จริงในไฟล์หลัก
        valid_columns = [col for col in columns_to_show if col in df_main.columns]
        
        # 3. ค้นหาข้อมูล
        query = q.strip().lower()
        # ค้นหาแบบคลุมเครือจากทุกคอลัมน์ที่มี
        mask = df_main.astype(str).apply(lambda x: x.str.contains(query, case=False, na=False)).any(axis=1)
        result_df = df_main[mask].copy()
        
        if result_df.empty:
            return {"count": 0, "results": []}

        # 4. จัดการ Format ข้อมูลก่อนส่งกลับ (วันที่และตัวเลข)
        # กรองเอาเฉพาะคอลัมน์ที่เราตกลงว่าจะโชว์
        final_data = result_df[valid_columns].copy()
        
        # แปลงวันที่ให้เป็น Format YYYY-MM-DD
        for col in final_data.columns:
            if pd.api.types.is_datetime64_any_dtype(final_data[col]):
                final_data[col] = final_data[col].dt.strftime('%Y-%m-%d')
        
        # แปลงเป็น JSON List of Objects
        # .to_dict(orient='records') จะทำให้ JavaScript อ่านง่ายที่สุด
        records = final_data.fillna("-").to_dict(orient='records')
        
        return {
            "count": len(records),
            "results": records
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    return {"status": "online", "message": "Backend is running smoothly"}

if __name__ == "__main__":
    import uvicorn
    # รันบนเครื่องตัวเองที่พอร์ต 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)