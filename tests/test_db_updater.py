#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_db_updater.py - Unit & Integration tests for Phase 4 (Database Update Checking & Validation)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from NewDataMiner.db_updater import DatabaseUpdater, LocalDatabaseInfo, RemoteDatabaseInfo


class TestDatabaseUpdater(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parent.parent
        cls.db_path = cls.project_root / "master.db"
        cls.updater = DatabaseUpdater(cls.db_path)

    def test_01_local_info_inspection(self):
        info = self.updater.get_local_info()
        self.assertTrue(info.exists)
        self.assertGreater(info.size_bytes, 10 * 1024 * 1024, "master.db should be > 10MB")
        self.assertIn("MB", info.human_size)

    def test_02_remote_lightweight_update_check(self):
        # Perform remote HEAD check without full download
        res = self.updater.check_for_updates(timeout_sec=15)
        self.assertIsInstance(res.local_info, LocalDatabaseInfo)
        self.assertIsInstance(res.remote_info, RemoteDatabaseInfo)
        
        # Verify remote metadata was gathered
        if res.remote_info.size_bytes:
            self.assertGreater(res.remote_info.size_bytes, 10 * 1024 * 1024)
        if res.remote_info.version:
            self.assertTrue(res.remote_info.version.isdigit(), f"Version should be digits, got {res.remote_info.version}")
            self.assertEqual(len(res.remote_info.version), 8, f"Expected 8-digit version e.g. 10071600, got {res.remote_info.version}")

    def test_03_validate_real_database_file(self):
        valid, msg = self.updater.validate_database_file(self.db_path)
        self.assertTrue(valid, f"Real master.db should pass validation: {msg}")
        self.assertIn("tables verified", msg)

    def test_04_reject_corrupt_database_file(self):
        # Create a temporary corrupt file
        corrupt_path = Path(__file__).resolve().parent / "corrupt_test.db"
        try:
            corrupt_path.write_bytes(b"CORRUPT_HEADER_NOT_A_SQLITE_DATABASE" * 50)
            valid, msg = self.updater.validate_database_file(corrupt_path)
            self.assertFalse(valid, "Corrupt file should be rejected by validator.")
        finally:
            if corrupt_path.is_file():
                corrupt_path.unlink()


if __name__ == "__main__":
    unittest.main()
