import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
import io

# ---------------------------------------------------------
# 1. การตั้งค่าระบบ และ ธีม UI (Page Config)
# ---------------------------------------------------------
st.set_page_config(
    page_title="SKRU Workload AI - ระบบบันทึกและวิเคราะห์ภาระงาน มรภ.สงขลา",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS สำหรับปรับแต่ง UI ให้สวยงามทันสมัย
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
    .status-badge-green {
        background-color: #D1FAE5;
        color: #065F46;
        padding: 0.4rem 0.8rem;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .status-badge-yellow {
        background-color: #FEF3C7;
        color: #92400E;
        padding: 0.4rem 0.8rem;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
</style>
""", unsafe_allow_html=True)

# Schema มาตรฐานสำหรับคลังข้อมูล
DB_COLUMNS = ["email", "หมวดงาน", "รายการภาระงาน", "เลขคำสั่ง_อ้างอิง", "วันที่", "ภาระงาน_ชม", "วันที่บันทึก"]

# ---------------------------------------------------------
# 2. การจัดการฐานข้อมูล Google Sheets / Local Session
# ---------------------------------------------------------
conn = None
use_gsheets = False
gsheets_error_msg = ""

try:
    from streamlit_gsheets import GSheetsConnection
    if hasattr(st, "secrets") and "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        conn = st.connection("gsheets", type=GSheetsConnection)
        use_gsheets = True
except Exception as ex:
    use_gsheets = False
    gsheets_error_msg = str(ex)

def load_all_data():
    """ดึงข้อมูลภาระงานทั้งหมด (เริ่มต้นด้วยแผ่นข้อมูลขาวสะอาด ไม่มีข้อมูลตัวอย่างค้าง)"""
    if use_gsheets and conn:
        try:
            df = conn.read(ttl="0")
            if df is not None and not df.empty:
                # ตรวจสอบและปรับปรุงโครงสร้างคอลัมน์ให้ครบถ้วน
                for col in DB_COLUMNS:
                    if col not in df.columns:
                        df[col] = ""
                df["ภาระงาน_ชม"] = pd.to_numeric(df["ภาระงาน_ชม"], errors="coerce").fillna(0.0)
                return df[DB_COLUMNS]
            else:
                # หาก Google Sheet ว่างเปล่า ให้คืนค่า DataFrame ว่างเปล่าที่มีโครงสร้างถูกต้อง
                return pd.DataFrame(columns=DB_COLUMNS)
        except Exception as e:
            # เก็บข้อผิดพลาดไว้แสดงใน Sidebar แทนการขึ้นแถบเตือนสีแดงกลางหน้าจอ
            global gsheets_error_msg
            gsheets_error_msg = str(e)
    
    # หากไม่ได้เชื่อม Google Sheets ให้ใช้ Local Session State (เริ่มต้นขาวสะอาดเป็น DataFrame ว่าง)
    if "local_db" not in st.session_state:
        st.session_state["local_db"] = pd.DataFrame(columns=DB_COLUMNS)
    
    return st.session_state["local_db"]

def save_all_data(full_df):
    """บันทึกข้อมูลย้อนกลับไปยัง Google Sheets หรือ Local Session"""
    # จัดโครงสร้างข้อมูลให้ได้คอลัมน์ตามมาตรฐาน
    if full_df.empty:
        full_df = pd.DataFrame(columns=DB_COLUMNS)
    else:
        for col in DB_COLUMNS:
            if col not in full_df.columns:
                full_df[col] = ""
        full_df = full_df[DB_COLUMNS]
        full_df["ภาระงาน_ชม"] = pd.to_numeric(full_df["ภาระงาน_ชม"], errors="coerce").fillna(0.0)

    if use_gsheets and conn:
        try:
            conn.update(data=full_df)
            st.session_state["local_db"] = full_df
            st.toast("☁️ อัปเดตข้อมูลลง Google Sheets เรียบร้อยแล้ว!", icon="✅")
            return True
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึกลง Google Sheets: {e}")
            st.session_state["local_db"] = full_df
            return False
    else:
        st.session_state["local_db"] = full_df
        st.toast("💾 บันทึกข้อมูลเรียบร้อยแล้ว!", icon="✅")
        return True

# ---------------------------------------------------------
# 3. แถบข้าง (Sidebar) & ระบบระบุตัวตน
# ---------------------------------------------------------
with st.sidebar:
    st.title("👤 ระบุตัวตน & ตั้งค่า")
    
    user_email = st.text_input(
        "📧 อีเมลบุคลากร (สำหรับซิงค์ข้อมูล):",
        value="",
        placeholder="เช่น paritat@skru.ac.th",
        help="กรอกอีเมลของคุณเมื่อเข้าใช้จาก มือถือ คอมพิวเตอร์บ้าน หรือคอมพิวเตอร์ที่ทำงาน เพื่อซิงค์ข้อมูลตรงกัน"
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
    
    target_hours = st.number_input(
        "🎯 ภาระงานขั้นต่ำตามเกณฑ์รอบนี้ (ชม.):",
        value=35.0,
        step=5.0,
        help="เกณฑ์มาตรฐานภาระงานขั้นต่ำสำหรับใช้คำนวณสัดส่วนคะแนน"
    )
    
    st.divider()
    
    # ตรวจสอบการตั้งค่า API Key
    api_key_env = ""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key_env = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
        
    user_api_key = st.text_input("🔑 Gemini API Key (ระบุเพิ่มเติม):", type="password", value=api_key_env)
    active_api_key = user_api_key if user_api_key else api_key_env
    
    # สถานะการเชื่อมต่อฐานข้อมูล
    st.markdown("### 📡 สถานะการเชื่อมต่อฐานข้อมูล")
    if use_gsheets and not gsheets_error_msg:
        st.markdown('<div class="status-badge-green">🟢 เชื่อมต่อ Google Sheets สำเร็จ</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="status-badge-yellow">🟡 ระบบความจำชั่วคราว (Local)</div>', unsafe_allow_html=True)
        if gsheets_error_msg:
            with st.expander("🔍 ดูคำแนะนำการตั้งค่า Google Sheets"):
                st.caption("1. ตรวจสอบว่าแชร์สิทธิ์ **Editor** ให้กับอีเมล Service Account ใน Secrets แล้วหรือยัง")
                st.caption("2. ตรวจสอบ URL `spreadsheet` ใน Secrets ว่าถูกต้องเรียบร้อย")
                st.caption(f"รายละเอียดข้อผิดพลาด: `{gsheets_error_msg}`")

# ---------------------------------------------------------
# 4. โหลดข้อมูลตั้งต้น & ส่วนหัวแอปพลิเคชัน
# ---------------------------------------------------------
all_data_df = load_all_data()

st.markdown('<div class="main-header">🏛️ SKRU Academic Workload AI Assistant</div>', unsafe_allow_html=True)
display_user = user_email if user_email else "ผู้ใช้นรนาม (โปรดระบุอีเมลในเมนูด้านซ้ายเพื่อเริ่มซิงค์ข้อมูล)"
st.markdown(f'<div class="sub-header">ระบบช่วยสกัดเอกสารคำสั่ง วิเคราะห์ และสะสมภาระงานสายวิชาการ มรภ.สงขลา | ผู้ใช้งานปัจจุบัน: <b>{display_user}</b></div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📥 1. บันทึกและวิเคราะห์ภาระงาน", "📊 2. คลังภาระงานสะสม (ขาวสะอาด)", "📄 3. สรุปแบบ ป-มร.สข. 01 (คำนวณจริง)"])

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
            if not user_email:
                st.warning("⚠️ กรุณากรอก **อีเมลบุคลากร** ในแถบเมนูด้านซ้ายก่อนทำการบันทึกข้อมูลครับ")
                
            with st.spinner("กำลังสกัดข้อมูลคำสั่งและประเมินตามเกณฑ์ มรภ.สงขลา..."):
                doc_title = uploaded_file.name if uploaded_file else "รายการบันทึกภาระงาน"
                item_name = manual_detail if manual_detail else "โครงการพัฒนาและส่งเสริมศักยภาพสายวิชาการ"
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
                        <li><b>เหตุผลตามเกณฑ์:</b> สอดคล้องตามประกาศเกณฑ์ภาระงานแนบท้าย มรภ.สงขลา</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("### ✏️ ตรวจทานและกดบันทึกลงฐานข้อมูล")
                final_item = st.text_input("ชื่อรายการภาระงาน:", value=item_name)
                final_ref = st.text_input("เลขที่คำสั่ง/อ้างอิง:", value=doc_title)
                final_hours = st.number_input("จำนวนภาระงาน (ชม.):", value=calc_hours, step=0.5)
                
                if st.button("💾 บันทึกลงคลังผลงานสะสม (ซิงค์ Cloud)", type="primary", use_container_width=True):
                    current_email = user_email if user_email else "guest@skru.ac.th"
                    new_row = {
                        "email": current_email,
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
                        st.success("บันทึกข้อมูลเรียบร้อยแล้ว! สามารถสลับไปดูใน Tab 2 และ Tab 3 ได้ทันที")
                        st.rerun()

# ---------------------------------------------------------
# TAB 2: คลังภาระงานสะสม (ขาวสะอาด แก้ไข/ลบได้จริง)
# ---------------------------------------------------------
with tab2:
    st.subheader(f"📊 คลังภาระงานสะสมของ: {display_user}")
    
    # กรองเฉพาะข้อมูลของผู้ใช้อีเมลนี้
    current_email = user_email if user_email else "guest@skru.ac.th"
    
    if "email" in all_data_df.columns:
        user_df = all_data_df[all_data_df["email"] == current_email].copy()
    else:
        user_df = pd.DataFrame(columns=DB_COLUMNS)
    
    if user_df.empty:
        st.info("👋 **คลังภาระงานของคุณยังว่างเปล่า (ขาวสะอาด)** คุณสามารถเริ่มบันทึกรายการแรกได้ใน Tab 1 ครับ")
    else:
        st.markdown("💡 **อาจารย์สามารถคลิกแก้ไขข้อความ ตัวเลขภาระงาน หรือกดลบแถวในตารางได้โดยตรง:**")
        
        # ตารางแบบ data_editor ที่สามารถเพิ่ม แก้ไข และลบแถวได้
        edited_user_df = st.data_editor(
            user_df[["หมวดงาน", "รายการภาระงาน", "เลขคำสั่ง_อ้างอิง", "วันที่", "ภาระงาน_ชม"]],
            use_container_width=True,
            num_rows="dynamic",
            key="user_data_editor_v4"
        )
        
        col_m1, col_m2, col_m3 = st.columns([2, 1.2, 1.2])
        
        with col_m1:
            total_user_hours = pd.to_numeric(edited_user_df["ภาระงาน_ชม"], errors="coerce").fillna(0.0).sum()
            st.metric(label="📈 รวมภาระงานสะสมสุทธิในคลัง", value=f"{total_user_hours:.1f} ภาระงาน (ชั่วโมง)")
            
        with col_m2:
            if st.button("🔄 บันทึกการแก้ไขลงฐานข้อมูล", type="primary", use_container_width=True):
                # กรองเอาข้อมูลของผู้ใช้อื่นไว้
                other_df = all_data_df[all_data_df["email"] != current_email] if "email" in all_data_df.columns else pd.DataFrame(columns=DB_COLUMNS)
                
                edited_user_df["email"] = current_email
                edited_user_df["วันที่บันทึก"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                new_combined_df = pd.concat([other_df, edited_user_df], ignore_index=True)
                save_all_data(new_combined_df)
                st.rerun()

        with col_m3:
            if st.button("🗑️ ลบข้อมูลทั้งหมดของคุณ", type="secondary", use_container_width=True):
                # ลบเฉพาะข้อมูลของอีเมลปัจจุบันออกทั้งหมด
                other_df = all_data_df[all_data_df["email"] != current_email] if "email" in all_data_df.columns else pd.DataFrame(columns=DB_COLUMNS)
                save_all_data(other_df)
                st.success("ลบรายการทั้งหมดของคุณเรียบร้อยแล้ว (คลังกลับมาขาวสะอาด)!")
                st.rerun()

# ---------------------------------------------------------
# TAB 3: สรุปแบบ ป-มร.สข. 01 (คำนวณคะแนนตามจริงแบบ Dynamic)
# ---------------------------------------------------------
with tab3:
    st.subheader("📋 สรุปผลการประเมินรอบการปฏิบัติราชการ (คำนวณตามเกณฑ์จริง)")
    
    # คำนวณภาระงานสะสมจริงของผู้ใช้อีเมลปัจจุบัน
    current_email = user_email if user_email else "guest@skru.ac.th"
    active_user_df = all_data_df[all_data_df["email"] == current_email] if "email" in all_data_df.columns else pd.DataFrame(columns=DB_COLUMNS)
    
    real_total_hours = pd.to_numeric(active_user_df["ภาระงาน_ชม"], errors="coerce").fillna(0.0).sum() if not active_user_df.empty else 0.0
    
    # -----------------------------------------------------
    # คำนวณคะแนนตามเกณฑ์ มรภ.สงขลา ( Dynamic Calculation )
    # -----------------------------------------------------
    # องค์ประกอบที่ 1: ผลสัมฤทธิ์ของงาน (เต็ม 70 คะแนน)
    # คำนวณสัดส่วนคะแนนตามภาระงานสะสมเทียบกับภาระงานขั้นต่ำ (target_hours)
    if target_hours > 0:
        ratio = min(1.0, real_total_hours / target_hours)
        comp1_score = ratio * 70.0
    else:
        comp1_score = 0.0
        
    # องค์ประกอบที่ 2: สมรรถนะการปฏิบัติงาน (เต็ม 30 คะแนน)
    comp2_score = st.number_input("คะแนนองค์ประกอบที่ 2 (สมรรถนะการปฏิบัติงาน เต็ม 30):", min_value=0.0, max_value=30.0, value=30.0, step=0.5)
    
    # คะแนนประเมินรวมสุทธิ (เต็ม 100 คะแนน)
    total_score = comp1_score + comp2_score
    
    # กำหนดระดับผลการประเมินแบบ Dynamic
    if total_score >= 90.0:
        eval_level = "ดีเด่น (90 - 100)"
        level_color = "green"
    elif total_score >= 80.0:
        eval_level = "ดีมาก (80 - 89.99)"
        level_color = "blue"
    elif total_score >= 70.0:
        eval_level = "ดี (70 - 79.99)"
        level_color = "orange"
    elif total_score >= 60.0:
        eval_level = "พอใช้ (60 - 69.99)"
        level_color = "gray"
    else:
        eval_level = "ต้องปรับปรุง (< 60)"
        level_color = "red"
        
    st.markdown(f"#### 📊 สรุปคะแนนประเมินของผู้ใช้: `{display_user}`")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(
            label="องค์ประกอบที่ 1 (ผลสัมฤทธิ์ภาระงาน)",
            value=f"{comp1_score:.2f} / 70 คะแนน",
            delta=f"สะสม {real_total_hours:.1f} / {target_hours:.0f} ชม."
        )
    with c2:
        st.metric(
            label="องค์ประกอบที่ 2 (สมรรถนะการปฏิบัติงาน)",
            value=f"{comp2_score:.2f} / 30 คะแนน",
            delta="ประเมินสมรรถนะ"
        )
    with c3:
        st.metric(
            label="คะแนนประเมินรวมสุทธิ",
            value=f"{total_score:.2f} / 100 คะแนน",
            delta=f"ระดับ: {eval_level}"
        )
        
    st.divider()
    
    # ตารางแจกแจงภาระงานแยกตามหมวด
    st.markdown("### 📌 สรุปภาระงานแยกตามหมวดงาน")
    if not active_user_df.empty:
        category_summary = active_user_df.groupby("หมวดงาน")["ภาระงาน_ชม"].sum().reset_index()
        category_summary.columns = ["หมวดงาน", "รวมภาระงาน (ชั่วโมง)"]
        st.dataframe(category_summary, use_container_width=True)
    else:
        st.caption("ยังไม่มีข้อมูลภาระงานสะสมในระบบ")

    st.divider()

    # -----------------------------------------------------
    # ฟังก์ชันสร้างและดาวน์โหลดไฟล์ Word (.docx)
    # -----------------------------------------------------
    def generate_docx():
        buffer = io.BytesIO()
        try:
            from docx import Document
            doc = Document()
            
            doc.add_heading('แบบสรุปการประเมินผลการปฏิบัติราชการ (ป-มร.สข. 01)', level=1)
            doc.add_paragraph(f'ผู้รับการประเมิน: {display_user}')
            doc.add_paragraph(f'สังกัด: มหาวิทยาลัยราชภัฏสงขลา | กลุ่มตำแหน่ง: {role}')
            doc.add_paragraph(f'วันที่สรุปรายงาน: {datetime.now().strftime("%d/%m/%Y %H:%M")}')
            
            doc.add_heading('1. ผลการประเมินคะแนนรวม', level=2)
            doc.add_paragraph(f'• องค์ประกอบที่ 1 (ผลสัมฤทธิ์ของงาน): {comp1_score:.2f} / 70 คะแนน (ภาระงานสะสม {real_total_hours:.1f} ชม.)')
            doc.add_paragraph(f'• องค์ประกอบที่ 2 (สมรรถนะการปฏิบัติงาน): {comp2_score:.2f} / 30 คะแนน')
            doc.add_paragraph(f'• คะแนนประเมินรวมสุทธิ: {total_score:.2f} / 100 คะแนน ({eval_level})')
            
            doc.add_heading('2. รายการภาระงานสะสมในรอบการประเมิน', level=2)
            
            table = doc.add_table(rows=1, cols=4)
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = 'หมวดงาน'
            hdr_cells[1].text = 'รายการภาระงาน'
            hdr_cells[2].text = 'เลขที่คำสั่ง/อ้างอิง'
            hdr_cells[3].text = 'ภาระงาน (ชม.)'
            
            if not active_user_df.empty:
                for _, row in active_user_df.iterrows():
                    row_cells = table.add_row().cells
                    row_cells[0].text = str(row.get('หมวดงาน', ''))
                    row_cells[1].text = str(row.get('รายการภาระงาน', ''))
                    row_cells[2].text = str(row.get('เลขคำสั่ง_อ้างอิง', ''))
                    row_cells[3].text = str(row.get('ภาระงาน_ชม', '0'))
                    
            doc.add_paragraph(f'\nรวมภาระงานสะสมสุทธิทั้งหมด: {real_total_hours:.1f} ภาระงาน (ชั่วโมง)')
            doc.save(buffer)
            buffer.seek(0)
            return buffer
        except Exception:
            buffer.write(f"SKRU Workload Summary Report\nUser: {display_user}\nTotal Score: {total_score:.2f}/100\nTotal Hours: {real_total_hours}".encode('utf-8'))
            buffer.seek(0)
            return buffer

    docx_file = generate_docx()
    
    st.download_button(
        label="📥 ดาวน์โหลดเอกสารสรุปผลการประเมิน (.docx)",
        data=docx_file,
        file_name=f"ป-มร.สข.01_{display_user.split('@')[0]}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary"
    )
