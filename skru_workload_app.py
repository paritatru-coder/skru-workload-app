import streamlit as st
import pandas as pd
import json
import io
import re
import time
import base64
import mimetypes
from datetime import datetime
import requests

# ---------------------------------------------------------
# Optional Dependencies (Graceful Degradation)
# ---------------------------------------------------------
try:
    import fitz  # PyMuPDF สำหรับแปลงหน้า PDF เป็นรูปภาพ
except ImportError:
    fitz = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

APP_VERSION = "v15-Pro"

CATEGORIES = [
    "1. ภาระงานสอน",
    "2. ภาระงานวิจัย / งานประพันธ์ / งานสร้างสรรค์",
    "3. ภาระงานบริการวิชาการ",
    "4. ภาระงานทำนุบำรุงศิลปวัฒนธรรม",
    "5. ภาระงานอื่น ๆ / งานสนับสนุน / คำสั่งเฉพาะกิจ",
    "6. งานประกันคุณภาพการศึกษา (QA)",
    "7. งานบริหาร / ตำแหน่งทางวิชาการ",
]
AUTO_CATEGORY = "ให้ AI ประเมินหมวดงานอัตโนมัติ"
DB_COLUMNS = ["email", "หมวดงาน", "รายการภาระงาน", "เลขคำสั่ง_อ้างอิง", "วันที่", "ภาระงาน_ชม", "วันที่บันทึก"]

DEFAULT_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
MAX_INLINE_BYTES = 10 * 1024 * 1024  # 10MB limit สำหรับ inline PDF

# ---------------------------------------------------------
# 1. Page Config & Custom Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title=f"SKRU Workload AI ({APP_VERSION})",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-header { color: #1E3A8A; font-size: 2.2rem; font-weight: 700; margin-bottom: 0.2rem; }
    .sub-header { color: #4B5563; font-size: 1.05rem; margin-bottom: 1.2rem; }
    .success-alert { background-color: #DCFCE7; border: 2px solid #22C55E; color: #15803D; padding: 1rem; border-radius: 8px; font-weight: bold; margin-bottom: 1rem; }
    .info-alert { background-color: #EFF6FF; border: 1px solid #93C5FD; color: #1E40AF; padding: 0.8rem; border-radius: 8px; margin-bottom: 1rem; }
    .warning-alert { background-color: #FEF08A; border: 1px solid #EAB308; color: #854D0E; padding: 0.8rem; border-radius: 8px; margin-bottom: 1rem; }
    .formatted-preview { background-color: #F0F9FF; border: 1px solid #BAE6FD; border-radius: 8px; padding: 1rem; color: #0369A1; font-weight: 500; margin-top: 0.5rem; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. Database Manager
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

def ensure_schema(df):
    if df is None or df.empty:
        df = pd.DataFrame(columns=DB_COLUMNS)
    df = df.copy()
    for c in DB_COLUMNS:
        if c not in df.columns:
            df[c] = 0.0 if c == "ภาระงาน_ชม" else ""
    df["ภาระงาน_ชม"] = pd.to_numeric(df["ภาระงาน_ชม"], errors="coerce").fillna(0.0)
    for c in DB_COLUMNS:
        if c != "ภาระงาน_ชม":
            df[c] = df[c].fillna("").astype(str)
    return df[DB_COLUMNS]

def load_all_data():
    if use_gsheets and conn:
        try:
            df = conn.read(ttl="0")
            if df is not None and not df.empty:
                return ensure_schema(df.dropna(how="all"))
        except Exception:
            pass
    if "local_db" not in st.session_state:
        st.session_state["local_db"] = pd.DataFrame(columns=DB_COLUMNS)
    return ensure_schema(st.session_state["local_db"])

def save_all_data(full_df):
    full_df = ensure_schema(full_df)
    if use_gsheets and conn:
        try:
            conn.update(data=full_df)
            st.session_state["local_db"] = full_df
            return True, "Google Sheets"
        except Exception as e:
            st.session_state["local_db"] = full_df
            return False, str(e)
    st.session_state["local_db"] = full_df
    return True, "Local Session"

# ---------------------------------------------------------
# 3. PDF Handling & Image Rendering
# ---------------------------------------------------------
def render_pdf_to_images(file_bytes, max_pages=5, zoom=2.0):
    """แปลง PDF เป็นรูปภาพเพื่อส่งเข้า Vision API (แก้ปัญหา Image/Scan PDF)"""
    if fitz is None:
        raise RuntimeError("ไม่พบไลบรารี PyMuPDF (fitz) ไม่สามารถแปลง PDF สแกนเป็นรูปภาพได้")
    images = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            if i >= max_pages: break
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            images.append(pix.tobytes("png"))
    if not images:
        raise RuntimeError("ไม่พบหน้าใน PDF")
    return images

# ---------------------------------------------------------
# 4. Gemini API Engine
# ---------------------------------------------------------
class GeminiError(Exception): pass

RUBRIC_TEXT = """
เกณฑ์ภาระงาน มรภ.สงขลา (สรุปสั้น):
- งานสร้างสรรค์/วิจัย: นานาชาติได้รับรางวัล/ดีเยี่ยม = 24 ชม., นานาชาติไม่รางวัล = 21, อาเซียนรางวัล = 18, ระดับชาติรางวัล = 10
- บริการวิชาการ: ผู้รับผิดชอบหลัก 5, วิทยากร 0.5 ชม./1 ชม.
- ศิลปวัฒนธรรม: ประธาน 1 ชม./วัน, กรรมการ/เข้าร่วม 0.5 ชม./วัน
- พัฒนานักศึกษา/อื่นๆ: ที่ปรึกษาโครงงาน 1 ชม./คน, อบรมพัฒนาตนเองในประเทศ 1 ชม./วันทำการ
"""

def build_prompt(category_hint):
    hint = f"\nหมวดงานเบื้องต้น: {category_hint}\n" if category_hint != AUTO_CATEGORY else "\n"
    return (
        "คุณคือนักวิเคราะห์ข้อมูลมืออาชีพ สกัดข้อมูลจากเอกสารทางการไทย\n"
        + hint +
        "กฎเหล็ก:\n"
        "1. ห้ามนำชื่อไฟล์ (เช่น .pdf, .jpg) มาใช้ในช่อง title, venue, หรือ ref เด็ดขาด\n"
        "2. ดึงเฉพาะ 'ชื่อผลงาน/โครงการจริง', 'สถานที่จัดจริง', 'วันที่จริง' (เช่น 16 มิ.ย. 2569) และ 'เลขที่คำสั่งอ้างอิงจริง' จากข้อความในเอกสาร\n"
        "3. หากเป็นงานระดับ 'นานาชาติ' (International) และมีคำว่า 'ดีเยี่ยม', 'Excellent', 'รางวัล', 'Award' ให้กำหนด has_award = true\n"
        "4. หากไม่พบข้อมูลใดให้ใส่ค่าว่าง \"\" ห้ามจินตนาการข้อมูลเอง\n"
        + RUBRIC_TEXT +
        "\nส่งกลับเป็น JSON ล้วนๆ ห้ามมี Markdown ตามโครงสร้างนี้:\n"
        '{"category": "", "title": "", "venue": "", "date": "", "ref": "", "level": "นานาชาติ/ชาติ/อื่นๆ", "has_award": false, "formula": "", "hours": 0.0, "notes": ""}'
    )

def call_gemini(api_key, models, parts):
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    
    last_err = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=45)
            if resp.status_code == 200:
                cands = resp.json().get("candidates", [])
                if cands:
                    text_out = cands[0]["content"]["parts"][0]["text"]
                    text_clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text_out.strip(), flags=re.I)
                    return json.loads(text_clean), model
            elif resp.status_code in (401, 403, 400):
                if "API_KEY" in resp.text: raise GeminiError("API Key ไม่ถูกต้อง")
        except requests.RequestException as e:
            last_err = str(e)
            continue
        except json.JSONDecodeError:
            last_err = "AI ไม่ได้ตอบกลับเป็น JSON"
            continue
    raise GeminiError(f"ไม่สามารถเชื่อมต่อ Gemini ได้: {last_err}")

# ---------------------------------------------------------
# 5. Core Logic & Normalization
# ---------------------------------------------------------
def clean_filename_from_text(val, filename):
    if not val: return ""
    v = str(val).strip()
    if filename and (filename.lower() in v.lower() or v.lower() in filename.lower()):
        return ""
    if re.search(r'\.(pdf|png|jpe?g)$', v, re.I):
        return ""
    return v

def finalize_result(raw, filename, hint):
    cat = raw.get("category", "")
    if cat not in CATEGORIES:
        cat = hint if hint in CATEGORIES else CATEGORIES[1]
        
    title = clean_filename_from_text(raw.get("title"), filename)
    venue = clean_filename_from_text(raw.get("venue"), filename)
    ref = clean_filename_from_text(raw.get("ref"), filename)
    date = str(raw.get("date", "")).strip()
    formula = str(raw.get("formula", "")).strip()
    
    try: hours = float(raw.get("hours", 0.0))
    except: hours = 0.0
    
    is_intl = "นานาชาติ" in str(raw.get("level", "")) or "international" in str(raw.get("level", "")).lower()
    has_award = raw.get("has_award", False)
    rule_applied = False
    
    # กฎเหล็ก: งานสร้างสรรค์/วิจัย นานาชาติ + รางวัล/ดีเยี่ยม = 24.0 เสมอ
    if cat.startswith("2.") and is_intl and has_award:
        hours = 24.0
        formula = "(นับสิทธิ์เผยแพร่นานาชาติ ระดับดีเยี่ยม/ได้รับรางวัล = 24 ภาระงาน)"
        rule_applied = True
        
    parts = [p for p in [title, venue, date] if p]
    head = " ".join(parts)
    if ref: head += f" ({ref})"
    formal = f"{head} = {formula} = {hours:.1f} ชม." if formula else f"{head} = {hours:.1f} ชม."
    
    return {
        "cat": cat, "title": title, "venue": venue, "date": date, "ref": ref,
        "formula": formula, "hours": hours, "formal": formal,
        "notes": raw.get("notes", ""), "rule_applied": rule_applied
    }

# ---------------------------------------------------------
# 6. UI & App Flow
# ---------------------------------------------------------
with st.sidebar:
    st.title("👤 ระบุตัวตน & ตั้งค่า")
    email = st.text_input("📧 อีเมลบุคลากร:", value=st.session_state.get("email_saved", ""), key="email_input")
    if email: st.session_state["email_saved"] = email.strip()
    
    role = st.selectbox("🏛️ ตำแหน่ง:", ["อาจารย์สายสอน", "ประธานหลักสูตร (15)", "รองคณบดี (25)"])
    
    api_key_env = st.secrets.get("GEMINI_API_KEY", "") if hasattr(st, "secrets") else ""
    user_api = st.text_input("🔑 Gemini API Key:", type="password", placeholder="ใช้ Secret อยู่" if api_key_env else "ใส่ API Key")
    active_api = user_api.strip() or api_key_env
    
    if active_api: st.success("🟢 พบ API Key", icon="🔑")
    else: st.warning("🟡 ไม่มี API Key (ใช้งานได้เฉพาะกรอกเอง)", icon="⚠️")
    if fitz is None: st.caption("ℹ️ ไม่พบ PyMuPDF (ไม่สามารถอ่าน PDF แบบสแกนภาพได้)")

st.markdown(f'<div class="main-header">🏛️ SKRU Academic Workload AI ({APP_VERSION})</div>', unsafe_allow_html=True)
st.markdown(f'<div class="sub-header">ผู้ใช้: <b>{email or "guest@skru.ac.th"}</b></div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📥 1. สกัดข้อมูล (AI)", "📊 2. คลังสะสม", "📄 3. ออกรายงาน Word"])
all_data = load_all_data()

with tab1:
    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.subheader("1. อัปโหลด/กรอกข้อมูล")
        cat_hint = st.selectbox("📂 หมวดงาน (เบื้องต้น):", [AUTO_CATEGORY] + CATEGORIES)
        method = st.radio("วิธีป้อนข้อมูล:", ["📤 ไฟล์ (PDF/ภาพ)", "✍️ พิมพ์ข้อความ"])
        
        file_up, text_in = None, ""
        if "ไฟล์" in method: file_up = st.file_uploader("แนบเอกสาร:", type=["pdf", "png", "jpg"])
        else: text_in = st.text_area("พิมพ์รายละเอียด:")
        
        if st.button("🤖 สกัดด้วย AI", type="primary", use_container_width=True):
            if not active_api:
                st.session_state["ai_msg"] = ("warning", "กรุณาใส่ API Key ด้านซ้ายเพื่อใช้งาน AI หรือพิมพ์กรอกเองฝั่งขวา")
            elif not file_up and not text_in.strip():
                st.session_state["ai_msg"] = ("warning", "กรุณาแนบไฟล์หรือพิมพ์ข้อความ")
            else:
                with st.spinner("กำลังวิเคราะห์..."):
                    try:
                        parts = [{"text": build_prompt(cat_hint)}]
                        filename = ""
                        
                        if file_up:
                            filename = file_up.name
                            mime = file_up.type
                            bytes_data = file_up.getvalue()
                            
                            # ถ้าเป็น PDF ให้แปลงเป็นรูปภาพเสมอเพื่อแก้ปัญหาไฟล์ Scan/ไม่มี Text Layer
                            if mime == "application/pdf" and fitz is not None:
                                images = render_pdf_to_images(bytes_data)
                                for img in images:
                                    parts.append({"inline_data": {"mime_type": "image/png", "data": base64.b64encode(img).decode()}})
                            else:
                                parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(bytes_data).decode()}})
                        else:
                            parts[0]["text"] += f"\n\nข้อความจากผู้ใช้:\n{text_in}"

                        raw_json, model_used = call_gemini(active_api, model_list=FALLBACK_MODELS, parts=parts)
                        res = finalize_result(raw_json, filename, cat_hint)
                        
                        st.session_state.update({
                            "f_cat": res["cat"], "f_title": res["title"], "f_venue": res["venue"],
                            "f_date": res["date"], "f_ref": res["ref"], "f_form": res["formula"], 
                            "f_hrs": res["hours"], "f_formal": res["formal"]
                        })
                        
                        msg = f"✅ อ่านสำเร็จด้วย {model_used}"
                        if res["rule_applied"]: msg += " | 🎯 ปรับคะแนนเป็น 24 ตามเกณฑ์งานสร้างสรรค์นานาชาติ"
                        if res["notes"]: msg += f" | 📝 หมายเหตุ: {res['notes']}"
                        st.session_state["ai_msg"] = ("success", msg)
                    
                    except Exception as e:
                        st.session_state["ai_msg"] = ("warning", f"AI ผิดพลาด: {str(e)} (ระบบไม่ล่ม คุณสามารถกรอกเองได้)")

    with col2:
        st.subheader("2. ตรวจสอบ/แก้ไข")
        msg = st.session_state.get("ai_msg")
        if msg:
            if msg[0] == "success": st.success(msg[1])
            else: st.warning(msg[1])
            
        def_cat = st.session_state.get("f_cat", CATEGORIES[1])
        if def_cat not in CATEGORIES: def_cat = CATEGORIES[1]
        
        c_cat = st.selectbox("หมวดงาน:", CATEGORIES, index=CATEGORIES.index(def_cat))
        
        cx1, cx2 = st.columns(2)
        with cx1:
            c_title = st.text_input("ชื่อผลงาน:", value=st.session_state.get("f_title", ""))
            c_date = st.text_input("วันที่:", value=st.session_state.get("f_date", ""))
            c_form = st.text_input("สูตรคำนวณ:", value=st.session_state.get("f_form", ""))
        with cx2:
            c_venue = st.text_input("สถานที่/หน่วยงาน:", value=st.session_state.get("f_venue", ""))
            c_ref = st.text_input("เลขที่อ้างอิง:", value=st.session_state.get("f_ref", ""))
            c_hrs = st.number_input("ภาระงาน (ชม.):", value=st.session_state.get("f_hrs", 0.0), step=0.5)

        auto = st.checkbox("สร้างข้อความอัตโนมัติ", value=True)
        if auto:
            p_parts = [p for p in [c_title, c_venue, c_date] if p]
            t_head = " ".join(p_parts)
            if c_ref: t_head += f" ({c_ref})"
            live_text = f"{t_head} = {c_form} = {c_hrs:.1f} ชม." if c_form else f"{t_head} = {c_hrs:.1f} ชม."
            st.session_state["f_formal"] = live_text
            
        final_text = st.text_area("ข้อความทางการ:", value=st.session_state.get("f_formal", ""))
        
        if st.button("💾 บันทึกข้อมูล", type="primary", use_container_width=True):
            if not final_text.strip():
                st.error("กรุณากรอกข้อความทางการก่อนบันทึก")
            else:
                new_row = {
                    "email": email or "guest", "หมวดงาน": c_cat, "รายการภาระงาน": final_text,
                    "เลขคำสั่ง_อ้างอิง": c_ref, "วันที่": c_date, "ภาระงาน_ชม": c_hrs,
                    "วันที่บันทึก": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                new_df = pd.concat([all_data, pd.DataFrame([new_row])], ignore_index=True)
                ok, src = save_all_data(new_df)
                if ok: 
                    st.success("🎉 บันทึกสำเร็จ!")
                    st.rerun()

with tab2:
    st.subheader("📊 คลังภาระงานสะสม")
    my_data = all_data[all_data["email"] == (email or "guest")].copy() if not all_data.empty else pd.DataFrame()
    
    if my_data.empty:
        st.info("ยังไม่มีข้อมูลภาระงาน")
    else:
        edited = st.data_editor(my_data, use_container_width=True, hide_index=True)
        t_hrs = pd.to_numeric(edited["ภาระงาน_ชม"], errors="coerce").sum()
        st.metric("รวมภาระงานสะสม", f"{t_hrs:.1f} ชม.")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔄 อัปเดตตาราง", type="primary", use_container_width=True):
                other = all_data[all_data["email"] != (email or "guest")]
                save_all_data(pd.concat([other, edited]))
                st.success("อัปเดตแล้ว!")
                st.rerun()
        with col_btn2:
            if st.checkbox("ยืนยันการลบ"):
                if st.button("🗑️ ลบข้อมูลทั้งหมด", type="secondary", use_container_width=True):
                    other = all_data[all_data["email"] != (email or "guest")]
                    save_all_data(other)
                    st.rerun()

with tab3:
    st.subheader("📄 สรุปแบบ ป-มร.สข. 01")
    my_data = all_data[all_data["email"] == (email or "guest")]
    t_hrs = pd.to_numeric(my_data["ภาระงาน_ชม"], errors="coerce").sum() if not my_data.empty else 0.0
    
    score1 = min(t_hrs / 35.0, 1.0) * 70.0
    score2 = st.number_input("คะแนนองค์ประกอบที่ 2:", value=30.0, max_value=30.0)
    total = score1 + score2
    
    c1, c2, c3 = st.columns(3)
    c1.metric("องค์ประกอบ 1", f"{score1:.2f}/70")
    c2.metric("องค์ประกอบ 2", f"{score2:.2f}/30")
    c3.metric("คะแนนรวม", f"{total:.2f}/100")
    
    if HAS_DOCX and st.button("📥 สร้างไฟล์ Word"):
        doc = Document()
        doc.add_heading("สรุปภาระงาน ป-มร.สข. 01", 0)
        doc.add_paragraph(f"ผู้รับการประเมิน: {email or 'guest'}\nคะแนนรวม: {total:.2f}/100")
        
        t = doc.add_table(rows=1, cols=3)
        t.style = 'Table Grid'
        t.rows[0].cells[0].text, t.rows[0].cells[1].text, t.rows[0].cells[2].text = "หมวดงาน", "รายการ", "ชม."
        
        for _, r in my_data.iterrows():
            row = t.add_row().cells
            row[0].text, row[1].text, row[2].text = str(r["หมวดงาน"]), str(r["รายการภาระงาน"]), str(r["ภาระงาน_ชม"])
            
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        st.download_button("โหลดไฟล์ .docx", data=buf, file_name="report.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    elif not HAS_DOCX:
        st.warning("⚠️ กรุณาติดตั้ง python-docx (pip install python-docx) เพื่อใช้งานฟังก์ชันนี้")
