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
    page_title="SKRU Workload AI - ระบบบันทึกและวิเคราะห์ภาระงาน มรภ.สงขลา (v7)",
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
            return True
        except Exception:
            st.session_state["local_db"] = full_df
            return False
    else:
        st.session_state["local_db"] = full_df
        return True

# ---------------------------------------------------------
# 3. Sidebar Configuration
# ---------------------------------------------------------
with st.sidebar:
    st.title("👤 ระบุตัวตน & ตั้งค่า")
    
    user_email = st.text_input(
        "📧 อีเมลบุคลากร (สำหรับซิงค์ข้อมูล):",
        value="paritat@skru.ac.th",
        help="กรอกอีเมลเพื่อซิงค์ข้อมูลตรงกันจากมือถือ คอมพิวเตอร์บ้าน และคอมพิวเตอร์ทำงาน"
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

    st.markdown("### ☁️ สถานะการเชื่อมต่อ")
    if use_gsheets:
        st.success("🟢 เชื่อมต่อ Google Sheets สำเร็จ", icon="☁️")
    else:
        st.info("🟡 ระบบบันทึกส่วนบุคคล (Local Session)", icon="💾")

# ---------------------------------------------------------
# 4. Main Interface & Tabs
# ---------------------------------------------------------
st.markdown('<div class="main-header">🏛️ SKRU Academic Workload AI Assistant (v7)</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">ระบบช่วยสกัด เรียบเรียงภาษาทางการ และประเมินภาระงานตามเกณฑ์ มรภ.สงขลา (มติกช.) | ผู้ใช้: <b>{user_email}</b></div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📥 1. สกัดและเรียบเรียงภาระงาน (AI)", "📊 2. คลังภาระงานสะสม", "📄 3. สรุปแบบ ป-มร.สข. 01 (Word)"])

all_data_df = load_all_data()

# ---------------------------------------------------------
# TAB 1: บันทึก สกัด และเรียบเรียงข้อความทางการตามเกณฑ์ มรภ.สงขลา
# ---------------------------------------------------------
with tab1:
    col_a, col_b = st.columns([1, 1], gap="large")
    
    with col_a:
        st.subheader("📝 ขั้นตอนที่ 1: ป้อนข้อมูล / เลือกสูตรคำนวณตามเกณฑ์")
        
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
        
        # ตัวแปรช่วยคำนวณและเรียบเรียง
        calc_formula_str = ""
        suggested_title = ""
        default_hours = 1.0
        
        if "2. ภาระงานวิจัย" in category:
            preset_option = st.selectbox("เลือกประเภทงานวิจัย/งานสร้างสรรค์:", [
                "กำหนดเอง / AI สกัดจากคำสั่ง",
                "งานสร้างสรรค์ เผยแพร่นานาชาติ มีรางวัล (24 ชม.)",
                "งานสร้างสรรค์ เผยแพร่นานาชาติ ไม่ได้รับรางวัล (21 ชม.)",
                "งานสร้างสรรค์ เผยแพร่อาเซียน มีรางวัล (18 ชม.)",
                "งานสร้างสรรค์ เผยแพร่อาเซียน ไม่ได้รับรางวัล (15 ชม.)",
                "บทความวารสาร TCI กลุ่ม 1 / สิทธิบัตร (19 ชม.)",
                "บทความวารสาร TCI กลุ่ม 2 / อนุสิทธิบัตร (15 ชม.)",
                "Proceedings ระดับนานาชาติ (12 ชม.)",
                "Proceedings ระดับชาติ (10 ชม.)"
            ])
            if "24 ชม." in preset_option: default_hours = 24.0; calc_formula_str = "(นับสิทธิ์เผยแพร่นานาชาติ มีรางวัล = 24 ภาระงาน)"; suggested_title = "ผลงานประพันธ์เพลงสร้างสรรค์"
            elif "21 ชม." in preset_option: default_hours = 21.0; calc_formula_str = "(นับสิทธิ์เผยแพร่นานาชาติ ไม่ได้รับรางวัล = 21 ภาระงาน)"
            elif "18 ชม." in preset_option: default_hours = 18.0; calc_formula_str = "(นับสิทธิ์เผยแพร่อาเซียน มีรางวัล = 18 ภาระงาน)"
            elif "15 ชม." in preset_option: default_hours = 15.0; calc_formula_str = "(นับสิทธิ์เผยแพร่อาเซียน ไม่ได้รับรางวัล = 15 ภาระงาน)"
            elif "19 ชม." in preset_option: default_hours = 19.0; calc_formula_str = "(บทความวารสาร TCI กลุ่ม 1 = 19 ภาระงาน)"; suggested_title = "บทความวิจัยตีพิมพ์ในวารสารวิชาการ"
            elif "15 ชม." in preset_option: default_hours = 15.0; calc_formula_str = "(บทความวารสาร TCI กลุ่ม 2 = 15 ภาระงาน)"
            elif "12 ชม." in preset_option: default_hours = 12.0; calc_formula_str = "(Proceedings นานาชาติ = 12 ภาระงาน)"
            elif "10 ชม." in preset_option: default_hours = 10.0; calc_formula_str = "(Proceedings ระดับชาติ = 10 ภาระงาน)"

        elif "3. ภาระงานบริการ" in category:
            preset_option = st.selectbox("เลือกบทบาทบริการวิชาการ:", [
                "กำหนดเอง / AI สกัดจากคำสั่ง",
                "วิทยากร (สูตร: ชั่วโมง x วัน x 0.5)",
                "ผู้รับผิดชอบหลัก โครงการบริการวิชาการ (5 ชม.)",
                "ประธานฝ่าย โครงการบริการวิชาการ (2 ชม.)",
                "เลขานุการ โครงการบริการวิชาการ (1.5 ชม.)",
                "กรรมการ โครงการบริการวิชาการ (1 ชม.)",
                "อ่าน/ประเมินผลงานวิชาการ (2 ชม./ผลงาน)"
            ])
            if "วิทยากร" in preset_option:
                suggested_title = "วิทยากรโครงการอบรมเชิงปฏิบัติการ เรื่อง..."
                calc_formula_str = "(3ชม x 5วัน x 0.5) = 7.5 ชม."
                default_hours = 7.5
            elif "ผู้รับผิดชอบหลัก" in preset_option: default_hours = 5.0; calc_formula_str = "(= 5 ภาระงาน)"; suggested_title = "ผู้รับผิดชอบหลักโครงการบริการวิชาการ"
            elif "ประธานฝ่าย" in preset_option: default_hours = 2.0; calc_formula_str = "(= 2 ภาระงาน)"
            elif "เลขานุการ" in preset_option: default_hours = 1.5; calc_formula_str = "(= 1.5 ภาระงาน)"
            elif "กรรมการ" in preset_option: default_hours = 1.0; calc_formula_str = "(= 1 ภาระงาน)"

        elif "4. ภาระงานทำนุบำรุง" in category:
            preset_option = st.selectbox("เลือกบทบาททำนุบำรุงศิลปวัฒนธรรม:", [
                "กำหนดเอง / AI สกัดจากคำสั่ง",
                "ผู้จัดโครงการ / ประธาน (สูตร: 1 ชม./วัน)",
                "กรรมการดำเนินงาน (สูตร: 0.5 ชม./วัน)",
                "เลขานุการโครงการ (สูตร: 0.75 ชม./วัน)",
                "ผู้ร่วมบรรเลง/แสดงดนตรีศิลปวัฒนธรรม (0.5 ชม./ครั้ง)"
            ])
            if "ผู้จัด" in preset_option: suggested_title = "ผู้จัดโครงการส่งเสริมและทำนุบำรุงศิลปวัฒนธรรม..."; calc_formula_str = "(= 2 วัน x 1.0) = 2 ชม."; default_hours = 2.0
            elif "กรรมการ" in preset_option: suggested_title = "คณะกรรมการดำเนินงานโครงการศิลปวัฒนธรรม..."; calc_formula_str = "(= 2 วัน x 0.5) = 1 ชม."; default_hours = 1.0
            elif "ผู้ร่วมบรรเลง" in preset_option: suggested_title = "ร่วมบรรเลงดนตรีไทยในงานพิธี..."; calc_formula_str = "(= 1 ครั้ง x 0.5) = 0.5 ชม."; default_hours = 0.5

        elif "5. ภาระงานอื่น" in category:
            preset_option = st.selectbox("เลือกประเภทงานสนับสนุน/คำสั่งเฉพาะกิจ:", [
                "กำหนดเอง / AI สกัดจากคำสั่ง",
                "กรรมการบริหารหลักสูตร (8 ชม.)",
                "อาจารย์ที่ปรึกษาหมู่เรียน (2-3 ชม.)",
                "คณะกรรมการตรวจรับพัสดุ / TOR (1 ชม.)",
                "ปฏิบัติงานตามคำสั่งเฉพาะกิจ มหาวิทยาลัย/คณะ (0.5 ชม.)",
                "อบรม/สัมมนาพัฒนาตนเอง (0.5 ชม./วัน)"
            ])
            if "กรรมการบริหารหลักสูตร" in preset_option: default_hours = 8.0; calc_formula_str = "(= 8 ภาระงาน)"; suggested_title = "กรรมการบริหารหลักสูตร..."
            elif "อาจารย์ที่ปรึกษาหมู่เรียน" in preset_option: default_hours = 3.0; calc_formula_str = "(= 3 ภาระงาน)"; suggested_title = "อาจารย์ที่ปรึกษาหมู่เรียนนักศึกษาชั้นปีที่..."
            elif "คำสั่งเฉพาะกิจ" in preset_option: default_hours = 0.5; calc_formula_str = "(= 1 คำสั่ง x 0.5) = 0.5 ชม."; suggested_title = "คณะกรรมการดำเนินงานพิธี/กิจกรรมเฉพาะกิจ..."

        st.markdown("---")
        st.markdown("📌 **กรอกรายละเอียดองค์ประกอบเพื่อสร้างข้อความทางการ:**")
        
        project_title = st.text_input("1. ชื่อบทบาท / โครงการ / ผลงาน:", value=suggested_title if suggested_title else "วิทยากรโครงการอบรมเชิงปฏิบัติการ...")
        location_host = st.text_input("2. สถานที่จัด / หน่วยงานผู้จัด:", value="ณ ทัณฑสถานหญิงสงขลา")
        date_range = st.text_input("3. วันที่ปฏิบัติงาน:", value="ระหว่างวันที่ 16, 17, 22, 23, 24 มิถุนายน 2569")
        order_ref = st.text_input("4. เลขที่คำสั่ง / หนังสืออ้างอิง:", value="คำสั่งคณะศิลปกรรมศาสตร์ ที่ 046/2569")
        
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            formula_input = st.text_input("5. สูตรการคำนวณ (ในวงเล็บ):", value=calc_formula_str if calc_formula_str else "(3ชมx5วันx0.5)")
        with col_f2:
            final_hours_num = st.number_input("6. สรุปชั่วโมงภาระงานสุทธิ:", value=float(default_hours), step=0.5)

        input_method = st.radio("แนบไฟล์คำสั่งอ้างอิง (ถ้ามี):", ["📤 อัปโหลด PDF/รูปภาพ", "📷 ถ่ายรูปจากมือถือ", "🚫 ไม่แนบไฟล์"])
        uploaded_file = None
        if "อัปโหลด" in input_method:
            uploaded_file = st.file_uploader("แนบคำสั่ง/ประกาศ (PDF, JPG, PNG):", type=["pdf", "png", "jpg", "jpeg"])
        elif "ถ่ายรูป" in input_method:
            uploaded_file = st.camera_input("ถ่ายภาพคำสั่งจากกล้องมือถือ")

        btn_format = st.button("🤖 ให้ AI สกัดและเรียบเรียงข้อความทางการ", type="primary", use_container_width=True)

    with col_b:
        st.subheader("🤖 ขั้นตอนที่ 2: ข้อความเรียบเรียงทางการสำหรับไฟล์ Word")
        
        # สร้างข้อความเรียบเรียงตามรูปแบบมาตรฐาน มรภ.สงขลา
        formatted_text = f"{project_title} {location_host} {date_range} ({order_ref}) = {formula_input} = {final_hours_num:.1f} ชม."
        
        if btn_format or "current_formatted" not in st.session_state:
            st.session_state["current_formatted"] = {
                "หมวดงาน": category,
                "รายการภาระงาน": formatted_text,
                "เลขคำสั่ง_อ้างอิง": order_ref,
                "วันที่": date_range,
                "ภาระงาน_ชม": float(final_hours_num)
            }

        curr = st.session_state["current_formatted"]

        st.markdown("""<div class="card-box">
            <h4 style="color:#1E3A8A; margin-top:0;">✨ ตัวอย่างข้อความที่จะปรากฏใน แบบ ป-มร.สข. 01:</h4>
        </div>""", unsafe_allow_html=True)
        
        # กล่องแสดงพรีวิวข้อความภาษาทางการ
        edited_formatted_text = st.text_area(
            "✏️ สามารถตรวจสอบและแก้ไขข้อความทางการได้ที่นี่:",
            value=curr["รายการภาระงาน"],
            height=120
        )

        st.markdown(f"""
        <div class="formatted-preview">
            <b>📂 หมวดงาน:</b> {curr['หมวดงาน']}<br>
            <b>📄 เลขคำสั่ง:</b> {order_ref}<br>
            <b>📊 ชั่วโมงภาระงาน:</b> <span style="color:green; font-size:1.2rem; font-weight:bold;">{final_hours_num:.1f} ภาระงาน</span>
        </div>
        """, unsafe_allow_html=True)

        if st.button("💾 บันทึกลงคลังภาระงานสะสม (ซิงค์ Google Sheets)", type="primary", use_container_width=True):
            new_row = {
                "email": user_email,
                "หมวดงาน": category,
                "รายการภาระงาน": edited_formatted_text,
                "เลขคำสั่ง_อ้างอิง": order_ref,
                "วันที่": date_range,
                "ภาระงาน_ชม": float(final_hours_num),
                "วันที่บันทึก": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            
            updated_all_df = pd.concat([all_data_df, pd.DataFrame([new_row])], ignore_index=True)
            if save_all_data(updated_all_df):
                st.balloons()
                st.success("🎉 บันทึกรายการภาระงานเข้าคลังเรียบร้อยแล้ว!")
                st.rerun()

# ---------------------------------------------------------
# TAB 2: คลังภาระงานสะสม (ซิงค์ Cloud / Local)
# ---------------------------------------------------------
with tab2:
    st.subheader(f"📊 คลังภาระงานสะสมของ: {user_email}")
    
    current_all_df = load_all_data()
    user_df = current_all_df[current_all_df["email"] == user_email].copy() if "email" in current_all_df.columns and not current_all_df.empty else pd.DataFrame()
    
    if user_df.empty or len(user_df) == 0:
        st.info("👋 ขณะนี้คลังภาระงานของคุณว่างเปล่า สามารถเริ่มบันทึกรายการแรกได้ใน Tab 1 ครับ")
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
            key="user_data_editor_v7"
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
                    st.warning("เคลียร์คลังภาระงานเรียบร้อยแล้ว!")
                    st.rerun()

# ---------------------------------------------------------
# TAB 3: สรุปแบบ ป-มร.สข. 01 & ดาวน์โหลดไฟล์ Word (.docx)
# ---------------------------------------------------------
with tab3:
    st.subheader("📋 สรุปผลการประเมินภาระงานและสร้างไฟล์ Word (ป-มร.สข. 01)")
    
    current_all_df = load_all_data()
    user_df = current_all_df[current_all_df["email"] == user_email].copy() if "email" in current_all_df.columns and not current_all_df.empty else pd.DataFrame()
    
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

    # ฟังก์ชันสร้างไฟล์ Word (.docx) พร้อมเรียบเรียงข้อความทางการครบถ้วน
    def generate_docx_v7():
        buffer = io.BytesIO()
        try:
            from docx import Document
            from docx.shared import Pt, Inches, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            
            doc = Document()
            
            # หัวกระดาษเอกสาร
            title_p = doc.add_paragraph()
            title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run_title = title_p.add_run('แบบสรุปการประเมินผลการปฏิบัติราชการของบุคลากรสายวิชาการ (ป-มร.สข. 01)')
            run_title.bold = True
            run_title.font.size = Pt(16)
            
            p_sub = doc.add_paragraph()
            p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_sub.add_run(f'มหาวิทยาลัยราชภัฏสงขลา | รอบการประเมิน {datetime.now().strftime("%Y")}')
            
            doc.add_paragraph(f'ผู้รับการประเมิน: {user_email}')
            doc.add_paragraph(f'ตำแหน่ง/สังกัด: {role}')
            doc.add_paragraph(f'กลุ่มการประเมิน: {track_type}')
            doc.add_paragraph(f'วันที่ออกรายงาน: {datetime.now().strftime("%d/%m/%Y")}')
            
            doc.add_heading('1. สรุปคะแนนการประเมินผลการปฏิบัติงาน', level=2)
            doc.add_paragraph(f'• องค์ประกอบที่ 1 (ผลสัมฤทธิ์ของงาน): {score_component1:.2f} / 70 คะแนน')
            doc.add_paragraph(f'• องค์ประกอบที่ 2 (พฤติกรรม/สมรรถนะ): {competency_score:.2f} / 30 คะแนน')
            doc.add_paragraph(f'• คะแนนรวมสุทธิ: {total_score:.2f} / 100 คะแนน (ระดับผลการประเมิน: {grade_text})')
            
            doc.add_heading('2. รายละเอียดภาระงานสะสม (เรียบเรียงภาษาทางการ)', level=2)
            
            # ตารางแสดงภาระงาน
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
            buffer.write(f"SKRU Workload Report v7\nUser: {user_email}\nTotal Hours: {total_actual_hours}\nScore: {total_score}".encode('utf-8'))
            buffer.seek(0)
            return buffer

    docx_file = generate_docx_v7()
    
    st.download_button(
        label="📥 ดาวน์โหลดแบบสรุป ป-มร.สข. 01 (.docx)",
        data=docx_file,
        file_name=f"ป-มร.สข.01_{user_email.split('@')[0]}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary"
    )
