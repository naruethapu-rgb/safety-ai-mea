"""Unit Test 6: AI Accident Intelligence Analyzer & WI Matching.
Tests similar past incident retrieval, WI clause matching, and offline analysis.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analyzer import (
    find_similar_past_incidents, match_relevant_wi,
    generate_offline_analysis, save_analysis_record, list_saved_analyses,
    init_analysis_table
)
from src.config import DB_PATH


class TestAnalyzer(unittest.TestCase):
    def setUp(self):
        init_analysis_table(DB_PATH)

    def test_similar_slip_fall_incident_matching(self):
        """A new incident describing oil slip on floor must match the past slip/fall case."""
        new_incident = (
            "รายงานอุบัติเหตุใหม่: พนักงานฝ่ายผลิตกำลังเดินตรวจงานในกะดึก "
            "ได้ลื่นไถลจากคราบน้ำมันหล่อลื่นที่นองอยู่บนพื้น ข้อเท้าเคล็ด และกล่องควบคุมเครื่องจักรแตก"
        )
        similar_cases = find_similar_past_incidents(new_incident, top_n=3, db_path=DB_PATH)
        self.assertGreaterEqual(len(similar_cases), 1)
        top_case = similar_cases[0]
        # Should match Case 2024_001 (slip & fall) or slip_fall
        self.assertIn("slip", top_case["filename"].lower())
        self.assertGreater(top_case["similarity_score"], 20.0)

    def test_wi_clause_matching(self):
        """A forklift incident must match WI-SAF-003 (forklift operation)."""
        forklift_incident = (
            "อุบัติเหตุใหม่: รถโฟล์กลิฟต์เบอร์ 4 กำลังถอยหลังเข้าช่องเก็บสินค้า "
            "คนขับมองไม่เห็นเสาค้ำยันจึงถอยชนเสา และไม่ได้บีบแตรให้สัญญาณ"
        )
        matched_wi = match_relevant_wi(forklift_incident, top_n=3, db_path=DB_PATH)
        self.assertGreaterEqual(len(matched_wi), 1)
        top_wi = matched_wi[0]
        self.assertIn("forklift", top_wi["filename"].lower())
        self.assertGreater(top_wi["relevance_score"], 15.0)

    def test_offline_analysis_and_save(self):
        """Offline analysis generation and saving to SQLite must succeed."""
        incident = "สารเคมีกรดกระเด็นใส่แขนพนักงาน ไม่สวมถุงมือยาง"
        similar = find_similar_past_incidents(incident, top_n=2, db_path=DB_PATH)
        matched_wi = match_relevant_wi(incident, top_n=2, db_path=DB_PATH)

        report = generate_offline_analysis(incident, similar, matched_wi)
        self.assertIn("ผลการวิเคราะห์หาสาเหตุและวิธีการป้องกัน", report)
        self.assertIn("การเปรียบเทียบเชิงลึกกับอุบัติเหตุในอดีต", report)

        rec_id = save_analysis_record(
            incident_title="ทดสอบเคสกรดหก",
            incident_text=incident,
            source_filename="test_acid.pdf",
            similar_cases=similar,
            matched_wi=matched_wi,
            analysis_markdown=report,
            ai_engine="Offline Engine",
            db_path=DB_PATH
        )
        self.assertGreater(rec_id, 0)

        saved = list_saved_analyses(DB_PATH)
        self.assertTrue(any(s["id"] == rec_id for s in saved))


if __name__ == "__main__":
    unittest.main()
