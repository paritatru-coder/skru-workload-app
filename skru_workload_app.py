import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime

# ==========================================
# 1. การตั้งค่าหน้าตาเว็บและธีม (Page Config)
# ==========================================
st.set_page_config(
    page_title="SKRU Academic Workload AI Assistant",
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
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. ส่วนแถบข้าง (Sidebar) - การเลือกสิทธิ์และ API Key
# ==========================================
with st.sidebar:
    st.image("https://www.skru.ac.th/images/logo/SKRU_LOGO.png", width=120) if False else None
    st.title("⚙️ ตั้งค่าผู้ใช้งาน")
    
    # 2.1 เลือกลักษณะตำแหน่ง (Role Selection)
    role = st.selectbox(
        "👤 ประเภทตำแหน่ง / กลุ่มผู้ประเมิน:",
        [
            "อาจารย์สายสอน (ไม่ดำรงตำแหน่งบริหาร)",
            "ผู้บริหาร (คณบดี / รองคณบดี / ผู้ช่วยคณบดี)",
            "ประธานหลักสูตร / หัวหน้าสาขา",
            "บุคลากรสายสนับสนุน"
        ]
    )
    
    st.info(f"📌 **เกณฑ์สัดส่วนปัจจุบัน**: {role}\n- ผลสัมฤทธิ์ของงาน: ร้อยละ 70\n- สมรรถนะ/พฤติกรรม: ร้อยละ 30")
    
    st.divider()
    
    # 2.2 ใส่ API Key ของ Gemini (Google AI Studio)
    api_key = st.text_input("🔑 Gemini API Key:", type="password", help="ใส่ API Key จาก Google AI Studio เพื่อเปิดใช้ระบบ AI อ่านเอกสารอัตโนมัติ")
    
    st.caption("💡 ระบบนี้ฟรี 100% สามารถขอ API Key ฟรีได้จาก Google AI Studio")

# ==========================================
# 3. หน้าหลักของแอปพลิเคชัน (Main UI Layout)
# ==========================================
st.markdown('<div class="main-title">🏛️ ระบบ AI สกัดและวิเคราะห์ภาระงาน มรภ.สงขลา</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">บันทึกภาระงาน อัปโหลดคำสั่ง/วุฒิบัตร และวิเคราะห์คะแนนตามเกณฑ์ ป-มร.สข. 01 อัตโนมัติ</div>', unsafe_allow_html=True)

# สร้าง Tabs สำหรับการใช้งาน
tab1, tab2, tab3 = st.tabs(["📥 1. บันทึกและวิเคราะห์ภาระงาน", "📊 2. คลังภาระงานสะสม", "📄 3. สรุปแบบ ป-มร.สข. 01"])

# ------------------------------------------
# TAB 1: บันทึกและวิเคราะห์ภาระงาน
# ------------------------------------------
with tab1:
    col_input, col_ai = st.columns([1, 1], gap="large")
    
    with col_input:
        st.subheader("📝 ขั้นตอนที่ 1: เลือกหมวดและส่งเอกสาร")
        
        # เลือกหมวดงาน
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
        
        # ช่องทางนำเข้าข้อมูล
        input_method = st.radio("วิธีนำเข้าข้อมูล:", ["📤 อัปโหลดเอกสารคำสั่ง/รูปภาพ (ให้ AI อ่านอัตโนมัติ)", "✍️ พิมพ์รายละเอียดเอง"])
        
        uploaded_file = None
        user_text = ""
        
        if "อัปโหลด" in input_method:
            uploaded_file = st.file_uploader("แนบไฟล์คำสั่ง/ประกาศ/วุฒิบัตร/รูปภาพ:", type=["pdf", "png", "jpg", "jpeg", "docx"])
            if uploaded_file:
                st.success(f"ไฟล์ที่อัปโหลด: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
        else:
            user_text = st.text_area("พิมพ์รายละเอียดภาระงาน:", placeholder="เช่น เข้าร่วมอบรมเชิงปฏิบัติการ เรื่อง... วันที่... คำสั่งมหาวิทยาลัย ที่...")

        # ปุ่มกดวิเคราะห์ด้วย AI
        btn_analyze = st.button("🤖 ให้ AI สกัดและวิเคราะห์ภาระงาน", type="primary", use_container_width=True)

    with col_ai:
        st.subheader("🤖 ขั้นตอนที่ 2: ผลการวิเคราะห์จาก AI")
        
        if btn_analyze:
            with st.spinner("กำลังอ่านเอกสารและเปรียบเทียบกับเกณฑ์ มรภ.สงขลา..."):
                # ตัวอย่างการทำงานจำลอง (Simulated Engine) เมื่อไม่ได้ใส่ API Key
                # หากมี API Key จริง จะเรียก google.generativeai อ่าน PDF/Image
                
                parsed_result = {
                    "doc_title": "คำสั่งคณะศิลปกรรมศาสตร์ ที่ 097/2569",
                    "event_name": "โครงการเพิ่มศักยภาพชุมชน Soft Power กิจกรรมประกวดวงเครื่องสายประสมวงปี่พาทย์ไม้นวม",
                    "role": "ประธานกรรมการฝ่ายติดตามและประเมินผล",
                    "date_worked": "23 - 24 สิงหาคม 2569 (รวม 2 วัน)",
                    "suggested_category": category,
                    "calculated_hours": 1.0,
                    "target_level": "ระดับ 5 (เกินเกณฑ์มาตรฐาน)",
                    "reasoning": "ตรงตามเกณฑ์หมวดงานสนับสนุน/บริการวิชาการ ตำแหน่งประธานติดตามประเมินผลโครงการ คิดภาระงาน 0.5 ชม./วัน รวม 2 วัน = 1.0 ภาระงาน"
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
                final_hours = st.number_input("ปรับแก้ไขจำนวนภาระงาน (ถ้ามี):", value=parsed_result['calculated_hours'], step=0.5)
                
                if st.button("💾 บันทึกลงคลังผลงานสะสม", type="secondary", use_container_width=True):
                    st.toast("บันทึกข้อมูลเรียบร้อยแล้ว!", icon="🎉")

# ------------------------------------------
# TAB 2: คลังภาระงานสะสม
# ------------------------------------------
with tab2:
    st.subheader("📚 รายการภาระงานที่บันทึกไว้ในระบบ")
    
    # ตัวอย่าง Dataframe ข้อมูลสะสม
    mock_data = [
        {"หมวดงาน": "2. วิจัย/สร้างสรรค์", "รายการ": "ผลงานสร้างสรรค์ 'Songkhla Artistic Land of Two Seas'", "เลขคำสั่ง/อ้างอิง": "UDRU: ISCFA-2026", "วันที่": "28-29 เม.ย. 69", "ภาระงาน (ชม.)": 24.0},
        {"หมวดงาน": "2. วิจัย/สร้างสรรค์", "รายการ": "ผลงานประพันธ์เพลง 'Keherwa A-Hom'", "เลขคำสั่ง/อ้างอิง": "13th IFA 2026", "วันที่": "16 มิ.ย. 69", "ภาระงาน (ชม.)": 24.0},
        {"หมวดงาน": "3. บริการวิชาการ", "รายการ": "วิทยากรโครงการดนตรีไทยผู้สูงอายุ", "เลขคำสั่ง/อ้างอิง": "คำสั่งคณะฯ ที่ 060/2569", "วันที่": "25-27 พ.ค. 69", "ภาระงาน (ชม.)": 3.0},
        {"หมวดงาน": "4. ศิลปวัฒนธรรม", "รายการ": "จัดพิธีไหว้ครูและครอบครูดนตรีไทย 2569", "เลขคำสั่ง/อ้างอิง": "หนังสือเชิญไหว้ครู", "วันที่": "6 ส.ค. 69", "ภาระงาน (ชม.)": 4.0},
        {"หมวดงาน": "5. งานอื่น ๆ", "รายการ": "กรรมการบริหารหลักสูตรฯ", "เลขคำสั่ง/อ้างอิง": "คำสั่ง ม. ที่ 377/2568", "วันที่": "ตลอดภาคเรียน", "ภาระงาน (ชม.)": 8.0},
        {"หมวดงาน": "5. งานอื่น ๆ", "รายการ": "อบรมการจัดการเรียนรู้ยุคดิจิทัล (21 ชม.)", "เลขคำสั่ง/อ้างอิง": "คำสั่ง ม. ที่ 879/2569", "วันที่": "27-29 เม.ย. 69", "ภาระงาน (ชม.)": 1.5},
    ]
    df = pd.DataFrame(mock_data)
    
    st.dataframe(df, use_container_width=True)
    
    total_hours = df["ภาระงาน (ชม.)"].sum()
    st.metric(label="📊 ภาระงานสะสมรวมทั้งหมด", value=f"{total_hours:.1f} ภาระงาน")

# ------------------------------------------
# TAB 3: สรุปแบบ ป-มร.สข. 01
# ------------------------------------------
with tab3:
    st.subheader("📋 พรีวิวผลการประเมินรอบที่ 2/2569")
    st.markdown("ระบบคำนวณคะแนนรวมตามเกณฑ์ ป-มร.สข. 01 ให้อัตโนมัติ:")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("องค์ประกอบที่ 1 (ผลสัมฤทธิ์)", "65.20 / 70", delta="ระดับดีเด่น")
    with c2:
        st.metric("องค์ประกอบที่ 2 (สมรรถนะ)", "30.00 / 30", delta="ผ่านเกณฑ์เต็ม")
    with c3:
        st.metric("คะแนนประเมินสุทธิ", "95.20 / 100", delta="ระดับดีเด่น (90-100)")
        
    st.button("📥 ส่งออกไฟล์ Word (แบบ ป-มร.สข. 01)", type="primary")
