"""Unit Test 1: PDF Extraction and Read-Only Verification.
Tests page-by-page text extraction, character counts, and confirms that
original files are never modified or corrupted.
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pdf_parser import extract_pdf_data, compute_sha256
from tests.generate_sample_pdfs import create_sample_pdf


class TestPDFExtraction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = PROJECT_ROOT / "tests" / "temp_docs"
        cls.test_dir.mkdir(parents=True, exist_ok=True)
        cls.sample_pdf = cls.test_dir / "sample_incident.pdf"
        
        cls.pages_text = [
            "หน้า 1: รายงานอุบัติเหตุพนักงานลื่นล้มในไลน์ผลิต ฝ่ายความปลอดภัย",
            "หน้า 2: มาตรการแก้ไขและสวมใส่อุปกรณ์คุ้มครองความปลอดภัยส่วนบุคคล PPE รองเท้านิรภัย"
        ]
        create_sample_pdf(cls.sample_pdf, cls.pages_text)

    @classmethod
    def tearDownClass(cls):
        import shutil
        if cls.test_dir.exists():
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_extract_pdf_pages_count(self):
        """Verify that total page count matches expected count."""
        result = extract_pdf_data(self.sample_pdf)
        self.assertIsNone(result.get("error"))
        self.assertEqual(result["total_pages"], 2)
        self.assertEqual(len(result["pages"]), 2)

    def test_extract_thai_text_content(self):
        """Verify that Thai text is extracted correctly on each page."""
        result = extract_pdf_data(self.sample_pdf)
        page1 = result["pages"][0]
        page2 = result["pages"][1]

        self.assertEqual(page1["page_number"], 1)
        self.assertIn("รายงานอุบัติเหตุ", page1["raw_text"])
        self.assertIn("ลื่นล้ม", page1["raw_text"])

        self.assertEqual(page2["page_number"], 2)
        self.assertIn("มาตรการแก้ไข", page2["raw_text"])
        self.assertIn("PPE", page2["raw_text"])
        self.assertIn("รองเท้านิรภัย", page2["raw_text"])

    def test_read_only_guarantee(self):
        """Verify that extracting text does not alter file hash or timestamp."""
        hash_before = compute_sha256(self.sample_pdf)
        mtime_before = self.sample_pdf.stat().st_mtime

        # Perform extraction
        _ = extract_pdf_data(self.sample_pdf)

        hash_after = compute_sha256(self.sample_pdf)
        mtime_after = self.sample_pdf.stat().st_mtime

        self.assertEqual(hash_before, hash_after, "File hash changed! Read-only violation.")
        self.assertEqual(mtime_before, mtime_after, "File mtime changed! Read-only violation.")


if __name__ == "__main__":
    unittest.main()
