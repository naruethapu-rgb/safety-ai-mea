"""Unit Test 4: Thai and Multilingual Search Engine Verification.
Tests word segmentation, FTS5 matching, category filtering,
and correct page number & filename attribution.
"""

import sys
import shutil
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import sync_documents, init_db, search_documents, get_page_detail
from tests.generate_sample_pdfs import generate_all_samples


class TestThaiSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_docs = PROJECT_ROOT / "tests" / "test_search_docs"
        cls.test_db = PROJECT_ROOT / "tests" / "test_search.db"
        if cls.test_docs.exists():
            shutil.rmtree(cls.test_docs)
        if cls.test_db.exists():
            cls.test_db.unlink()

        cls.test_docs.mkdir(parents=True, exist_ok=True)
        init_db(cls.test_db)
        
        # Populate all 5 categories with realistic safety documents
        generate_all_samples(cls.test_docs)
        sync_documents(docs_dir=cls.test_docs, db_path=cls.test_db)

    @classmethod
    def tearDownClass(cls):
        import gc
        gc.collect()
        if cls.test_docs.exists():
            shutil.rmtree(cls.test_docs, ignore_errors=True)
        if cls.test_db.exists():
            try:
                cls.test_db.unlink()
            except Exception:
                pass

    def test_thai_safety_terms_search(self):
        """Test searching standard Thai safety terms without manual spaces."""
        # 1. Search for 'ที่อับอากาศ' (Confined Space) -> should find WI-SAF-002
        results = search_documents("ที่อับอากาศ", db_path=self.test_db)
        self.assertGreaterEqual(len(results), 1)
        found_files = [r["filename"] for r in results]
        self.assertTrue(any("confined_space" in fn for fn in found_files))
        # Ensure page 1 is returned
        page_nums = [r["page_number"] for r in results if "confined_space" in r["filename"]]
        self.assertIn(1, page_nums)

        # 2. Search for 'สารเคมีรั่วไหล' (Chemical Spill)
        results_chem = search_documents("สารเคมีรั่วไหล", db_path=self.test_db)
        self.assertGreaterEqual(len(results_chem), 1)
        self.assertTrue(any("chemical_spill" in r["filename"] for r in results_chem))

        # 3. Search for 'รองเท้านิรภัย' (Safety Shoes)
        results_shoes = search_documents("รองเท้านิรภัย", db_path=self.test_db)
        self.assertGreaterEqual(len(results_shoes), 1)
        # Should match page 2 of slip_fall
        matched = [r for r in results_shoes if "slip_fall" in r["filename"]]
        self.assertTrue(len(matched) > 0)
        self.assertEqual(matched[0]["page_number"], 2)

    def test_english_and_code_search(self):
        """Test searching English words and alphanumeric document numbers."""
        # Search for PPE
        results_ppe = search_documents("PPE", db_path=self.test_db)
        self.assertGreaterEqual(len(results_ppe), 1)

        # Search for Forklift
        results_fl = search_documents("Forklift", db_path=self.test_db)
        self.assertGreaterEqual(len(results_fl), 1)
        self.assertTrue(any("forklift" in r["filename"] for r in results_fl))

        # Search for Document Code: WI-SAF-002
        results_code = search_documents("WI-SAF-002", db_path=self.test_db)
        self.assertGreaterEqual(len(results_code), 1)

    def test_category_filtering(self):
        """Test search with category filter applied."""
        # Search 'รายงานอุบัติเหตุ' specifically in 'Accidents_Road'
        results = search_documents("รายงานอุบัติเหตุ", category="Accidents_Road", db_path=self.test_db)
        self.assertGreaterEqual(len(results), 1)
        for r in results:
            self.assertEqual(r["category"], "Accidents_Road")

    def test_snippet_highlighting(self):
        """Verify that snippet contains HTML highlight marks."""
        results = search_documents("ถังดับเพลิง", db_path=self.test_db)
        self.assertGreaterEqual(len(results), 1)
        snippet = results[0]["snippet"]
        self.assertIn("<mark", snippet)
        self.assertIn("ถังดับเพลิง", snippet)

    def test_page_detail_retrieval(self):
        """Verify full original text retrieval by page_id."""
        results = search_documents("ที่อับอากาศ", db_path=self.test_db)
        self.assertGreaterEqual(len(results), 1)
        page_id = results[0]["page_id"]

        detail = get_page_detail(page_id, db_path=self.test_db)
        self.assertIsNotNone(detail)
        self.assertIn("คู่มือปฏิบัติงาน: ความปลอดภัยในสถานที่อับอากาศ", detail["raw_text"])
        self.assertGreater(detail["char_count"], 50)


if __name__ == "__main__":
    unittest.main()
