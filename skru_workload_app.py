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

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

APP_VERSION = "v14.4 (Ultimate Fix)"

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

DEFAULT_MODEL = "gemini-2.0-flash"
FALLBACK_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
MAX_INLINE_BYTES = 8 * 1024 * 1024  

# ---------------------------------------------------------
# 1. Page Config
# ---------------------------------------------------------
st.set_page_config(
    page_title=f"SKRU Workload AI - ระบบบันทึกและวิเคราะห์ภาระงาน มรภ.สงขลา ({APP_VERSION})",
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
# 3. PDF Parsing
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
    if not text.strip() and fitz:
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    t = page.get_text()
                    if t: text += t + "\n"
        except: pass
    return text.strip()

def render_pdf_pages_to_png(file_bytes, max_pages=5, zoom=1.3):
    if not fitz: raise RuntimeError("ไม่พบไลบรารี PyMuPDF")
    images = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            if i >= max_pages: break
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            images.append(pix.tobytes("png"))
    if not images: raise RuntimeError("PDF ไม่มีหน้าที่แปลงเป็นภาพได้")
    return images

# ---------------------------------------------------------
# 4. Gemini API
# ---------------------------------------------------------
class GeminiError(Exception): pass

RUBRIC_TEXT = """
เกณฑ์ภาระงาน มรภ.สงขลา (สรุป):
- งานวิชาการ: Proceedings ชาติ 10; นานาชาติ/วารสาร 12; TCI2=15; TCI1=19; บทความ ก.พ.อ.=21; บทความรางวัล=14/20; วิจัยบูรณาการ=4
- ทุนวิจัย(ชม./สัปดาห์): คณะ 6, มหาลัย 8, นอก 10
- ตำรา/หนังสือ ไม่เกิน 12; คำสอน ไม่เกิน 9; ประกอบการสอน/สื่อ ไม่เกิน 6
- สร้างสรรค์: ชาติไม่รางวัล 5; ชาติรางวัล 10; ร่วมมือตปท 12; อาเซียนไม่รางวัล 15; อาเซียนรางวัล 18; นานาชาติไม่รางวัล 21; นานาชาติรางวัล 24
- บริการวิชาการ: รับผิดชอบหลัก 5; ประธานฝ่าย 2; กรรมการ 1; เลขา 1.5; วิทยากร 0.5 ชม./1 ชม.
- ทำนุบำรุง(ผู้จัด): ประธาน 1 ชม./วัน; กรรมการ 0.5; เลขา 0.75; เข้าร่วม 0.5 ชม./โครงการ
- ที่ปรึกษา: โครงงาน ป.ตรี ที่ปรึกษา 1 ชม./คน; ที่ปรึกษาร่วม 0.75; กรรมการสอบหัวข้อ 0.15/เค้าโครง 0.3/โครงการ 0.5
- พัฒนาตนเอง: อบรมในประเทศ 1 ชม./วันทำการ, ตปท 1.5 ชม./วันทำการ
- งานพัสดุ: ประธาน/กรรมการ/เลขา คิดตามวงเงินคำสั่ง
"""

def build_prompt(category_hint, local_text):
    hint_line = f"ผู้ใช้ระบุหมวดงาน: {category_hint}\n" if category_hint and category_hint != AUTO_CATEGORY else ""
    prompt = (
        "คุณคือผู้ช่วยตรวจเอกสารภาระงาน มรภ.สงขลา สกัดข้อมูลจริงจากเอกสารเท่านั้น\n\n"
        + hint_line +
        "กติกาสำคัญ:\n"
        "1. ห้ามใช้ชื่อไฟล์ (.pdf/.png/.jpg) เป็นข้อมูลใดๆ\n"
        "2. title=ชื่อผลงาน/โครงการจริง, venue=เวที/สถานที่จัดจริง, date=วันที่จริง, ref=เลขที่หนังสือ/คำสั่งอ้างอิงจริง\n"
        "3. ถ้าไม่พบข้อมูลให้ใส่สตริงว่าง \"\" ห้ามเดา\n"
        "4. level=ระดับผลงาน (ชาติ/อาเซียน/นานาชาติ), has_award=true (ถ้าพบคำว่า ดีเยี่ยม/Excellent/รางวัล)\n"
        "5. hours=ภาระงาน(ตัวเลข), formula=สูตรการคำนวณ\n"
        "6. category=หมวดงาน (1 ถึง 7)\n"
        "7. raw_text=ข้อความสกัดสำคัญ, notes=ข้อสังเกต\n\n"
        + RUBRIC_TEXT +
        "\nตอบเป็น JSON ล้วนๆ ห้ามมี Markdown:\n"
        '{"category": "", "title": "", "venue": "", "date": "", "ref": "", "level": "", "has_award": false, "formula": "", "hours": 0.0, "raw_text": "", "notes": ""}'
    )
    if local_text: prompt += "\nข้อความที่ดึงได้เบื้องต้น:\n" + local_text[:6000]
    return prompt

def extract_json(text):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.I)
    try: return json.loads(t)
    except: pass
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try: return json.loads(m.group(0))
        except: pass
    raise GeminiError("AI ไม่ได้ตอบเป็น JSON")

def call_gemini(api_key, models, parts):
    body = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}}
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    last_err = ""

    for model in models:
        # สลับ Endpoint ให้รองรับ 2.0 โดยอัตโนมัติ
        api_version = "v1alpha" if "2.0" in model else "v1beta"
        url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model}:generateContent"
        
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=60)
        except Exception as e:
            last_err = f"เชื่อมต่อไม่ได้: {e}"; continue

        if resp.status_code == 200:
            cands = resp.json().get("candidates", [])
            if not cands: raise GeminiError("AI ไม่ส่งข้อความกลับมา")
            return extract_json(cands[0]["content"]["parts"][0]["text"]), model
            
        err
