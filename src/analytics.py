"""Safety Incident Analytics & Statistics Module.
Analyzes inner document text ("ไส้ใน") to categorize incident nature,
extract incident years, and provide statistical aggregations and drill-downs.
"""

import re
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd
from src.config import DB_PATH, CATEGORY_MAP
from src.database import get_connection


def extract_incident_year(text: str, default_year: int = 2569) -> int:
    """Extracts Buddhist Era (พ.ศ.) or Christian Era year from inner text."""
    if not text:
        return default_year

    # Look for Thai Buddhist year (e.g. 2560 - 2575 or 60 - 75)
    match_be = re.search(r'\b(25[5-7][0-9])\b', text)
    if match_be:
        return int(match_be.group(1))

    # Look for 2-digit BE (e.g. /69, /2569)
    match_slash = re.search(r'/(25)?(6[0-9]|7[0-5])\b', text)
    if match_slash:
        y = int(match_slash.group(2))
        return 2500 + y if y < 100 else y

    # Look for CE year (e.g. 2020 - 2030)
    match_ce = re.search(r'\b(20[2-3][0-9])\b', text)
    if match_ce:
        return int(match_ce.group(1)) + 543

    return default_year


def classify_incident_nature(text: str, category: str) -> str:
    """Classifies the deep incident characteristics ("ไส้ใน") based on keywords."""
    t = text.lower() if text else ""

    # Check for electrical & fire first
    if any(k in t for k in ["ไฟดูด", "ไฟฟ้าดูด", "ไฟช็อต", "ไฟฟ้าช็อต", "ประกายไฟ", "อาร์ก", "กระแสไฟฟ้า", "สายไฟขาด", "hot work"]):
        return "⚡ โดนไฟดูด / ประกายไฟ / ไฟฟ้า"
    # Check for slip, trip, falls
    elif any(k in t for k in ["ลื่น", "สะดุด", "พลัดตก", "หกล้ม", "เสียหลักล้ม", "ตกจากที่สูง", "น้ำขัง", "พื้นเปียก"]):
        return "🚶‍♂️ พลัดตกหกล้ม / สะดุด / ลื่นล้ม"
    # Check for chemical hazards
    elif any(k in t for k in ["สารเคมี", "กรด", "ด่าง", "ไฮโดรคลอริก", "รั่วไหล", "สารกัดกร่อน", "กระเด็น", "spill"]):
        return "🧪 สารเคมี / ของเหลวอันตราย"
    # Check for vehicle collisions (Note: avoid bare 'ชน' which matches 'ประชาชน'!)
    elif any(k in t for k in ["เฉี่ยวชน", "รถชน", "ชนท้าย", "ชนเสา", "ชนกับ", "ถอยชน", "การชน", "ถูกชน", "ถอยหลัง", "รถบรรทุก", "รถกระบะ", "โฟล์กลิฟต์", "forklift", "เปลี่ยนช่องทาง", "วงเลี้ยว", "ไฟท้ายแตก"]):
        return "🚗 เฉี่ยวชน / ยานพาหนะ"
    # Check for struck by / pinched / caught in
    elif any(k in t for k in ["ของตกใส่", "วัตถุตก", "หล่นทับ", "หนีบ", "กระแทก", "ทับมือ", "ทับเท้า", "คอนเหล็ก"]):
        return "📦 วัตถุตกใส่ / หนีบ / กระแทก"
    elif category == "OB_PO_3":
        return "🚗 เฉี่ยวชน / ยานพาหนะ"
    elif category == "OB_PO_4":
        return "👥 ประชาชน / บุคคลภายนอก"
    else:
        return "📋 อุบัติเหตุอื่นๆ"


def extract_district(text: str) -> str:
    """Extracts MEA district (กฟน.เขต) or department from inner text."""
    t = text if text else ""
    for d in ["บางใหญ่", "บางนา", "ธนบุรี", "มีนบุรี", "ลาดกระบัง", "นนทบุรี", "พระนคร", "สมุทรปราการ", "บางเขน", "คลองเตย", "ยานนาวา", "บางกะปิ", "ราษฎร์บูรณะ", "สปฟ."]:
        if d in t:
            return f"กฟน.เขต{d}" if d != "สปฟ." else "สหกรณ์บริการ (สปฟ.)"
    return "กฟน.เขตอื่นๆ / ทั่วไป"


def get_incident_analytics_data(db_path: Path = DB_PATH) -> pd.DataFrame:
    """Builds a rich statistical dataset from indexed documents by reading 'ไส้ใน'."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                f.id as file_id,
                f.filename,
                f.filepath,
                f.category,
                f.file_size,
                f.total_pages,
                f.imported_at,
                GROUP_CONCAT(dp.raw_text, ' ') as full_text
            FROM files f
            LEFT JOIN document_pages dp ON f.id = dp.file_id
            WHERE f.is_active = 1
              AND f.category IN ('OB_PO_1_2', 'OB_PO_3', 'OB_PO_4', 'Accidents_Personnel', 'Accidents_Road', 'Other')
            GROUP BY f.id
        """)
        rows = cursor.fetchall()
    finally:
        conn.close()

    records = []
    for r in rows:
        text = r["full_text"] or ""
        cat = r["category"]

        # Map legacy categories
        if cat == "Accidents_Personnel":
            standard_cat = "OB_PO_1_2"
        elif cat == "Accidents_Road":
            standard_cat = "OB_PO_3"
        else:
            standard_cat = cat

        year = extract_incident_year(text)
        nature = classify_incident_nature(text, standard_cat)
        district = extract_district(text)

        # Brief summary from first 150 characters
        summary = text[:150].replace("\n", " ").strip()
        if len(text) > 150:
            summary += "..."

        records.append({
            "file_id": r["file_id"],
            "filename": r["filename"],
            "filepath": r["filepath"],
            "category": standard_cat,
            "category_th": CATEGORY_MAP.get(standard_cat, standard_cat),
            "year": year,
            "nature": nature,
            "district": district,
            "summary": summary,
            "total_pages": r["total_pages"],
            "file_size_kb": round(r["file_size"] / 1024, 1),
            "imported_at": r["imported_at"]
        })

    if not records:
        return pd.DataFrame()

    return pd.DataFrame(records)
