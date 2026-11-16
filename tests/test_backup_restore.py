"""Unit Test 5: Live Database Backup Verification.
Tests SQLite online backup, file creation, and structural integrity.
"""

import sys
import shutil
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database import (
    init_db, sync_documents, backup_database, list_backups,
    get_connection
)
from tests.generate_sample_pdfs import generate_all_samples


class TestBackupRestore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_docs = PROJECT_ROOT / "tests" / "test_backup_docs"
        cls.test_db = PROJECT_ROOT / "tests" / "test_backup_orig.db"
        cls.backup_dir = PROJECT_ROOT / "tests" / "test_backups"

        for p in [cls.test_docs, cls.backup_dir]:
            if p.exists():
                shutil.rmtree(p)
            p.mkdir(parents=True, exist_ok=True)

        if cls.test_db.exists():
            cls.test_db.unlink()

        init_db(cls.test_db)
        generate_all_samples(cls.test_docs)
        sync_documents(docs_dir=cls.test_docs, db_path=cls.test_db)

    @classmethod
    def tearDownClass(cls):
        import gc
        gc.collect()
        for p in [cls.test_docs, cls.backup_dir]:
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
        if cls.test_db.exists():
            try:
                cls.test_db.unlink()
            except Exception:
                pass

    def test_backup_creation_and_integrity(self):
        """Creates an online backup and verifies all tables and records match."""
        # 1. Trigger live online backup
        backup_path_str = backup_database(db_path=self.test_db, backup_dir=self.backup_dir)
        backup_path = Path(backup_path_str)

        self.assertTrue(backup_path.exists(), "Backup file was not created")
        self.assertGreater(backup_path.stat().st_size, 0, "Backup file is empty")

        # 2. Verify backup listing
        backups = list_backups(self.backup_dir)
        self.assertGreaterEqual(len(backups), 1)
        self.assertEqual(backups[0]["filename"], backup_path.name)

        # 3. Verify backup database integrity
        orig_conn = get_connection(self.test_db)
        bak_conn = get_connection(backup_path)
        try:
            # Compare files table count
            orig_files_count = orig_conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            bak_files_count = bak_conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            self.assertEqual(orig_files_count, bak_files_count)
            self.assertGreater(bak_files_count, 0)

            # Compare document_pages table count
            orig_pages_count = orig_conn.execute("SELECT COUNT(*) FROM document_pages").fetchone()[0]
            bak_pages_count = bak_conn.execute("SELECT COUNT(*) FROM document_pages").fetchone()[0]
            self.assertEqual(orig_pages_count, bak_pages_count)
            self.assertGreater(bak_pages_count, 0)

            # Test FTS5 query directly on backup database
            cursor = bak_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM pages_fts WHERE pages_fts MATCH '\"ความปลอดภัย\"'")
            fts_count = cursor.fetchone()[0]
            self.assertGreaterEqual(fts_count, 1, "Backup FTS5 table is intact and queryable")
        finally:
            orig_conn.close()
            bak_conn.close()


if __name__ == "__main__":
    unittest.main()
