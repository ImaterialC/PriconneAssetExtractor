#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_integrated_workflow.py - End-to-end integration tests for Phase 5
(Database Discovery -> Targeted Mining -> XUAT Repack -> Redirection Validation)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import asset_registry
from NewDataMiner.dataminer import DataMiner
from NewDataMiner.resource_cross_ref import DiscoveryStatus


class TestIntegratedWorkflow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent.parent
        cls.dm = DataMiner(db_path=cls.root / "master.db")
        cls.dm.manifest_manager.load_manifests()
        
        # Test real BepInEx workspace
        bepinex_root = Path(r"C:\[Gacha]\PriconneRe-TL\src\BepInEx")
        cls.ws = asset_registry.BepInExWorkspace.resolve(bepinex_root)
        cls.redir_index = asset_registry.RedirectIndex(cls.ws.redirected_resources_dir)

    def test_01_database_to_manifest_resolution(self):
        # Query story episode 1058001 (Pecorine Ep 1)
        res = self.dm.discover_stories("1058001")
        self.assertGreater(len(res), 0)
        story = res[0]
        self.assertEqual(story.entity_id, "1058001")
        self.assertEqual(story.status, DiscoveryStatus.CONFIRMED_MAPPING)

        # Confirm target story script bundle
        bundle_names = [e.name for e in story.matched_entries]
        self.assertIn("storydata_1058001.unity3d", bundle_names)

    def test_02_redirection_pre_check(self):
        # 0000011 is already in RedirectedResources (2,492 live files)
        ident_existing = asset_registry.AssetIdentity.from_path("storydata_0000011.unity3d")
        self.assertTrue(self.redir_index.contains(ident_existing), "storydata_0000011 should be detected as already implemented.")

        # Check a new non-existing story (e.g. fictitious or un-redirected)
        ident_new = asset_registry.AssetIdentity.from_path("storydata_9999999.unity3d")
        self.assertFalse(self.redir_index.contains(ident_new), "Non-existent bundle should be recognized as new.")

    def test_03_integrated_scope_calculation(self):
        # Search for unit Pecorine
        units = self.dm.discover_units("105801")
        self.assertGreater(len(units), 0)
        pecorine = units[0]
        
        scope = pecorine.download_scope
        self.assertGreater(scope.total_count, 10)
        self.assertGreater(scope.total_bytes, 0)
        self.assertIn("MB", scope.human_size)

    def test_04_story_targeted_pipeline_readiness(self):
        # Verify 9080155.unity3d local asset exists and can be inspected
        local_sample = self.root / "input" / "9080155.unity3d"
        self.assertTrue(local_sample.is_file(), "Local test bundle 9080155.unity3d should exist in input/.")
        
        ident = asset_registry.AssetIdentity.from_path(local_sample.name)
        self.assertEqual(ident.stem, "9080155")
        self.assertEqual(ident.flattened_name, "storydata_9080155.unity3d")


if __name__ == "__main__":
    unittest.main()
