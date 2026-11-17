#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_xuat_matching.py - Test XUnity Auto Translator whitespace-insensitivity
and player name placeholder ({playername} <-> {0}) matching & injection.
"""
import unittest
from pathlib import Path
import tempfile
import shutil

import advscript
import conflict_manager


class TestXUATMatchingAndPlaceholders(unittest.TestCase):
    """
    Verifies that dialogue matching properly implements:
    1. XUnity's 'IgnoreWhitespaceInDialogue' (ignoring spaces, tabs, \u3000, \n)
    2. Player name placeholder mapping ({playername} in XUAT <-> {0} in raw game data)
    3. Proper conversion back to {0} when repacking into game-ready format
    """

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="priconne_xuat_test_"))
        self.store = advscript.Store()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_placeholder_normalization_in_game_to_xuat(self):
        """Raw text with {0} must convert to {playername} via game_to_xuat."""
        raw_text = "キャルちゃん、コッコロちゃん、{0}くん！"
        converted = advscript.game_to_xuat(raw_text)
        self.assertEqual(converted, "キャルちゃん、コッコロちゃん、{playername}くん！")

    def test_02_placeholder_conversion_in_xuat_to_game(self):
        """English translation with {playername} must convert to {0} for game engine formatting."""
        en_xuat = "Kyaru-chan, Kokkoro-chan, {playername}-kun!"
        converted = advscript.xuat_to_game(en_xuat, "\n")
        self.assertEqual(converted, "Kyaru-chan, Kokkoro-chan, {0}-kun!")

        # Case-insensitive placeholder variants ({PlayerName}, {player_name})
        en_variants = "Hello {playerName}, welcome {player_name}!"
        converted_v = advscript.xuat_to_game(en_variants, "\n")
        self.assertEqual(converted_v, "Hello {0}, welcome {0}!")

    def test_03_exact_matching_across_placeholders(self):
        """Raw dialogue with {0} must match XUAT dictionary key with {playername}."""
        # Add dictionary entry written by community translator using {playername}
        self.store.add(
            "そ、それもそうね……\nあけましておめでとう{playername}！\nこのアタシがよろしくしてあげるわ！",
            "Y-You're right... Happy New Year, {playername}! I'll be taking good care of you!",
            "test_dict.txt",
            1
        )

        # Raw game text extracted from cutscene using {0}
        raw_game_text = "そ、それもそうね……\nあけましておめでとう{0}！\nこのアタシがよろしくしてあげるわ！"
        entry, level = self.store.lookup(raw_game_text)

        self.assertIsNotNone(entry, "Failed to match raw text containing {0} with dictionary key containing {playername}")
        self.assertEqual(level, "exact")
        self.assertIn("{playername}", entry.val)

    def test_04_ignore_whitespace_in_dialogue_newlines(self):
        """Raw text with newlines must match XUAT dictionary key without newlines (single line)."""
        # Dictionary entry without newlines (saved by XUAT when IgnoreWhitespaceInDialogue=True)
        self.store.add(
            "冒険の扉はもう目の前ですよ♪キャルちゃん、コッコロちゃん、{playername}くん！",
            "The door to adventure is right in front of us♪ Kyaru-chan, Kokkoro-chan, {playername}-kun!",
            "test_dict.txt",
            1
        )

        # Raw game script has formatting newlines between lines and uses {0}
        raw_game_text = "冒険の扉はもう目の前ですよ♪\nキャルちゃん、コッコロちゃん、{0}くん！"
        entry, level = self.store.lookup(raw_game_text)

        self.assertIsNotNone(entry, "Failed to match multi-line raw text with single-line XUAT entry")
        self.assertIn(level, ("norm", "exact"))

    def test_05_ignore_whitespace_fullwidth_and_halfwidth_spaces(self):
        """Raw text with full-width spaces (\\u3000) or half-width spaces must match regardless of spacing."""
        self.store.add(
            "願いを叶える…… そのためなら何度でも戦えるわ！ 何度でもね！",
            "To grant my wish... I will fight as many times as it takes! As many times as needed!",
            "test_dict.txt",
            1
        )

        # Raw game text uses Japanese ideographic space (\u3000) and newlines
        raw_game_text = "願いを叶える……\nそのためなら何度でも戦えるわ！\u3000何度でもね！"
        entry, level = self.store.lookup(raw_game_text)

        self.assertIsNotNone(entry, "Failed to match text with full-width space (\\u3000) against spaced dictionary")
        self.assertIn(level, ("norm", "exact"))

    def test_06_conflict_manager_placeholder_and_whitespace_normalization(self):
        """Conflict manager norm_key must normalize both whitespace and placeholders."""
        key_raw = "あけましておめでとう{0}！\nよろしくね！"
        key_xuat_clean = "あけましておめでとう{playername}！よろしくね！"
        key_xuat_spaced = "あけましておめでとう\u3000{playername}！\nよろしくね！"

        norm_raw = conflict_manager.norm_key(key_raw)
        norm_clean = conflict_manager.norm_key(key_xuat_clean)
        norm_spaced = conflict_manager.norm_key(key_xuat_spaced)

        self.assertEqual(norm_raw, norm_clean)
        self.assertEqual(norm_raw, norm_spaced)

    def test_07_box_key_uses_playername_for_translation_sheets(self):
        """box_key() must output {playername} so generated translation sheets follow community standards."""
        class DummyBox:
            text = "お帰りなさい、{0}さま！"

        key = advscript.box_key(DummyBox(), policy="never")
        self.assertEqual(key, "お帰りなさい、{playername}さま！")


if __name__ == "__main__":
    unittest.main()
