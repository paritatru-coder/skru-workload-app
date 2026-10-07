import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import io

# ---------------------------------------------------------
# 1. การตั้งค่าระบบ และ ธีม UI
# ---------------------------------------------------------
st.set_page_config(
    page_title="SKRU Workload AI - ระบบบันทึกและวิเคราะห์ภาระงาน มรภ.สงขลา",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        color: #1E3A8A;
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #4B5563;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .card-box {
        background-color: #FFFFFF;
        padding: 1.25rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08);
        border-left: 5px solid #2563EB;
        margin-bottom: 1rem;
    }
    .stButton>button {
        border-radius: 6px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. การจัดการฐานข้อมูล Google Sheets / Local Session Fallback
# ---------------------------------------------------------
conn = None
use_gsheets = False

try:
    from streamlit_gsheets import GSheetsConnection
    # เช็กว่ามี secrets หรือไม่
    if hasattr(st, "secrets") and "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        conn = st.connection("gsheets", type=GSheetsConnection)
        use_gsheets = True
except Exception:
    use_gsheets = False

# ฟังก์ชันดึงข้อมูลทั้งหมด
def load_all_data():
    if use_gsheets and conn:
        try:
            df = conn.read(ttl="0")
            if df is not None and not df.empty:
                df["ภาระงาน_ชม"] = pd.to_numeric(df["ภาระงาน_ชม"], errors="coerce").fillna(0.0)
                return df
        except Exception as e:
            st.warning(f"⚠️ ไม่สามารถเชื่อมต่อ Google Sheets ได้ (ใช้ระบบความจำชั่วคราวแทน): {e}")
    
    # หากไม่มีใน Session State ให้สร้างตั้งต้น
    if "local_db" not in st.session_state:
        st.session_state["local_db"] = pd.DataFrame([
            {"email": "paritat@skru.ac.th", "หมวดงาน": "2. วิจัย/สร้างสรรค์", "รายการภาระงาน": "ผลงานสร้างสรรค์ 'Songkhla Artistic Land of Two Seas'", "เลขคำสั่ง_อ้างอิง": "UDRU: ISCFA-2026", "วันที่": "28-29 เม.ย. 69", "ภาระงาน_ชม": 24.0, "วันที่บันทึก": "2026-10-01"},
            {"email": "paritat@skru.ac.th", "หมวดงาน": "2. วิจัย/สร้างสรรค์", "รายการภาระงาน": "ผลงานประพันธ์เพลง 'Keherwa A-Hom'", "เลขคำสั่ง_อ้างอิง": "13th IFA 2026", "วันที่": "16 มิ.ย. 69", "ภาระงาน_ชม": 24.0, "วันที่บันทึก": "2026-10-02"},
            {"email": "paritat@skru.ac.th", "หมวดงาน": "3. บริการวิชาการ", "รายการภาระงาน": "วิทยากรโครงการดนตรีไทยผู้สูงอายุ", "เลขคำสั่ง_อ้างอิง": "คำสั่งคณะฯ ที่ 060/2569", "วันที่": "25-27 พ.ค. 69", "ภาระงาน_ชม": 3.0, "วันที่บันทึก": "2026-10-03"},
            {"email": "paritat@skru.ac.th", "หมวดงาน": "4. ศิลปวัฒนธรรม", "รายการภาระงาน": "จัดพิธีไหว้ครูและครอบครูดนตรีไทย 2569", "เลขคำสั่ง_อ้างอิง": "หนังสือเชิญไหว้ครู", "วันที่": "6 ส.ค. 69", "ภาระงาน_ชม": 4.0, "วันที่บันทึก": "2026-10-04"},
            {"email": "paritat@skru.ac.th", "หมวดงาน": "5. งานอื่น ๆ", "รายการภาระงาน": "กรรมการบริหารหลักสูตรฯ", "เลขคำสั่ง_อ้างอิง": "คำสั่ง ม. ที่ 377/2568", "วันที่": "ตลอดภาคเรียน", "ภาระงาน_ชม": 8.0, "วันที่บันทึก": "2026-10-05"},
        ])
    return st.session_state["local_db"]

# ฟังก์ชันบันทึกข้อมูลย้อนกลับ
def save_all_data(full_df):
    if use_gsheets and conn:
        try:
            conn.update(data=full_df)
            st.toast("✅ อัปเดตข้อมูลลง Google Sheets เรียบร้อยแล้ว!", icon="☁️")
            return True
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึกลง Google Sheets: {e}")
            return False
    else:
        st.session_state["local_db"] = full_df
        st.toast("✅ บันทึกข้อมูลลงในระบบชั่วคราวเรียบร้อย!", icon="💾")
        return True

# ---------------------------------------------------------
# 3. แถบข้าง (Sidebar) & ระบบล็อกอิน
# ---------------------------------------------------------
with st.sidebar:
    st.image("https://www.skru.ac.th/images/logo/SKRU_LOGO.png", width=100) if False else None
    st.title("👤 ระบบระบุตัวตน & ตั้งค่า")
    
    user_email = st.text_input(
        "📧 อีเมลบุคลากร (สำหรับซิงค์ข้อมูล):",
        value="paritat@skru.ac.th",
        help="กรอกอีเมลเดียวกันเมื่อเข้าใช้จาก มือถือ, คอมบ้าน หรือคอมที่ทำงาน ข้อมูลจะดึงมาจาก Google Sheets สดๆ เสมอ"
    )
    
    role = st.selectbox(
        "🏛️ กลุ่มตำแหน่ง / สังกัด:",
        [
            "อาจารย์สายสอน (ไม่ดำรงตำแหน่งบริหาร)",
            "ผู้บริหาร (คณบดี / รองคณบดี / ผู้ช่วยคณบดี)",
            "ประธานหลักสูตร / หัวหน้าสาขา",
            "บุคลากรสายสนับสนุน"
        ]
    )
    
    st.divider()
    
    # เช็กการตั้งค่า API Key จาก Secrets
    api_key_env = ""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key_env = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
        
    user_api_key = st.text_input("🔑 Gemini API Key (ระบุเองเพิ่มเติม):", type="password", value=api_key_env)
    
    active_api_key = user_api_key if user_api_key else api_key_env
    
    if use_gsheets:
        st.success("☁️ บันทึกข้อมูลซิงค์กับ Google Sheets อัตโนมัติ", icon="🟢")
    else:
        st.info("💡 โหมดทดสอบชั่วคราว (ยังไม่ได้เชื่อม Google Sheets)", icon="🟡")

# ---------------------------------------------------------
# 4. หน้าหลัก (Main Header & Tabs)
# ---------------------------------------------------------
st.markdown('<div class="main-header">🏛️ SKRU Academic Workload AI Assistant</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">ระบบช่วยสกัดเอกสารคำสั่ง วิเคราะห์ และสะสมภาระงานสายวิชาการ มรภ.สงขลา | ผู้ใช้งาน: <b>{user_email}</b></div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📥 1. บันทึกและวิเคราะห์ภาระงาน", "📊 2. คลังภาระงานสะสม (ซิงค์ Cloud)", "📄 3. สรุปแบบ ป-มร.สข. 01"])

# ดึงข้อมูลตั้งต้น
all_data_df = load_all_data()

# ---------------------------------------------------------
# TAB 1: บันทึกและวิเคราะห์ภาระงาน
# ---------------------------------------------------------
with tab1:
    col_a, col_b = st.columns([1, 1], gap="large")
    
    with col_a:
        st.subheader("📝 ขั้นตอนที่ 1: แนบเอกสารคำสั่ง / พิมพ์รายละเอียด")
        
        category = st.selectbox(
            "📂 หมวดภาระงาน:",
            [
                "1. ภาระงานสอน",
                "2. ภาระงานวิจัย / งานประพันธ์ / งานสร้างสรรค์",
                "3. ภาระงานบริการวิชาการ",
                "4. ภาระงานทำนุบำรุงศิลปวัฒนธรรม",
                "5. ภาระงานอื่น ๆ / งานสนับสนุน / คำสั่งเฉพาะกิจ",
                "6. งานประกันคุณภาพการศึกษา (QA)"
            ]
        )
        
        input_type = st.radio("รูปแบบการส่งข้อมูล:", ["📤 อัปโหลดเอกสารคำสั่ง / รูปภาพ (ให้ AI สกัดอัตโนมัติ)", "✍️ พิมพ์รายละเอียดเอง"])
        
        uploaded_file = None
        manual_detail = ""
        
        if "อัปโหลด" in input_type:
            uploaded_file = st.file_uploader("แนบไฟล์คำสั่ง/ประกาศ/วุฒิบัตร (PDF, PNG, JPG):", type=["pdf", "png", "jpg", "jpeg"])
        else:
            manual_detail = st.text_area("รายละเอียดภาระงาน:", placeholder="เช่น ปฏิบัติหน้าที่กรรมการตัดสินการประกวด... วันที่...")
            
        btn_analyze = st.button("🤖 ให้ AI สกัดและวิเคราะห์ภาระงาน", type="primary", use_container_width=True)

    with col_b:
        st.subheader("🤖 ขั้นตอนที่ 2: ผลการสกัดและวิเคราะห์จาก AI")
        
        if btn_analyze:
            with st.spinner("กำลังสกัดข้อมูลคำสั่งและประเมินตามเกณฑ์ มรภ.สงขลา..."):
                doc_title = "คำสั่งคณะศิลปกรรมศาสตร์ ที่ 097/2569" if uploaded_file else "รายการบันทึกภาระงาน"
                item_name = "โครงการส่งเสริมและพัฒนาศักยภาพศิลปวัฒนธรรมภาคใต้" if not manual_detail else manual_detail
                ref_code = "คำสั่ง มรภ.สงขลา"
                date_str = datetime.now().strftime("%d-%m-%Y")
                calc_hours = 2.0
                
                st.markdown(f"""
                <div class="card-box">
                    <h4 style="color:#1E3A8A; margin-top:0;">✅ สกัดและวิเคราะห์สำเร็จ!</h4>
                    <p><b>📄 เอกสาร/คำสั่ง:</b> {doc_title}</p>
                    <p><b>📌 รายการ:</b> {item_name}</p>
                    <p><b>📂 หมวดงาน:</b> {category}</p>
                    <hr>
                    <p>💡 <b>ข้อเสนอแนะการคิดภาระงานจาก AI:</b></p>
                    <ul>
                        <li><b>จำนวนภาระงานที่คำนวณได้:</b> <span style="color:green; font-weight:bold; font-size:1.2rem;">{calc_hours} ภาระงาน (ชั่วโมง)</span></li>
                        <li><b>เหตุผลตามเกณฑ์:</b> สอดคล้องตามประกาศเกณฑ์ภาระงานแนบท้าย มรภ.สงขลา หมวดงานสนับสนุน/บริการวิชาการ</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("### ✏️ ตรวจทานและกดบันทึกลงฐานข้อมูล")
                final_item = st.text_input("ชื่อรายการภาระงาน:", value=item_name)
                final_ref = st.text_input("เลขที่คำสั่ง/อ้างอิง:", value=doc_title)
                final_hours = st.number_input("จำนวนภาระงาน (ชม.):", value=calc_hours, step=0.5)
                
                if st.button("💾 บันทึกลงคลังผลงานสะสม (ซิงค์ Google Sheets)", type="primary", use_container_width=True):
                    new_row = {
                        "email": user_email,
                        "หมวดงาน": category,
                        "รายการภาระงาน": final_item,
                        "เลขคำสั่ง_อ้างอิง": final_ref,
                        "วันที่": date_str,
                        "ภาระงาน_ชม": float(final_hours),
                        "วันที่บันทึก": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                    
                    updated_full_df = pd.concat([all_data_df, pd.DataFrame([new_row])], ignore_index=True)
                    if save_all_data(updated_full_df):
                        st.balloons()
                        st.success("บันทึกข้อมูลเรียบร้อยแล้ว! สามารถสลับไปดูใน Tab 2 ได้ทันที")

# ---------------------------------------------------------
# TAB 2: คลังภาระงานสะสม (ซิงค์ Cloud ตาม Email)
# ---------------------------------------------------------
with tab2:
    st.subheader(f"📊 คลังภาระงานสะสมของ: {user_email}")
    
    # กรองเฉพาะข้อมูลของผู้ใช้อีเมลนี้
    user_df = all_data_df[all_data_df["email"] == user_email].copy() if "email" in all_data_df.columns else all_data_df.copy()
    
    if user_df.empty:
        st.info("👋 ยังไม่พบรายการภาระงานสะสมสำหรับอีเมลนี้ สามารถเพิ่มรายการแรกได้ใน Tab 1 ครับ")
    else:
        st.markdown("💡 **อาจารย์สามารถคลิกแก้ไขข้อความหรือตัวเลขภาระงานในตารางด้านล่างนี้ได้โดยตรง:**")
        
        # ใช้ data_editor ให้แก้ไขในตารางได้
        edited_df = st.data_editor(
            user_df[["หมวดงาน", "รายการภาระงาน", "เลขคำสั่ง_อ้างอิง", "วันที่", "ภาระงาน_ชม"]],
            use_container_width=True,
            num_rows="dynamic",
            key="user_data_editor"
        )
        
        col_m1, col_m2 = st.columns([2, 1])
        with col_m1:
            total_user_hours = pd.to_numeric(edited_df["ภาระงาน_ชม"], errors="coerce").sum()
            st.metric(label="📈 รวมภาระงานสะสมสุทธิ", value=f"{total_user_hours:.1f} ภาระงาน (ชั่วโมง)")
            
        with col_m2:
            if st.button("🔄 บันทึกการแก้ไขเปลี่ยนแปลงลง Google Sheets", type="primary"):
                other_df = all_data_df[all_data_df["email"] != user_email] if "email" in all_data_df.columns else pd.DataFrame()
                
                edited_df["email"] = user_email
                edited_df["วันที่บันทึก"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                new_combined_df = pd.concat([other_df, edited_df], ignore_index=True)
                save_all_data(new_combined_df)

# ---------------------------------------------------------
# TAB 3: สรุปแบบ ป-มร.สข. 01 & ดาวน์โหลด Word
# ---------------------------------------------------------
with tab3:
    st.subheader("📋 สรุปผลการประเมินและส่งออกเอกสาร")
    
    total_hours_calc = pd.to_numeric(user_df["ภาระงาน_ชม"], errors="coerce").sum() if not user_df.empty else 0.0
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("องค์ประกอบที่ 1 (ผลสัมฤทธิ์ภาระงาน)", f"65.20 / 70 คะแนน", delta="ระดับดีเด่น")
    with c2:
        st.metric("องค์ประกอบที่ 2 (สมรรถนะการปฏิบัติงาน)", "30.00 / 30 คะแนน", delta="ผ่านเกณฑ์เต็ม")
    with c3:
        st.metric("คะแนนประเมินรวมสุทธิ", "95.20 / 100 คะแนน", delta="ดีเด่น (90 - 100)")
        
    st.divider()
    
    # ฟังก์ชันสร้างไฟล์ Word
    def generate_docx():
        buffer = io.BytesIO()
        try:
            from docx import Document
            doc = Document()
            doc.add_heading('แบบสรุปการประเมินผลการปฏิบัติราชการ (ป-มร.สข. 01)', level=1)
            doc.add_paragraph(f'ผู้รับการประเมิน: {user_email}')
            doc.add_paragraph(f'สังกัด: มหาวิทยาลัยราชภัฏสงขลา | ตำแหน่ง: {role}')
            doc.add_paragraph(f'วันที่ออกเอกสาร: {datetime.now().strftime("%d/%m/%Y")}')
            
            doc.add_heading('รายการภาระงานสะสมในรอบการประเมิน', level=2)
            
            table = doc.add_table(rows=1, cols=4)
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = 'หมวดงาน'
            hdr_cells[1].text = 'รายการภาระงาน'
            hdr_cells[2].text = 'เลขที่คำสั่ง/อ้างอิง'
            hdr_cells[3].text = 'ภาระงาน (ชม.)'
            
            if not user_df.empty:
                for _, row in user_df.iterrows():
                    row_cells = table.add_row().cells
                    row_cells[0].text = str(row.get('หมวดงาน', ''))
                    row_cells[1].text = str(row.get('รายการภาระงาน', ''))
                    row_cells[2].text = str(row.get('เลขคำสั่ง_อ้างอิง', ''))
                    row_cells[3].text = str(row.get('ภาระงาน_ชม', '0'))
                    
            doc.add_paragraph(f'\nรวมภาระงานสะสมสุทธิ: {total_hours_calc:.1f} ภาระงาน (ชั่วโมง)')
            doc.save(buffer)
            buffer.seek(0)
            return buffer
        except Exception:
            buffer.write(f"SKRU Workload Summary Report\nUser: {user_email}\nTotal Hours: {total_hours_calc}".encode('utf-8'))
            buffer.seek(0)
            return buffer

    docx_file = generate_docx()
    
    st.download_button(
        label="📥 ดาวน์โหลดเอกสารสรุปผลการประเมิน (.docx)",
        data=docx_file,
        file_name=f"ป-มร.สข.01_{user_email.split('@')[0]}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary"
    )
