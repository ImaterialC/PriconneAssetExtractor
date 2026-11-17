#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora/tests/test_misora_core.py - Unit test suite for Misora's core engine.
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
MISORA_DIR = TESTS_DIR.parent
if str(MISORA_DIR) not in sys.path:
    sys.path.insert(0, str(MISORA_DIR))
if str(MISORA_DIR.parent) not in sys.path:
    sys.path.insert(0, str(MISORA_DIR.parent))

try:
    from misora.core import (
        StoryDocument, Box, Record,
        game_to_xuat, xuat_to_game, norm_search,
        load_bundle_story, save_bundle_story,
        ProjectSearchEngine, SearchOptions,
        XUnitySyncManager
    )
except ImportError:
    from core import (
        StoryDocument, Box, Record,
        game_to_xuat, xuat_to_game, norm_search,
        load_bundle_story, save_bundle_story,
        ProjectSearchEngine, SearchOptions,
        XUnitySyncManager
    )


class TestMisoraCore(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="misora_test_"))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_story_document_creation_and_boxes(self):
        recs = [
            Record(cmd_id=6, cmd_name="print", args=["Pecorine", "I'm hungry!\\nLet's eat!"]),
            Record(cmd_id=10, cmd_name="touch", args=["vo_adv_1058001"]),
            Record(cmd_id=6, cmd_name="print", args=["Kyaru", "Not again... {0}!"]),
        ]
        doc = StoryDocument(recs)
        self.assertEqual(len(doc.boxes), 2)
        self.assertEqual(doc.boxes[0].speaker, "Pecorine")
        self.assertEqual(doc.boxes[1].speaker, "Kyaru")
        # Check {0} -> {playername} in clean_text
        self.assertIn("{playername}", doc.boxes[1].clean_text)

    def test_02_inject_box_converts_playername_to_zero(self):
        recs = [
            Record(cmd_id=6, cmd_name="print", args=["Hiyori", "Original text"]),
        ]
        doc = StoryDocument(recs)
        doc.inject_box(0, new_speaker="Hiyori", new_text="Hello, {playername}!")
        # Internal record must have converted {playername} -> {0}
        self.assertEqual(doc.records[0].args[1], "Hello, {0}!")

    def test_03_binary_roundtrip(self):
        recs = [
            Record(cmd_id=0, cmd_name="fade", args=["0"]),
            Record(cmd_id=6, cmd_name="print", args=["Pecorine", "Yabai desu ne!☆"]),
        ]
        doc = StoryDocument(recs)
        binary_bytes = doc.to_binary()
        doc_restored = StoryDocument.from_binary(binary_bytes)
        self.assertEqual(len(doc_restored.records), len(doc.records))
        self.assertEqual(doc_restored.records[1].args[0], "Pecorine")
        self.assertEqual(doc_restored.records[1].args[1], "Yabai desu ne!☆")

    def test_04_search_engine_whitespace_and_regex(self):
        sample_txt = self.tmp_dir / "sample_tl.txt"
        sample_txt.write_text(
            "そ、それもそうね……\\nあけましておめでとう{playername}！\\nよろしく！=Happy New Year!\n",
            encoding="utf-8"
        )
        engine = ProjectSearchEngine()

        # Whitespace-insensitive search
        opts = SearchOptions(
            query="あけましておめでとう{0}！",
            ignore_whitespace=True,
            include_text=True,
            include_bundles=False
        )
        results = engine.search_file(sample_txt, opts)
        self.assertEqual(len(results), 1)

        # Regex search
        opts_rx = SearchOptions(
            query=r"Happy\s+New\s+Year",
            use_regex=True,
            include_text=True,
            include_bundles=False
        )
        results_rx = engine.search_file(sample_txt, opts_rx)
        self.assertEqual(len(results_rx), 1)

    def test_05_xunity_sync_update(self):
        dict_file = self.tmp_dir / "Events.txt"
        dict_file.write_text(
            "Key1=Old Translation\n"
            "キャルちゃん、{playername}くん！=Old Translation With Typo\n",
            encoding="utf-8"
        )
        mgr = XUnitySyncManager()
        matches = mgr.find_and_update(
            japanese_key="キャルちゃん、{0}くん！",
            new_english_text="Fixed Translation",
            search_roots=[self.tmp_dir],
            backup=False
        )
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].success)

        # Verify content on disk
        updated_content = dict_file.read_text(encoding="utf-8")
        self.assertIn("Fixed Translation", updated_content)
        self.assertNotIn("Old Translation With Typo", updated_content)


if __name__ == "__main__":
    unittest.main()
