// --- Configuration ---
// เช็คอัตโนมัติ: ถ้ารันบน localhost ให้ชี้ไปที่ port 8000, ถ้า deploy แล้วใช้ /api
const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
    ? "http://localhost:8000" 
    : "/api";

async function handleSearch() {
    const input = document.getElementById('searchInput').value.trim();
    const resultArea = document.getElementById('result-area');
    const loading = document.getElementById('loading');

    if (!input) return;

    // 1. เคลียร์หน้าจอและแสดง Loading
    resultArea.innerHTML = '';
    loading.style.display = 'block';

    try {
        // 2. เรียก API ไปยัง Backend (FastAPI) โดยระบุ /search (ต่อจาก API_BASE_URL)
        const response = await fetch(`${API_BASE_URL}/search?q=${encodeURIComponent(input)}`);
        
        if (!response.ok) {
            throw new Error("ไม่สามารถเชื่อมต่อระบบได้");
        }

        const data = await response.json();
        loading.style.display = 'none';

        // 3. กรณีไม่พบข้อมูล
        if (data.count === 0) {
            resultArea.innerHTML = `
                <article class="result-card" style="border-left-color: #dc3545; text-align: center;">
                    <h5 style="color: #dc3545; margin-bottom: 0.5rem;">❌ ไม่พบข้อมูล</h5>
                    <p style="margin-bottom: 0.5rem;">ไม่พบรายการ "<strong>${input}</strong>" หรือรายการยังไม่ได้รับอนุมัติ</p>
                    <small style="color: #888;">โปรดตรวจสอบเลข Invoice อีกครั้ง (ต้องพิมพ์ตรงกับที่ระบุในเอกสารทุกตัวอักษร)</small>
                </article>`;
            return;
        }

        // 4. กรณีพบข้อมูล: วนลูปสร้างการ์ด (Card)
        resultArea.innerHTML = `<h6 style="margin-bottom: 1rem; color: #666;">พบทั้งหมด ${data.count} รายการ</h6>` + 
        data.results.map(item => {
            // กำหนดสีสถานะ (ใช้คอลัมน์ "สถานะรายการ" ตามไฟล์ CSV)
            let statusClass = 'status-default';
            let statusText = item['สถานะรายการ'] || 'รอดำเนินการ'; 
            
            if (statusText.includes('สำเร็จ') || statusText.includes('จ่าย') || statusText.includes('โอน')) {
                statusClass = 'status-success';
            } else if (statusText.includes('รอ') || statusText.includes('ค้าง')) {
                statusClass = 'status-pending';
            }

            // จัดหน้าตา Card ใหม่ให้ดึงเฉพาะ 7 คอลัมน์ที่คุณสนใจมาแสดง
            return `
            <div class="result-card" style="border-left-color: ${statusClass === 'status-success' ? '#28a745' : '#ffc107'};">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                    <div>
                        <small style="color: #888;">Invoice: ${item['Invoice_Number'] || '-'}</small>
                        <h5 style="margin: 0; font-weight: bold; color: #333;">${item['ชื่อผู้รับเงิน'] || 'ไม่ระบุชื่อ'}</h5>
                    </div>
                    <span class="status-pill ${statusClass}">
                        ${statusText}
                    </span>
                </div>
                
                <hr style="margin: 0.5rem 0; border-color: #eee;">
                
                <div class="grid">
                    <div>
                        <small style="color: #666;">รายละเอียด</small><br>
                        <em style="color: #555;">${item['รายละเอียดของรายการ'] || '-'}</em><br><br>
                        
                        <small style="color: #666;">ข้อมูลการโอนเงิน</small><br>
                        <small>ธนาคาร: <strong>${item['ธนาคาร'] || '-'}</strong> สาขา: ${item['สาขาธนาคารผู้รับเงิน'] || '-'}</small><br>
                        <small>เลขบัญชี: <strong>${item['บัญชีผู้รับเงิน'] || '-'}</strong></small><br><br>
                        
                        <div style="padding: 8px 12px; background: #e8f5e9; border-radius: 6px; border-left: 4px solid #4caf50; display: inline-block;">
                            <small style="color: #2e7d32; font-weight: bold;">📅 วันที่รายการมีผล: <span style="font-size: 1.1em;">${item['วันที่รายการมีผล'] || '-'}</span></small>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <small style="color: #666;">จำนวนเงิน</small><br>
                        <span class="amount-text">฿${Number(item['จำนวนเงิน'] || 0).toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
                    </div>
                </div>
            </div>
            `;
        }).join('');

    } catch (error) {
        loading.style.display = 'none';
        console.error("Error:", error);
        resultArea.innerHTML = `
            <article class="result-card" style="border-left-color: #dc3545; background-color: #fff5f5;">
                <strong>⚠️ เกิดข้อผิดพลาด:</strong> ไม่สามารถดึงข้อมูลได้ในขณะนี้ (${error.message})
            </article>`;
    }
}