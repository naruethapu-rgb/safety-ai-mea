"""Unit Test 3: Incremental Sync and Change Detection Verification.
Tests adding new files, skipping unchanged files, updating modified files,
and deactivating deleted files.
"""

import sys
import shutil
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import sync_documents, init_db, get_connection, search_documents
from tests.generate_sample_pdfs import create_sample_pdf


class TestSyncMechanism(unittest.TestCase):
    def setUp(self):
        self.test_docs = PROJECT_ROOT / "tests" / "test_sync_docs"
        self.test_db = PROJECT_ROOT / "tests" / "test_sync.db"
        if self.test_docs.exists():
            shutil.rmtree(self.test_docs)
        if self.test_db.exists():
            self.test_db.unlink()

        self.test_docs.mkdir(parents=True, exist_ok=True)
        init_db(self.test_db)

    def tearDown(self):
        import gc
        gc.collect()
        if self.test_docs.exists():
            shutil.rmtree(self.test_docs, ignore_errors=True)
        if self.test_db.exists():
            try:
                self.test_db.unlink()
            except Exception:
                pass

    def test_incremental_sync_lifecycle(self):
        """Tests the full lifecycle: Add -> Skip -> Update -> Deactivate."""
        target_file = self.test_docs / "WI" / "WI-001.pdf"
        
        # 1. ADD NEW FILE
        create_sample_pdf(target_file, ["เวอร์ชันแรก: ขั้นตอนการทำงานที่ปลอดภัย"])
        stats1 = sync_documents(docs_dir=self.test_docs, db_path=self.test_db)
        self.assertEqual(stats1["added"], 1)
        self.assertEqual(stats1["skipped"], 0)
        self.assertEqual(stats1["updated"], 0)

        # 2. SYNC UNCHANGED FILE (Should Skip)
        stats2 = sync_documents(docs_dir=self.test_docs, db_path=self.test_db)
        self.assertEqual(stats2["added"], 0)
        self.assertEqual(stats2["skipped"], 1)
        self.assertEqual(stats2["updated"], 0)

        # 3. MODIFY FILE (Wait 1 sec to ensure mtime changes)
        time.sleep(1.0)
        create_sample_pdf(target_file, [
            "เวอร์ชันสอง: มีการแก้ไขเนื้อหาใหม่ เพิ่มกฎระเบียบฉุกเฉิน",
            "หน้า 2: รายละเอียดเพิ่มเติม"
        ])
        stats3 = sync_documents(docs_dir=self.test_docs, db_path=self.test_db)
        self.assertEqual(stats3["updated"], 1)
        self.assertEqual(stats3["skipped"], 0)

        # Verify updated content is searchable
        results = search_documents("กฎระเบียบฉุกเฉิน", db_path=self.test_db)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["total_pages"], 2)

        # 4. REMOVE FILE (Should Deactivate)
        target_file.unlink()
        stats4 = sync_documents(docs_dir=self.test_docs, db_path=self.test_db)
        self.assertEqual(stats4["deactivated"], 1)

        # Deactivated file should not appear in search results
        results_after_delete = search_documents("กฎระเบียบฉุกเฉิน", db_path=self.test_db)
        self.assertEqual(len(results_after_delete), 0)


if __name__ == "__main__":
    unittest.main()
