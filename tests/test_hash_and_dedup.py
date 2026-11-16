"""Unit Test 2: Cryptographic SHA-256 and Deduplication Verification.
Tests hash stability and ensures identical file contents are detected as duplicates.
"""

import sys
import shutil
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pdf_parser import compute_sha256
from src.database import sync_documents, init_db, get_connection
from tests.generate_sample_pdfs import create_sample_pdf


class TestHashAndDeduplication(unittest.TestCase):
    def setUp(self):
        import gc
        gc.collect()
        self.test_docs = PROJECT_ROOT / "tests" / "test_dedup_docs"
        self.test_db = PROJECT_ROOT / "tests" / "test_dedup.db"
        if self.test_docs.exists():
            shutil.rmtree(self.test_docs, ignore_errors=True)
        if self.test_db.exists():
            try:
                self.test_db.unlink()
            except Exception:
                pass

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

    def test_sha256_hash_reproducibility(self):
        """SHA-256 must produce deterministic and repeatable hash."""
        pdf_path = self.test_docs / "doc1.pdf"
        create_sample_pdf(pdf_path, ["ทดสอบระบบความปลอดภัย SHA256"])

        hash1 = compute_sha256(pdf_path)
        hash2 = compute_sha256(pdf_path)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64, "SHA-256 must be 64 hexadecimal characters")

    def test_duplicate_file_detection(self):
        """Identical content under a different filename must be detected as duplicate."""
        original_pdf = self.test_docs / "Accidents_Personnel" / "incident_original.pdf"
        duplicate_pdf = self.test_docs / "Other" / "copy_of_incident.pdf"

        # Create original PDF
        create_sample_pdf(original_pdf, ["เนื้อหาเหมือนกันทุกประการ เพื่อทดสอบ Deduplication"])
        
        # Copy to create duplicate file
        duplicate_pdf.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original_pdf, duplicate_pdf)

        # Sync documents into test database
        stats = sync_documents(docs_dir=self.test_docs, db_path=self.test_db)

        # Expect 1 added, 1 detected as duplicate
        self.assertEqual(stats["added"], 1)
        self.assertEqual(stats["duplicates"], 1)

        # Check database records
        conn = get_connection(self.test_db)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM files")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1, "Only one unique file should be ingested")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
