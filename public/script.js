// --- Configuration ---
// ถ้าทดสอบในเครื่อง (Localhost) ให้ใช้ "http://localhost:8000"
// ถ้าขึ้น Vercel หรือ Production ให้ใช้ "" (เรียก path เดียวกัน)
const API_BASE_URL = "http://localhost:8000"; 

async function handleSearch() {
    const input = document.getElementById('searchInput').value.trim();
    const resultArea = document.getElementById('result-area');
    const loading = document.getElementById('loading');

    if (!input) return;

    // 1. เคลียร์หน้าจอและแสดง Loading
    resultArea.innerHTML = '';
    loading.style.display = 'block';

    try {
        // 2. เรียก API ไปยัง Backend (FastAPI)
        const response = await fetch(`${API_BASE_URL}/search?q=${encodeURIComponent(input)}`);
        
        if (!response.ok) {
            throw new Error("ไม่สามารถเชื่อมต่อระบบได้");
        }

        const data = await response.json();
        
        // ซ่อน Loading
        loading.style.display = 'none';

        // 3. กรณีไม่พบข้อมูล
        if (data.count === 0) {
            resultArea.innerHTML = `
                <article class="result-card" style="border-left-color: #dc3545; text-align: center;">
                    <h5 style="color: #dc3545; margin-bottom: 0.5rem;">❌ ไม่พบข้อมูล</h5>
                    <p style="margin-bottom: 0;">ไม่พบรายการที่ตรงกับ "${input}" โปรดตรวจสอบความถูกต้องอีกครั้ง</p>
                </article>`;
            return;
        }

        // 4. กรณีพบข้อมูล: วนลูปสร้างการ์ด (Card)
        resultArea.innerHTML = `<h6 style="margin-bottom: 1rem; color: #666;">พบทั้งหมด ${data.count} รายการ</h6>` + 
        data.results.map(item => {
            // กำหนดสีสถานะ (Logic ง่ายๆ)
            let statusClass = 'status-default';
            let statusText = item['สถานะ'] || 'รอดำเนินการ'; // ใช้ชื่อคอลัมน์จาก Excel
            
            if (statusText.includes('จ่าย') || statusText.includes('สำเร็จ') || statusText.includes('โอน')) {
                statusClass = 'status-success';
            } else if (statusText.includes('รอ') || statusText.includes('ค้าง')) {
                statusClass = 'status-pending';
            }

            // สร้าง HTML ของการ์ด
            // หมายเหตุ: ชื่อ key (item['...']) ต้องตรงกับ Header ใน Excel ของคุณ Art เป๊ะๆ
            return `
            <div class="result-card" style="border-left-color: ${statusClass === 'status-success' ? '#28a745' : '#ffc107'};">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px;">
                    <div>
                        <small style="color: #888;">เลขที่รายการ: ${item['เลขที่อ้างอิงรายการ'] || '-'}</small>
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
                        <strong>${item['บริการ'] || '-'}</strong><br>
                        <small>วันที่: ${item['วันที่รายการมีผล'] || '-'}</small>
                    </div>
                    <div style="text-align: right;">
                        <small style="color: #666;">จำนวนเงินสุทธิ</small><br>
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