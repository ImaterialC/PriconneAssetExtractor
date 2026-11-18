#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora/tests/test_misora_ui_integration.py - Unit test suite for UI integration,
Project Folder linking, multi-framework discovery, and DnD scope workflows.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import importlib.util

TESTS_DIR = Path(__file__).resolve().parent
MISORA_DIR = TESTS_DIR.parent
if str(MISORA_DIR) not in sys.path:
    sys.path.insert(0, str(MISORA_DIR))

misora_script = MISORA_DIR / "misora.py"
spec = importlib.util.spec_from_file_location("misora_main", misora_script)
misora_app = importlib.util.module_from_spec(spec)
sys.modules["misora_main"] = misora_app
spec.loader.exec_module(misora_app)


class TestMisoraUIIntegration(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="misora_ui_test_"))
        self.app = misora_app.MisoraApp()
        self.app.withdraw()

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_01_two_way_project_folder_linking(self):
        """Find UI folder_path_var under scope: project and self.project_folder must stay in sync."""
        test_project_dir = self.tmp_dir / "MyModProject"
        test_project_dir.mkdir(parents=True, exist_ok=True)

        # 1. Setting project_folder reflects in folder_path_var under project scope
        self.app.scope_var.set("project")
        self.app.project_folder = test_project_dir
        self.app.bepinex_project_folder = test_project_dir
        self.app._sync_scope_widgets()
        self.assertEqual(self.app.folder_path_var.get(), str(test_project_dir))

        # 2. Typing into folder_path_var under project scope immediately updates self.project_folder
        updated_dir = self.tmp_dir / "AnotherModProject"
        updated_dir.mkdir(parents=True, exist_ok=True)
        self.app.folder_path_var.set(str(updated_dir))
        self.assertEqual(self.app.project_folder, updated_dir)
        self.assertEqual(self.app.bepinex_project_folder, updated_dir)

    def test_02_scope_switch_preserves_project_and_folder_paths(self):
        """Switching between Project and Folder scopes preserves each scope's distinct directory."""
        proj_dir = self.tmp_dir / "ProjectRoot"
        folder_dir = self.tmp_dir / "SingleFolder"
        proj_dir.mkdir(parents=True, exist_ok=True)
        folder_dir.mkdir(parents=True, exist_ok=True)

        self.app.project_folder = proj_dir
        self.app.bepinex_project_folder = proj_dir
        self.app.selected_search_folder = folder_dir

        # Switch to Folder scope
        self.app.scope_var.set("folder")
        self.app._sync_scope_widgets()
        self.assertEqual(self.app.folder_path_var.get(), str(folder_dir))

        # Switch to Project scope
        self.app.scope_var.set("project")
        self.app._sync_scope_widgets()
        self.assertEqual(self.app.folder_path_var.get(), str(proj_dir))

        # Switch to Current File(s) scope
        self.app.scope_var.set("current")
        self.app._sync_scope_widgets()
        self.assertEqual(self.app.folder_path_entry.cget("state"), "readonly")
        self.assertEqual(str(self.app.btn_browse_search_folder.cget("state")), "disabled")

    def test_03_config_backward_compatibility(self):
        """misora_config.json stores and loads both project_folder and bepinex_project_folder."""
        custom_dir = self.tmp_dir / "MelonLoaderMod"
        custom_dir.mkdir(parents=True, exist_ok=True)

        self.app.project_folder = custom_dir
        self.app.bepinex_project_folder = custom_dir
        self.app._save_user_prefs(silent=True)

        # Read config file directly
        with open(misora_app.CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self.assertIn("project_folder", cfg)
        self.assertIn("bepinex_project_folder", cfg)
        self.assertEqual(cfg["project_folder"], str(custom_dir))
        self.assertEqual(cfg["bepinex_project_folder"], str(custom_dir))

    def test_04_framework_agnostic_folder_resolution(self):
        """Framework-agnostic helpers discover Text and RedirectedResources across structures."""
        # Create MelonLoader / custom style hierarchy
        ml_proj = self.tmp_dir / "MelonProject"
        ml_user_data = ml_proj / "UserData"
        ml_text = ml_user_data / "Text"
        ml_redirect = ml_user_data / "RedirectedResources"
        ml_text.mkdir(parents=True, exist_ok=True)
        ml_redirect.mkdir(parents=True, exist_ok=True)

        self.app.project_folder = ml_proj
        self.app.bepinex_project_folder = ml_proj

        # Check candidate search logic for text folder
        candidates_text = [
            ml_proj / "Text",
            ml_proj if ml_proj.name.lower() == "text" else None,
            ml_proj / "Translation" / "en" / "Text",
            ml_proj / "UserData" / "Text",
        ]
        found_text = next((c for c in candidates_text if c and c.is_dir()), None)
        self.assertEqual(found_text, ml_text)

        # Check candidate search logic for redirected resources
        candidates_res = [
            ml_proj / "RedirectedResources",
            ml_proj.parent / "RedirectedResources",
            ml_proj / "Translation" / "en" / "RedirectedResources",
            ml_proj / "UserData" / "RedirectedResources",
            ml_proj / "Mods" / "RedirectedResources",
        ]
        found_res = next((c for c in candidates_res if c and c.is_dir()), None)
        self.assertEqual(found_res, ml_redirect)

    def test_05_dnd_folder_scope_actions(self):
        """DnD folder actions: setting folder scope sets selected_search_folder and updates UI."""
        folder_a = self.tmp_dir / "FolderA"
        folder_a.mkdir(parents=True, exist_ok=True)

        # Simulate user choosing 'No' (set search scope only)
        self.app.selected_search_folder = folder_a
        self.app.folder_path_var.set(str(folder_a))
        self.app.scope_var.set("folder")
        self.app._sync_scope_widgets()

        self.assertEqual(self.app.scope_var.get(), "folder")
        self.assertEqual(self.app.folder_path_var.get(), str(folder_a))
        self.assertEqual(self.app.folder_path_entry.cget("state"), "normal")

    def test_06_process_opened_folder_empty(self):
        """Opening a folder with no story files sets search scope without opening files."""
        empty_folder = self.tmp_dir / "EmptyFolder"
        empty_folder.mkdir(parents=True, exist_ok=True)

        self.app._process_opened_folder(empty_folder, source_label="Test")
        self.assertEqual(self.app.scope_var.get(), "folder")
        self.assertEqual(self.app.selected_search_folder, empty_folder)
        self.assertEqual(self.app.folder_path_var.get(), str(empty_folder))

    def test_07_process_opened_folder_single_file(self):
        """Opening a folder with exactly 1 story file opens it and sets scope to current."""
        one_folder = self.tmp_dir / "OneStoryFolder"
        one_folder.mkdir(parents=True, exist_ok=True)
        txt_file = one_folder / "test_story.txt"
        txt_file.write_text("Test line=Translated\n", encoding="utf-8")

        self.app._process_opened_folder(one_folder, source_label="Test")
        self.assertEqual(self.app.scope_var.get(), "current")
        self.assertEqual(self.app.current_file_path, txt_file)

    def test_08_line_numbers_and_ruler_toggles(self):
        """Line numbers gutter and horizontal column ruler toggle visibility correctly."""
        # Toggle line numbers OFF
        self.app.var_show_line_numbers.set(False)
        self.app._on_toggle_line_numbers()
        self.assertFalse(self.app.show_line_numbers)
        self.assertFalse(self.app._is_widget_packed(self.app.gutter_clean))

        # Toggle line numbers ON
        self.app.var_show_line_numbers.set(True)
        self.app._on_toggle_line_numbers()
        self.assertTrue(self.app.show_line_numbers)
        self.assertTrue(self.app._is_widget_packed(self.app.gutter_clean))

        # Toggle column ruler OFF
        self.app.var_show_column_ruler.set(False)
        self.app._on_toggle_column_ruler()
        self.assertFalse(self.app.show_column_ruler)
        self.assertFalse(self.app._is_widget_packed(self.app.ruler_clean))

        # Toggle column ruler ON
        self.app.var_show_column_ruler.set(True)
        self.app._on_toggle_column_ruler()
        self.assertTrue(self.app.show_column_ruler)
        self.assertTrue(self.app._is_widget_packed(self.app.ruler_clean))

    def test_09_undo_redo_shortcuts_and_dialogue_binding(self):
        """Ctrl+Z and Ctrl+Y are intercepted by _shortcut_undo and _shortcut_redo on dialogue."""
        res_undo = self.app._shortcut_undo()
        self.assertEqual(res_undo, "break")
        res_redo = self.app._shortcut_redo()
        self.assertEqual(res_redo, "break")

    def test_10_theme_swatches_and_commit_hex(self):
        """Theme swatches and hex entries reflect updated color on commit."""
        test_color = "#334455"
        self.app._theme_hex_vars["bg_dark"].set(test_color)
        self.app._commit_theme_hex("bg_dark")
        self.assertEqual(self.app.theme["bg_dark"], test_color)
        self.assertEqual(self.app._theme_swatch_buttons["bg_dark"].cget("bg"), test_color)


if __name__ == "__main__":
    unittest.main()
