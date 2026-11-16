"""Master Test Suite Runner for AI Accident Intelligence (Phase 1).
Executes all 5 test modules and outputs a detailed summary report.
"""

import sys
import unittest
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_pdf_extraction import TestPDFExtraction
from tests.test_hash_and_dedup import TestHashAndDeduplication
from tests.test_sync_mechanism import TestSyncMechanism
from tests.test_thai_search import TestThaiSearch
from tests.test_backup_restore import TestBackupRestore
from tests.test_analyzer import TestAnalyzer


def run_all():
    print("=" * 70)
    print("AI ACCIDENT INTELLIGENCE — COMPREHENSIVE TEST SUITE")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        ("1. PDF Extraction & Read-Only Guarantee", TestPDFExtraction),
        ("2. SHA-256 Hashing & Deduplication", TestHashAndDeduplication),
        ("3. Sync & Change Detection", TestSyncMechanism),
        ("4. Thai & English FTS5 Search Engine", TestThaiSearch),
        ("5. SQLite Live Online Backup", TestBackupRestore),
        ("6. Similar Incidents & WI Clause Matcher", TestAnalyzer),
    ]

    for name, test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    print("TEST SUMMARY REPORT")
    print("=" * 70)
    print(f"Total Tests Run: {result.testsRun}")
    print(f"Successful:     {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures:       {len(result.failures)}")
    print(f"Errors:         {len(result.errors)}")
    print("=" * 70)

    if result.wasSuccessful():
        print(">>> ALL TESTS PASSED SUCCESSFULLY! (100% PASS RATE) <<<")
        return 0
    else:
        print(">>> SOME TESTS FAILED. PLEASE REVIEW LOGS ABOVE. <<<")
        return 1


if __name__ == "__main__":
    sys.exit(run_all())
