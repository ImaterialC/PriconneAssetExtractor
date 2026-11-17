#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_asset_registry.py - Unit & Integration Tests for P1 Asset Registry & Duplicate Detection
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asset_registry import (
    BepInExWorkspace,
    AssetIdentity,
    RedirectIndex,
    NamingManager,
    NamingStrategy,
    PreConversionScanner,
    AssetStatus,
    MatchLevel
)


class TestAssetRegistry(unittest.TestCase):

    def test_01_workspace_resolution(self):
        real_bep = Path(r"C:\[Gacha]\PriconneRe-TL\src\BepInEx")
        ws1 = BepInExWorkspace.resolve(real_bep)
        self.assertEqual(ws1.bepinex_root, real_bep)
        self.assertEqual(ws1.xuat_text_dir, real_bep / "Translation" / "en" / "Text")
        self.assertEqual(ws1.redirected_resources_dir, real_bep / "Translation" / "en" / "RedirectedResources")
        self.assertTrue(ws1.redirected_exists())
        self.assertTrue(ws1.text_exists())

        # Resolving from Text subfolder
        text_sub = real_bep / "Translation" / "en" / "Text"
        ws2 = BepInExWorkspace.resolve(text_sub)
        self.assertEqual(ws2.bepinex_root, real_bep)
        self.assertEqual(ws2.xuat_text_dir, text_sub)

        # Resolving from RedirectedResources subfolder
        redir_sub = real_bep / "Translation" / "en" / "RedirectedResources"
        ws3 = BepInExWorkspace.resolve(redir_sub)
        self.assertEqual(ws3.bepinex_root, real_bep)
        self.assertEqual(ws3.redirected_resources_dir, redir_sub)

    def test_02_asset_identity(self):
        # Case A: folder + basename
        id1 = AssetIdentity.create(Path("storydata/0000011.unity3d"))
        self.assertEqual(id1.folder, "storydata")
        self.assertEqual(id1.basename, "0000011.unity3d")
        self.assertEqual(id1.category, "storydata")
        self.assertEqual(id1.asset_id, "0000011")
        self.assertEqual(id1.flattened_name, "storydata_0000011.unity3d")

        # Case B: already flattened name
        id2 = AssetIdentity.create(Path("storydata_0000011.unity3d"))
        self.assertEqual(id2.category, "storydata")
        self.assertEqual(id2.asset_id, "0000011")
        self.assertEqual(id2.flattened_name, "storydata_0000011.unity3d")

        # Case C: bare story ID
        id3 = AssetIdentity.create(Path("9080155.unity3d"))
        self.assertEqual(id3.category, "storydata")
        self.assertEqual(id3.asset_id, "9080155")
        self.assertEqual(id3.flattened_name, "storydata_9080155.unity3d")

    def test_03_real_redirected_index(self):
        real_redir = Path(r"C:\[Gacha]\PriconneRe-TL\src\BepInEx\Translation\en\RedirectedResources")
        idx = RedirectIndex(real_redir)
        self.assertGreater(idx.total_count, 2000, f"Expected >2000 bundles, got {idx.total_count}")

        # 0000011 should match storydata_0000011.unity3d
        id_known = AssetIdentity.create(Path("0000011.unity3d"))
        lvl, match, _ = idx.find_match(id_known)
        self.assertIsNotNone(match)
        self.assertEqual(match.name.lower(), "storydata_0000011.unity3d")
        self.assertIn(lvl, (MatchLevel.EXACT_FLATTENED, MatchLevel.NORMALIZED_ID, MatchLevel.BASENAME_UNIQUE))

        # 9080155 is NOT in RedirectedResources
        id_new = AssetIdentity.create(Path("9080155.unity3d"))
        lvl_new, match_new, _ = idx.find_match(id_new)
        self.assertIsNone(match_new)
        self.assertEqual(lvl_new, MatchLevel.NONE)

    def test_04_scanner_and_collision_prevention(self):
        real_bep = Path(r"C:\[Gacha]\PriconneRe-TL\src\BepInEx")
        ws = BepInExWorkspace.resolve(real_bep)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            (tmp_root / "storydata").mkdir()
            (tmp_root / "event").mkdir()

            f_existing = tmp_root / "0000011.unity3d"
            f_existing.write_bytes(b"dummy1")

            f_new = tmp_root / "9080155.unity3d"
            f_new.write_bytes(b"dummy2")

            f_clash1 = tmp_root / "storydata" / "conflict_test.unity3d"
            f_clash2 = tmp_root / "event" / "conflict_test.unity3d"
            f_clash1.write_bytes(b"clash1")
            f_clash2.write_bytes(b"clash2")

            scanner = PreConversionScanner(
                workspace=ws,
                strategy=NamingStrategy.AUTO_REDIRECT
            )

            input_files = [f_existing, f_new, f_clash1, f_clash2]
            candidates = scanner.scan_candidates(input_files, input_root=tmp_root)

            status_map = {c.identity.relative_path.as_posix(): c for c in candidates}

            # 1. Check existing bundle is flagged as ALREADY_IMPLEMENTED
            c_exist = status_map.get("0000011.unity3d")
            self.assertIsNotNone(c_exist)
            self.assertEqual(c_exist.status, AssetStatus.ALREADY_IMPLEMENTED)
            self.assertEqual(c_exist.action, "SKIP")

            # 2. Check new bundle is flagged as NEW
            c_new = status_map.get("9080155.unity3d")
            self.assertIsNotNone(c_new)
            self.assertEqual(c_new.status, AssetStatus.NEW)
            self.assertEqual(c_new.action, "CONVERT")


if __name__ == "__main__":
    unittest.main()
