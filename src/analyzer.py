"""AI Accident Intelligence Analyzer Module.
Compares new incidents against historical cases (OB_PO 1-4) and 
evaluates compliance against Work Instructions (WI).
Supports both OpenAI GPT Copilot and 100% Offline Machine Learning (TF-IDF).
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from src.config import DB_PATH, CATEGORY_MAP
from src.database import get_connection
from src.thai_indexer import tokenize_for_fts
from src.usage_tracker import record_api_usage

logger = logging.getLogger(__name__)


def init_analysis_table(db_path: Path = DB_PATH) -> None:
    """Creates the incident_analyses table if it doesn't exist."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS incident_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_title TEXT NOT NULL,
                incident_text TEXT NOT NULL,
                source_filename TEXT,
                top_similar_cases_json TEXT,
                relevant_wi_json TEXT,
                analysis_markdown TEXT NOT NULL,
                ai_engine TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    finally:
        conn.close()


def find_similar_past_incidents(
    incident_text: str, 
    top_n: int = 3, 
    db_path: Path = DB_PATH
) -> List[Dict[str, Any]]:
    """Finds top N most similar historical incidents from OB_PO forms using TF-IDF."""
    if not incident_text.strip():
        return []

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        # Query past incidents from OB_PO categories
        cursor.execute("""
            SELECT 
                dp.id as page_id,
                dp.file_id,
                dp.page_number,
                dp.raw_text,
                f.filename,
                f.filepath,
                f.category,
                f.imported_at
            FROM document_pages dp
            JOIN files f ON dp.file_id = f.id
            WHERE f.category IN ('OB_PO_1_2', 'OB_PO_3', 'OB_PO_4', 'Accidents_Personnel', 'Accidents_Road')
              AND f.is_active = 1
        """)
        past_records = cursor.fetchall()
    finally:
        conn.close()

    if not past_records:
        return []

    # Tokenize input and historical records
    tokenized_new = tokenize_for_fts(incident_text)
    corpus = [tokenized_new]
    doc_meta = []

    for rec in past_records:
        corpus.append(tokenize_for_fts(rec["raw_text"]))
        doc_meta.append(rec)

    try:
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(corpus)
        
        # Calculate cosine similarity of new incident (idx 0) against all past incidents (idx 1:)
        sim_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
        
        # Get top N indices
        top_indices = np.argsort(sim_scores)[::-1][:top_n]
        
        results = []
        for idx in top_indices:
            score = float(sim_scores[idx])
            rec = doc_meta[idx]
            
            # Extract preview snippet
            raw_text = rec["raw_text"]
            snippet = raw_text[:200].replace("\n", " ") + ("..." if len(raw_text) > 200 else "")
            
            results.append({
                "page_id": rec["page_id"],
                "file_id": rec["file_id"],
                "filename": rec["filename"],
                "filepath": rec["filepath"],
                "category": rec["category"],
                "category_th": CATEGORY_MAP.get(rec["category"], rec["category"]),
                "page_number": rec["page_number"],
                "imported_at": rec["imported_at"],
                "similarity_score": round(score * 100, 1),
                "snippet": snippet,
                "raw_text": raw_text
            })
            
        return results
    except Exception as e:
        logger.error(f"Error calculating incident similarity: {e}")
        return []


def match_relevant_wi(
    incident_text: str, 
    top_n: int = 3, 
    db_path: Path = DB_PATH
) -> List[Dict[str, Any]]:
    """Scans Work Instructions (WI) database to identify applicable safety standards."""
    if not incident_text.strip():
        return []

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                dp.id as page_id,
                dp.file_id,
                dp.page_number,
                dp.raw_text,
                f.filename,
                f.filepath,
                f.category
            FROM document_pages dp
            JOIN files f ON dp.file_id = f.id
            WHERE f.category = 'WI'
              AND f.is_active = 1
        """)
        wi_records = cursor.fetchall()
    finally:
        conn.close()

    if not wi_records:
        return []

    tokenized_new = tokenize_for_fts(incident_text)
    corpus = [tokenized_new]
    doc_meta = []

    for rec in wi_records:
        corpus.append(tokenize_for_fts(rec["raw_text"]))
        doc_meta.append(rec)

    try:
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(corpus)
        sim_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
        top_indices = np.argsort(sim_scores)[::-1][:top_n]

        results = []
        for idx in top_indices:
            score = float(sim_scores[idx])
            rec = doc_meta[idx]
            raw_text = rec["raw_text"]
            snippet = raw_text[:250].replace("\n", " ") + ("..." if len(raw_text) > 250 else "")

            results.append({
                "page_id": rec["page_id"],
                "file_id": rec["file_id"],
                "filename": rec["filename"],
                "filepath": rec["filepath"],
                "page_number": rec["page_number"],
                "relevance_score": round(score * 100, 1),
                "snippet": snippet,
                "raw_text": raw_text
            })
        return results
    except Exception as e:
        logger.error(f"Error matching WI: {e}")
        return []


def generate_offline_analysis(
    incident_text: str,
    similar_cases: List[Dict[str, Any]],
    matched_wi: List[Dict[str, Any]],
    target_form: str = "อบ.ปอ. 3",
    analyst_name: str = "นายนฤเทพ อุบลรัศมี"
) -> str:
    """Generates an intelligent rule-based analysis report following MEA official forms."""
    md = []
    
    # Header based on selected form
    if "1-2" in target_form:
        form_title = "อุบัติภัยสำหรับพนักงาน (อบ.ปอ. 1-2)"
    elif "4" in target_form:
        form_title = "อุบัติภัยสำหรับประชาชน/บุคคลภายนอก (อบ.ปอ. 4)"
    else:
        form_title = "อุบัติภัยสำหรับพนักงานขับยานพาหนะ (อบ.ปอ. 3)"

    md.append("# ผลการวิเคราะห์หาสาเหตุและวิธีการป้องกัน")
    md.append(f"## {form_title}\n")
    md.append(f"**อุบัติภัยราย:** (ข้อมูลตามรายงานที่ส่งมา) วันเวลาเกิดเหตุ: (ตามบันทึกข้อความ M/N)\n")

    md.append("### ลักษณะการเกิดอุบัติเหตุ")
    md.append(incident_text.strip() + "\n")

    md.append("### การเปรียบเทียบเชิงลึกกับอุบัติเหตุในอดีต (วิเคราะห์เนื้อหาไส้ใน)")
    if similar_cases:
        top_c = similar_cases[0]
        md.append(f"- **เคสในอดีตที่ตรวจพบว่าพฤติการณ์ใกล้เคียงที่สุด:** `{top_c['filename']}` (ระดับความคล้ายคลึง: **{top_c['similarity_score']}%**)")
        md.append(f"- **จุดที่เหมือน/ใกล้เคียงกัน:** ลักษณะพฤติกรรม สภาพพื้นที่ หรือประเภทของยานพาหนะ/อุปกรณ์ มีความสอดคล้องกับเหตุการณ์ก่อนหน้า")
        md.append(f"- **ข้อความจากเคสเดิม:** _{top_c['snippet']}_")
    else:
        md.append("- ไม่พบเคสเก่าในอดีตที่มีพฤติการณ์ตรงกันในระบบ")

    md.append("\n### สาเหตุ")
    if "3" in target_form:
        md.append("เกิดจากผู้ขับขี่ยานพาหนะเว้นระยะห่างกับรถคู่กรณีไม่เพียงพอ และประเมินรัศมีวงเลี้ยวของรถขนาดใหญ่ไม่ครอบคลุม ทำให้เกิดการเฉี่ยวชน กฟน. เป็นฝ่ายผิด")
    elif "1-2" in target_form:
        md.append("1. สภาพพื้นที่ปฏิบัติงานไม่ปลอดภัย มีน้ำขังหรือพื้นเปียกลื่น เพิ่มความเสี่ยงต่อการเสียหลักล้ม")
        md.append("2. การเคลื่อนย้ายอุปกรณ์มีความเสี่ยงต่อการเสียสมดุลและการทรงตัว")
        md.append("3. การประเมินความปลอดภัยของเส้นทางก่อนเคลื่อนย้ายยังไม่เพียงพอ")
    else:
        md.append("1. การจัดการพื้นที่และเส้นทางสัญจรสาธารณะไม่ปลอดภัย ขาดอุปกรณ์ป้องกันการสะดุดล้ม")
        md.append("2. ขาดการติดตั้งป้ายเตือนอันตรายและแนวกั้นพื้นที่ทำงานก่อสร้าง/ปรับปรุง")
        md.append("3. การกำกับดูแลความปลอดภัยงานผู้รับเหมาในพื้นที่สัญจรยังไม่รัดกุม")

    md.append("\n### การตรวจสอบการละเมิดคู่มือปฏิบัติงาน (WI)")
    if matched_wi:
        top_w = matched_wi[0]
        md.append(f"- **คู่มือ WI ที่เกี่ยวข้อง:** `{top_w['filename']}` (ความสอดคล้อง **{top_w['relevance_score']}%**)")
        md.append(f"- **ข้อกำหนดที่ต้องยึดถือ:** _{top_w['snippet']}_")
    else:
        md.append("- ไม่พบคู่มือ WI ที่เกี่ยวข้องโดยตรง")

    md.append("\n### วิธีการป้องกัน")
    if "3" in target_form:
        md.append("ก่อนบังคับรถเลี้ยว ผู้ขับขี่ยานพาหนะต้องประเมินเว้นระยะห่างจากรถคันอื่นโดยรอบให้เพียงพอและเหมาะสมกับขนาดรถ โดยเฉพาะบริเวณทางแยก ใช้ความเร็วเหมาะสม และใช้ความระมัดระวังเป็นพิเศษ")
    elif "1-2" in target_form:
        md.append("1. ก่อนเคลื่อนย้ายอุปกรณ์ ให้ตรวจสอบสภาพเส้นทางเดิน หากพบพื้นเปียกลื่นหรือมีน้ำขัง ต้องหลีกเลี่ยงหรือแก้ไขก่อน")
        md.append("2. ประเมินน้ำหนัก ขนาด และความยาวของอุปกรณ์ โดยใช้อุปกรณ์ช่วยยก (เช่น รถเข็น หรือคนช่วยหาม)")
        md.append("3. ปรับปรุงและดูแลพื้นที่ทางเดินให้ปลอดภัยเพื่อลดความเสี่ยงจากการลื่นล้ม")
        md.append("4. เมื่อเกิดอุบัติเหตุ ให้หยุดปฏิบัติงานและแจ้งหัวหน้างานทันที")
    else:
        md.append("1. ห้ามวางสิ่งกีดขวางหรือลากสายไฟผ่านทางสัญจรของประชาชน หากจำเป็นต้องมีรางครอบกันสะดุด (Cable Ramp)")
        md.append("2. กั้นแนวกั้นพื้นที่ทำงานและติดตั้งป้ายเตือนให้เห็นชัดเจนก่อนถึงจุดทำงาน")
        md.append("3. เจ้าหน้าที่ควบคุมงานต้องตรวจสอบความปลอดภัยของพื้นที่ก่อนเริ่มงานและสุ่มตรวจสม่ำเสมอ")

    md.append(f"\n\n                                                        {analyst_name}\n                                                            ผู้วิเคราะห์")
    return "\n".join(md)


def generate_gpt_analysis(
    incident_text: str,
    similar_cases: List[Dict[str, Any]],
    matched_wi: List[Dict[str, Any]],
    api_key: str,
    model_name: str = "gpt-4o-mini",
    target_form: str = "อบ.ปอ. 3",
    analyst_name: str = "นายนฤเทพ อุบลรัศมี"
) -> Tuple[str, str]:
    """Generates deep AI accident analysis following MEA official forms."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        similar_cases_context = ""
        for i, c in enumerate(similar_cases[:3]):
            similar_cases_context += f"\n[เคสเก่าในอดีตที่ {i+1}]: ไฟล์ {c['filename']} (หมวด {c['category_th']}) ความคล้าย {c['similarity_score']}%\nเนื้อหาไส้ใน: {c['raw_text'][:600]}\n"

        wi_context = ""
        for i, w in enumerate(matched_wi[:3]):
            wi_context += f"\n[คู่มือ WI ที่ {i+1}]: ไฟล์ {w['filename']} ความเกี่ยวข้อง {w['relevance_score']}%\nเนื้อหาข้อกำหนด: {w['raw_text'][:600]}\n"

        system_prompt = (
            "คุณคือผู้เชี่ยวชาญระดับสูงด้านความปลอดภัยและอาชีวอนามัย (Senior Safety Specialist / จป.วิชาชีพ) ของการไฟฟ้านครหลวง (กฟน.) "
            "หน้าที่ของคุณคือวิเคราะห์รายงานอุบัติเหตุที่เกิดขึ้นใหม่ โดยอ่านและวิเคราะห์ 'ไส้ใน' (เนื้อหาพฤติการณ์การเกิดเหตุทั้งหมด) "
            "เปรียบเทียบกับอุบัติเหตุเก่าในอดีต (อบ.ปอ. 1-4) และตรวจสอบเทียบกับคู่มือขั้นตอนการปฏิบัติงาน (Work Instructions - WI) "
            f"โดยต้องร่างรายงานผลการวิเคราะห์ให้ออกมาตามแบบฟอร์มทางการ '{target_form}' อย่างเคร่งครัด "
            f"และลงชื่อท้ายรายงานโดย '{analyst_name} ผู้วิเคราะห์'"
        )

        user_prompt = f"""
กรุณาวิเคราะห์อุบัติเหตุเคสใหม่นี้ตามแบบฟอร์มทางการ '{target_form}':

================== รายงานอุบัติเหตุเคสใหม่ (ข้อมูลไส้ใน) ==================
{incident_text}

================== อุบัติเหตุในอดีตที่ระบบดึงเนื้อหาไส้ในมาเทียบ ==================
{similar_cases_context if similar_cases_context else "ไม่มีเคสเก่าที่ตรงกัน"}

================== ข้อกำหนดในคู่มือปฏิบัติงานที่เกี่ยวข้อง (WI) ==================
{wi_context if wi_context else "ไม่มีคู่มือ WI ที่ตรงกันโดยตรง"}

================== รูปแบบผลการวิเคราะห์ที่ต้องสร้าง (ตามแบบฟอร์มทางการ กฟน.) ==================
# ผลการวิเคราะห์หาสาเหตุและวิธีการป้องกัน
## {target_form}

**อุบัติภัยราย:** (ระบุชื่อผู้ประสบเหตุ ตำแหน่ง สังกัด แผนก กอง เขต วันเวลาเกิดเหตุ จากข้อมูลเคสใหม่)

### ลักษณะการเกิดอุบัติเหตุ
(เล่าพฤติการณ์ไส้ในอย่างกระชับ ชัดเจน ระบุประเภทรถ หมายเลขทะเบียน ภารกิจ เส้นทาง ช่องจราจร และความเสียหาย)

### การเปรียบเทียบเชิงลึกกับอุบัติเหตุในอดีต (วิเคราะห์เนื้อหาไส้ใน)
- ระบุชื่อเคสในอดีตที่ใกล้เคียงที่สุด พร้อมระดับความคล้ายคลึง
- เปรียบเทียบไส้ใน: ชี้จุดที่เหมือนกันของลักษณะการเกิดเหตุ (เช่น ท่าทางการเลี้ยว, วงเลี้ยวรถใหญ่, การยกของยาว, สภาพพื้น)
- สรุปว่าเข้าข่ายอุบัติเหตุซ้ำซากหรือไม่

### สาเหตุ
(ระบุสาเหตุรากเหง้าอย่างตรงไปตรงมา เป็นข้อย่อย 1, 2, 3 ตามสไตล์แบบฟอร์ม กฟน.)

### การตรวจสอบการละเมิดคู่มือปฏิบัติงาน (WI)
(ระบุว่าเข้าข่ายไม่ปฏิบัติตามคู่มือ WI รหัสใด ข้อไหน เรื่องอะไร)

### วิธีการป้องกัน
(ระบุมาตรการปฏิบัติที่เป็นรูปธรรมและปฏิบัติได้จริง เป็นข้อย่อย 1, 2, 3, 4)

                                                        {analyst_name}
                                                            ผู้วิเคราะห์
"""

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=2500
        )

        content = response.choices[0].message.content or ""
        prompt_tokens = response.usage.prompt_tokens if response.usage else 0
        completion_tokens = response.usage.completion_tokens if response.usage else 0

        cost_info = record_api_usage(
            feature="AI Analyzer (วิเคราะห์)",
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            incident_title=target_form
        )
        return content, f"OpenAI ({model_name})", cost_info

    except Exception as e:
        logger.error(f"OpenAI GPT Analysis failed: {e}")
        fallback_text = (
            f"> ⚠️ **การเชื่อมต่อ OpenAI ขัดข้อง:** {str(e)}\n\n"
            f"ระบบจึงสลับมาใช้ผลวิเคราะห์จาก **Offline Safety Engine** อัตโนมัติ:\n\n"
            + generate_offline_analysis(incident_text, similar_cases, matched_wi, target_form, analyst_name)
        )
        return fallback_text, "Offline Safety Matcher (Fallback)", None


def save_analysis_record(
    incident_title: str,
    incident_text: str,
    source_filename: Optional[str],
    similar_cases: List[Dict[str, Any]],
    matched_wi: List[Dict[str, Any]],
    analysis_markdown: str,
    ai_engine: str,
    db_path: Path = DB_PATH
) -> int:
    """Saves the analysis outcome to database for permanent record keeping."""
    init_analysis_table(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO incident_analyses (
                incident_title, incident_text, source_filename,
                top_similar_cases_json, relevant_wi_json,
                analysis_markdown, ai_engine
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            incident_title,
            incident_text,
            source_filename or "",
            json.dumps([{k: v for k, v in c.items() if k != "raw_text"} for c in similar_cases], ensure_ascii=False),
            json.dumps([{k: v for k, v in w.items() if k != "raw_text"} for w in matched_wi], ensure_ascii=False),
            analysis_markdown,
            ai_engine
        ))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_saved_analyses(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    """Retrieves all past accident analyses."""
    init_analysis_table(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, incident_title, source_filename, ai_engine, created_at, analysis_markdown
            FROM incident_analyses
            ORDER BY created_at DESC
        """)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
