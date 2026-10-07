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

APP_VERSION = "v14.3 (Fixed-OCR)"

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

# แก้ไขชื่อรุ่นให้ถูกต้องและมีอยู่จริง
DEFAULT_MODEL = "gemini-2.0-flash"
FALLBACK_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash-latest", "gemini-1.5-flash", "gemini-1.5-pro"]
MAX_INLINE_BYTES = 8 * 1024 * 1024  # ลดเหลือ 8MB ป้องกัน Payload Too Large

# ---------------------------------------------------------
# 1. Page Config & Custom Styling
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
    .success-alert {
        background-color: #DCFCE7; border: 2px solid #22C55E; color: #15803D;
        padding: 1rem; border-radius: 8px; font-weight: bold; font-size: 1.15rem; margin-bottom: 1rem;
    }
    .info-alert {
        background-color: #EFF6FF; border: 1px solid #93C5FD; color: #1E40AF;
        padding: 0.8rem; border-radius: 8px; margin-bottom: 1rem;
    }
    .formatted-preview {
        background-color: #F0F9FF; border: 1px solid #BAE6FD; border-radius: 8px;
        padding: 1rem; font-family: 'Sarabun', sans-serif; color: #0369A1; font-weight: 500;
        margin-top: 0.5rem; margin-bottom: 1rem;
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

def ensure_schema(df):
    if df is None:
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
                df = df.dropna(how="all")
                return ensure_schema(df)
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
# 3. PDF Text Layer Reader
# ---------------------------------------------------------
def extract_text_from_pdf_bytes(file_bytes):
    text = ""
    if pdfplumber is not None:
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t: text += t + "\n"
        except Exception: pass

    if not text.strip():
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                t = page.extract_text()
                if t: text += t + "\n"
        except Exception: pass

    if not text.strip() and fitz is not None:
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    t = page.get_text()
                    if t: text += t + "\n"
        except Exception: pass
    return text.strip()

def render_pdf_pages_to_png(file_bytes, max_pages=5, zoom=1.3):
    """ลด zoom และ max_pages ป้องกัน API แจ้ง 400 Bad Request Payload Too Large"""
    if fitz is None:
        raise RuntimeError("ไม่พบไลบรารี PyMuPDF (pip install PyMuPDF)")
    images = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            if i >= max_pages: break
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            images.append(pix.tobytes("png"))
    if not images:
        raise RuntimeError("PDF ไม่มีหน้าที่แปลงเป็นภาพได้")
    return images

# ---------------------------------------------------------
# 4. Gemini Vision Engine (REST API)
# ---------------------------------------------------------
class GeminiError(Exception): pass
class GeminiAuthError(GeminiError): pass
class GeminiRequestError(GeminiError): pass
class GeminiUnavailable(GeminiError): pass

RUBRIC_TEXT = """
เกณฑ์ภาระงาน มรภ.สงขลา (สรุป):
- ผลงานวิชาการ/วิจัย: Proceedings ระดับชาติ 10 ชม.; Proceedings ระดับนานาชาติ หรือวารสารที่สภามหาวิทยาลัยอนุมัติ 12; TCI กลุ่ม 2 = 15; TCI กลุ่ม 1 = 19; บทความที่ประกาศใน ก.พ.อ. = 21; บทความได้รับรางวัลระดับชาติ/นานาชาติ = 14/20; ผลงานวิจัยบูรณาการ = 4. ทุนวิจัย (ชม./สัปดาห์): คณะ 6, มหาวิทยาลัย 8, ภายนอก 10
- ตำรา/หนังสือ ไม่เกิน 12; เอกสารคำสอน ไม่เกิน 9; เอกสารประกอบการสอน ไม่เกิน 6; สื่อประกอบการสอน ไม่เกิน 6
- งานสร้างสรรค์/สิ่งประดิษฐ์: ระดับชาติไม่รางวัล ไม่เกิน 5; ระดับชาติรางวัล ไม่เกิน 10; ความร่วมมือระหว่างประเทศ ไม่เกิน 12; อาเซียนไม่รางวัล ไม่เกิน 15; อาเซียนรางวัล ไม่เกิน 18; นานาชาติไม่รางวัล ไม่เกิน 21; นานาชาติรางวัล ไม่เกิน 24
- บริการวิชาการ: ผู้รับผิดชอบหลัก 5; ประธานฝ่าย 2; กรรมการ 1; เลขานุการ 1.5; วิทยากร 0.5 ชม./1 ชม.; ผลงานบูรณาการ 4
- บริการวิชาการที่มีรายได้: <25,000 = 2; 25,001-50,000 = 3; 50,000-75,000 = 4; 75,000-100,000 = 5; >100,000 = 6
- ทำนุบำรุงศิลปวัฒนธรรม (ผู้จัด): ประธาน 1 ชม./วัน; กรรมการ 0.5 ชม./วัน; เลขานุการ 0.75 ชม./วัน; เข้าร่วมโครงการ 0.5 ชม./โครงการ
- การอ่านผลงาน: ระดับอุดมศึกษา 2 ชม./ผลงาน; เพื่อเผยแพร่/ตำแหน่งวิชาการ 1 ชม./ผลงาน; บรรณาธิการวารสาร 3; กองบรรณาธิการ 1; กรรมการวิชาการ/ผู้เชี่ยวชาญภายนอก 1 ชม./คำสั่ง
- ที่ปรึกษาโครงงานปริญญาตรี: ที่ปรึกษา 1 ชม./คน; ที่ปรึกษาร่วม 0.75 ชม./คน (รวมไม่เกิน 10); กรรมการสอบ หัวข้อ 0.15 เค้าโครง 0.3 โครงการ 0.5 ชม./เรื่อง; ที่ปรึกษาวิทยานิพนธ์ 3 ชม./สัปดาห์; ที่ปรึกษาร่วม/ค้นคว้าอิสระ 2 ชม./สัปดาห์
- พัฒนานักศึกษา: อาจารย์ที่ปรึกษา 1-30 คน 2 ชม./หมู่เรียน, เกิน 30 คน 3 ชม./หมู่เรียน; ประธานที่ปรึกษาโครงการ 3; กรรมการที่ปรึกษา 1.5; ผู้จัดการทีม 1 ชม./คำสั่ง; ผู้ฝึกสอนกีฬา 3 ชม./คำสั่ง; ประธาน 1 / กรรมการ 0.5 / เลขานุการ 0.75 ชม./คำสั่ง
- คำสั่งเฉพาะกิจ (ต่อคำสั่ง): ประธาน 1 / กรรมการ 0.5 / เลขานุการ 0.75; โครงการเกิน 1 ภาคการศึกษา: 3 / 1 / 2; สอบข้อเท็จจริงหรือวินัย: 5 / 2 / 3
- พัฒนาตนเอง: เข้าร่วมตามแผนพัฒนารายบุคคล ในประเทศ 1 ชม./วันทำการ, ต่างประเทศ 1.5 ชม./วันทำการ; ผลงานสืบเนื่องจากการพัฒนาตนเอง 4 ชม./ผลงาน
- งานบริหาร: อธิการบดี 35; รองอธิการบดี/คณบดี 30; ผู้ช่วยอธิการบดี/รองคณบดี 25; ประธานหลักสูตร 15; เลขานุการหลักสูตร/ผู้ควบคุมหอพัก 10; กรรมการบริหารหลักสูตร 8; กรรมการสโมสรอาจารย์ 2
- งานพัสดุ: ให้คิดตามบทบาท ประธาน/กรรมการ/เลขานุการ ต่อคำสั่ง ตามวงเงินในเอกสาร
"""

def build_prompt(category_hint, local_text):
    cat_list = "\n".join(CATEGORIES)
    hint_line = f"ผู้ใช้ระบุหมวดงานเบื้องต้นไว้แล้วว่า: {category_hint} (ให้ใช้หมวดนี้)\n" if category_hint and category_hint != AUTO_CATEGORY else ""

    prompt = (
        "คุณคือผู้ช่วยตรวจเอกสารภาระงานสายวิชาการของมหาวิทยาลัยราชภัฏสงขลา "
        "อ่านเอกสารที่แนบมาอย่างละเอียด แล้วสกัดข้อมูลจริงจากเนื้อหาในเอกสาร\n\n"
        + hint_line +
        "กติกาสำคัญ:\n"
        "1. ห้ามใช้ชื่อไฟล์ (.pdf/.png/.jpg) เป็นข้อมูลใดๆ ทั้งสิ้น\n"
        "2. title = ชื่อผลงาน/โครงการ/หลักสูตร/บทบาทที่ระบุไว้จริงในเอกสาร\n"
        "3. venue = เวที/สถานที่/หน่วยงานผู้จัดที่ระบุไว้จริง\n"
        "4. date = วันที่จริงในเอกสาร (รูปแบบไทย พ.ศ. เช่น 16 มิถุนายน 2569; ถ้าหลายวันให้คั่นด้วยจุลภาค)\n"
        "5. ref = เลขที่หนังสือ/เลขที่คำสั่ง/เลขที่ประกาศอ้างอิงจริง (เช่น คำสั่งคณะ ... ที่ 046/2569)\n"
        "6. ถ้าไม่พบข้อมูลช่องใดให้ใส่สตริงว่าง \"\" ห้ามเดา ห้ามแต่งขึ้นเอง\n"
        "7. level = ระดับของผลงาน เลือกจาก: ระดับชาติ, อาเซียน, นานาชาติ, ความร่วมมือระหว่างประเทศ, ไม่เกี่ยวข้อง/ไม่ระบุ\n"
        "8. has_award = true ถ้าพบคำว่า ดีเยี่ยม, Excellent, รางวัล, Award หรือผลการประเมินระดับสูงสุด\n"
        "9. hours = จำนวนภาระงาน (ตัวเลข) คำนวณตามเกณฑ์ด้านล่าง; formula = สูตรคำนวณสั้นๆ ในวงเล็บ เช่น (3ชมx5วันx0.5)\n"
        "10. category ต้องเป็นข้อความหนึ่งในรายการต่อไปนี้ทุกตัวอักษร:\n" + cat_list + "\n"
        "11. raw_text = ข้อความสำคัญที่อ่านได้จากเอกสาร (ถอดความตามต้นฉบับ ไม่เกิน 2500 ตัวอักษร)\n"
        "12. notes = ข้อสังเกตหรือสิ่งที่ผู้ใช้ควรตรวจสอบซ้ำ (ถ้ามี)\n\n"
        + RUBRIC_TEXT +
        "\nตอบกลับเป็น JSON เท่านั้น ห้ามมีข้อความอื่นนอก JSON ตามโครงสร้าง:\n"
        '{"category": "", "title": "", "venue": "", "date": "", "ref": "", "level": "", '
        '"has_award": false, "formula": "", "hours": 0, "raw_text": "", "notes": ""}\n'
    )
    if local_text:
        prompt += "\nข้อความที่ดึงจาก text layer ของไฟล์:\n" + local_text[:6000] + "\n"
    return prompt

def extract_json(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
    t = re.sub(r"\s*```$", "", t)
    try: return json.loads(t)
    except Exception: pass
    
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try: return json.loads(m.group(0))
        except Exception: pass
    raise GeminiRequestError("Gemini ตอบกลับในรูปแบบที่อ่านเป็น JSON ไม่ได้")

def inline_part(data_bytes, mime):
    # แก้ไขเป็นรูปแบบ camelCase ตามมาตรฐาน REST API ของ Google
    return {"inlineData": {"mimeType": mime, "data": base64.b64encode(data_bytes).decode("ascii")}}

def call_gemini(api_key, models, parts):
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    last_err = "ไม่ทราบสาเหตุ"

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(2):
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=120)
            except requests.RequestException as e:
                last_err = f"เชื่อมต่อไม่ได้: {e}"
                time.sleep(1.0)
                continue

            code = resp.status_code
            if code == 200:
                try:
                    payload = resp.json()
                    cands = payload.get("candidates") or []
                    if not cands: raise GeminiRequestError("Gemini ไม่ส่งผลลัพธ์กลับมา")
                    texts = [p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])]
                    return extract_json("".join(texts)), model
                except Exception as e:
                    raise GeminiRequestError(f"อ่านผลลัพธ์ไม่สำเร็จ: {e}")

            try: err_msg = resp.json().get("error", {}).get("message", resp.text[:200])
            except Exception: err_msg = resp.text[:200]

            if code in (401, 403) or (code == 400 and ("API key" in err_msg or "API_KEY" in err_msg)):
                raise GeminiAuthError(f"API Key ไม่มีสิทธิ์ใช้งาน: {err_msg}")
            
            if code == 404:
                last_err = f"ไม่พบรุ่น {model} (404)"
                break # รุ่นนี้ไม่มีอยู่จริง ข้ามไปรุ่นถัดไป
                
            if code == 400:
                # 400 เกิดจาก Payload ผิดปกติ โยน Error ทันที ไม่ต้องวนต่อ
                raise GeminiRequestError(f"API ปฏิเสธคำขอ (อาจเพราะไฟล์ภาพใหญ่เกินไป): {err_msg}")
                
            if code in (429, 500, 502, 503, 504):
                last_err = f"Server Error ({code}): {err_msg}"
                time.sleep(2.0 * (attempt + 1))
                continue
                
            last_err = f"Status {code}: {err_msg}"
            break

    raise GeminiUnavailable(f"ลองใช้งานครบทุกรุ่นแล้วแต่ไม่สำเร็จ: {last_err}")

def analyze_with_gemini(api_key, models, file_bytes, mime, local_text, category_hint, typed_text=""):
    prompt = build_prompt(category_hint, local_text)

    if typed_text:
        parts = [{"text": prompt + "\nข้อความที่ผู้ใช้พิมพ์เอง:\n" + typed_text[:8000]}]
        return call_gemini(api_key, models, parts)

    if mime == "application/pdf":
        first_error = None
        # ลองส่ง PDF ตรงๆ เข้าไปก่อน (ถ้าขนาดไม่เกิน 8MB)
        if len(file_bytes) <= MAX_INLINE_BYTES:
            try:
                parts = [{"text": prompt}, inline_part(file_bytes, "application/pdf")]
                return call_gemini(api_key, models, parts)
            except GeminiRequestError as e:
                first_error = e  
            except GeminiUnavailable as e:
                first_error = e 
                
        # หากส่ง PDF ตรงๆ ไม่ผ่าน หรือเกินโควต้า ให้แปลงเป็นภาพทีละหน้า (Fallback)
        try:
            images = render_pdf_pages_to_png(file_bytes)
        except Exception as e:
            if first_error: raise first_error
            raise GeminiRequestError(f"ไฟล์ PDF มีปัญหาและแปลงเป็นภาพไม่ได้: {e}")
            
        parts = [{"text": prompt}] + [inline_part(img, "image/png") for img in images]
        return call_gemini(api_key, models, parts)

    parts = [{"text": prompt}, inline_part(file_bytes, mime)]
    return call_gemini(api_key, models, parts)

# ---------------------------------------------------------
# 5. Business Rules & Normalization
# ---------------------------------------------------------
AWARD_KEYWORDS = ["ดีเยี่ยม", "excellent", "รางวัล", "award"]
INTL_KEYWORDS = ["นานาชาติ", "international", "intl"]
BAD_VALUES = {"none", "null", "n/a", "-", "ไม่ระบุ", "ไม่พบ", "ไม่มี"}
FILE_EXT_RE = re.compile(r"\.(pdf|png|jpe?g|webp)\b", re.I)

def clean_field(value, filename=""):
    if value is None: return ""
    s = str(value).strip()
    if s.lower() in BAD_VALUES: return ""
    if FILE_EXT_RE.search(s): return ""
    if filename:
        stem = filename.rsplit(".", 1)[0].strip().lower()
        if s.lower() == filename.strip().lower() or (stem and s.lower() == stem):
            return ""
    return s

def normalize_category(value, hint=""):
    if hint and hint != AUTO_CATEGORY and hint in CATEGORIES: return hint
    v = (value or "").strip()
    if v in CATEGORIES: return v
    m = re.match(r"\s*([1-7])\b", v)
    if m: return CATEGORIES[int(m.group(1)) - 1]
    return CATEGORIES[1]

def compose_formal_text(title, venue, date, ref, formula, hours):
    head = " ".join(p.strip() for p in [title, venue, date] if p and p.strip())
    if ref and ref.strip(): head += f" ({ref.strip()})"
    head = head.strip()
    if formula and formula.strip(): return f"{head} = {formula.strip()} = {hours:.1f} ชม."
    return f"{head} = {hours:.1f} ชม."

def finalize_result(raw, evidence_text, filename, category_hint):
    category = normalize_category(raw.get("category", ""), category_hint)
    title = clean_field(raw.get("title"), filename)
    venue = clean_field(raw.get("venue"), filename)
    date_str = clean_field(raw.get("date"), filename)
    ref_code = clean_field(raw.get("ref"), filename)
    formula = clean_field(raw.get("formula"), filename)
    level = str(raw.get("level", "") or "")
    notes = clean_field(raw.get("notes"), filename)
    
    try: hours = float(raw.get("hours", 0.0))
    except Exception: hours = 0.0

    all_text = " ".join([evidence_text or "", str(raw.get("raw_text", "") or ""), title, venue, ref_code, formula, level, notes])
    is_intl = contains_any(all_text, INTL_KEYWORDS) or "นานาชาติ" in level
    has_award = bool(raw.get("has_award")) or contains_any(all_text, AWARD_KEYWORDS)

    rule_applied = False
    if category == CATEGORIES[1] and is_intl and has_award:
        hours = 24.0
        formula = "(นับสิทธิ์เผยแพร่นานาชาติ ที่ได้รับรางวัล/ระดับดีเยี่ยม = 24 ภาระงาน)"
        rule_applied = True

    return {
        "category": category, "title": title, "venue": venue, "date": date_str,
        "ref": ref_code, "formula": formula, "hours": hours,
        "formal_text": compose_formal_text(title, venue, date_str, ref_code, formula, hours),
        "notes": notes, "rule_applied": rule_applied,
    }

# ---------------------------------------------------------
# 6. Local Fallback Parser
# ---------------------------------------------------------
def contains_any(text, keywords):
    return any(k in (text or "").lower() for k in keywords)

def guess_category_local(text):
    t = text or ""
    if contains_any(t, ["วิทยากร", "บริการวิชาการ", "โครงการอบรม"]): return CATEGORIES[2]
    if contains_any(t, ["ประพันธ์", "สร้างสรรค์", "วิจัย", "proceedings", "journal", "บทความ", "นานาชาติ"]): return CATEGORIES[1]
    if contains_any(t, ["ทำนุบำรุง", "ศิลปวัฒนธรรม"]): return CATEGORIES[3]
    if contains_any(t, ["ประกันคุณภาพ", "qa"]): return CATEGORIES[5]
    return CATEGORIES[4]

def parse_text_local(text, filename, category_hint):
    t = text or ""
    raw = {"category": guess_category_local(t), "title": "", "venue": "", "date": "", "ref": "",
           "formula": "", "hours": 0.0, "level": "", "has_award": False, "raw_text": t[:2500], "notes": ""}
    return finalize_result(raw, t, filename, category_hint)

def blank_result(category_hint):
    return {"category": normalize_category("", category_hint), "title": "", "venue": "", "date": "", "ref": "", "formula": "",
            "hours": 0.0, "formal_text": "", "notes": "", "rule_applied": False}

def guess_mime(uploaded):
    mime = getattr(uploaded, "type", None)
    if mime and mime != "application/octet-stream": return mime
    guess, _ = mimetypes.guess_type(getattr(uploaded, "name", "") or "")
    return guess or "image/jpeg"

# ---------------------------------------------------------
# 7. Sidebar Configuration
# ---------------------------------------------------------
with st.sidebar:
    st.title("👤 ระบุตัวตน & ตั้งค่า")
    user_email = st.text_input("📧 อีเมลบุคลากร:", value=st.session_state.get("user_email_saved", ""), key="sidebar_email_input")
    if user_email: st.session_state["user_email_saved"] = user_email.strip()

    track_type = st.selectbox("🎯 กลุ่มการประเมินสายวิชาการ:", ["กลุ่มเน้นการสอน", "กลุ่มเน้นการวิจัย"])
    role = st.selectbox("🏛️ ตำแหน่งบริหาร/วิชาการ:", ["อาจารย์สายสอน", "ประธานหลักสูตร", "รองคณบดี", "คณบดี"])
    st.divider()

    api_key_env = str(st.secrets["GEMINI_API_KEY"]).strip() if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets else ""
    user_api_key = st.text_input("🔑 Gemini API Key:", type="password", value="", placeholder="ใช้ค่าจาก Secrets อยู่" if api_key_env else "วาง API Key ที่นี่")
    active_api_key = (user_api_key or "").strip() or api_key_env

    model_choice = st.text_input("🧠 รุ่น Gemini:", value=DEFAULT_MODEL)
    model_list = [model_choice.strip()] if model_choice.strip() else []
    for m_name in FALLBACK_MODELS:
        if m_name not in model_list: model_list.append(m_name)

    if active_api_key: st.success("🟢 พบ Gemini API Key", icon="🔑")
    else: st.warning("🟡 ยังไม่ได้ใส่ Gemini API Key", icon="⚠️")

# ---------------------------------------------------------
# 8. Main Interface & Tabs
# ---------------------------------------------------------
st.markdown(f'<div class="main-header">🏛️ SKRU Academic Workload AI Assistant ({APP_VERSION})</div>', unsafe_allow_html=True)
effective_email = user_email.strip() if user_email and user_email.strip() != "" else "guest@skru.ac.th"
st.markdown(f'<div class="sub-header">ระบบช่วยสกัด เรียบเรียงภาษาทางการ และประเมินภาระงาน มรภ.สงขลา | ผู้ใช้: <b>{effective_email}</b></div>', unsafe_allow_html=True)

if st.session_state.get("show_saved_success"):
    st.markdown('<div class="success-alert">🎉 บันทึกข้อมูลเรียบร้อย!</div>', unsafe_allow_html=True)
    st.session_state["show_saved_success"] = False

tab1, tab2, tab3 = st.tabs(["📥 1. สกัดและเรียบเรียงภาระงาน (AI)", "📊 2. คลังภาระงานสะสม", "📄 3. สรุปแบบ ป-มร.สข. 01 (Word)"])
all_data_df = load_all_data()

with tab1:
    col_a, col_b = st.columns([1, 1], gap="large")

    with col_a:
        st.subheader("📝 ขั้นตอนที่ 1: ส่งไฟล์ / ภาพคำสั่ง / พิมพ์ข้อความ")
        category_input = st.selectbox("📂 เลือกหมวดภาระงานเบื้องต้น:", [AUTO_CATEGORY] + CATEGORIES)
        input_method = st.radio("เลือกวิธีป้อนข้อมูล:", ["📤 อัปโหลดไฟล์ (PDF, PNG, JPG)", "📷 ถ่ายภาพคำสั่ง", "✍️ พิมพ์รายละเอียดเอง"])

        uploaded_file, raw_text_input = None, ""
        if "อัปโหลด" in input_method: uploaded_file = st.file_uploader("แนบคำสั่ง/ประกาศ:", type=["pdf", "png", "jpg", "jpeg", "webp"])
        elif "ถ่ายภาพ" in input_method: uploaded_file = st.camera_input("ถ่ายภาพคำสั่ง")
        else: raw_text_input = st.text_area("พิมพ์รายละเอียดภาระงาน:")

        btn_ai_process = st.button("🤖 ให้ AI อ่านเอกสาร", type="primary", use_container_width=True)

    if btn_ai_process:
        if not uploaded_file and not raw_text_input.strip():
            st.session_state["ai_notice"] = ("warning", "⚠️ กรุณาแนบไฟล์หรือพิมพ์ข้อความก่อนครับ")
        else:
            with st.spinner("กำลังทำงาน..."):
                result, notice, filename, local_text, file_bytes, mime, typed_text = None, None, "", "", b"", "", ""
                try:
                    if uploaded_file:
                        file_bytes = uploaded_file.getvalue()
                        filename = getattr(uploaded_file, "name", "")
                        mime = guess_mime(uploaded_file)
                        if filename.lower().endswith(".pdf"): mime = "application/pdf"
                        if mime == "application/pdf": local_text = extract_text_from_pdf_bytes(file_bytes)
                    else:
                        typed_text, local_text = raw_text_input.strip(), raw_text_input.strip()
                except Exception as e:
                    notice = ("warning", f"⚠️ อ่านไฟล์ไม่สำเร็จ: {e}")

                is_scan_pdf = (mime == "application/pdf" and not local_text)

                if not notice and active_api_key:
                    try:
                        raw_json, used_model = analyze_with_gemini(active_api_key, model_list, file_bytes, mime, local_text, category_input, typed_text)
                        result = finalize_result(raw_json, local_text, filename, category_input)
                        msg = f"✅ อ่านเอกสารสำเร็จด้วย {used_model}"
                        if is_scan_pdf: msg += " (พบเป็น PDF สแกน จึงประมวลผลจากภาพแทน)"
                        if result["rule_applied"]: msg += " | 🎯 ปรับคะแนน 24 อัตโนมัติ (งานสร้างสรรค์นานาชาติ)"
                        notice = ("success", msg)
                    except GeminiAuthError as e: notice = ("warning", f"⚠️ {e}")
                    except GeminiUnavailable as e: notice = ("warning", f"⚠️ Gemini ขัดข้อง: {e} — ใช้โหมดสํารองแล้ว")
                    except Exception as e: notice = ("warning", f"⚠️ Error: {e} — ใช้โหมดสํารองแทน")
                elif not active_api_key:
                    notice = ("warning", "⚠️ ยังไม่ได้ใส่ Gemini API Key")

                if not result:
                    result = parse_text_local(local_text, filename, category_input) if local_text else blank_result(category_input)
                    if is_scan_pdf or mime.startswith("image/"): notice = (notice[0], notice[1] + " | เอกสารนี้เป็นภาพสแกน ต้องมี API Key จึงจะทำงานได้สมบูรณ์")

                st.session_state.update({
                    "ai_notice": notice, "edit_cat": result["category"], "edit_title": result["title"],
                    "edit_venue": result["venue"], "edit_date": result["date"], "edit_ref": result["ref"],
                    "edit_formula": result["formula"], "edit_hours": float(result["hours"]), "auto_compose": True
                })

    with col_b:
        st.subheader("🤖 ขั้นตอนที่ 2: ผลการประเมินจาก AI")
        notice = st.session_state.get("ai_notice")
        if notice:
            if notice[0] == "success": st.success(notice[1])
            else: st.warning(notice[1])

        defaults = {"edit_cat": CATEGORIES[1], "edit_title": "", "edit_venue": "", "edit_date": "", "edit_ref": "", "edit_formula": "", "edit_hours": 0.0, "auto_compose": True}
        for k, v in defaults.items():
            if k not in st.session_state: st.session_state[k] = v

        final_cat = st.selectbox("📂 หมวดภาระงาน:", CATEGORIES, key="edit_cat")
        c_f1, c_f2 = st.columns(2)
        with c_f1:
            final_title = st.text_input("1. ชื่อบทบาท / ผลงาน:", key="edit_title")
            final_date = st.text_input("3. วันที่ปฏิบัติงาน:", key="edit_date")
            final_formula = st.text_input("5. สูตรคำนวณ (ในวงเล็บ):", key="edit_formula")
        with c_f2:
            final_venue = st.text_input("2. สถานที่จัด:", key="edit_venue")
            final_ref = st.text_input("4. เลขที่อ้างอิง:", key="edit_ref")
            final_hours = st.number_input("6. ชั่วโมงสุทธิ:", min_value=0.0, step=0.5, format="%.2f", key="edit_hours")

        if st.checkbox("สร้างข้อความอัตโนมัติ", key="auto_compose"):
            st.session_state["edit_formal_text"] = compose_formal_text(final_title, final_venue, final_date, final_ref, final_formula, float(final_hours))

        final_formal_text = st.text_area("📝 ข้อความทางการ:", key="edit_formal_text", height=120)

        if st.button("💾 บันทึกลงคลังภาระงาน", type="primary", use_container_width=True):
            if not final_formal_text.strip(): st.warning("⚠️ ยังไม่มีข้อความให้บันทึก")
            else:
                new_entry = {"email": effective_email, "หมวดงาน": final_cat, "รายการภาระงาน": final_formal_text, "เลขคำสั่ง_อ้างอิง": final_ref, "วันที่": final_date, "ภาระงาน_ชม": float(final_hours), "วันที่บันทึก": datetime.now().strftime("%Y-%m-%d %H:%M")}
                updated_all_df = pd.concat([all_data_df, pd.DataFrame([new_entry])], ignore_index=True)
                ok, err = save_all_data(updated_all_df)
                if ok:
                    st.session_state["show_saved_success"] = True
                    st.rerun()

# ---------------------------------------------------------
# TAB 2 & 3 (คลังและออกรายงาน - ใช้ตรรกะเดิมตามที่วางมาได้เลย)
# ---------------------------------------------------------
with tab2:
    st.subheader(f"📊 คลังภาระงานสะสม: {effective_email}")
    user_df = all_data_df[all_data_df["email"] == effective_email].copy()
    if user_df.empty: st.info("ยังไม่มีข้อมูลภาระงาน")
    else:
        edited_user_df = st.data_editor(user_df[["หมวดงาน", "รายการภาระงาน", "เลขคำสั่ง_อ้างอิง", "วันที่", "ภาระงาน_ชม"]].reset_index(drop=True), use_container_width=True, num_rows="dynamic")
        c1, c2, c3 = st.columns([1.5, 1, 1])
        with c1: st.metric(label="📈 รวมชั่วโมงสะสม", value=f"{pd.to_numeric(edited_user_df['ภาระงาน_ชม'], errors='coerce').fillna(0).sum():.1f}")
        with c2:
            if st.button("🔄 บันทึกการแก้ไข", type="primary"):
                to_save = edited_user_df.copy()
                to_save["email"], to_save["วันที่บันทึก"] = effective_email, datetime.now().strftime("%Y-%m-%d %H:%M")
                save_all_data(pd.concat([all_data_df[all_data_df["email"] != effective_email], to_save[to_save["รายการภาระงาน"].str.strip() != ""]]))
                st.rerun()
        with c3:
            if st.button("🗑️ ลบข้อมูลคุณทั้งหมด", type="secondary") and st.checkbox("ยืนยัน", key="del"):
                save_all_data(all_data_df[all_data_df["email"] != effective_email])
                st.rerun()

with tab3:
    st.subheader(f"📋 สรุปผลการประเมิน: {effective_email}")
    user_df = all_data_df[all_data_df["email"] == effective_email]
    t_hrs = float(pd.to_numeric(user_df["ภาระงาน_ชม"], errors="coerce").fillna(0).sum()) if not user_df.empty else 0.0
    c1 = min(t_hrs / 35.0, 1.0) * 70.0
    c2 = st.number_input("องค์ประกอบ 2:", value=30.0, max_value=30.0)
    st.metric("คะแนนรวมสุทธิ", f"{c1 + c2:.2f} / 100")
