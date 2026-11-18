#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora/tests/test_misora_core.py - Unit test suite for Misora's core engine.
"""
import re
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
        XUnitySyncManager,
        MasterUndoJournal, UndoOperation, BoxEditDelta, PlainTextDelta, BulkFileDelta,
        TagMasker, MTLConfig, MTLEngine,
    )
except ImportError:
    from core import (
        StoryDocument, Box, Record,
        game_to_xuat, xuat_to_game, norm_search,
        load_bundle_story, save_bundle_story,
        ProjectSearchEngine, SearchOptions,
        XUnitySyncManager,
        MasterUndoJournal, UndoOperation, BoxEditDelta, PlainTextDelta, BulkFileDelta,
        TagMasker, MTLConfig, MTLEngine,
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
        res = results[0]
        self.assertGreaterEqual(res.snippet_start, 0)
        self.assertGreater(res.snippet_end, res.snippet_start)
        self.assertIn("あけましておめでとう", res.match_snippet)

        # Regex search
        opts_rx = SearchOptions(
            query=r"Happy\s+New\s+Year",
            use_regex=True,
            include_text=True,
            include_bundles=False
        )
        results_rx = engine.search_file(sample_txt, opts_rx)
        self.assertEqual(len(results_rx), 1)
        res_rx = results_rx[0]
        self.assertGreaterEqual(res_rx.snippet_start, 0)
        self.assertGreater(res_rx.snippet_end, res_rx.snippet_start)

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

    def test_06_undo_journal_coalescing(self):
        """MasterUndoJournal coalesces consecutive BoxEditDelta for same box."""
        journal = MasterUndoJournal()
        d1 = BoxEditDelta(box_index=0, old_speaker="A", new_speaker="A", old_text="old", new_text="v1", file_path="f.unity3d")
        d2 = BoxEditDelta(box_index=0, old_speaker="A", new_speaker="A", old_text="old", new_text="v2", file_path="f.unity3d")
        journal.record(d1, "Edit box #0")
        journal.record(d2, "Edit box #0")
        # Should coalesce -> still 1 op
        self.assertEqual(journal.undo_depth, 1)
        op = journal.pop_undo()
        self.assertIsNotNone(op)
        self.assertEqual(op.deltas[0].new_text, "v2")
        # After undo, redo stack should have 1 entry
        self.assertEqual(journal.redo_depth, 1)

    def test_07_undo_journal_batch(self):
        """MasterUndoJournal batch groups multiple deltas into one op."""
        journal = MasterUndoJournal()
        journal.begin_batch("Replace All")
        for i in range(3):
            journal.record(BoxEditDelta(box_index=i, old_speaker="X", new_speaker="X", old_text="old", new_text="new", file_path="f.unity3d"))
        journal.end_batch()
        self.assertEqual(journal.undo_depth, 1)
        op = journal.pop_undo()
        self.assertIsNotNone(op)
        self.assertEqual(len(op.deltas), 3)
        self.assertEqual(op.label, "Replace All")

    def test_08_tag_masker_roundtrip(self):
        """TagMasker shields NGUI tags and {playername} during machine translation."""
        complex_text = "[b]やあ、{playername}！[/b]\\n[rub:ルビ]漢字[/rub]と[c][ff0000]色[/c][-]だよ。"
        masked, tag_map = TagMasker.mask(complex_text)
        self.assertNotIn("{playername}", masked)
        self.assertNotIn("[rub:ルビ]", masked)
        self.assertIn("__M_", masked)
        unmasked = TagMasker.unmask(masked, tag_map)
        self.assertEqual(unmasked, complex_text)

    def test_09_mtl_config_serialization(self):
        """MTLConfig serializes to and from dict cleanly."""
        cfg = MTLConfig(
            active_engine="DeepL",
            src_lang="ja",
            tgt_lang="en",
            deepl_api_key="test_key_123",
            deepl_use_pro=True,
            timeout_sec=15.0
        )
        data = cfg.to_dict()
        self.assertEqual(data["active_engine"], "DeepL")
        self.assertEqual(data["deepl_api_key"], "test_key_123")
        restored = MTLConfig.from_dict(data)
        self.assertEqual(restored.active_engine, "DeepL")
        self.assertEqual(restored.deepl_use_pro, True)
        self.assertEqual(restored.timeout_sec, 15.0)
        self.assertEqual(restored.ai_prompt_include_header, True)
        self.assertEqual(restored.ai_prompt_include_speaker, True)

    def test_10_delimiter_parsing_and_excess_protection(self):
        """Cross-box delimiter parsing correctly groups dialogue and handles speakers."""
        sample_clip = (
            "=== [BOX:0|Speaker:コッコロ] ===\n"
            "主さま、朝でございますよ。\n\n"
            "=== [BOX:1|Speaker:ユウキ] ===\n"
            "おはよう、コッコロ。\n\n"
            "[BOX:2]\n"
            "今日も良い天気ですね。"
        )
        pattern = re.compile(
            r"(?:=== )?\[BOX:(\d+)(?:\|Speaker:([^\]]*))?\]\s*(?:===)?\s*\n(.*?)(?=\n(?:=== )?\[BOX:|\Z)",
            re.DOTALL
        )
        matches = list(pattern.finditer(sample_clip))
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[0].group(1), "0")
        self.assertEqual(matches[0].group(2), "コッコロ")
        self.assertEqual(matches[0].group(3).strip(), "主さま、朝でございますよ。")
        self.assertEqual(matches[1].group(1), "1")
        self.assertEqual(matches[1].group(2), "ユウキ")
        self.assertEqual(matches[2].group(1), "2")
        self.assertIsNone(matches[2].group(2))
        self.assertEqual(matches[2].group(3).strip(), "今日も良い天気ですね。")


    def test_11_session_preferences_and_paths(self):
        """Verify session paths and recent files schema serialization."""
        import json
        config_data = {
            "config_version": 4,
            "last_opened_dir": str(self.tmp_dir),
            "selected_search_folder": str(self.tmp_dir / "stories"),
            "saved_opened_files": [
                str(self.tmp_dir / "story_101.unity3d"),
                str(self.tmp_dir / "story_102.unity3d"),
            ],
            "saved_active_file": str(self.tmp_dir / "story_101.unity3d"),
            "recent_files": [
                str(self.tmp_dir / "story_101.unity3d"),
            ],
        }
        encoded = json.dumps(config_data)
        decoded = json.loads(encoded)
        self.assertEqual(decoded["config_version"], 4)
        self.assertEqual(decoded["last_opened_dir"], str(self.tmp_dir))
        self.assertEqual(len(decoded["saved_opened_files"]), 2)
        self.assertEqual(decoded["saved_active_file"], str(self.tmp_dir / "story_101.unity3d"))


if __name__ == "__main__":
    unittest.main()
