// --- Configuration ---
// เช็คอัตโนมัติ: ถ้ารันบน localhost ให้ชี้ไปที่ port 8000, ถ้า deploy แล้วใช้ /api
const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? "http://localhost:8000/api"
    : "/api";

// --- Security Helper ---
// ป้องกัน XSS: escape HTML entities ก่อน inject ลง innerHTML เสมอ
function esc(val, fallback = '-') {
    const s = (val != null && val !== '' && val !== '-') ? String(val) : fallback;
    return s
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// ✅ Highlight function (รับ escaped text)
function highlight(text, term) {
    if (!term || !text) return text;
    // Escape regex special characters
    const pattern = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${pattern})`, 'gi');
    return text.replace(regex, '<mark class="highlight">$1</mark>');
}

// ✅ Highlight with Escape (escape + highlight combined)
function highlightEsc(val, term, fallback = '-') {
    const escaped = esc(val, fallback);
    return highlight(escaped, term);
}

function showMessage(resultArea, title, message, detail = '', color = '#dc3545') {
    resultArea.innerHTML = `
        <article class="result-card" style="border-left-color: ${color}; text-align: center;">
            <h5 style="color: ${color}; margin-bottom: 0.5rem;">${esc(title)}</h5>
            <p style="margin-bottom: 0.5rem;">${esc(message)}</p>
            ${detail ? `<small style="color: #888;">${esc(detail)}</small>` : ''}
        </article>`;
}

function validateTaxId(rawInput) {
    const value = rawInput.replace(/\s+/g, '');
    if (!value) {
        return { value, message: 'กรุณาระบุเลขประจำตัวผู้เสียภาษี 13 หลัก' };
    }
    if (!/^\d+$/.test(value)) {
        return {
            value,
            message: 'เลขประจำตัวผู้เสียภาษีต้องเป็นตัวเลขเท่านั้น',
            detail: 'ระบบลบช่องว่างให้อัตโนมัติ แต่ไม่รับขีด ตัวอักษร หรือสัญลักษณ์'
        };
    }
    if (value.length < 13) {
        return { value, message: `เลขยังไม่ครบ ต้องมี 13 หลัก ตอนนี้มี ${value.length} หลัก` };
    }
    if (value.length > 13) {
        return { value, message: `เลขเกิน ต้องมี 13 หลัก ตอนนี้มี ${value.length} หลัก` };
    }
    return { value };
}

async function handleSearch() {
    const searchInput = document.getElementById('searchInput');
    const validation = validateTaxId(searchInput.value);
    const input = validation.value;
    const resultArea = document.getElementById('result-area');
    const loading = document.getElementById('loading');

    searchInput.value = input;
    if (validation.message) {
        loading.style.display = 'none';
        showMessage(resultArea, 'ตรวจสอบเลขผู้เสียภาษี', validation.message, validation.detail || '');
        return;
    }

    // 1. เคลียร์หน้าจอและแสดง Loading
    resultArea.innerHTML = '';
    loading.style.display = 'block';

    try {
        // 2. เรียก API ไปยัง Backend (FastAPI) โดยระบุ /search (ต่อจาก API_BASE_URL)
        const response = await fetch(`${API_BASE_URL}/search?q=${encodeURIComponent(input)}`);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || "ไม่สามารถเชื่อมต่อระบบได้");
        }

        const data = await response.json();
        loading.style.display = 'none';

        // 3. กรณีไม่พบข้อมูล
        if (data.count === 0) {
            showMessage(
                resultArea,
                'ไม่พบข้อมูล',
                `เลขผู้เสียภาษี ${input} ถูกต้องตามรูปแบบแล้ว แต่ไม่พบรายการจ่ายเงิน`,
                'อาจยังไม่มีข้อมูลในไฟล์ tax-id หรือยังจับคู่เลขเอกสารกับ Payment_Detail_Report ไม่ได้'
            );
            return;
        }

        // 4. กรณีพบข้อมูล: วนลูปสร้างการ์ด (Card)
        resultArea.innerHTML = `<h6 style="margin-bottom: 1rem; color: #666;">พบทั้งหมด ${Number(data.count)} รายการ</h6>` +
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
                        <small style="color: #888;">เลขผู้เสียภาษี: ${highlightEsc(item['เลขประจำตัวผู้เสียภาษี'], input)}</small><br>
                        <small style="color: #888;">เลขเอกสาร: ${highlightEsc(item['เลขเอกสาร'], input)}</small>
                        <h5 style="margin: 0; font-weight: bold; color: #333;">${highlightEsc(item['ชื่อผู้รับเงิน'], input, 'ไม่ระบุชื่อ')}</h5>
                    </div>
                    <span class="status-pill ${statusClass}">
                        ${highlightEsc(statusText, input)}
                    </span>
                </div>

                <hr style="margin: 0.5rem 0; border-color: #eee;">

                <div class="grid">
                    <div>
                        <small style="color: #666;">รายละเอียด</small><br>
                        <em style="color: #555;">${highlightEsc(item['รายละเอียดของรายการ'], input)}</em><br><br>

                        <small style="color: #666;">ข้อมูลการโอนเงิน</small><br>
                        <small>ธนาคาร: <strong>${highlightEsc(item['ธนาคาร'], input)}</strong> สาขา: ${highlightEsc(item['สาขาธนาคารผู้รับเงิน'], input)}</small><br>
                        <small>เลขบัญชี: <strong>${highlightEsc(item['บัญชีผู้รับเงิน'], input)}</strong></small><br><br>

                        <div style="padding: 8px 12px; background: #e8f5e9; border-radius: 6px; border-left: 4px solid #4caf50; display: inline-block;">
                            <small style="color: #2e7d32; font-weight: bold;">📅 วันที่โอนเงินเข้าบัญชี: <span style="font-size: 1.1em;">${highlightEsc(item['วันที่โอนเงินเข้าบัญชี'], input)}</span></small>
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
                <strong>⚠️ เกิดข้อผิดพลาด:</strong> ไม่สามารถดึงข้อมูลได้ในขณะนี้ (${esc(error.message)})
            </article>`;
    }
}
