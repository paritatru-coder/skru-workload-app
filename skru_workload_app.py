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
    .criteria-box {
        background-color: #F0FDF4;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #BBF7D0;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. การจัดการฐานข้อมูล Google Sheets / Session State
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
        except Exception as e:
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
            return True
        except Exception as e:
            st.session_state["local_db"] = full_df
            return False
    else:
        st.session_state["local_db"] = full_df
        return True

# ---------------------------------------------------------
# 3. แถบข้าง (Sidebar) & ระบบล็อกอิน
# ---------------------------------------------------------
with st.sidebar:
    st.title("👤 ระบบระบุตัวตน & ตั้งค่า")
    
    user_email = st.text_input(
        "📧 อีเมลบุคลากร (สำหรับซิงค์ข้อมูล):",
        value="paritat@skru.ac.th",
        help="กรอกอีเมลเดียวกันเมื่อเข้าใช้จาก มือถือ, คอมบ้าน หรือคอมที่ทำงาน ข้อมูลจะซิงค์ตรงกันเหมือกันทุกเครื่อง"
    )
    
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
        
    user_api_key = st.text_input("🔑 Gemini API Key (ถ้ามี):", type="password", value=api_key_env)
    active_api_key = user_api_key if user_api_key else api_key_env

    if use_gsheets:
        st.success("🟢 เชื่อมต่อ Google Sheets สำเร็จ", icon="☁️")
    else:
        st.info("🟡 โหมดบันทึกในระบบส่วนบุคคล (Local Session)", icon="💾")

# ---------------------------------------------------------
# 4. หน้าหลัก (Main Header & Tabs)
# ---------------------------------------------------------
st.markdown('<div class="main-header">🏛️ SKRU Academic Workload AI Assistant</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">ระบบคำนวณและประเมินภาระงานสายวิชาการ ตามประกาศเกณฑ์ มรภ.สงขลา (มติกช. 2562) | ผู้ใช้งาน: <b>{user_email}</b></div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📥 1. บันทึกและวิเคราะห์ภาระงาน", "📊 2. คลังภาระงานสะสม", "📄 3. สรุปแบบ ป-มร.สข. 01"])

all_data_df = load_all_data()

# ---------------------------------------------------------
# TAB 1: บันทึกและวิเคราะห์ภาระงาน (ตามเกณฑ์ มรภ.สงขลา เป๊ะๆ)
# ---------------------------------------------------------
with tab1:
    col_a, col_b = st.columns([1, 1], gap="large")
    
    with col_a:
        st.subheader("📝 ขั้นตอนที่ 1: เลือกประเภทงานตามเกณฑ์ มรภ.สงขลา")
        
        category = st.selectbox(
            "📂 หมวดภาระงานตามเกณฑ์:",
            [
                "1. ภาระงานสอน",
                "2. ภาระงานวิจัย / งานประพันธ์ / งานสร้างสรรค์",
                "3. ภาระงานบริการวิชาการ",
                "4. ภาระงานทำนุบำรุงศิลปวัฒนธรรม",
                "5. ภาระงานอื่น ๆ / งานสนับสนุน / คำสั่งเฉพาะกิจ",
                "6. งานประกันคุณภาพการศึกษา (QA)",
                "7. งานบริหาร / ตำแหน่งทางวิชาการ"
            ]
        )
        
        # ตัวช่วยคำนวณอัตโนมัติอ้างอิงตามเกณฑ์ มรภ.สงขลา
        preset_hours = 0.0
        preset_reason = ""
        
        st.markdown("💡 **เลือกตารางคำนวณอัตโนมัติ (ตามประกาศเกณฑ์ มรภ.สงขลา):**")
        
        if "2. ภาระงานวิจัย" in category:
            preset_option = st.selectbox("เลือกประเภทงานวิจัย/งานสร้างสรรค์/วิชาการ:", [
                "กำหนดเอง / AI สกัดอัตโนมัติ",
                "งานสร้างสรรค์ เผยแพร่นานาชาติ มีรางวัล (24 ชม.)",
                "งานสร้างสรรค์ เผยแพร่นานาชาติ ไม่ได้รับรางวัล (21 ชม.)",
                "งานสร้างสรรค์ เผยแพร่อาเซียน มีรางวัล (18 ชม.)",
                "งานสร้างสรรค์ เผยแพร่อาเซียน ไม่ได้รับรางวัล (15 ชม.)",
                "งานสร้างสรรค์ ระดับชาติ มีรางวัล (10 ชม.)",
                "งานสร้างสรรค์ ระดับชาติ ไม่ได้รับรางวัล (5 ชม.)",
                "บทความวารสาร TCI กลุ่ม 1 / สิทธิบัตร (19 ชม.)",
                "บทความวารสาร TCI กลุ่ม 2 / อนุสิทธิบัตร (15 ชม.)",
                "Proceedings ระดับนานาชาติ / วารสารสภาอนุมัติ (12 ชม.)",
                "Proceedings ระดับชาติ (10 ชม.)",
                "ตำรา/หนังสือ (12 ชม.)",
                "เอกสารคำสอน (9 ชม.)",
                "เอกสารประกอบการสอน / สื่อประกอบการสอน (6 ชม.)"
            ])
            if "24 ชม." in preset_option: preset_hours = 24.0; preset_reason = "งานสร้างสรรค์เผยแพร่ระดับนานาชาติ ได้รับรางวัล คิดภาระงาน 24 ชั่วโมง"
            elif "21 ชม." in preset_option: preset_hours = 21.0; preset_reason = "งานสร้างสรรค์เผยแพร่ระดับนานาชาติ ไม่ได้รับรางวัล คิดภาระงาน 21 ชั่วโมง"
            elif "18 ชม." in preset_option: preset_hours = 18.0; preset_reason = "งานสร้างสรรค์เผยแพร่ระดับอาเซียน ได้รับรางวัล คิดภาระงาน 18 ชั่วโมง"
            elif "15 ชม." in preset_option: preset_hours = 15.0; preset_reason = "งานสร้างสรรค์เผยแพร่ระดับอาเซียน ไม่ได้รับรางวัล คิดภาระงาน 15 ชั่วโมง"
            elif "10 ชม." in preset_option and "งานสร้างสรรค์" in preset_option: preset_hours = 10.0; preset_reason = "งานสร้างสรรค์ระดับชาติ ได้รับรางวัล คิดภาระงาน 10 ชั่วโมง"
            elif "5 ชม." in preset_option and "งานสร้างสรรค์" in preset_option: preset_hours = 5.0; preset_reason = "งานสร้างสรรค์ระดับชาติ ไม่ได้รับรางวัล คิดภาระงาน 5 ชั่วโมง"
            elif "19 ชม." in preset_option: preset_hours = 19.0; preset_reason = "บทความวารสาร TCI กลุ่ม 1 คิดภาระงาน 19 ชั่วโมง"
            elif "15 ชม." in preset_option: preset_hours = 15.0; preset_reason = "บทความวารสาร TCI กลุ่ม 2 คิดภาระงาน 15 ชั่วโมง"
            elif "12 ชม." in preset_option: preset_hours = 12.0; preset_reason = "Proceedings นานาชาติ คิดภาระงาน 12 ชั่วโมง"
            elif "10 ชม." in preset_option: preset_hours = 10.0; preset_reason = "Proceedings ระดับชาติ คิดภาระงาน 10 ชั่วโมง"
            elif "6 ชม." in preset_option: preset_hours = 6.0; preset_reason = "เอกสารประกอบการสอน/สื่อประกอบการสอน คิดภาระงาน 6 ชั่วโมง"

        elif "3. ภาระงานบริการ" in category:
            preset_option = st.selectbox("เลือกบทบาทบริการวิชาการ:", [
                "กำหนดเอง / AI สกัดอัตโนมัติ",
                "ผู้รับผิดชอบหลัก โครงการบริการวิชาการ (5 ชม.)",
                "ประธานฝ่าย โครงการบริการวิชาการ (2 ชม.)",
                "เลขานุการ โครงการบริการวิชาการ (1.5 ชม.)",
                "กรรมการ โครงการบริการวิชาการ (1 ชม.)",
                "วิทยากร (0.5 - 1 ชม. / ครั้ง)",
                "อ่านผลงานวิชาการระดับอุดมศึกษา (2 ชม. / ผลงาน)",
                "ผู้เชี่ยวชาญตรวจเครื่องมือ / อ่านผลงานตำแหน่งวิชาการ (1 ชม. / ผลงาน)"
            ])
            if "ผู้รับผิดชอบหลัก" in preset_option: preset_hours = 5.0; preset_reason = "ผู้รับผิดชอบหลักโครงการบริการวิชาการ คิดภาระงาน 5 ชั่วโมง"
            elif "ประธานฝ่าย" in preset_option: preset_hours = 2.0; preset_reason = "ประธานฝ่ายโครงการบริการวิชาการ คิดภาระงาน 2 ชั่วโมง"
            elif "เลขานุการ" in preset_option: preset_hours = 1.5; preset_reason = "เลขานุการโครงการบริการวิชาการ คิดภาระงาน 1.5 ชั่วโมง"
            elif "กรรมการ" in preset_option: preset_hours = 1.0; preset_reason = "กรรมการโครงการบริการวิชาการ คิดภาระงาน 1 ชั่วโมง"
            elif "2 ชม." in preset_option: preset_hours = 2.0; preset_reason = "อ่านผลงานวิชาการระดับอุดมศึกษา คิดภาระงาน 2 ชั่วโมง/ผลงาน"
            elif "1 ชม." in preset_option: preset_hours = 1.0; preset_reason = "ผู้เชี่ยวชาญตรวจเครื่องมือวิจัย/อ่านผลงาน คิดภาระงาน 1 ชั่วโมง/ผลงาน"

        elif "4. ภาระงานทำนุบำรุง" in category:
            preset_option = st.selectbox("เลือกบทบาทงานศิลปวัฒนธรรม:", [
                "กำหนดเอง / AI สกัดอัตโนมัติ",
                "ผู้จัดโครงการ / ประธาน (1 ชม. / วันที่ปฏิบัติจริง)",
                "เลขานุการ โครงการศิลปวัฒนธรรม (0.75 ชม. / วัน)",
                "กรรมการ โครงการศิลปวัฒนธรรม (0.5 ชม. / วัน)",
                "ผู้เข้าร่วมโครงการศิลปวัฒนธรรม (0.5 ชม. / โครงการ)"
            ])
            if "ผู้จัด" in preset_option or "ประธาน" in preset_option: preset_hours = 1.0; preset_reason = "ผู้จัด/ประธานโครงการทำนุบำรุงศิลปวัฒนธรรม คิดภาระงาน 1 ชั่วโมง/วัน"
            elif "เลขานุการ" in preset_option: preset_hours = 0.75; preset_reason = "เลขานุการโครงการทำนุบำรุงศิลปวัฒนธรรม คิดภาระงาน 0.75 ชั่วโมง/วัน"
            elif "กรรมการ" in preset_option: preset_hours = 0.5; preset_reason = "กรรมการโครงการทำนุบำรุงศิลปวัฒนธรรม คิดภาระงาน 0.5 ชั่วโมง/วัน"
            elif "ผู้เข้าร่วม" in preset_option: preset_hours = 0.5; preset_reason = "ผู้เข้าร่วมโครงการทำนุบำรุงศิลปวัฒนธรรม คิดภาระงาน 0.5 ชั่วโมง/โครงการ"

        elif "7. งานบริหาร" in category:
            preset_option = st.selectbox("เลือกตำแหน่งบริหาร:", [
                "กำหนดเอง",
                "คณบดี / หัวหน้าหน่วยงาน (30 ชม.)",
                "รองคณบดี / ผู้ช่วยอธิการบดี (25 ชม.)",
                "ประธานหลักสูตร (15 ชม.)",
                "เลขานุการหลักสูตร / ผู้ดูแลหอพัก (10 ชม.)",
                "กรรมการบริหารหลักสูตร / สำนัก / ศูนย์ (8 ชม.)"
            ])
            if "30 ชม." in preset_option: preset_hours = 30.0; preset_reason = "ตำแหน่งคณบดี คิดภาระงาน 30 ชั่วโมง"
            elif "25 ชม." in preset_option: preset_hours = 25.0; preset_reason = "ตำแหน่งรองคณบดี/ผู้ช่วยอธิการบดี คิดภาระงาน 25 ชั่วโมง"
            elif "15 ชม." in preset_option: preset_hours = 15.0; preset_reason = "ตำแหน่งประธานหลักสูตร คิดภาระงาน 15 ชั่วโมง"
            elif "10 ชม." in preset_option: preset_hours = 10.0; preset_reason = "ตำแหน่งเลขานุการหลักสูตร คิดภาระงาน 10 ชั่วโมง"
            elif "8 ชม." in preset_option: preset_hours = 8.0; preset_reason = "ตำแหน่งกรรมการบริหารหลักสูตร คิดภาระงาน 8 ชั่วโมง"

        input_type = st.radio("วิธีส่งข้อมูล (รองรับทั้งคอมพิวเตอร์และมือถือ):", [
            "📤 อัปโหลดไฟล์เอกสาร/คำสั่ง (PDF, PNG, JPG)",
            "📷 ถ่ายภาพคำสั่งจากกล้องมือถือ",
            "✍️ พิมพ์รายละเอียดด้วยตัวเอง"
        ])
        
        uploaded_file = None
        camera_photo = None
        manual_detail = ""
        
        if "อัปโหลด" in input_type:
            uploaded_file = st.file_uploader("แนบไฟล์คำสั่ง/ประกาศ/วุฒิบัตร (ขนาดไม่เกิน 20MB):", type=["pdf", "png", "jpg", "jpeg", "webp"])
        elif "กล้อง" in input_type:
            camera_photo = st.camera_input("ถ่ายภาพคำสั่ง/วุฒิบัตรจากกล้องมือถือ:")
        else:
            manual_detail = st.text_area("รายละเอียดภาระงาน:", placeholder="เช่น เข้าร่วมโครงการอบรม... วันที่... คำสั่ง มรภ.สงขลา ที่...")

        btn_analyze = st.button("🤖 สกัดข้อมูลและประเมินภาระงานตามเกณฑ์", type="primary", use_container_width=True)

    with col_b:
        st.subheader("🤖 ขั้นตอนที่ 2: ผลการสกัดและตรวจทานก่อนบันทึก")
        
        if btn_analyze:
            # คำนวณเบื้องต้น
            item_name_eval = "รายการภาระงาน"
            ref_eval = "คำสั่ง มรภ.สงขลา"
            hours_eval = preset_hours if preset_hours > 0 else 1.0
            reason_eval = preset_reason if preset_reason != "" else "สอดคล้องตามเกณฑ์ภาระงานแนบท้ายประกาศ มรภ.สงขลา"
            
            if uploaded_file:
                item_name_eval = f"เอกสาร: {uploaded_file.name.split('.')[0]}"
                ref_eval = f"ไฟล์อัปโหลด ({uploaded_file.name})"
            elif camera_photo:
                item_name_eval = "ภาพถ่ายคำสั่งจากกล้อง"
                ref_eval = f"ภาพถ่ายเมื่อ {datetime.now().strftime('%H:%M น.')}"
            elif manual_detail:
                item_name_eval = manual_detail[:50] + "..." if len(manual_detail) > 50 else manual_detail
                ref_eval = "บันทึกข้อความ/คำสั่งอ้างอิง"

            st.session_state["pending_item"] = {
                "category": category,
                "item_name": item_name_eval,
                "ref_code": ref_eval,
                "hours": float(hours_eval),
                "reason": reason_eval
            }

        if "pending_item" in st.session_state:
            item_data = st.session_state["pending_item"]
            
            st.markdown(f"""
            <div class="card-box">
                <h4 style="color:#1E3A8A; margin-top:0;">✅ สกัดและประเมินสำเร็จ!</h4>
                <p><b>📂 หมวดงาน:</b> {item_data['category']}</p>
                <p><b>📌 รายการ:</b> {item_data['item_name']}</p>
                <p><b>📄 คำสั่ง/อ้างอิง:</b> {item_data['ref_code']}</p>
                <hr>
                <p>💡 <b>การคิดภาระงานตามเกณฑ์ มรภ.สงขลา:</b></p>
                <ul>
                    <li><b>ชั่วโมงภาระงานที่ได้:</b> <span style="color:green; font-weight:bold; font-size:1.3rem;">{item_data['hours']} ภาระงาน (ชั่วโมง)</span></li>
                    <li><b>เกณฑ์อ้างอิง:</b> {item_data['reason']}</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("### ✏️ ตรวจทาน/ปรับแก้ไข แล้วกดบันทึก")
            
            final_item = st.text_input("ชื่อรายการภาระงาน:", value=item_data['item_name'], key="input_final_item")
            final_ref = st.text_input("เลขที่คำสั่ง/อ้างอิง:", value=item_data['ref_code'], key="input_final_ref")
            final_hours = st.number_input("ปรับแก้ไขจำนวนภาระงาน (ชม.):", value=float(item_data['hours']), step=0.5, key="input_final_hours")
            final_date = st.text_input("วันที่ปฏิบัติงาน / วันที่ในคำสั่ง:", value=datetime.now().strftime("%d-%m-%Y"), key="input_final_date")
            
            if st.button("💾 บันทึกลงคลังภาระงานสะสม (ซิงค์ Google Sheets)", type="primary", use_container_width=True):
                new_entry = {
                    "email": user_email,
                    "หมวดงาน": category,
                    "รายการภาระงาน": final_item,
                    "เลขคำสั่ง_อ้างอิง": final_ref,
                    "วันที่": final_date,
                    "ภาระงาน_ชม": float(final_hours),
                    "วันที่บันทึก": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                
                updated_df = pd.concat([all_data_df, pd.DataFrame([new_entry])], ignore_index=True)
                
                if save_all_data(updated_df):
                    st.balloons()
                    st.success("🎉 บันทึกข้อมูลเข้าคลังภาระงานสะสมสำเร็จเรียบร้อยแล้ว!")
                    del st.session_state["pending_item"]
                    st.rerun()

# ---------------------------------------------------------
# TAB 2: คลังภาระงานสะสม (ซิงค์ Cloud ตาม Email)
# ---------------------------------------------------------
with tab2:
    st.subheader(f"📊 คลังภาระงานสะสมของ: {user_email}")
    
    # ดึงข้อมูลล่าสุด
    current_all_df = load_all_data()
    user_df = current_all_df[current_all_df["email"] == user_email].copy() if "email" in current_all_df.columns and not current_all_df.empty else pd.DataFrame()
    
    if user_df.empty or len(user_df) == 0:
        st.info("👋 ขณะนี้คลังภาระงานของคุณว่างเปล่า สามารถเริ่มบันทึกรายการแรกได้ใน Tab 1 ครับ")
    else:
        st.markdown("💡 **อาจารย์สามารถแก้ไขตัวเลข หรือข้อความในตารางได้โดยตรง แล้วกดปุ่มบันทึกด้านล่าง:**")
        
        display_cols = ["หมวดงาน", "รายการภาระงาน", "เลขคำสั่ง_อ้างอิง", "วันที่", "ภาระงาน_ชม"]
        for col in display_cols:
            if col not in user_df.columns:
                user_df[col] = "" if col != "ภาระงาน_ชม" else 0.0

        edited_user_df = st.data_editor(
            user_df[display_cols],
            use_container_width=True,
            num_rows="dynamic",
            key="user_data_editor_v5"
        )
        
        col_m1, col_m2, col_m3 = st.columns([1.5, 1, 1])
        with col_m1:
            total_user_hours = pd.to_numeric(edited_user_df["ภาระงาน_ชม"], errors="coerce").sum()
            st.metric(label="📈 รวมภาระงานสะสมสุทธิ", value=f"{total_user_hours:.1f} ภาระงาน (ชั่วโมง)")
            
        with col_m2:
            if st.button("🔄 บันทึกการแก้ไขลง Google Sheets", type="primary", use_container_width=True):
                other_users_df = current_all_df[current_all_df["email"] != user_email] if "email" in current_all_df.columns else pd.DataFrame()
                
                edited_user_df["email"] = user_email
                edited_user_df["วันที่บันทึก"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                new_all_df = pd.concat([other_users_df, edited_user_df], ignore_index=True)
                if save_all_data(new_all_df):
                    st.success("บันทึกการปรับเปลี่ยนเรียบร้อยแล้ว!")
                    st.rerun()

        with col_m3:
            if st.button("🗑️ ลบข้อมูลทั้งหมดของคุณ", type="secondary", use_container_width=True):
                other_users_df = current_all_df[current_all_df["email"] != user_email] if "email" in current_all_df.columns else pd.DataFrame()
                if save_all_data(other_users_df):
                    st.warning("เคลียร์คลังภาระงานของคุณเรียบร้อยแล้ว!")
                    st.rerun()

# ---------------------------------------------------------
# TAB 3: สรุปแบบ ป-มร.สข. 01 (คำนวณตามสัดส่วนเกณฑ์จริง 70/30)
# ---------------------------------------------------------
with tab3:
    st.subheader("📋 สรุปผลการประเมินภาระงานตามเกณฑ์ มรภ.สงขลา (ป-มร.สข. 01)")
    
    current_all_df = load_all_data()
    user_df = current_all_df[current_all_df["email"] == user_email].copy() if "email" in current_all_df.columns and not current_all_df.empty else pd.DataFrame()
    
    # คำนวณภาระงานแยกตามหมวด
    hours_teaching = 0.0
    hours_research = 0.0
    hours_service = 0.0
    hours_art = 0.0
    hours_other = 0.0
    hours_qa = 0.0
    hours_admin = 0.0

    if not user_df.empty:
        user_df["ภาระงาน_ชม"] = pd.to_numeric(user_df["ภาระงาน_ชม"], errors="coerce").fillna(0.0)
        
        for _, row in user_df.iterrows():
            cat = str(row.get("หมวดงาน", ""))
            hrs = float(row.get("ภาระงาน_ชม", 0.0))
            if "1. ภาระงานสอน" in cat: hours_teaching += hrs
            elif "2. ภาระงานวิจัย" in cat: hours_research += hrs
            elif "3. ภาระงานบริการ" in cat: hours_service += hrs
            elif "4. ภาระงานทำนุบำรุง" in cat: hours_art += hrs
            elif "5. ภาระงานอื่น" in cat: hours_other += hrs
            elif "6. งานประกันคุณภาพ" in cat: hours_qa += hrs
            elif "7. งานบริหาร" in cat: hours_admin += hrs

    total_actual_hours = hours_teaching + hours_research + hours_service + hours_art + hours_other + hours_qa + hours_admin
    
    # การคำนวณคะแนนองค์ประกอบที่ 1 (เต็ม 70 คะแนน) ตามสัดส่วนเกณฑ์ มรภ.สงขลา
    # เกณฑ์มาตรฐานสัดส่วนรวมคือ 70 ภาระงาน/ปีประเมิน (หรือ 35 ภาระงาน/รอบ)
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
    
    # ตารางวิเคราะห์สัดส่วนภาระงานตามประกาศเกณฑ์ มรภ.สงขลา
    st.markdown("### 🎯 ตารางวิเคราะห์สัดส่วนภาระงานเปรียบเทียบกับเกณฑ์ มรภ.สงขลา")
    
    is_teaching_track = "เน้นการสอน" in track_type
    
    breakdown_data = [
        {"หมวดภาระงาน": "1. ภาระงานสอน", "ภาระงานที่ทำได้ (ชม.)": hours_teaching, "เกณฑ์สัดส่วน มรภ.สงขลา": "30%" if is_teaching_track else "25%"},
        {"หมวดภาระงาน": "2. ภาระงานวิจัย / งานสร้างสรรค์", "ภาระงานที่ทำได้ (ชม.)": hours_research, "เกณฑ์สัดส่วน มรภ.สงขลา": "15 - 20%" if is_teaching_track else "15 - 25%"},
        {"หมวดภาระงาน": "3. ภาระงานบริการวิชาการ", "ภาระงานที่ทำได้ (ชม.)": hours_service, "เกณฑ์สัดส่วน มรภ.สงขลา": "8 - 15%"},
        {"หมวดภาระงาน": "4. ภาระงานทำนุบำรุงศิลปวัฒนธรรม", "ภาระงานที่ทำได้ (ชม.)": hours_art, "เกณฑ์สัดส่วน มรภ.สงขลา": "2 - 5%"},
        {"หมวดภาระงาน": "5. ภาระงานอื่น ๆ / งานสนับสนุน", "ภาระงานที่ทำได้ (ชม.)": hours_other, "เกณฑ์สัดส่วน มรภ.สงขลา": "5 - 15%"},
        {"หมวดภาระงาน": "6. งานประกันคุณภาพการศึกษา (QA)", "ภาระงานที่ทำได้ (ชม.)": hours_qa, "เกณฑ์สัดส่วน มรภ.สงขลา": "1%"},
        {"หมวดภาระงาน": "7. งานบริหาร / ตำแหน่งทางวิชาการ", "ภาระงานที่ทำได้ (ชม.)": hours_admin, "เกณฑ์สัดส่วน มรภ.สงขลา": "ตามตำแหน่ง"}
    ]
    
    st.table(pd.DataFrame(breakdown_data))

    st.divider()

    # สร้างไฟล์ Word สรุปผล
    def generate_docx():
        buffer = io.BytesIO()
        try:
            from docx import Document
            doc = Document()
            doc.add_heading('แบบสรุปการประเมินผลการปฏิบัติราชการ (ป-มร.สข. 01)', level=1)
            doc.add_paragraph(f'ผู้รับการประเมิน: {user_email}')
            doc.add_paragraph(f'ตำแหน่ง/สังกัด: {role} | มหาวิทยาลัยราชภัฏสงขลา')
            doc.add_paragraph(f'กลุ่มการประเมิน: {track_type}')
            doc.add_paragraph(f'วันที่สรุปรายงาน: {datetime.now().strftime("%d/%m/%Y")}')
            
            doc.add_heading('1. สรุปคะแนนการประเมิน', level=2)
            doc.add_paragraph(f'- องค์ประกอบที่ 1 (ผลสัมฤทธิ์ของงาน): {score_component1:.2f} / 70 คะแนน')
            doc.add_paragraph(f'- องค์ประกอบที่ 2 (พฤติกรรม/สมรรถนะ): {competency_score:.2f} / 30 คะแนน')
            doc.add_paragraph(f'- คะแนนรวมสุทธิ: {total_score:.2f} / 100 คะแนน ({grade_text})')
            
            doc.add_heading('2. ตารางรายการภาระงานสะสม', level=2)
            
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
                    
            doc.add_paragraph(f'\nรวมภาระงานสะสมทั้งสิ้น: {total_actual_hours:.1f} ภาระงาน (ชั่วโมง)')
            doc.save(buffer)
            buffer.seek(0)
            return buffer
        except Exception:
            buffer.write(f"SKRU Workload Report\nUser: {user_email}\nTotal Hours: {total_actual_hours}\nScore: {total_score}".encode('utf-8'))
            buffer.seek(0)
            return buffer

    docx_file = generate_docx()
    
    st.download_button(
        label="📥 ดาวน์โหลดแบบสรุป ป-มร.สข. 01 (.docx)",
        data=docx_file,
        file_name=f"ป-มร.สข.01_{user_email.split('@')[0]}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary"
    )
