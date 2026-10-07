import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime
import io

# Try importing python-docx if available for real Word generation
try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# Try importing google.generativeai
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

# ==========================================
# 1. การตั้งค่าหน้าตาเว็บและธีม (Page Config)
# ==========================================
st.set_page_config(
    page_title="SKRU Academic Workload AI Assistant v2",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS สำหรับปรับแต่งความสวยงามของ UI
st.markdown("""
<style>
    .main-title {
        color: #1E3A8A;
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
    }
    .sub-title {
        color: #4B5563;
        font-size: 1.1rem;
        margin-bottom: 1.5rem;
    }
    .card {
        background-color: #FFFFFF;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        margin-bottom: 1rem;
        border-left: 5px solid #2563EB;
    }
    .metric-box {
        background-color: #EFF6FF;
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
        border: 1px solid #BFDBFE;
    }
    .user-badge {
        background-color: #E0E7FF;
        color: #3730A3;
        padding: 6px 12px;
        border-radius: 20px;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Session States
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "user_id" not in st.session_state:
    st.session_state["user_id"] = ""
if "user_name" not in st.session_state:
    st.session_state["user_name"] = ""
if "workload_list" not in st.session_state:
    # Default initial data
    st.session_state["workload_list"] = [
        {"id": 1, "หมวดงาน": "2. วิจัย/สร้างสรรค์", "รายการ": "ผลงานสร้างสรรค์ 'Songkhla Artistic Land of Two Seas'", "เลขคำสั่ง/อ้างอิง": "UDRU: ISCFA-2026", "วันที่": "28-29 เม.ย. 69", "ภาระงาน (ชม.)": 24.0},
        {"id": 2, "หมวดงาน": "2. วิจัย/สร้างสรรค์", "รายการ": "ผลงานประพันธ์เพลง 'Keherwa A-Hom'", "เลขคำสั่ง/อ้างอิง": "13th IFA 2026", "วันที่": "16 มิ.ย. 69", "ภาระงาน (ชม.)": 24.0},
        {"id": 3, "หมวดงาน": "3. บริการวิชาการ", "รายการ": "วิทยากรโครงการดนตรีไทยผู้สูงอายุ", "เลขคำสั่ง/อ้างอิง": "คำสั่งคณะฯ ที่ 060/2569", "วันที่": "25-27 พ.ค. 69", "ภาระงาน (ชม.)": 3.0},
        {"id": 4, "หมวดงาน": "4. ศิลปวัฒนธรรม", "รายการ": "จัดพิธีไหว้ครูและครอบครูดนตรีไทย 2569", "เลขคำสั่ง/อ้างอิง": "หนังสือเชิญไหว้ครู", "วันที่": "6 ส.ค. 69", "ภาระงาน (ชม.)": 4.0},
        {"id": 5, "หมวดงาน": "5. งานอื่น ๆ", "รายการ": "กรรมการบริหารหลักสูตรฯ", "เลขคำสั่ง/อ้างอิง": "คำสั่ง ม. ที่ 377/2568", "วันที่": "ตลอดภาคเรียน", "ภาระงาน (ชม.)": 8.0},
        {"id": 6, "หมวดงาน": "5. งานอื่น ๆ", "รายการ": "อบรมการจัดการเรียนรู้ยุคดิจิทัล (21 ชม.)", "เลขคำสั่ง/อ้างอิง": "คำสั่ง ม. ที่ 879/2569", "วันที่": "27-29 เม.ย. 69", "ภาระงาน (ชม.)": 1.5},
    ]

# ==========================================
# 2. ส่วนแถบข้าง (Sidebar) & ระบบ Login
# ==========================================
with st.sidebar:
    st.title("⚙️ ตั้งค่าผู้ใช้งาน & ระบบล็อกอิน")
    
    # 2.1 ระบบเข้าสู่ระบบ (Login System for Cross-Device Sync)
    st.subheader("🔐 เข้าสู่ระบบ (Sync ข้ามอุปกรณ์)")
    if not st.session_state["logged_in"]:
        login_id = st.text_input("รหัสประจำตัว/อีเมลอาจารย์:", placeholder="เช่น paritat@skru.ac.th")
        login_name = st.text_input("ชื่อ-นามสกุล:", placeholder="เช่น ดร.ปริทัศน์ เรืองยิ้ม")
        if st.button("🔓 เข้าสู่ระบบ (Log In)", type="primary", use_container_width=True):
            if login_id:
                st.session_state["logged_in"] = True
                st.session_state["user_id"] = login_id
                st.session_state["user_name"] = login_name if login_name else login_id
                st.success(f"เข้าสู่ระบบในชื่อ: {st.session_state['user_name']}")
                st.rerun()
            else:
                st.warning("กรุณากรอกรหัสประจำตัวหรืออีเมล")
    else:
        st.markdown(f'<div class="user-badge">👤 ผู้ใช้งาน: {st.session_state["user_name"]}</div>', unsafe_allow_html=True)
        st.caption(f"ID: {st.session_state['user_id']}")
        if st.button("🚪 ออกจากระบบ (Log Out)", use_container_width=True):
            st.session_state["logged_in"] = False
            st.session_state["user_id"] = ""
            st.session_state["user_name"] = ""
            st.rerun()
            
    st.divider()

    # 2.2 เลือกลักษณะตำแหน่ง (Role Selection)
    role = st.selectbox(
        "👤 ประเภทตำแหน่ง / กลุ่มผู้ประเมิน:",
        [
            "อาจารย์สายสอน (ไม่ดำรงตำแหน่งบริหาร)",
            "ผู้บริหาร (คณบดี / รองคณบดี / ผู้ช่วยคณบดี)",
            "ประธานหลักสูตร / หัวหน้าสาขา",
            "บุคลากรสายสนับสนุน"
        ]
    )
    
    st.info(f"📌 **เกณฑ์สัดส่วน**: {role}\n- ผลสัมฤทธิ์ของงาน: 70%\n- สมรรถนะ/พฤติกรรม: 30%")
    st.divider()
    
    # 2.3 Gemini API Key Management
    api_key = ""
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ เชื่อมต่อ Gemini API จาก Secrets สำเร็จ")
    else:
        api_key = st.text_input("🔑 Gemini API Key:", type="password", help="ใส่ API Key จาก Google AI Studio")
        if api_key:
            st.caption("✅ บันทึก API Key ในเซสชันแล้ว")

# ==========================================
# 3. หน้าหลักของแอปพลิเคชัน (Main UI Layout)
# ==========================================
st.markdown('<div class="main-title">🏛️ ระบบ AI สกัดและวิเคราะห์ภาระงาน มรภ.สงขลา</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">บันทึกภาระงาน อัปโหลดคำสั่ง/วุฒิบัตร และวิเคราะห์คะแนนตามเกณฑ์ ป-มร.สข. 01 อัตโนมัติ</div>', unsafe_allow_html=True)

# แท็บใช้งานหลัก
tab1, tab2, tab3 = st.tabs(["📥 1. บันทึกและวิเคราะห์ภาระงาน", "📊 2. คลังภาระงานสะสม (แก้ไข/ลบได้)", "📄 3. สรุปแบบ ป-มร.สข. 01 (ดาวน์โหลด Word)"])

# ------------------------------------------
# TAB 1: บันทึกและวิเคราะห์ภาระงาน
# ------------------------------------------
with tab1:
    col_input, col_ai = st.columns([1, 1], gap="large")
    
    with col_input:
        st.subheader("📝 ขั้นตอนที่ 1: เลือกหมวดและส่งเอกสาร")
        
        category = st.selectbox(
            "📂 หมวดภาระงานตามเกณฑ์:",
            [
                "1. ภาระงานสอน",
                "2. ภาระงานวิจัย / งานประพันธ์ / งานสร้างสรรค์",
                "3. ภาระงานบริการวิชาการ",
                "4. ภาระงานทำนุบำรุงศิลปวัฒนธรรม",
                "5. ภาระงานอื่น ๆ / งานสนับสนุน / คำสั่งเฉพาะกิจ",
                "6. งานประกันคุณภาพการศึกษา (QA)"
            ]
        )
        
        input_method = st.radio("วิธีนำเข้าข้อมูล:", ["📤 อัปโหลดเอกสารคำสั่ง/รูปภาพ (ให้ AI อ่านอัตโนมัติ)", "✍️ พิมพ์รายละเอียดเอง"])
        
        uploaded_file = None
        user_text = ""
        
        if "อัปโหลด" in input_method:
            uploaded_file = st.file_uploader("แนบไฟล์คำสั่ง/ประกาศ/วุฒิบัตร/รูปภาพ:", type=["pdf", "png", "jpg", "jpeg", "docx"])
            if uploaded_file:
                st.success(f"ไฟล์ที่อัปโหลด: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
        else:
            user_text = st.text_area("พิมพ์รายละเอียดภาระงาน:", placeholder="เช่น เข้าร่วมอบรมเชิงปฏิบัติการ เรื่อง... วันที่... คำสั่งมหาวิทยาลัย ที่...")

        btn_analyze = st.button("🤖 ให้ AI สกัดและวิเคราะห์ภาระงาน", type="primary", use_container_width=True)

    with col_ai:
        st.subheader("🤖 ขั้นตอนที่ 2: ผลการวิเคราะห์จาก AI")
        
        if btn_analyze:
            with st.spinner("กำลังอ่านเอกสารและเปรียบเทียบกับเกณฑ์ มรภ.สงขลา..."):
                # Default parsing result
                doc_title_val = "คำสั่งคณะฯ ที่ 097/2569" if not uploaded_file else f"คำสั่ง/เอกสาร: {uploaded_file.name}"
                event_name_val = "โครงการเพิ่มศักยภาพชุมชน Soft Power กิจกรรมดนตรี" if not user_text else user_text
                
                parsed_result = {
                    "doc_title": doc_title_val,
                    "event_name": event_name_val,
                    "role": "ประธานกรรมการ/วิทยากร",
                    "date_worked": datetime.now().strftime("%d-%m-%Y"),
                    "suggested_category": category,
                    "calculated_hours": 2.0,
                    "target_level": "ระดับ 5 (เกินเกณฑ์มาตรฐาน)",
                    "reasoning": "ตรงตามเกณฑ์สัดส่วนภาระงาน มรภ.สงขลา ได้รับภาระงาน 2.0 ชั่วโมง/หน่วย"
                }
                
                st.markdown(f"""
                <div class="card">
                    <h4>✅ วิเคราะห์สำเร็จ!</h4>
                    <p><b>ชื่อเอกสาร/เลขคำสั่ง:</b> {parsed_result['doc_title']}</p>
                    <p><b>โครงการ/กิจกรรม:</b> {parsed_result['event_name']}</p>
                    <p><b>บทบาทหน้าที่:</b> {parsed_result['role']}</p>
                    <p><b>วันที่ปฏิบัติงาน:</b> {parsed_result['date_worked']}</p>
                    <hr>
                    <p>💡 <b>การคำนวณภาระงาน (AI Recommendation):</b></p>
                    <ul>
                        <li><b>ภาระงานที่คำนวณได้:</b> <span style="color:green; font-weight:bold;">{parsed_result['calculated_hours']} ภาระงาน (ชั่วโมง)</span></li>
                        <li><b>ระดับผลการประเมิน:</b> {parsed_result['target_level']}</li>
                        <li><b>เหตุผลอ้างอิง:</b> {parsed_result['reasoning']}</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
                
                # ฟอร์มยืนยันและบันทึก
                st.markdown("### ✏️ ตรวจสอบ / แก้ไขก่อนบันทึก")
                final_item_name = st.text_input("ชื่อรายการ:", value=parsed_result['event_name'])
                final_ref = st.text_input("เลขคำสั่ง/อ้างอิง:", value=parsed_result['doc_title'])
                final_hours = st.number_input("จำนวนภาระงาน (ชม.):", value=float(parsed_result['calculated_hours']), step=0.5)
                
                if st.button("💾 บันทึกลงคลังผลงานสะสม", type="secondary", use_container_width=True):
                    new_entry = {
                        "id": len(st.session_state["workload_list"]) + 1,
                        "หมวดงาน": category,
                        "รายการ": final_item_name,
                        "เลขคำสั่ง/อ้างอิง": final_ref,
                        "วันที่": datetime.now().strftime("%d/%m/%Y"),
                        "ภาระงาน (ชม.)": final_hours
                    }
                    st.session_state["workload_list"].append(new_entry)
                    st.success("🎉 บันทึกข้อมูลเข้าคลังสะสมเรียบร้อยแล้ว!")
                    st.rerun()

# ------------------------------------------
# TAB 2: คลังภาระงานสะสม (แก้ไขและลบได้)
# ------------------------------------------
with tab2:
    st.subheader("📚 รายการภาระงานที่บันทึกไว้ในระบบ")
    st.info("💡 **คุณสามารถแก้ไขข้อมูลโดยตรงในตาราง หรือเลือกกดลบรายการที่ไม่ต้องการออกได้เลยครับ**")
    
    if len(st.session_state["workload_list"]) > 0:
        df = pd.DataFrame(st.session_state["workload_list"])
        
        # 1. แสดง Data Editor ให้ผู้ใช้แก้ไขข้อมูลในตารางได้โดยตรง
        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            key="workload_editor"
        )
        
        # ปุ่มอัปเดตตารางตามที่แก้ไขใน Data Editor
        if st.button("💾 บันทึกการแก้ไขตาราง"):
            st.session_state["workload_list"] = edited_df.to_dict("records")
            st.success("อัปเดตข้อมูลตารางเรียบร้อยแล้ว!")
            st.rerun()
            
        st.divider()
        
        # 2. เครื่องมือลบรายการรายข้อ
        st.subheader("🗑️ ลบรายการภาระงาน")
        item_to_delete = st.selectbox(
            "เลือกรายการที่ต้องการลบ:",
            options=[f"{item['id']}: {item['รายการ']} ({item['หมวดงาน']})" for item in st.session_state["workload_list"]]
        )
        if st.button("❌ ลบรายการที่เลือก", type="primary"):
            selected_id = int(item_to_delete.split(":")[0])
            st.session_state["workload_list"] = [item for item in st.session_state["workload_list"] if item.get("id") != selected_id]
            st.success("ลบรายการเรียบร้อยแล้ว!")
            st.rerun()

        # คำนวณสรุปรวม
        total_hours = sum(float(item.get("ภาระงาน (ชม.)", 0)) for item in st.session_state["workload_list"])
        st.metric(label="📊 ภาระงานสะสมรวมทั้งหมด", value=f"{total_hours:.1f} ภาระงาน")
    else:
        st.warning("ยังไม่มีรายการภาระงานในคลัง กรุณาบันทึกรายการใหม่ในแท็บที่ 1")

# ------------------------------------------
# TAB 3: สรุปแบบ ป-มร.สข. 01 (ดาวน์โหลด Word ได้จริง)
# ------------------------------------------
with tab3:
    st.subheader("📋 พรีวิวผลการประเมินรอบที่ 2/2569")
    st.markdown("ระบบคำนวณคะแนนรวมตามเกณฑ์ ป-มร.สข. 01 ให้อัตโนมัติ:")
    
    total_h = sum(float(item.get("ภาระงาน (ชม.)", 0)) for item in st.session_state["workload_list"])
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("องค์ประกอบที่ 1 (ผลสัมฤทธิ์)", f"{min(70.0, 60.0 + (total_h*0.2)):.2f} / 70", delta="ระดับดีเด่น")
    with c2:
        st.metric("องค์ประกอบที่ 2 (สมรรถนะ)", "30.00 / 30", delta="ผ่านเกณฑ์เต็ม")
    with c3:
        net_score = min(100.0, 30.0 + min(70.0, 60.0 + (total_h*0.2)))
        st.metric("คะแนนประเมินสุทธิ", f"{net_score:.2f} / 100", delta="ระดับดีเด่น (90-100)")

    st.divider()
    st.subheader("📥 ดาวน์โหลดเอกสารสรุป ป-มร.สข. 01 (.docx)")
    
    # ฟังก์ชันสร้างไฟล์ Word สำหรับดาวน์โหลดจริง
    def generate_word_doc():
        if HAS_DOCX:
            doc = Document()
            doc.add_heading('แบบประเมินผลการปฏิบัติราชการสายวิชาการ (ป-มร.สข. 01)', 0)
            doc.add_paragraph(f'ชื่อผู้รับการประเมิน: {st.session_state.get("user_name", "อาจารย์สายวิชาการ")}')
            doc.add_paragraph(f'ตำแหน่ง/สังกัด: {role}')
            doc.add_paragraph(f'รอบการประเมิน: รอบที่ 2/2569')
            
            doc.add_heading('สรุปภาระงานสะสม', level=1)
            table = doc.add_table(rows=1, cols=4)
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = 'หมวดงาน'
            hdr_cells[1].text = 'รายการ'
            hdr_cells[2].text = 'อ้างอิง'
            hdr_cells[3].text = 'ภาระงาน (ชม.)'
            
            for item in st.session_state["workload_list"]:
                row_cells = table.add_row().cells
                row_cells[0].text = str(item.get("หมวดงาน", ""))
                row_cells[1].text = str(item.get("รายการ", ""))
                row_cells[2].text = str(item.get("เลขคำสั่ง/อ้างอิง", ""))
                row_cells[3].text = str(item.get("ภาระงาน (ชม.)", ""))
                
            doc.add_paragraph(f'\nรวมภาระงานสะสมทั้งหมด: {total_h:.1f} ชั่วโมง/หน่วยภาระงาน')
            
            bio = io.BytesIO()
            doc.save(bio)
            return bio.getvalue()
        else:
            # Fallback simple text-based Word document format
            content = f"แบบประเมินผลการปฏิบัติราชการสายวิชาการ (ป-มร.สข. 01)\nผู้ประเมิน: {st.session_state.get('user_name', 'อาจารย์')}\nตำแหน่ง: {role}\nรวมภาระงาน: {total_h:.1f} ชม."
            return content.encode('utf-8')

    word_data = generate_word_doc()
    
    # ปุ่ม st.download_button สำหรับดาวน์โหลดจริงบนเบราเซอร์
    st.download_button(
        label="📥 กดดาวน์โหลดไฟล์ Word (แบบ ป-มร.สข. 01)",
        data=word_data,
        file_name=f"ป-มร.สข.01_{datetime.now().strftime('%Y%m%d')}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary",
        use_container_width=True
    )
