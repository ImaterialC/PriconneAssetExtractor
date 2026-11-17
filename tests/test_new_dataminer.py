#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_new_dataminer.py - Unit & Integration Tests for P2 Universal Data Miner
"""
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from NewDataMiner.config import MinerConfig
from NewDataMiner.dataminer import DataMiner
from NewDataMiner.extractor import AssetExtractor
from NewDataMiner.manifest_manager import ManifestManager
from NewDataMiner.models import AssetCategory, DownloadScope, ManifestEntry


class TestNewDataMiner(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dm = DataMiner()
        cls.dm.manifest_manager.load_manifests()

    def test_01_manifest_indexing_and_fast_search(self):
        total = self.dm.manifest_manager.total_entries
        self.assertGreater(total, 10000, f"Expected > 10,000 assets across manifests, got {total}")

        # Search 1: Quest 80-9 story script (9080155)
        story_matches = self.dm.search("9080155", category=AssetCategory.STORY)
        self.assertGreaterEqual(len(story_matches), 1)
        found_story = story_matches[0]
        self.assertIn("9080155", found_story.name)
        self.assertEqual(found_story.category, AssetCategory.STORY)

        # Search 2: Unit 1001
        unit_matches = self.dm.search("1001", category=AssetCategory.UNIT)
        self.assertGreaterEqual(len(unit_matches), 1)

        # Search 3: Sound BGM (bgm_AM01)
        sound_matches = self.dm.search("bgm_AM01", category=AssetCategory.SOUND)
        self.assertGreaterEqual(len(sound_matches), 1)

        # Search 4: Movie arcade
        movie_matches = self.dm.search("arcade_1001", category=AssetCategory.MOVIE)
        self.assertGreaterEqual(len(movie_matches), 1)

    def test_02_download_scope_preview(self):
        story_matches = self.dm.search("9080155", category=AssetCategory.STORY)
        scope = self.dm.preview_scope(story_matches)
        self.assertEqual(scope.total_count, len(story_matches))
        self.assertGreater(scope.total_bytes, 0)
        self.assertIn("file(s)", scope.summary())

    def test_03_local_bundle_extraction(self):
        root = Path(__file__).resolve().parent.parent
        sample_bundle = root / "input" / "9080155.unity3d"
        self.assertTrue(sample_bundle.is_file(), f"Sample bundle {sample_bundle} must exist")

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_out = Path(tmp_dir)
            extractor = AssetExtractor()
            extracted = extractor.extract_unity_bundle(sample_bundle, dest_dir=tmp_out)
            self.assertGreater(len(extracted), 0, "Expected at least 1 extracted asset from 9080155.unity3d")
            text_file = extracted[0]
            self.assertTrue(text_file.exists())
            self.assertEqual(text_file.suffix.lower(), ".txt")
            content = text_file.read_bytes()
            self.assertGreater(len(content), 0)


if __name__ == "__main__":
    unittest.main()
