import os
import pandas as pd
import msal
import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import quote
from dotenv import load_dotenv

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

# กำหนดคอลัมน์ที่สนใจ 7 คอลัมน์ + เพิ่มสถานะรายการ เพื่อให้เว็บแสดงผลป้ายสีได้
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

def get_access_token():
    authority = f"https://login.microsoftonline.com/{TENANT_ID}"
    client_app = msal.ConfidentialClientApplication(
        CLIENT_ID, authority=authority, client_credential=CLIENT_SECRET
    )
    result = client_app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return result.get("access_token")

def fetch_all_excel_data():
    """ดึงข้อมูลจากทุกไฟล์ คืนค่ากลับมาเป็น (DataFrame, รายการLog)"""
    logs = []
    token = get_access_token()
    if not token:
        return pd.DataFrame(), ["❌ ไม่สามารถขอ Access Token จาก Azure ได้"]
    
    headers = {'Authorization': f'Bearer {token}'}
    
    site_url = f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_HOST}:/sites/{SHAREPOINT_SITE_NAME}"
    site_res = requests.get(site_url, headers=headers).json()
    site_id = site_res.get('id')
    if not site_id:
        return pd.DataFrame(), [f"❌ หา Site ID ไม่เจอ: {site_res}"]

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
        
        if file_name.startswith('Payment_Detail_Report'):
            download_url = file_item.get('@microsoft.graph.downloadUrl')
            
            if download_url:
                try:
                    # ตรวจสอบนามสกุลไฟล์เพื่อเลือก engine ที่เหมาะสม
                    if file_name.endswith('.xlsx'):
                        df = pd.read_excel(download_url, engine='openpyxl', dtype=str)
                        all_dataframes.append(df)
                        logs.append(f"✅ สำเร็จ (Excel .xlsx): {file_name} ({len(df)} แถว)")
                    elif file_name.endswith('.xls'):
                        df = pd.read_excel(download_url, engine='xlrd', dtype=str)
                        all_dataframes.append(df)
                        logs.append(f"✅ สำเร็จ (Excel .xls): {file_name} ({len(df)} แถว)")
                    else:
                        # กรณีไม่มีนามสกุล หรือไฟล์อื่นๆ ลอง Excel ก่อน
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
                            logs.append(f"✅ สำเร็จ (CSV ภาษาไทย TIS-620): {file_name} ({len(df)} แถว)")
                        except Exception as e3:
                            logs.append(f"❌ ล้มเหลว: {file_name} - {str(e1)[:100]}")

    if not all_dataframes:
         return pd.DataFrame(), logs + ["❌ ไม่พบไฟล์ที่สามารถอ่านข้อมูลได้เลย"]
    
    combined_df = pd.concat(all_dataframes, ignore_index=True)
    combined_df.columns = combined_df.columns.astype(str).str.strip()
    
    # ลบข้อมูลซ้ำ (กรณีมีข้อมูลเดียวกันอยู่หลายไฟล์)
    before_count = len(combined_df)
    combined_df = combined_df.drop_duplicates()
    after_count = len(combined_df)
    
    if before_count > after_count:
        logs.append(f"ℹ️ ลบข้อมูลซ้ำ: {before_count - after_count} รายการ (เหลือ {after_count} รายการ)")
    
    return combined_df, logs

# --- API Endpoints ---

@app.get("/")
async def root():
    return {"status": "online", "service": "Vendor Payment Tracking API", "message": "โปรดไปที่ /index.html เพื่อเข้าสู่หน้าค้นหาข้อมูลสถานะการจ่ายเงิน"}

@app.get("/api/search")
async def search_vendor(q: str = Query(..., description="คำค้นหา (เลขรหัส Invoice เท่านั้น)")):
    try:
        df_main, logs = fetch_all_excel_data()
        
        if df_main.empty:
            return {"count": 0, "results": [], "message": "ตารางข้อมูลว่างเปล่า (อ่านไฟล์ไม่สำเร็จ)", "logs": logs}
            
        if 'รายละเอียดของรายการ' not in df_main.columns:
             return {"count": 0, "results": [], "message": f"ไม่พบคอลัมน์ 'รายละเอียดของรายการ'", "logs": logs}

        # สร้างคอลัมน์ Invoice_Number โดยตัดคำที่เว้นวรรค
        df_main['Invoice_Number'] = df_main['รายละเอียดของรายการ'].astype(str).str.strip().str.split().str[0]
        
        query = q.strip().upper()
        result_df = df_main[df_main['Invoice_Number'].str.upper() == query].copy()
        
        if result_df.empty:
            return {"count": 0, "results": [], "message": "ไม่พบข้อมูลรายการดังกล่าว", "logs": logs}

        valid_columns = [col for col in TARGET_COLUMNS if col in result_df.columns]
        final_data = result_df[valid_columns].copy()
        
        # แนบ Invoice_Number กลับไปให้หน้าเว็บแสดงผลด้วย
        final_data['Invoice_Number'] = result_df['Invoice_Number']
        
        records = final_data.fillna("-").to_dict(orient='records')
        
        return {
            "count": len(records),
            "results": records,
            "logs": logs
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check endpoints (สำหรับ Local และ Vercel)
@app.get("/health")
async def health_check_local():
    return {"status": "online", "message": "Backend is running"}

@app.get("/api/health")
async def health_check():
    return {"status": "online", "message": "Backend is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)