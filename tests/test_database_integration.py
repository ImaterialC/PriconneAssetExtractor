#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_database_integration.py - Comprehensive Unit & Integration Tests for Phase 3
(GameDatabase, ResourceCrossReferencer, and Targeted Discovery)
"""
import sys
import unittest
from pathlib import Path

# Ensure NewDataMiner can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent))

from NewDataMiner.database import GameDatabase
from NewDataMiner.manifest_manager import ManifestManager
from NewDataMiner.resource_cross_ref import (
    DiscoveredResource,
    DiscoveryStatus,
    ResourceCrossReferencer,
)


class TestDatabaseIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parent.parent
        cls.db_path = cls.project_root / "master.db"
        if not cls.db_path.is_file():
            raise unittest.SkipTest(f"master.db not found at {cls.db_path}; skipping DB tests.")

        cls.db = GameDatabase(cls.db_path)
        cls.mm = ManifestManager()
        cls.mm.load_manifests()
        cls.cross_ref = ResourceCrossReferencer(cls.db, cls.mm)

    def test_01_database_availability_and_tables(self):
        self.assertTrue(self.db.is_available(), "Database should be recognized as valid SQLite file.")
        tables = self.db.list_tables()
        self.assertGreater(len(tables), 500, f"Expected > 500 tables in master.db, found {len(tables)}")
        
        # Check core game tables exist
        table_names = {t["name"] for t in tables}
        for expected in ("unit_data", "unit_profile", "story_detail", "skill_data", "unit_comments", "room_unit_comments"):
            self.assertIn(expected, table_names, f"Expected core table '{expected}' in master.db")

    def test_02_table_schema_inspection(self):
        schema = self.db.get_table_schema("unit_data")
        col_names = {c.name for c in schema}
        self.assertIn("unit_id", col_names)
        self.assertIn("unit_name", col_names)

        # Check primary key detection
        pk_cols = [c.name for c in schema if c.pk]
        self.assertIn("unit_id", pk_cols)

    def test_03_search_units_multilingual(self):
        # Search by English Name
        res_en = self.db.search_units("Pecorine")
        self.assertGreater(len(res_en), 0, "Should find Pecorine by English name.")
        self.assertEqual(res_en[0]["unit_id"], 105801)

        # Search by Japanese Name
        res_jp = self.db.search_units("ペコリーヌ")
        self.assertGreater(len(res_jp), 0, "Should find Pecorine by Japanese name.")
        self.assertEqual(res_jp[0]["unit_id"], 105801)

        # Search by Unit ID
        res_id = self.db.search_units("105801")
        self.assertGreater(len(res_id), 0)
        self.assertEqual(res_id[0]["unit_name"], "Pecorine")

    def test_04_search_stories(self):
        # Search for Pecorine story episodes
        stories = self.db.search_stories("ペコリーヌ")
        self.assertGreater(len(stories), 0, "Should find story episodes for Pecorine.")
        story_ids = [s["story_id"] for s in stories]
        self.assertIn(1058001, story_ids, "Story episode 1058001 should be present.")

    def test_05_search_skills(self):
        skills = self.db.search_skills("Princess")
        self.assertGreater(len(skills), 0, "Should find skills matching 'Princess'.")

    def test_06_search_dialogues(self):
        dialogues = self.db.search_dialogues("ペコリーヌ")
        homescreen = dialogues.get("homescreen", [])
        self.assertGreater(len(homescreen), 0, "Should find homescreen dialogue lines referencing Pecorine.")
        self.assertEqual(homescreen[0]["unit_id"], 105801)

    def test_07_export_table_sql(self):
        out_sql = Path(__file__).resolve().parent / "test_exports" / "unit_data_sample.sql"
        try:
            rows = self.db.export_table_sql("unit_data", out_sql, max_rows=10)
            self.assertEqual(rows, 10)
            self.assertTrue(out_sql.is_file())
            content = out_sql.read_text(encoding="utf-8")
            self.assertIn("CREATE TABLE", content)
            self.assertIn("INSERT INTO \"unit_data\"", content)
        finally:
            if out_sql.is_file():
                out_sql.unlink()
            if out_sql.parent.is_dir():
                try:
                    out_sql.parent.rmdir()
                except Exception:
                    pass

    def test_08_story_cross_referencing(self):
        # Cross reference story 1058001 -> should find storydata_1058001.unity3d and vo_adv audio
        discovered = self.cross_ref.discover_story("1058001")
        self.assertGreater(len(discovered), 0)
        disc = discovered[0]
        self.assertEqual(disc.entity_id, "1058001")
        self.assertEqual(disc.status, DiscoveryStatus.CONFIRMED_MAPPING)

        # Check matched entries contain the story script bundle
        matched_names = {e.name for e in disc.matched_entries}
        self.assertIn("storydata_1058001.unity3d", matched_names)
        self.assertIn("vo_adv_1058001.acb", matched_names)
        self.assertIn("vo_adv_1058001.awb", matched_names)

    def test_09_unit_cross_referencing(self):
        # Cross reference Pecorine (105801)
        discovered = self.cross_ref.discover_unit("105801")
        self.assertGreater(len(discovered), 0)
        disc = discovered[0]
        self.assertEqual(disc.entity_id, "105801")
        self.assertEqual(disc.status, DiscoveryStatus.CONFIRMED_MAPPING)
        self.assertGreater(len(disc.matched_entries), 20, "Should match voices, battle, spine and icon bundles.")

    def test_10_unresolved_and_status_tags(self):
        # Test fictitious unit ID that exists neither in DB nor manifests
        discovered = self.cross_ref.discover_unit("999999999")
        self.assertEqual(len(discovered), 0)


if __name__ == "__main__":
    unittest.main()
