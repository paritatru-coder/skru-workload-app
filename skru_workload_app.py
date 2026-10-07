import streamlit as st
import pandas as pd
import json
import io
import re
import base64
import mimetypes
from datetime import datetime
import time
import requests

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

APP_VERSION = "v21 (Next-Gen Exclusive)"

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

# ---------------------------------------------------------
# 1. Page Config
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
    .formatted-preview { background-color: #F0F9FF; border: 1px solid #BAE6FD; border-radius: 8px; padding: 1rem; color: #0369A1; font-weight: 500; margin-top: 0.5rem; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# 2. Database
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
    if df is None: df = pd.DataFrame(columns=DB_COLUMNS)
    df = df.copy()
    for c in DB_COLUMNS:
        if c not in df.columns: df[c] = 0.0 if c == "ภาระงาน_ชม" else ""
    df["ภาระงาน_ชม"] = pd.to_numeric(df["ภาระงาน_ชม"], errors="coerce").fillna(0.0)
    for c in DB_COLUMNS:
        if c != "ภาระงาน_ชม": df[c] = df[c].fillna("").astype(str)
    return df[DB_COLUMNS]

def load_all_data():
    if use_gsheets and conn:
        try:
            df = conn.read(ttl="0")
            if df is not None and not df.empty:
                return ensure_schema(df.dropna(how="all"))
        except Exception: pass
    if "local_db" not in st.session_state: st.session_state["local_db"] = pd.DataFrame(columns=DB_COLUMNS)
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
# 3. Text Extraction Fallback (ถ้า AI พัง)
# ---------------------------------------------------------
def extract_text_from_pdf_bytes(file_bytes):
    text = ""
    if pdfplumber:
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t: text += t + "\n"
        except: pass
    if not text.strip():
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                t = page.extract_text()
                if t: text += t + "\n"
        except: pass
    return text.strip()

# ---------------------------------------------------------
# 4. Gemini API Logic
# ---------------------------------------------------------
class GeminiError(Exception): pass

RUBRIC_TEXT = """
เกณฑ์การคิดภาระงาน มรภ.สงขลา และการเขียนสูตร (formula) ให้ยึดรูปแบบตามนี้อย่างเคร่งครัด:
1. บริการวิชาการ (วิทยากร): ได้ 0.5 ภาระงาน ต่อ 1 ชม.จริง (เต็มวัน=6ชม., ครึ่งวัน=3ชม.) 
   -> สูตรตัวอย่าง: (6ชม.x2วันx0.5) หรือ (3ชม.x5วันx0.5)
2. ทำนุบำรุงศิลปวัฒนธรรม (ผู้จัดงาน): ประธาน 1 ชม./วัน, กรรมการ 0.5 ชม./วัน, เลขา 0.75 ชม./วัน 
   -> สูตรตัวอย่าง: (0.5x2วัน) หรือ (1x1วัน)
3. ทำนุบำรุงศิลปวัฒนธรรม (ผู้เข้าร่วม): เหมาจ่าย 0.5 ชม./โครงการ (ไม่คูณจำนวนวัน) 
   -> สูตรตัวอย่าง: (0.5x1โครงการ)
4. คำสั่งเฉพาะกิจ/กรรมการอื่นๆ: นับเหมาเป็น "ต่อ 1 คำสั่ง" (ไม่คูณจำนวนวัน) ประธาน 1 ชม./คำสั่ง, กรรมการ 0.5 ชม./คำสั่ง, เลขา 0.75 ชม./คำสั่ง 
   -> สูตรตัวอย่าง: (0.5x1คำสั่ง) หรือ (1x1คำสั่ง)
5. ที่ปรึกษา/สอบ ป.ตรี: ที่ปรึกษา 1 ชม./คน, กรรมการสอบโครงการ 0.5 ชม./เรื่อง 
   -> สูตรตัวอย่าง: (1x5คน) หรือ (0.5x2เรื่อง)
6. งานสร้างสรรค์/วิชาการ/วิจัย: ระบุคะแนนเหมาจ่ายตามเกณฑ์
   -> สูตรตัวอย่าง: (นับสิทธิ์เผยแพร่ระดับชาติ = 10 ภาระงาน) หรือ (นับสิทธิ์เผยแพร่นานาชาติ ที่ได้รับรางวัล = 24 ภาระงาน)
"""

def build_prompt(category_hint, local_text):
    hint_line = f"ผู้ใช้ระบุหมวดงาน: {category_hint}\n" if category_hint and category_hint != AUTO_CATEGORY else ""
    prompt = (
        "คุณคือผู้ช่วยตรวจเอกสารภาระงาน มรภ.สงขลา สกัดข้อมูลจริงจากเอกสารเท่านั้น\n\n"
        + hint_line +
        "กติกาสำคัญ:\n"
        "1. ห้ามใช้ชื่อไฟล์ (.pdf/.png/.jpg) เป็นข้อมูลใดๆ\n"
        "2. title=ชื่อผลงาน/โครงการ/บทบาทจริง\n"
        "3. venue=เวที/สถานที่จัดจริง\n"
        "4. date=วันที่จริง\n"
        "5. ref=เลขที่หนังสือ/คำสั่งอ้างอิงจริง\n"
        "6. level=ระดับผลงาน (ชาติ/อาเซียน/นานาชาติ), has_award=true (ถ้าพบคำว่า ดีเยี่ยม/Excellent/รางวัล/Award)\n"
        "7. hours=ภาระงานสุทธิ (ตัวเลข)\n"
        "8. formula=เขียนเฉพาะตัวเลขสูตรในวงเล็บให้ชัดเจนตามเกณฑ์ด้านล่าง เช่น (3ชม.x5วันx0.5) หรือ (0.5x1คำสั่ง) ห้ามเขียนข้อความอธิบายยาวๆ\n"
        "9. category=หมวดงาน (1 ถึง 7)\n"
        "10. ถ้าไม่พบข้อมูลให้ใส่สตริงว่าง \"\"\n\n"
        + RUBRIC_TEXT +
        "\nตอบเป็น JSON ล้วนๆ ห้ามมี Markdown:\n"
        '{"category": "", "title": "", "venue": "", "date": "", "ref": "", "level": "", "has_award": false, "formula": "", "hours": 0.0, "raw_text": "", "notes": ""}'
    )
    if local_text: prompt += "\nข้อความที่ดึงได้เบื้องต้น:\n" + local_text[:6000]
    return prompt

def extract_json(text):
    t = (text or "").strip()
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try: return json.loads(m.group(0))
        except: pass
    raise GeminiError("AI ไม่ได้ตอบเป็น JSON")

def call_gemini(api_key, model_list, parts):
    body = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}}
    headers = {"Content-Type": "application/json"}
    last_err = ""

    # ใช้เฉพาะโมเดลที่คุณกรอกมาในหน้าเว็บเท่านั้น ไม่มีฮาร์ดโค้ดขยะแอบแฝง
    safe_models = [m.strip() for m in model_list if m.strip()]
    if not safe_models: safe_models = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

    for model in safe_models:
        endpoints = [
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            f"https://generativelanguage.googleapis.com/v1alpha/models/{model}:generateContent?key={api_key}"
        ]
        
        for url in endpoints:
            for attempt in range(3):
                try: resp = requests.post(url, headers=headers, json=body, timeout=60)
                except Exception as e: last_err = f"เชื่อมต่อไม่ได้: {e}"; break

                if resp.status_code == 200:
                    cands = resp.json().get("candidates", [])
                    if not cands: raise GeminiError("AI ประมวลผลสำเร็จแต่ไม่ส่งข้อความกลับมา")
                    return extract_json(cands[0]["content"]["parts"][0]["text"]), model
                
                if resp.status_code == 503:
                    last_err = f"503 High Demand (รุ่น {model}) - ลองส่งใหม่รอบที่ {attempt+1}..."
                    time.sleep(2)
                    continue

                err_msg = resp.json().get("error", {}).get("message", resp.text[:150]) if "error" in resp.text else resp.text[:150]
                if resp.status_code == 404: last_err = f"404 Not Found (ไม่มีรุ่น {model})"; break 
                if resp.status_code in (401, 403): raise GeminiError(f"API Key ผิด/ไม่มีสิทธิ์: {err_msg}")
                if resp.status_code == 400: raise GeminiError(f"400 Bad Request (ไฟล์อาจมีปัญหา): {err_msg}")
                
                last_err = f"Error {resp.status_code}: {err_msg}"
                break
            
    raise GeminiError(f"ทดสอบโมเดลของคุณไม่สำเร็จ: {last_err}")

def inline_part(data_bytes, mime):
    return {"inlineData": {"mimeType": mime, "data": base64.b64encode(data_bytes).decode("ascii")}}

def analyze_with_gemini(api_key, model_list, file_bytes, mime, local_text, category_hint, typed_text=""):
    prompt = build_prompt(category_hint, local_text)
    if typed_text: return call_gemini(api_key, model_list, [{"text": prompt + f"\n\n{typed_text[:8000]}"}])
    return call_gemini(api_key, model_list, [{"text": prompt}, inline_part(file_bytes, mime)])

# ---------------------------------------------------------
# 5. Core Normalization Logic
# ---------------------------------------------------------
AWARD_KEYWORDS = ["ดีเยี่ยม", "excellent", "รางวัล", "award"]
INTL_KEYWORDS = ["นานาชาติ", "international", "intl"]
FILE_EXT_RE = re.compile(r"\.(pdf|png|jpe?g|webp)\b", re.I)

def clean_field(value, filename=""):
    if not value: return ""
    v = str(value).strip()
    if v.lower() in {"none", "null", "n/a", "-", "ไม่ระบุ", "ไม่พบ", "ไม่มี"}: return ""
    if FILE_EXT_RE.search(v): return ""
    if filename and (v.lower() in filename.lower() or filename.lower() in v.lower()): return ""
    return v

def compose_formal_text(title, venue, date, ref, formula, hours):
    parts = []
    if title: parts.append(title)
    if venue: parts.append(venue)
    if date: parts.append(date)
    head = " ".join(parts)
    if ref: head += f" ({ref.strip()})"
    
    if formula:
        if not formula.startswith("("): formula = f"({formula})"
        return f"{head} = {formula} = {hours:.1f} ชม."
    return f"{head} = {hours:.1f} ชม."

def finalize_result(raw, evidence_text, filename, category_hint):
    cat = raw.get("category", "")
    if cat not in CATEGORIES: cat = category_hint if category_hint in CATEGORIES else CATEGORIES[1]
    title, venue, date_str, ref = clean_field(raw.get("title"), filename), clean_field(raw.get("venue"), filename), clean_field(raw.get("date"), filename), clean_field(raw.get("ref"), filename)
    formula, level, notes = clean_field(raw.get("formula"), filename), str(raw.get("level", "")), clean_field(raw.get("notes"), filename)
    try: hours = float(raw.get("hours", 0.0))
    except: hours = 0.0

    all_text = " ".join([evidence_text or "", str(raw.get("raw_text", "")), title, venue, ref, formula, level, notes])
    rule_applied = False

    if cat == CATEGORIES[1] and (("นานาชาติ" in level or any(k in all_text.lower() for k in INTL_KEYWORDS)) and (raw.get("has_award") or any(k in all_text.lower() for k in AWARD_KEYWORDS))):
        hours, formula, rule_applied = 24.0, "(นับสิทธิ์เผยแพร่นานาชาติ ที่ได้รับรางวัล/ระดับดีเยี่ยม = 24 ภาระงาน)", True

    return {"category": cat, "title": title, "venue": venue, "date": date_str, "ref": ref, "formula": formula, "hours": hours, "formal_text": compose_formal_text(title, venue, date_str, ref, formula, hours), "notes": notes, "rule_applied": rule_applied}

def guess_mime(uploaded):
    if uploaded.type and uploaded.type != "application/octet-stream": return uploaded.type
    return mimetypes.guess_type(uploaded.name)[0] or "application/pdf"

# ---------------------------------------------------------
# 6. UI Structure
# ---------------------------------------------------------
with st.sidebar:
    st.title("👤 ตั้งค่า")
    user_email = st.text_input("📧 อีเมลบุคลากร:", value=st.session_state.get("user_email", ""))
    if user_email: st.session_state["user_email"] = user_email.strip()
    st.divider()
    
    api_key_env = str(st.secrets["GEMINI_API_KEY"]).strip() if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets else ""
    user_api_key = st.text_input("🔑 Gemini API Key:", type="password", value="", placeholder="ใช้ค่าจาก Secrets อยู่" if api_key_env else "")
    active_api_key = user_api_key.strip() or api_key_env
    
    models_input = st.text_area(
        "🧠 รุ่น Gemini (เรียงลำดับสำรอง):", 
        value="gemini-2.5-flash-lite, gemini-2.5-flash",
        key="gemini_models_input_v21",
        help="คั่นด้วยลูกน้ำ (,) ระบบจะลองไปเรื่อยๆ"
    )
    user_models = [m.strip() for m in models_input.split(",") if m.strip()]

    if active_api_key: 
        st.success("🟢 พบ API Key")
        if st.button("🔍 เช็ครุ่น AI ที่ใช้ได้จริง", use_container_width=True):
            with st.spinner("กำลังถาม Google..."):
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={active_api_key}"
                    res = requests.get(url, timeout=10)
                    if res.status_code == 200:
                        m_list = [m["name"].replace("models/", "") for m in res.json().get("models", []) if "gemini" in m.get("name", "").lower() and "generateContent" in m.get("supportedGenerationMethods", [])]
                        if m_list: st.success(f"✅ รุ่นที่คุณมีสิทธิ์ใช้:\n\n" + "\n".join([f"- {x}" for x in m_list]))
                        else: st.warning("ไม่มีรุ่น Gemini ที่รองรับ")
                    else: st.error(f"ตรวจสอบไม่ได้: {res.text[:100]}")
                except Exception as e: st.error(f"Error: {e}")
    else: 
        st.warning("🟡 ไม่มี API Key")

st.markdown(f'<div class="main-header">🏛️ SKRU Academic Workload AI ({APP_VERSION})</div>', unsafe_allow_html=True)
email_val = user_email.strip() or "guest@skru.ac.th"

if st.session_state.get("show_success"):
    st.markdown('<div class="success-alert">🎉 บันทึกข้อมูลสำเร็จ!</div>', unsafe_allow_html=True)
    st.session_state["show_success"] = False

tab1, tab2, tab3 = st.tabs(["📥 1. สกัดข้อมูล (AI)", "📊 2. คลังข้อมูล", "📄 3. รายงาน Word"])
all_data_df = load_all_data()

with tab1:
    col_a, col_b = st.columns([1, 1], gap="large")
    with col_a:
        st.subheader("1. อัปโหลดเอกสาร")
        cat_in = st.selectbox("📂 หมวดงานเบื้องต้น:", [AUTO_CATEGORY] + CATEGORIES)
        
        method = st.radio("วิธีป้อนข้อมูล:", ["📤 ไฟล์ (PDF, PNG)", "📷 ถ่ายภาพกล้องมือถือ", "✍️ พิมพ์เอง"])
        file_up, text_in = None, ""
        if "ไฟล์" in method: file_up = st.file_uploader("แนบเอกสาร:", type=["pdf", "png", "jpg", "jpeg"])
        elif "กล้อง" in method: file_up = st.camera_input("ถ่ายภาพเอกสารคำสั่ง")
        else: text_in = st.text_area("พิมพ์รายละเอียด:")

        if st.button("🤖 ให้ AI อ่านเอกสาร", type="primary", use_container_width=True):
            if not file_up and not text_in.strip(): st.warning("⚠️ โปรดแนบไฟล์หรือข้อความ")
            else:
                with st.spinner("กำลังส่งข้อมูลวิเคราะห์..."):
                    result, notice = None, None
                    try:
                        f_bytes, f_name, mime, l_text, t_text = b"", "", "", "", ""
                        if file_up:
                            f_bytes, f_name, mime = file_up.getvalue(), getattr(file_up, "name", "camera_image.jpg"), guess_mime(file_up)
                            if mime == "application/pdf": l_text = extract_text_from_pdf_bytes(f_bytes)
                        else:
                            t_text = l_text = text_in.strip()

                        if active_api_key:
                            raw_json, used_model = analyze_with_gemini(active_api_key, user_models, f_bytes, mime, l_text, cat_in, t_text)
                            result = finalize_result(raw_json, l_text, f_name, cat_in)
                            notice = ("success", f"✅ อ่านสำเร็จด้วย {used_model}" + (" | 🎯 ปรับคะแนนเป็น 24.0" if result["rule_applied"] else ""))
                        else: notice = ("warning", "⚠️ ไม่มี API Key ใช้โหมดกรอกเอง")
                    except Exception as e:
                        notice = ("warning", f"⚠️ {e}")

                    if result:
                        st.session_state.update({
                            "notice": notice, "e_cat": result["category"], "e_title": result["title"],
                            "e_venue": result["venue"], "e_date": result["date"], "e_ref": result["ref"],
                            "e_formula": result["formula"], "e_hours": float(result["hours"])
                        })
                    else:
                        st.session_state.update({
                            "notice": notice, "e_cat": CATEGORIES[1], "e_title": "", "e_venue": "", "e_date": "", 
                            "e_ref": "", "e_formula": "", "e_hours": 0.0
                        })

    with col_b:
        st.subheader("2. ตรวจสอบ & บันทึก")
        if "notice" in st.session_state:
            if st.session_state["notice"][0] == "success": st.success(st.session_state["notice"][1])
            else: st.warning(st.session_state["notice"][1])

        e_cat = st.selectbox("📂 หมวดงาน:", CATEGORIES, index=CATEGORIES.index(st.session_state.get("e_cat", CATEGORIES[1])) if st.session_state.get("e_cat") in CATEGORIES else 1)
        c1, c2 = st.columns(2)
        with c1:
            e_title = st.text_input("1. ชื่อบทบาท:", value=st.session_state.get("e_title", ""))
            e_date = st.text_input("3. วันที่:", value=st.session_state.get("e_date", ""))
            e_form = st.text_input("5. สูตรคำนวณ:", value=st.session_state.get("e_formula", ""))
        with c2:
            e_venue = st.text_input("2. สถานที่:", value=st.session_state.get("e_venue", ""))
            e_ref = st.text_input("4. เลขที่อ้างอิง:", value=st.session_state.get("e_ref", ""))
            e_hrs = st.number_input("6. ชั่วโมงสุทธิ:", value=st.session_state.get("e_hours", 0.0), step=0.5)

        live_txt = compose_formal_text(e_title, e_venue, e_date, e_ref, e_form, e_hrs)
        f_txt = st.text_area("📝 ข้อความทางการ:", value=live_txt, height=120)

        if st.button("💾 บันทึกลงคลัง", type="primary", use_container_width=True):
            if not f_txt.strip(): st.warning("⚠️ ไม่มีข้อความ")
            else:
                new_row = pd.DataFrame([{"email": email_val, "หมวดงาน": e_cat, "รายการภาระงาน": f_txt, "เลขคำสั่ง_อ้างอิง": e_ref, "วันที่": e_date, "ภาระงาน_ชม": e_hrs, "วันที่บันทึก": datetime.now().strftime("%Y-%m-%d %H:%M")}])
                if save_all_data(pd.concat([all_data_df, new_row], ignore_index=True))[0]:
                    st.session_state["show_success"] = True
                    st.rerun()

with tab2:
    st.subheader(f"📊 คลังภาระงาน: {email_val}")
    u_df = all_data_df[all_data_df["email"] == email_val].copy()
    if u_df.empty: st.info("ยังไม่มีข้อมูล")
    else:
        edited = st.data_editor(u_df[["หมวดงาน", "รายการภาระงาน", "เลขคำสั่ง_อ้างอิง", "วันที่", "ภาระงาน_ชม"]].reset_index(drop=True), use_container_width=True, num_rows="dynamic")
        st.metric("รวมชั่วโมง", f"{pd.to_numeric(edited['ภาระงาน_ชม'], errors='coerce').sum():.1f}")
        c1, c2 = st.columns(2)
        if c1.button("🔄 อัปเดต", type="primary"):
            edited["email"], edited["วันที่บันทึก"] = email_val, datetime.now().strftime("%Y-%m-%d %H:%M")
            save_all_data(pd.concat([all_data_df[all_data_df["email"] != email_val], edited[edited["รายการภาระงาน"].str.strip() != ""]]))
            st.rerun()
        if c2.button("🗑️ ลบทั้งหมด") and st.checkbox("ยืนยัน"):
            save_all_data(all_data_df[all_data_df["email"] != email_val])
            st.rerun()

with tab3:
    st.subheader(f"📋 สรุปคะแนน: {email_val}")
    u_df = all_data_df[all_data_df["email"] == email_val]
    t_hrs = pd.to_numeric(u_df["ภาระงาน_ชม"], errors="coerce").sum()
    c1 = min(t_hrs / 35.0, 1.0) * 70.0
    c2 = st.number_input("คะแนนองค์ประกอบ 2:", value=30.0)
    total_score = c1 + c2
    st.metric("คะแนนรวม", f"{total_score:.2f} / 100")

    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        def generate_docx():
            doc = Document()
            title_p = doc.add_paragraph()
            title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run_title = title_p.add_run("แบบสรุปการประเมินผลการปฏิบัติราชการของบุคลากรสายวิชาการ (ป-มร.สข. 01)")
            run_title.bold = True
            run_title.font.size = Pt(16)

            doc.add_paragraph(f"ผู้รับการประเมิน: {email_val}")
            doc.add_paragraph(f"คะแนนรวมสุทธิ: {total_score:.2f} / 100 คะแนน")

            doc.add_heading("รายละเอียดภาระงานสะสม", level=2)
            table = doc.add_table(rows=1, cols=4)
            table.style = "Table Grid"
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text, hdr_cells[1].text, hdr_cells[2].text, hdr_cells[3].text = "หมวดงาน", "รายการ", "อ้างอิง", "ชม."

            for _, r in u_df.iterrows():
                row_cells = table.add_row().cells
                row_cells[0].text = str(r["หมวดงาน"])
                row_cells[1].text = str(r["รายการภาระงาน"])
                row_cells[2].text = str(r["เลขคำสั่ง_อ้างอิง"])
                row_cells[3].text = str(r["ภาระงาน_ชม"])

            buf = io.BytesIO()
            doc.save(buf)
            buf.seek(0)
            return buf

        st.download_button(
            label="📥 ดาวน์โหลดแบบสรุป ป-มร.สข. 01 (.docx)",
            data=generate_docx(),
            file_name=f"ป-มร.สข.01_{email_val.split('@')[0]}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary"
        )
    except ImportError:
        st.warning("⚠️ ไม่สามารถสร้างไฟล์ Word ได้ กรุณาติดตั้งไลบรารี python-docx (เพิ่มลงใน requirements.txt)")
