import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import io

# ---------------------------------------------------------
# 1. Page Config & Custom Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="SKRU Workload AI - ระบบบันทึกและวิเคราะห์ภาระงาน มรภ.สงขลา (v10)",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        margin-bottom: 1.2rem;
    }
    .card-box {
        background-color: #FFFFFF;
        padding: 1.25rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08);
        border-left: 5px solid #2563EB;
        margin-bottom: 1rem;
    }
    .success-alert {
        background-color: #DCFCE7;
        border: 2px solid #22C55E;
        color: #15803D;
        padding: 1rem;
        border-radius: 8px;
        font-weight: bold;
        font-size: 1.15rem;
        margin-bottom: 1rem;
    }
    .info-alert {
        background-color: #EFF6FF;
        border: 1px solid #93C5FD;
        color: #1E40AF;
        padding: 0.8rem;
        border-radius: 8px;
        margin-bottom: 1rem;
    }
    .formatted-preview {
        background-color: #F0F9FF;
        border: 1px solid #BAE6FD;
        border-radius: 8px;
        padding: 1rem;
        font-family: 'Sarabun', sans-serif;
        color: #0369A1;
        font-weight: 500;
        margin-top: 0.5rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. Database Manager (Google Sheets / Local Session)
# ---------------------------------------------------------
conn = None
use_gsheets = False

try:
    from streamlit_gsheets import GSheetsConnection
    if hasattr(st, "secrets") and "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        conn = st.connection("gsheets", type=GSheetsConnection)
        use_gsheets = True
except Exception:
    use_gsheets = False

def load_all_data():
    if use_gsheets and conn:
        try:
            df = conn.read(ttl="0")
            if df is not None and not df.empty:
                df["ภาระงาน_ชม"] = pd.to_numeric(df["ภาระงาน_ชม"], errors="coerce").fillna(0.0)
                return df
        except Exception:
            pass
    
    if "local_db" not in st.session_state:
        st.session_state["local_db"] = pd.DataFrame(columns=[
            "email", "หมวดงาน", "รายการภาระงาน", "เลขคำสั่ง_อ้างอิง", "วันที่", "ภาระงาน_ชม", "วันที่บันทึก"
        ])
    return st.session_state["local_db"]

def save_all_data(full_df):
    if use_gsheets and conn:
        try:
            conn.update(data=full_df)
            st.session_state["local_db"] = full_df
            return True, "Google Sheets"
        except Exception as e:
            st.session_state["local_db"] = full_df
            return False, str(e)
    else:
        st.session_state["local_db"] = full_df
        return True, "Local Session"

# ---------------------------------------------------------
# 3. Sidebar Configuration
# ---------------------------------------------------------
with st.sidebar:
    st.title("👤 ระบุตัวตน & ตั้งค่า")
    
    user_email = st.text_input(
        "📧 อีเมลบุคลากร (สำหรับซิงค์ข้อมูล):",
        value=st.session_state.get("user_email_saved", ""),
        placeholder="เช่น instructor@skru.ac.th",
        help="กรอกอีเมลบุคลากรของคุณ เพื่อซิงค์คลังภาระงานส่วนตัวจากมือถือ คอมพิวเตอร์บ้าน และที่ทำงาน",
        key="sidebar_email_input"
    )
    if user_email:
        st.session_state["user_email_saved"] = user_email.strip()
    
    track_type = st.selectbox(
        "🎯 กลุ่มการประเมินสายวิชาการ:",
        ["กลุ่มเน้นการสอน (สอน 30%, วิจัย 15-20%, บริการ 8-15%, ศิลปะ 2-5%, อื่นๆ 5-15%, QA 1%)",
         "กลุ่มเน้นการวิจัย (สอน 25%, วิจัย 15-25%, บริการ 8-15%, ศิลปะ 2-5%, อื่นๆ 5-15%, QA 1%)"]
    )
    
    role = st.selectbox(
        "🏛️ ตำแหน่งบริหาร/วิชาการ:",
        [
            "อาจารย์สายสอน (ไม่ดำรงตำแหน่งบริหาร)",
            "ประธานหลักสูตร / หัวหน้าสาขา (15 ภาระงาน)",
            "เลขานุการหลักสูตร (10 ภาระงาน)",
            "ผู้ช่วยอธิการบดี / รองคณบดี (25 ภาระงาน)",
            "คณบดี / หัวหน้าหน่วยงาน (30 ภาระงาน)"
        ]
    )
    
    st.divider()
    
    api_key_env = ""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key_env = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
        
    user_api_key = st.text_input("🔑 Gemini API Key (ถ้าระบุเอง):", type="password", value=api_key_env)
    active_api_key = user_api_key if user_api_key else api_key_env

    st.markdown("### ☁️ สถานะการเชื่อมต่อ")
    if use_gsheets:
        st.success("🟢 เชื่อมต่อ Google Sheets สำเร็จ", icon="☁️")
    else:
        st.info("🟡 โหมดบันทึกในระบบส่วนบุคคล (Local Session)", icon="💾")

    with st.expander("🧪 ทดสอบระบบ Google Sheets"):
        if st.button("กดทดสอบอ่าน-เขียน Google Sheets"):
            if use_gsheets and conn:
                try:
                    test_df = conn.read(ttl="0")
                    st.success("✅ อ่าน Google Sheets สำเร็จ! พบข้อมูลทั้งหมด " + str(len(test_df)) + " แถว")
                except Exception as ex:
                    st.error(f"❌ ไม่สามารถเชื่อมต่อได้: {ex}")
            else:
                st.warning("ยังไม่ได้เปิดใช้ Google Sheets ใน Secrets")

# ---------------------------------------------------------
# 4. Main Interface & Tabs
# ---------------------------------------------------------
st.markdown('<div class="main-header">🏛️ SKRU Academic Workload AI Assistant (v10 - Multimodal Gemini AI)</div>', unsafe_allow_html=True)
effective_email = user_email.strip() if user_email and user_email.strip() != "" else "guest@skru.ac.th"
st.markdown(f'<div class="sub-header">ระบบช่วยสกัด อ่านเอกสารจริงด้วย Gemini AI เรียบเรียงภาษาทางการ และประเมินภาระงานตามเกณฑ์ มรภ.สงขลา (มติกช.) | ผู้ใช้: <b>{effective_email}</b></div>', unsafe_allow_html=True)

# แสดงข้อความแจ้งเตือนเมื่อบันทึกสำเร็จ
if st.session_state.get("show_saved_success"):
    st.markdown("""
    <div class="success-alert">
        🎉 บันทึกข้อมูลเข้าคลังภาระงานสะสมเรียบร้อยแล้ว! สามารถสลับไปดูตารางใน Tab 2 หรือดาวน์โหลดไฟล์ Word ใน Tab 3 ได้ทันที
    </div>
    """, unsafe_allow_html=True)
    st.session_state["show_saved_success"] = False

tab1, tab2, tab3 = st.tabs(["📥 1. สกัดและเรียบเรียงภาระงาน (Gemini AI)", "📊 2. คลังภาระงานสะสม", "📄 3. สรุปแบบ ป-มร.สข. 01 (Word)"])

all_data_df = load_all_data()

# ---------------------------------------------------------
# TAB 1: บันทึก สกัด อ่าน PDF/ภาพ จริงด้วย Gemini AI
# ---------------------------------------------------------
with tab1:
    col_a, col_b = st.columns([1, 1], gap="large")
    
    with col_a:
        st.subheader("📝 ขั้นตอนที่ 1: ส่งไฟล์ PDF / ภาพคำสั่ง / พิมพ์ข้อความ")
        
        category_input = st.selectbox(
            "📂 เลือกหมวดภาระงานเบื้องต้น (หรือให้ AI ประเมินจากเอกสาร):",
            [
                "ให้ AI ประเมินหมวดงานจากเอกสารอัตโนมัติ",
                "1. ภาระงานสอน",
                "2. ภาระงานวิจัย / งานประพันธ์ / งานสร้างสรรค์",
                "3. ภาระงานบริการวิชาการ",
                "4. ภาระงานทำนุบำรุงศิลปวัฒนธรรม",
                "5. ภาระงานอื่น ๆ / งานสนับสนุน / คำสั่งเฉพาะกิจ",
                "6. งานประกันคุณภาพการศึกษา (QA)",
                "7. งานบริหาร / ตำแหน่งทางวิชาการ"
            ]
        )
        
        input_method = st.radio("เลือกวิธีป้อนข้อมูลให้ AI:", [
            "📤 อัปโหลดไฟล์เอกสาร/คำสั่ง/ผลงาน (PDF, PNG, JPG)",
            "📷 ถ่ายภาพคำสั่งจากกล้องมือถือ",
            "✍️ พิมพ์รายละเอียดภาระงานเอง"
        ])
        
        uploaded_file = None
        raw_text_input = ""
        
        if "อัปโหลด" in input_method:
            uploaded_file = st.file_uploader("แนบคำสั่ง/ประกาศ/ผลงานสร้างสรรค์/วุฒิบัตร (PDF, JPG, PNG):", type=["pdf", "png", "jpg", "jpeg", "webp"])
        elif "ถ่ายภาพ" in input_method:
            uploaded_file = st.camera_input("ถ่ายภาพคำสั่งจากกล้องมือถือ")
        else:
            raw_text_input = st.text_area("พิมพ์รายละเอียดภาระงานหรือข้อความในคำสั่ง:", placeholder="เช่น ผลงานประพันธ์เพลงสร้างสรรค์เรื่อง... เผยแพร่ระดับนานาชาติ...")

        btn_ai_process = st.button("🤖 ให้ Gemini AI อ่านเอกสารและวิเคราะห์ตามเกณฑ์ มรภ.สงขลา", type="primary", use_container_width=True)

    # เมื่อกดปุ่ม AI Process -> เรียก Gemini API อ่านเนื้อหาไฟล์ PDF / Image จริง
    if btn_ai_process:
        with st.spinner("กำลังส่งเนื้อหาไฟล์ให้ Gemini AI อ่าน OCR และวิเคราะห์ตามประกาศเกณฑ์ มรภ.สงขลา..."):
            
            ai_success = False
            ai_error_msg = ""
            
            # ตรวจสอบ API Key
            if not active_api_key or active_api_key.strip() == "":
                st.error("⚠️ ไม่พบ Gemini API Key! กรุณากรอก API Key ในเมนูด้านซ้าย หรือตั้งค่า GEMINI_API_KEY ใน Streamlit Secrets เพื่อเปิดใช้การอ่าน PDF/ภาพ แบบจริงครับ")
            else:
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=active_api_key.strip())
                    
                    # เลือกโมเดล Gemini
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    
                    prompt_instructions = """
                    คุณเป็น AI ผู้เชี่ยวชาญการตรวจประเมินภาระงานสายวิชาการของ มหาวิทยาลัยราชภัฏสงขลา (มรภ.สงขลา)
                    โปรดอ่าน สกัดข้อความ OCR และวิเคราะห์เนื้อหาจากเอกสาร/ภาพ/ข้อความที่แนบมานี้อย่างละเอียด
                    
                    เกณฑ์การคำนวณชั่วโมงภาระงานของ มรภ.สงขลา (มติกช.):
                    1. งานวิจัย/งานสร้างสรรค์:
                       - งานสร้างสรรค์เผยแพร่นานาชาติ มีรางวัล = 24 ชม. | ไม่ได้รับรางวัล = 21 ชม.
                       - งานสร้างสรรค์เผยแพร่อาเซียน มีรางวัล = 18 ชม. | ไม่ได้รับรางวัล = 15 ชม.
                       - งานสร้างสรรค์ระดับชาติ มีรางวัล = 10 ชม. | ไม่ได้รับรางวัล = 5 ชม.
                       - บทความวารสาร TCI กลุ่ม 1 = 19 ชม. | TCI กลุ่ม 2 = 15 ชม.
                       - Proceedings นานาชาติ = 12 ชม. | ระดับชาติ = 10 ชม.
                    2. บริการวิชาการ: วิทยากร (3ชมxวันx0.5 สำหรับครึ่งวัน หรือ 6ชมxวันx0.5 สำหรับทั้งวัน), ผู้รับผิดชอบหลัก = 5 ชม., ประธาน = 2 ชม., เลขา = 1.5 ชม., กรรมการ = 1 ชม.
                    3. ทำนุบำรุงศิลปวัฒนธรรม: ประธาน/ผู้จัด = 1 ชม./วัน, กรรมการ = 0.5 ชม./วัน, แสดง/บรรเลง = 0.5 ชม./ครั้ง
                    4. งานบริหาร: ประธานหลักสูตร = 15 ชม., เลขานุการหลักสูตร = 10 ชม., คณบดี = 30 ชม., รองคณบดี = 25 ชม.

                    โปรดตอบกลับเป็น JSON ภาษาไทยเท่านั้นในรูปแบบต่อไปนี้ (อย่าใส่ข้อความอื่นนอกเหนือจาก JSON):
                    {
                      "category": "หมวดงาน (เลือก 1 จาก: 1. ภาระงานสอน, 2. ภาระงานวิจัย / งานประพันธ์ / งานสร้างสรรค์, 3. ภาระงานบริการวิชาการ, 4. ภาระงานทำนุบำรุงศิลปวัฒนธรรม, 5. ภาระงานอื่น ๆ / งานสนับสนุน / คำสั่งเฉพาะกิจ, 6. งานประกันคุณภาพการศึกษา (QA), 7. งานบริหาร / ตำแหน่งทางวิชาการ)",
                      "title": "ชื่อบทบาท / ชื่อผลงานวิชาการ / ชื่อผลงานสร้างสรรค์ / ชื่อโครงการ (ห้ามนำชื่อไฟล์ .pdf มาใส่เด็ดขาด ให้ดึงชื่อจริงจากเนื้อหา)",
                      "venue": "สถานที่จัด / ชื่อวารสาร / เวทีแสดง / หน่วยงานผู้จัด",
                      "date": "วันที่ปฏิบัติงาน หรือ วัน/เดือน/ปี ที่เผยแพร่ (เช่น ระหว่างวันที่ 10-12 สิงหาคม 2569)",
                      "ref": "เลขที่คำสั่ง / เลขฉบับวารสาร / หนังสืออ้างอิงจริงในเอกสาร",
                      "formula": "สูตรการคำนวณในวงเล็บตามเกณฑ์ มรภ.สงขลา (เช่น (นับสิทธิ์เผยแพร่นานาชาติ ไม่ได้รับรางวัล = 21 ภาระงาน) หรือ (3ชมx5วันx0.5))",
                      "hours": 21.0,
                      "formal_text": "ข้อความภาษาทางการฉบับเต็มสมบูรณ์ที่จะนำไปวางในตาราง แบบ ป-มร.สข. 01"
                    }
                    """

                    contents_payload = []
                    
                    if uploaded_file is not None:
                        file_bytes = uploaded_file.getvalue()
                        mime_type = uploaded_file.type if uploaded_file.type else "application/pdf"
                        
                        # รองรับ PDF / Images
                        contents_payload.append({"mime_type": mime_type, "data": file_bytes})
                        contents_payload.append(f"หมวดงานที่ผู้ใช้ระบุเบื้องต้น: {category_input}\n{prompt_instructions}")
                    elif raw_text_input.strip() != "":
                        contents_payload.append(f"ข้อความรายละเอียดภาระงาน:\n{raw_text_input}\n\nหมวดงานที่เลือก: {category_input}\n{prompt_instructions}")
                    else:
                        st.warning("⚠️ กรุณาอัปโหลดไฟล์ ถ่ายภาพ หรือพิมพ์ข้อความรายละเอียดก่อนกดปุ่ม AI Process ครับ")

                    if contents_payload:
                        response = model.generate_content(contents_payload)
                        res_text = response.text.strip()
                        
                        # ทำความสะอาด JSON string
                        if res_text.startswith("```json"):
                            res_text = res_text.split("```json")[1].split("```")[0].strip()
                        elif res_text.startswith("```"):
                            res_text = res_text.split("```")[1].split("```")[0].strip()
                            
                        parsed_json = json.loads(res_text)
                        
                        st.session_state["edit_cat"] = parsed_json.get("category", "2. ภาระงานวิจัย / งานประพันธ์ / งานสร้างสรรค์")
                        st.session_state["edit_title"] = parsed_json.get("title", "ผลงานสร้างสรรค์")
                        st.session_state["edit_venue"] = parsed_json.get("venue", "ณ มหาวิทยาลัยราชภัฏสงขลา")
                        st.session_state["edit_date"] = parsed_json.get("date", datetime.now().strftime("%d-%m-%Y"))
                        st.session_state["edit_ref"] = parsed_json.get("ref", "คำสั่ง มรภ.สงขลา")
                        st.session_state["edit_formula"] = parsed_json.get("formula", "(= 1.0 ชม.)")
                        st.session_state["edit_hours"] = float(parsed_json.get("hours", 1.0))
                        st.session_state["edit_formal_text"] = parsed_json.get("formal_text", "")
                        st.session_state["ai_just_extracted"] = True
                        ai_success = True

                except Exception as ex:
                    ai_error_msg = str(ex)
                    st.error(f"เกิดข้อผิดพลาดในการเรียก Gemini AI: {ai_error_msg}")

    with col_b:
        st.subheader("🤖 ขั้นตอนที่ 2: ผลการประเมินจาก Gemini AI (ตรวจทาน/ปรับแก้ได้)")
        
        if st.session_state.get("ai_just_extracted"):
            st.success("✅ Gemini AI อ่านเอกสารสกัดข้อมูลและร่างข้อความทางการให้เรียบร้อยแล้ว! สามารถตรวจสอบและปรับแก้ไขทุกช่องได้ด้านล่างนี้เลยครับ")
            st.session_state["ai_just_extracted"] = False
        else:
            st.markdown("<div class='info-alert'>💡 <b>อัปโหลดไฟล์แล้วกดปุ่ม '🤖 ให้ Gemini AI อ่านเอกสาร...'</b> ระบบจะสกัดเนื้อหาจริงและร่างข้อความทางการให้ คุณสามารถพิมพ์แก้ไขทุกช่องได้ทันที</div>", unsafe_allow_html=True)

        if "edit_cat" not in st.session_state: st.session_state["edit_cat"] = "2. ภาระงานวิจัย / งานประพันธ์ / งานสร้างสรรค์"
        if "edit_title" not in st.session_state: st.session_state["edit_title"] = "ผลงานประพันธ์เพลงสร้างสรรค์"
        if "edit_venue" not in st.session_state: st.session_state["edit_venue"] = "ณ มหาวิทยาลัยราชภัฏสงขลา"
        if "edit_date" not in st.session_state: st.session_state["edit_date"] = "ระหว่างวันที่ 10-12 สิงหาคม 2569"
        if "edit_ref" not in st.session_state: st.session_state["edit_ref"] = "คำสั่ง มรภ.สงขลา ที่ 123/2569"
        if "edit_formula" not in st.session_state: st.session_state["edit_formula"] = "(นับสิทธิ์เผยแพร่นานาชาติ = 21 ภาระงาน)"
        if "edit_hours" not in st.session_state: st.session_state["edit_hours"] = 21.0

        final_cat = st.selectbox("📂 หมวดภาระงาน:", [
            "1. ภาระงานสอน",
            "2. ภาระงานวิจัย / งานประพันธ์ / งานสร้างสรรค์",
            "3. ภาระงานบริการวิชาการ",
            "4. ภาระงานทำนุบำรุงศิลปวัฒนธรรม",
            "5. ภาระงานอื่น ๆ / งานสนับสนุน / คำสั่งเฉพาะกิจ",
            "6. งานประกันคุณภาพการศึกษา (QA)",
            "7. งานบริหาร / ตำแหน่งทางวิชาการ"
        ], key="edit_cat")

        c_f1, c_f2 = st.columns(2)
        with c_f1:
            final_title = st.text_input("1. ชื่อบทบาท / โครงการ / ผลงาน:", key="edit_title")
            final_date = st.text_input("3. วันที่ปฏิบัติงาน / วันที่เผยแพร่:", key="edit_date")
            final_formula = st.text_input("5. สูตรคำนวณ (ในวงเล็บ):", key="edit_formula")
        with c_f2:
            final_venue = st.text_input("2. สถานที่จัด / ชื่อวารสาร / เวที:", key="edit_venue")
            final_ref = st.text_input("4. เลขที่คำสั่ง / หนังสืออ้างอิง:", key="edit_ref")
            final_hours = st.number_input("6. สรุปชั่วโมงภาระงานสุทธิ:", step=0.5, key="edit_hours")

        composed_live_text = f"{final_title} {final_venue} {final_date} ({final_ref}) = {final_formula} = {final_hours:.1f} ชม."

        if "edit_formal_text" not in st.session_state or st.session_state["edit_formal_text"] == "":
            st.session_state["edit_formal_text"] = composed_live_text

        final_formal_text = st.text_area(
            "📝 ข้อความภาษาทางการฉบับสมบูรณ์ (ที่จะบันทึกลงตารางและไฟล์ Word):",
            key="edit_formal_text",
            height=120
        )

        st.markdown(f"""
        <div class="formatted-preview">
            <b>📂 หมวดงาน:</b> {final_cat}<br>
            <b>📄 อ้างอิง:</b> {final_ref}<br>
            <b>📊 ภาระงานสุทธิ:</b> <span style="color:green; font-size:1.2rem; font-weight:bold;">{final_hours:.1f} ภาระงาน</span>
        </div>
        """, unsafe_allow_html=True)

        btn_save_item = st.button("💾 บันทึกลงคลังภาระงานสะสม (ซิงค์ Cloud)", type="primary", use_container_width=True)

        if btn_save_item:
            save_email = effective_email
            
            new_entry = {
                "email": save_email,
                "หมวดงาน": final_cat,
                "รายการภาระงาน": final_formal_text,
                "เลขคำสั่ง_อ้างอิง": final_ref,
                "วันที่": final_date,
                "ภาระงาน_ชม": float(final_hours),
                "วันที่บันทึก": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            
            updated_all_df = pd.concat([all_data_df, pd.DataFrame([new_entry])], ignore_index=True)
            success, msg = save_all_data(updated_all_df)
            
            if success:
                st.balloons()
                st.toast("🎉 บันทึกข้อมูลเข้าคลังภาระงานเรียบร้อยแล้ว!", icon="✅")
                st.success(f"🎉 บันทึกรายการภาระงานสำหรับผู้ใช้ '{save_email}' ลงคลังสะสมเรียบร้อยแล้ว! สามารถสลับไปดูตารางใน Tab 2 หรือดาวน์โหลดไฟล์ Word ใน Tab 3 ได้ทันที")
                st.session_state["show_saved_success"] = True
            else:
                st.error(f"เกิดข้อผิดพลาดในการบันทึก: {msg}")

# ---------------------------------------------------------
# TAB 2: คลังภาระงานสะสม (ซิงค์ Cloud / Local)
# ---------------------------------------------------------
with tab2:
    st.subheader(f"📊 คลังภาระงานสะสมของผู้ใช้: {effective_email}")
    
    current_all_df = load_all_data()
    
    user_df = current_all_df[current_all_df["email"] == effective_email].copy() if "email" in current_all_df.columns and not current_all_df.empty else pd.DataFrame()
    
    if user_df.empty or len(user_df) == 0:
        st.info(f"👋 ขณะนี้คลังภาระงานของผู้ใช้ '{effective_email}' ยังว่างเปล่า สามารถเริ่มบันทึกรายการแรกได้ใน Tab 1 ครับ")
    else:
        st.markdown("💡 **อาจารย์สามารถแก้ไขข้อความ หรือลบรายการในตารางได้โดยตรง แล้วกดปุ่มบันทึกด้านล่าง:**")
        
        display_cols = ["หมวดงาน", "รายการภาระงาน", "เลขคำสั่ง_อ้างอิง", "วันที่", "ภาระงาน_ชม"]
        for c in display_cols:
            if c not in user_df.columns:
                user_df[c] = "" if c != "ภาระงาน_ชม" else 0.0

        edited_user_df = st.data_editor(
            user_df[display_cols],
            use_container_width=True,
            num_rows="dynamic",
            key="user_data_editor_v10"
        )
        
        col_m1, col_m2, col_m3 = st.columns([1.5, 1, 1])
        with col_m1:
            total_user_hours = pd.to_numeric(edited_user_df["ภาระงาน_ชม"], errors="coerce").sum()
            st.metric(label="📈 รวมภาระงานสะสมสุทธิ", value=f"{total_user_hours:.1f} ภาระงาน (ชั่วโมง)")
            
        with col_m2:
            if st.button("🔄 บันทึกการแก้ไขลง Google Sheets", type="primary", use_container_width=True):
                other_users_df = current_all_df[current_all_df["email"] != effective_email] if "email" in current_all_df.columns else pd.DataFrame()
                
                edited_user_df["email"] = effective_email
                edited_user_df["วันที่บันทึก"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                new_all_df = pd.concat([other_users_df, edited_user_df], ignore_index=True)
                ok, err = save_all_data(new_all_df)
                if ok:
                    st.success("บันทึกการปรับเปลี่ยนลงฐานข้อมูลเรียบร้อยแล้ว!")
                    st.rerun()
                else:
                    st.error(f"ไม่สามารถบันทึกได้: {err}")

        with col_m3:
            if st.button("🗑️ ลบข้อมูลทั้งหมดของคุณ", type="secondary", use_container_width=True):
                other_users_df = current_all_df[current_all_df["email"] != effective_email] if "email" in current_all_df.columns else pd.DataFrame()
                save_all_data(other_users_df)
                st.warning("เคลียร์คลังภาระงานของคุณเรียบร้อยแล้ว!")
                st.rerun()

# ---------------------------------------------------------
# TAB 3: สรุปแบบ ป-มร.สข. 01 & ดาวน์โหลดไฟล์ Word (.docx)
# ---------------------------------------------------------
with tab3:
    st.subheader(f"📋 สรุปผลการประเมินภาระงานและสร้างไฟล์ Word (ผู้ใช้: {effective_email})")
    
    current_all_df = load_all_data()
    user_df = current_all_df[current_all_df["email"] == effective_email].copy() if "email" in current_all_df.columns and not current_all_df.empty else pd.DataFrame()
    
    total_actual_hours = pd.to_numeric(user_df["ภาระงาน_ชม"], errors="coerce").sum() if not user_df.empty else 0.0
    
    target_benchmark = 35.0
    achieved_ratio = min(total_actual_hours / target_benchmark, 1.0) if target_benchmark > 0 else 0.0
    score_component1 = achieved_ratio * 70.0
    
    st.markdown("### 📊 คะแนนประเมินรวมรายองค์ประกอบ")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("องค์ประกอบที่ 1 (ผลสัมฤทธิ์ภาระงาน)", f"{score_component1:.2f} / 70 คะแนน", delta=f"ภาระงานสะสม {total_actual_hours:.1f} ชม.")
    with c2:
        competency_score = st.number_input("องค์ประกอบที่ 2 (สมรรถนะ/พฤติกรรม):", min_value=0.0, max_value=30.0, value=30.0, step=0.5)
    with c3:
        total_score = score_component1 + competency_score
        grade_text = "ต้องปรับปรุง (< 60)"
        if total_score >= 90: grade_text = "ดีเด่น (90.00 - 100)"
        elif total_score >= 80: grade_text = "ดีมาก (80.00 - 89.99)"
        elif total_score >= 70: grade_text = "ดี (70.00 - 79.99)"
        elif total_score >= 60: grade_text = "พอใช้ (60.00 - 69.99)"
        
        st.metric("คะแนนประเมินรวมสุทธิ", f"{total_score:.2f} / 100 คะแนน", delta=grade_text)

    st.divider()

    def generate_docx_v10():
        buffer = io.BytesIO()
        try:
            from docx import Document
            from docx.shared import Pt, Inches, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            
            doc = Document()
            
            title_p = doc.add_paragraph()
            title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run_title = title_p.add_run('แบบสรุปการประเมินผลการปฏิบัติราชการของบุคลากรสายวิชาการ (ป-มร.สข. 01)')
            run_title.bold = True
            run_title.font.size = Pt(16)
            
            p_sub = doc.add_paragraph()
            p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_sub.add_run(f'มหาวิทยาลัยราชภัฏสงขลา | รอบการประเมิน {datetime.now().strftime("%Y")}')
            
            doc.add_paragraph(f'ผู้รับการประเมิน: {effective_email}')
            doc.add_paragraph(f'ตำแหน่ง/สังกัด: {role}')
            doc.add_paragraph(f'กลุ่มการประเมิน: {track_type}')
            doc.add_paragraph(f'วันที่ออกรายงาน: {datetime.now().strftime("%d/%m/%Y")}')
            
            doc.add_heading('1. สรุปคะแนนการประเมินผลการปฏิบัติงาน', level=2)
            doc.add_paragraph(f'• องค์ประกอบที่ 1 (ผลสัมฤทธิ์ของงาน): {score_component1:.2f} / 70 คะแนน')
            doc.add_paragraph(f'• องค์ประกอบที่ 2 (พฤติกรรม/สมรรถนะ): {competency_score:.2f} / 30 คะแนน')
            doc.add_paragraph(f'• คะแนนรวมสุทธิ: {total_score:.2f} / 100 คะแนน (ระดับผลการประเมิน: {grade_text})')
            
            doc.add_heading('2. รายละเอียดภาระงานสะสม (เรียบเรียงภาษาทางการ)', level=2)
            
            table = doc.add_table(rows=1, cols=4)
            table.style = 'Table Grid'
            
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = 'หมวดงาน'
            hdr_cells[1].text = 'รายการภาระงานและสูตรการคำนวณ (ภาษาทางการ)'
            hdr_cells[2].text = 'เลขที่คำสั่ง/อ้างอิง'
            hdr_cells[3].text = 'ภาระงาน (ชม.)'
            
            if not user_df.empty:
                for _, row in user_df.iterrows():
                    row_cells = table.add_row().cells
                    row_cells[0].text = str(row.get('หมวดงาน', ''))
                    row_cells[1].text = str(row.get('รายการภาระงาน', ''))
                    row_cells[2].text = str(row.get('เลขคำสั่ง_อ้างอิง', ''))
                    row_cells[3].text = f"{float(row.get('ภาระงาน_ชม', 0)):.1f}"
                    
            doc.add_paragraph(f'\nรวมภาระงานสะสมสุทธิทั้งสิ้น: {total_actual_hours:.1f} ภาระงาน (ชั่วโมง)')
            doc.save(buffer)
            buffer.seek(0)
            return buffer
        except Exception:
            buffer.write(f"SKRU Workload Report v10\nUser: {effective_email}\nTotal Hours: {total_actual_hours}\nScore: {total_score}".encode('utf-8'))
            buffer.seek(0)
            return buffer

    docx_file = generate_docx_v10()
    
    file_email_slug = effective_email.split('@')[0]
    st.download_button(
        label="📥 ดาวน์โหลดแบบสรุป ป-มร.สข. 01 (.docx)",
        data=docx_file,
        file_name=f"ป-มร.สข.01_{file_email_slug}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary"
    )
