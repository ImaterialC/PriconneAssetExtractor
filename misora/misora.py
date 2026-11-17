#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Misora: Unity3D Revision Tool & Story Editor
=============================================
A specialized GUI text editor for inspecting, searching, and in-place patching
of Princess Connect! Re:Dive Unity3D story bundles (.unity3d) and XUAT translation files.
"""
from __future__ import annotations

import colorsys
import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Set, Tuple, Union

if sys.platform == "win32":
    from ctypes import wintypes

# Ensure both Misora root and toolkit parent are in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

try:
    from misora.assets.icon import THEME, apply_window_icon
    from misora.core import (
        ALWAYS_ON_CATEGORY, LOG_CATEGORIES, LOG_LEVELS, Box, BundleIOError,
        BoxEditDelta, BulkFileDelta, LogEntry, MasterUndoJournal, MisoraLogger,
        PlainTextDelta, ProjectSearchEngine, Record, SearchOptions, SearchResult,
        StoryDocument, UndoOperation, XUnitySyncManager, load_bundle_story,
        save_bundle_story,
    )
except ImportError:
    from assets.icon import THEME, apply_window_icon
    from core import (
        ALWAYS_ON_CATEGORY, LOG_CATEGORIES, LOG_LEVELS, Box, BundleIOError,
        BoxEditDelta, BulkFileDelta, LogEntry, MasterUndoJournal, MisoraLogger,
        PlainTextDelta, ProjectSearchEngine, Record, SearchOptions, SearchResult,
        StoryDocument, UndoOperation, XUnitySyncManager, load_bundle_story,
        save_bundle_story,
    )

CONFIG_PATH = SCRIPT_DIR / "misora_config.json"
DEBUG_LOG_PATH = SCRIPT_DIR / "misora_debug.log"
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Matches Priconne/NGUI rich-text tags (including shorthand [/]) and placeholders
NGUI_TAG_RE = re.compile(
    r"(\[(?:/|/?(?:"
    r"rub(?::[^\]]*)?|"
    r"b|i|u|s|sub|sup|c|"
    r"url(?:=[^\]]*)?|"
    r"-|"
    r"[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?(?:[-,][0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?)?"
    r"))\]|\{playername\}|\{\d+\})"
)

# Tokenizer for compiled NGUI preview rendering
NGUI_TOKEN_RE = re.compile(
    r"(\[rub:([^\]]*)\](.*?)\[/rub\]|"
    r"\[/?(?:b|i|u|s|sub|sup|c)\]|"
    r"\[/\]|"
    r"\[url=[^\]]*\]|\[/url\]|"
    r"\[-\]|"
    r"\[([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?(?:[-,]([0-9a-fA-F]{6})(?:[0-9a-fA-F]{2})?)?\]|"
    r"\{playername\}|\{\d+\})",
    re.DOTALL,
)

THEME_PRESETS: Dict[str, Dict[str, str]] = {
    "Misora Purple & White": {
        "bg_dark": "#f3eefb",
        "bg_panel": "#ffffff",
        "bg_editor": "#faf8fe",
        "border": "#d4c4ec",
        "fg_text": "#221833",
        "fg_muted": "#6b5a88",
        "misora_pink": "#7b42bc",
        "misora_pink_hover": "#9056d2",
        "misora_pink_active": "#612ea0",
        "accent_blue": "#536dfe",
        "accent_green": "#2e7d32",
        "accent_yellow": "#8e24aa",
        "highlight_bg": "#e8dbfa",
    },
    "Misora Classic (Dark)": {
        "bg_dark": "#14141a",
        "bg_panel": "#1e1e26",
        "bg_editor": "#181820",
        "border": "#30303e",
        "fg_text": "#f0f0f5",
        "fg_muted": "#9898a8",
        "misora_pink": "#ff7da7",
        "misora_pink_hover": "#ff99ba",
        "misora_pink_active": "#e05a87",
        "accent_blue": "#68b5f3",
        "accent_green": "#6ad18a",
        "accent_yellow": "#f5c26b",
        "highlight_bg": "#382433",
    },
    "Midnight Violet": {
        "bg_dark": "#161224",
        "bg_panel": "#201a33",
        "bg_editor": "#130f20",
        "border": "#3a2f5c",
        "fg_text": "#f1ecfa",
        "fg_muted": "#9c8ec0",
        "misora_pink": "#a66cff",
        "misora_pink_hover": "#b98aff",
        "misora_pink_active": "#894be8",
        "accent_blue": "#79c0ff",
        "accent_green": "#7ee787",
        "accent_yellow": "#e3b341",
        "highlight_bg": "#362459",
    },
    "Clean Daylight": {
        "bg_dark": "#eceef2",
        "bg_panel": "#ffffff",
        "bg_editor": "#f8f9fb",
        "border": "#cfd5e0",
        "fg_text": "#1f2430",
        "fg_muted": "#606a7e",
        "misora_pink": "#6f42c1",
        "misora_pink_hover": "#8458d4",
        "misora_pink_active": "#5932a3",
        "accent_blue": "#0969da",
        "accent_green": "#1a7f37",
        "accent_yellow": "#9a6700",
        "highlight_bg": "#e6dcf8",
    },
}

DEFAULT_PREFS: Dict[str, Any] = {
    "dialogue_font_family": "Segoe UI",
    "dialogue_font_size": 11,
    "raw_font_size": 9,
    "ui_font_size": 9,
    "theme": dict(THEME_PRESETS["Misora Purple & White"]),
    "debug": {
        "console_visible": False,
        "log_to_file": False,
        "level": "Info",
        "categories": {cat: True for cat in LOG_CATEGORIES},
    },
}

PRICONNE_SWATCHES: List[Tuple[str, str]] = [
    ("Misora Purple", "#7b42bc"),
    ("Misora Pink", "#ff7da7"),
    ("Astrum Blue", "#4a90e2"),
    ("Pecorine Gold", "#e5a93b"),
    ("Kokkoro Mint", "#2e9e5b"),
    ("Kyaru Violet", "#8e44ad"),
    ("Crimson Alert", "#d94862"),
    ("Pure White", "#ffffff"),
    ("Deep Plum", "#221833"),
    ("Soft Silver", "#9aa3b2"),
]

NGUI_GLOSSARY_ITEMS: List[Dict[str, str]] = [
    {
        "tag": "[rub:ruby]base[/rub]",
        "title": "Ruby / Furigana Text (Priconne NGUI)",
        "syntax": "[rub:Command]Wish[/rub]",
        "insert_open": "[rub:]",
        "insert_close": "[/rub]",
        "action": "ruby",
        "desc": "Cygames' custom Priconne NGUI tag. Renders 'ruby' in small text centered directly above 'base' (e.g., [rub:めいれい]願い[/rub]). Double-click or press Ctrl+R to wrap selected text.",
    },
    {
        "tag": "[RRGGBB]",
        "title": "Hex RGB Text Color",
        "syntax": "[7B42BC]Colored text[-]",
        "insert_open": "[7B42BC]",
        "insert_close": "[-]",
        "desc": "Changes text color starting at the tag using a 6-digit hexadecimal RGB code. Always close with [-] to restore default label color.",
    },
    {
        "tag": "[RRGGBBAA]",
        "title": "Hex RGBA Color + Alpha",
        "syntax": "[FFFFFF80]Semi-transparent[-]",
        "insert_open": "[FFFFFF80]",
        "insert_close": "[-]",
        "desc": "Sets both RGB color and alpha opacity (00 = invisible, FF = opaque) in NGUI UILabel.",
    },
    {
        "tag": "[RRGGBB-RRGGBB]",
        "title": "Vertical Gradient Color (Top-Bottom)",
        "syntax": "[7B42BC-FF7DA7]Gradient text[-]",
        "insert_open": "[7B42BC-FF7DA7]",
        "insert_close": "[-]",
        "desc": "Applies a top-to-bottom vertical gradient using a hyphen (-) between top and bottom hex colors. Note: NGUI requires '-' (comma syntax displays as literal text). Close with [-].",
    },
    {
        "tag": "[RRGGBBAA-RRGGBBAA]",
        "title": "Vertical Gradient Color + Alpha",
        "syntax": "[FF7DA7FF-68B5F380]Alpha gradient[-]",
        "insert_open": "[FF7DA7FF-68B5F380]",
        "insert_close": "[-]",
        "desc": "Applies a top-to-bottom vertical gradient with per-stop alpha opacity (00 = invisible, FF = opaque). Close with [-].",
    },
    {
        "tag": "[-]",
        "title": "Reset / Close Color Tag",
        "syntax": "[68B5F3]Blue[-] Normal",
        "insert_open": "[-]",
        "insert_close": "",
        "desc": "Pops the active [RRGGBB] or gradient color override and returns to the default dialogue text color.",
    },
    {
        "tag": "[/]",
        "title": "Reset / Close Style Tag (Shorthand)",
        "syntax": "[b][i]Bold italic[/] Normal",
        "insert_open": "[/]",
        "insert_close": "",
        "desc": "NGUI shorthand tag that closes active text formatting styles ([b], [i], [u], [s], [sub], [sup]).",
    },
    {
        "tag": "[b]...[/b]",
        "title": "Bold Style",
        "syntax": "[b]Emphasized text[/b]",
        "insert_open": "[b]",
        "insert_close": "[/b]",
        "desc": "Renders enclosed text in bold weight inside NGUI rich-text labels.",
    },
    {
        "tag": "[i]...[/i]",
        "title": "Italic Style",
        "syntax": "[i]Whispered thought[/i]",
        "insert_open": "[i]",
        "insert_close": "[/i]",
        "desc": "Slants enclosed text in italics for inner monologues, emphasis, or foreign terms.",
    },
    {
        "tag": "[u]...[/u]",
        "title": "Underline Style",
        "syntax": "[u]Underlined phrase[/u]",
        "insert_open": "[u]",
        "insert_close": "[/u]",
        "desc": "Draws an underline beneath the enclosed characters.",
    },
    {
        "tag": "[s]...[/s]",
        "title": "Strikethrough Style",
        "syntax": "[s]Crossed-out text[/s]",
        "insert_open": "[s]",
        "insert_close": "[/s]",
        "desc": "Draws a horizontal strikethrough line across the enclosed text.",
    },
    {
        "tag": "[sub]...[/sub]",
        "title": "Subscript Text",
        "syntax": "H[sub]2[/sub]O",
        "insert_open": "[sub]",
        "insert_close": "[/sub]",
        "desc": "Shrinks and lowers enclosed characters below the text baseline.",
    },
    {
        "tag": "[sup]...[/sup]",
        "title": "Superscript Text",
        "syntax": "10[sup]th[/sup] Anniversary",
        "insert_open": "[sup]",
        "insert_close": "[/sup]",
        "desc": "Shrinks and raises enclosed characters above the text baseline.",
    },
    {
        "tag": "[url=...]...[/url]",
        "title": "Clickable URL / Link Tag",
        "syntax": "[url=https://example.com]Link[/url]",
        "insert_open": "[url=]",
        "insert_close": "[/url]",
        "desc": "Marks a clickable text span retrievable via NGUI UILabel.GetUrlAtPosition().",
    },
    {
        "tag": "[c]...[/c]",
        "title": "Ignore Label Tint",
        "syntax": "[c]Untinted text[/c]",
        "insert_open": "[c]",
        "insert_close": "[/c]",
        "desc": "Prevents NGUI's widget color multiplier from tinting the enclosed characters.",
    },
    {
        "tag": "{playername}",
        "title": "Player Name Placeholder",
        "syntax": "Good morning, {playername}!",
        "insert_open": "{playername}",
        "insert_close": "",
        "desc": "Represents the protagonist's name in Misora & XUAT .txt dictionaries. Automatically compiled to {0} when saving .unity3d bundles.",
    },
    {
        "tag": "\\n",
        "title": "Explicit Line Break",
        "syntax": "First line\\nSecond line",
        "insert_open": "\\n",
        "insert_close": "",
        "desc": "Forces a line break inside the ADV dialogue box. Pressing Enter in the editor automatically serializes the bundle's line break format.",
    },
    {
        "tag": "──",
        "title": "ADV Dialogue Pause / Dash",
        "syntax": "──Wait right there!",
        "insert_open": "──",
        "insert_close": "",
        "desc": "Standard double box-drawing horizontal dash used at the start of Priconne dialogue interruptions.",
    },
]


# -----------------------------------------------------------------------------
# WCAG 2.1 Contrast-Safe Color Utilities (#13)
# -----------------------------------------------------------------------------
def wcag_relative_luminance(hex_color: str) -> float:
    """Compute WCAG 2.1 relative luminance in [0.0, 1.0] for a #RRGGBB hex string."""
    if not HEX_COLOR_RE.match(hex_color):
        return 0.0

    def _lin(c8: int) -> float:
        s = c8 / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r = _lin(int(hex_color[1:3], 16))
    g = _lin(int(hex_color[3:5], 16))
    b = _lin(int(hex_color[5:7], 16))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag_contrast_ratio(hex_a: str, hex_b: str) -> float:
    """Compute WCAG 2.1 contrast ratio in [1.0, 21.0] between two #RRGGBB colors."""
    la = wcag_relative_luminance(hex_a)
    lb = wcag_relative_luminance(hex_b)
    hi, lo = (la, lb) if la >= lb else (lb, la)
    return (hi + 0.05) / (lo + 0.05)


def best_contrast_fg(
    bg_hex: str,
    dark_fg: str = "#14141a",
    light_fg: str = "#ffffff",
) -> str:
    """Pick whichever of `dark_fg` or `light_fg` maximizes WCAG contrast on `bg_hex`."""
    if not HEX_COLOR_RE.match(bg_hex):
        return light_fg
    c_dark = wcag_contrast_ratio(bg_hex, dark_fg)
    c_light = wcag_contrast_ratio(bg_hex, light_fg)
    return light_fg if c_light >= c_dark else dark_fg


class NguiColorPickerPopup(tk.Toplevel):
    """Mini texture-editor style Color Picker & Gradient Builder with Screen Eyedropper."""

    SV_W = 180
    SV_H = 140
    HUE_W = 20
    HUE_H = 140

    def __init__(
        self,
        parent: "MisoraApp",
        primary_hex: str = "#7b42bc",
        secondary_hex: str = "#ff7da7",
    ):
        super().__init__(parent)
        self.app = parent
        self.theme = parent.theme
        self.title("NGUI Color & Gradient Picker")
        self.configure(bg=self.theme["bg_panel"])
        self.resizable(False, False)
        self.transient(parent)

        self.stop_colors: List[str] = [
            primary_hex.lower() if HEX_COLOR_RE.match(primary_hex) else "#7b42bc",
            secondary_hex.lower() if HEX_COLOR_RE.match(secondary_hex) else "#ff7da7",
        ]
        self.active_stop: int = 0
        self._eyedropper_active: bool = False
        self._eyedropper_after_id: Optional[str] = None
        self._mouse_was_down: bool = False

        r = int(self.stop_colors[0][1:3], 16) / 255.0
        g = int(self.stop_colors[0][3:5], 16) / 255.0
        b = int(self.stop_colors[0][5:7], 16) / 255.0
        self._h, self._s, self._v = colorsys.rgb_to_hsv(r, g, b)

        self._sv_photo: Optional[tk.PhotoImage] = None
        self._hue_photo: Optional[tk.PhotoImage] = None
        self._grad_photo: Optional[tk.PhotoImage] = None

        self._build_ui()
        self._render_hue_bar()
        self._render_sv_map()
        self._sync_ui_from_hsv()

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_reqwidth() // 2)
        py = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_reqheight() // 2)
        self.geometry(f"+{max(20, px)}+{max(20, py)}")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", self._on_escape)

    def _build_ui(self) -> None:
        t = self.theme
        accent_fg = best_contrast_fg(t["misora_pink"])
        accent_hover_fg = best_contrast_fg(t["misora_pink_hover"])
        editor_fg = best_contrast_fg(t["bg_editor"], t["fg_text"], "#ffffff")

        stop_bar = tk.Frame(self, bg=t["bg_panel"])
        stop_bar.pack(fill="x", padx=12, pady=(10, 6))

        tk.Label(
            stop_bar,
            text="Target Stop:",
            font=("Segoe UI", 9, "bold"),
            bg=t["bg_panel"],
            fg=best_contrast_fg(t["bg_panel"], t["fg_text"], "#ffffff"),
        ).pack(side="left", padx=(0, 6))

        self.btn_stop0 = tk.Button(
            stop_bar,
            text="1: Primary / Top",
            font=("Segoe UI", 8, "bold"),
            relief="solid",
            bd=1,
            cursor="hand2",
            command=lambda: self._select_stop(0),
        )
        self.btn_stop0.pack(side="left", padx=(0, 4))

        self.btn_stop1 = tk.Button(
            stop_bar,
            text="2: Gradient Bottom",
            font=("Segoe UI", 8, "bold"),
            relief="solid",
            bd=1,
            cursor="hand2",
            command=lambda: self._select_stop(1),
        )
        self.btn_stop1.pack(side="left")

        map_row = tk.Frame(self, bg=t["bg_panel"])
        map_row.pack(fill="x", padx=12, pady=4)

        self.canvas_sv = tk.Canvas(
            map_row,
            width=self.SV_W,
            height=self.SV_H,
            bd=1,
            relief="solid",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas_sv.pack(side="left")
        self.canvas_sv.bind("<Button-1>", self._on_sv_drag)
        self.canvas_sv.bind("<B1-Motion>", self._on_sv_drag)

        self.canvas_hue = tk.Canvas(
            map_row,
            width=self.HUE_W,
            height=self.HUE_H,
            bd=1,
            relief="solid",
            highlightthickness=0,
            cursor="sb_v_double_arrow",
        )
        self.canvas_hue.pack(side="left", padx=(8, 10))
        self.canvas_hue.bind("<Button-1>", self._on_hue_drag)
        self.canvas_hue.bind("<B1-Motion>", self._on_hue_drag)

        side_col = tk.Frame(map_row, bg=t["bg_panel"])
        side_col.pack(side="left", fill="y")

        swatch_pair = tk.Frame(side_col, bg=t["bg_panel"])
        swatch_pair.pack(fill="x", pady=(0, 6))

        self.lbl_swatch_active = tk.Label(
            swatch_pair,
            width=7,
            height=2,
            bg=self.stop_colors[0],
            relief="solid",
            bd=1,
        )
        self.lbl_swatch_active.pack(side="left")

        self.canvas_grad_preview = tk.Canvas(
            swatch_pair,
            width=46,
            height=34,
            bd=1,
            relief="solid",
            highlightthickness=0,
        )
        self.canvas_grad_preview.pack(side="left", padx=(6, 0))

        hex_row = tk.Frame(side_col, bg=t["bg_panel"])
        hex_row.pack(fill="x", pady=2)
        tk.Label(hex_row, text="Hex:", font=("Segoe UI", 8, "bold"), bg=t["bg_panel"], fg=t["fg_muted"]).pack(side="left")
        self.var_hex = tk.StringVar(value=self.stop_colors[0].upper())
        ent_hex = tk.Entry(
            hex_row,
            textvariable=self.var_hex,
            width=9,
            font=("Consolas", 9, "bold"),
            bg=t["bg_editor"],
            fg=editor_fg,
            insertbackground=t["misora_pink"],
            bd=1,
            relief="solid",
        )
        ent_hex.pack(side="right")
        ent_hex.bind("<Return>", self._on_hex_entry_commit)
        ent_hex.bind("<FocusOut>", self._on_hex_entry_commit)

        self.lbl_rgb = tk.Label(
            side_col,
            text="RGB: 123, 66, 188",
            font=("Consolas", 8),
            bg=t["bg_panel"],
            fg=t["fg_muted"],
            anchor="w",
        )
        self.lbl_rgb.pack(fill="x", pady=(2, 6))

        self.btn_eyedropper = tk.Button(
            side_col,
            text="Eyedropper",
            font=("Segoe UI", 8, "bold"),
            bg=t["bg_editor"],
            fg=editor_fg,
            activebackground=t["highlight_bg"],
            activeforeground=best_contrast_fg(t["highlight_bg"]),
            relief="solid",
            bd=1,
            padx=6,
            pady=3,
            cursor="hand2",
            command=self._toggle_eyedropper,
        )
        self.btn_eyedropper.pack(fill="x")

        self.lbl_eye_hint = tk.Label(
            side_col,
            text="",
            font=("Segoe UI", 7),
            bg=t["bg_panel"],
            fg=t["accent_blue"],
            wraplength=112,
            justify="left",
        )
        self.lbl_eye_hint.pack(fill="x", pady=(3, 0))

        sw_frame = tk.Frame(self, bg=t["bg_panel"])
        sw_frame.pack(fill="x", padx=12, pady=(6, 4))
        tk.Label(
            sw_frame,
            text="Quick Swatches:",
            font=("Segoe UI", 8),
            bg=t["bg_panel"],
            fg=t["fg_muted"],
        ).pack(side="left", padx=(0, 6))

        for _name, hex_c in PRICONNE_SWATCHES:
            sb = tk.Button(
                sw_frame,
                width=2,
                height=1,
                bg=hex_c,
                activebackground=hex_c,
                relief="solid",
                bd=1,
                cursor="hand2",
                command=lambda c=hex_c: self._set_color_hex(c),
            )
            sb.pack(side="left", padx=1)

        act_bar = tk.Frame(self, bg=t["bg_panel"])
        act_bar.pack(fill="x", padx=12, pady=(8, 12))

        self.btn_insert_single = tk.Button(
            act_bar,
            text=f"Insert [{self.stop_colors[0][1:].upper()}]",
            font=("Segoe UI", 9, "bold"),
            bg=t["misora_pink"],
            fg=accent_fg,
            activebackground=t["misora_pink_hover"],
            activeforeground=accent_hover_fg,
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._commit_single_color,
        )
        self.btn_insert_single.pack(side="left", padx=(0, 6))

        self.btn_insert_grad = tk.Button(
            act_bar,
            text="Insert Gradient [1-2]",
            font=("Segoe UI", 9, "bold"),
            bg=t["bg_editor"],
            fg=editor_fg,
            activebackground=t["highlight_bg"],
            activeforeground=best_contrast_fg(t["highlight_bg"]),
            relief="solid",
            bd=1,
            padx=10,
            pady=4,
            cursor="hand2",
            command=self._commit_gradient_color,
        )
        self.btn_insert_grad.pack(side="left")

        ttk.Button(act_bar, text="Close", style="TButton", command=self._on_close).pack(side="right")

    def _select_stop(self, stop_idx: int) -> None:
        self.active_stop = stop_idx
        hex_c = self.stop_colors[stop_idx]
        r = int(hex_c[1:3], 16) / 255.0
        g = int(hex_c[3:5], 16) / 255.0
        b = int(hex_c[5:7], 16) / 255.0
        self._h, self._s, self._v = colorsys.rgb_to_hsv(r, g, b)
        self._render_sv_map()
        self._sync_ui_from_hsv()

    def _render_hue_bar(self) -> None:
        img = tk.PhotoImage(width=self.HUE_W, height=self.HUE_H)
        rows: List[str] = []
        for y in range(self.HUE_H):
            h = y / max(1, self.HUE_H - 1)
            r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
            hx = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
            rows.append("{" + " ".join([hx] * self.HUE_W) + "}")
        img.put(" ".join(rows))
        self._hue_photo = img
        self.canvas_hue.delete("all")
        self.canvas_hue.create_image(0, 0, anchor="nw", image=img)

    def _render_sv_map(self) -> None:
        img = tk.PhotoImage(width=self.SV_W, height=self.SV_H)
        h = self._h
        rows: List[str] = []
        w_denom = max(1, self.SV_W - 1)
        h_denom = max(1, self.SV_H - 1)
        for y in range(self.SV_H):
            v = 1.0 - (y / h_denom)
            row_colors: List[str] = []
            for x in range(self.SV_W):
                s = x / w_denom
                r, g, b = colorsys.hsv_to_rgb(h, s, v)
                row_colors.append(f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
            rows.append("{" + " ".join(row_colors) + "}")
        img.put(" ".join(rows))
        self._sv_photo = img
        self.canvas_sv.delete("all")
        self.canvas_sv.create_image(0, 0, anchor="nw", image=img)

    def _render_gradient_preview(self) -> None:
        w, h = 46, 34
        c1, c2 = self.stop_colors[0], self.stop_colors[1]
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        img = tk.PhotoImage(width=w, height=h)
        rows: List[str] = []
        denom = max(1, h - 1)
        for y in range(h):
            t = y / denom
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)
            hx = f"#{r:02x}{g:02x}{b:02x}"
            rows.append("{" + " ".join([hx] * w) + "}")
        img.put(" ".join(rows))
        self._grad_photo = img
        self.canvas_grad_preview.delete("all")
        self.canvas_grad_preview.create_image(0, 0, anchor="nw", image=img)

    def _sync_ui_from_hsv(self) -> None:
        t = self.theme
        r_f, g_f, b_f = colorsys.hsv_to_rgb(self._h, self._s, self._v)
        r_i, g_i, b_i = int(round(r_f * 255)), int(round(g_f * 255)), int(round(b_f * 255))
        hex_c = f"#{r_i:02x}{g_i:02x}{b_i:02x}"
        self.stop_colors[self.active_stop] = hex_c

        cx = int(round(self._s * (self.SV_W - 1)))
        cy = int(round((1.0 - self._v) * (self.SV_H - 1)))
        self.canvas_sv.delete("cursor")
        ring_color = best_contrast_fg(hex_c)
        self.canvas_sv.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, outline=ring_color, width=2, tags="cursor")

        hy = int(round(self._h * (self.HUE_H - 1)))
        self.canvas_hue.delete("cursor")
        self.canvas_hue.create_rectangle(0, max(0, hy - 2), self.HUE_W, min(self.HUE_H, hy + 2), outline="#ffffff", width=2, tags="cursor")

        self.lbl_swatch_active.configure(bg=hex_c)
        self.var_hex.set(hex_c.upper())
        self.lbl_rgb.configure(text=f"RGB: {r_i}, {g_i}, {b_i}")
        self._render_gradient_preview()

        accent_fg = best_contrast_fg(t["misora_pink"])
        inactive_fg = best_contrast_fg(t["bg_editor"], t["fg_text"], "#ffffff")
        if self.active_stop == 0:
            self.btn_stop0.configure(bg=t["misora_pink"], fg=accent_fg)
            self.btn_stop1.configure(bg=t["bg_editor"], fg=inactive_fg)
        else:
            self.btn_stop0.configure(bg=t["bg_editor"], fg=inactive_fg)
            self.btn_stop1.configure(bg=t["misora_pink"], fg=accent_fg)

        c0_code = self.stop_colors[0][1:].upper()
        c1_code = self.stop_colors[1][1:].upper()
        self.btn_insert_single.configure(text=f"Insert [{c0_code}]")
        self.btn_insert_grad.configure(text=f"Insert [{c0_code}-{c1_code}]")

        self.app._set_ribbon_colors(self.stop_colors[0], self.stop_colors[1])

    def _on_sv_drag(self, event: tk.Event) -> None:
        x = max(0, min(self.SV_W - 1, event.x))
        y = max(0, min(self.SV_H - 1, event.y))
        self._s = x / max(1, self.SV_W - 1)
        self._v = 1.0 - (y / max(1, self.SV_H - 1))
        self._sync_ui_from_hsv()

    def _on_hue_drag(self, event: tk.Event) -> None:
        y = max(0, min(self.HUE_H - 1, event.y))
        self._h = y / max(1, self.HUE_H - 1)
        self._render_sv_map()
        self._sync_ui_from_hsv()

    def _set_color_hex(self, hex_str: str) -> None:
        val = hex_str.strip()
        if not val.startswith("#"):
            val = "#" + val
        if not HEX_COLOR_RE.match(val):
            return
        val = val.lower()
        r = int(val[1:3], 16) / 255.0
        g = int(val[3:5], 16) / 255.0
        b = int(val[5:7], 16) / 255.0
        self._h, self._s, self._v = colorsys.rgb_to_hsv(r, g, b)
        self._render_sv_map()
        self._sync_ui_from_hsv()

    def _on_hex_entry_commit(self, _event: Optional[tk.Event] = None) -> None:
        val = self.var_hex.get().strip()
        if not val.startswith("#"):
            val = "#" + val
        if HEX_COLOR_RE.match(val):
            self._set_color_hex(val)
        else:
            self.var_hex.set(self.stop_colors[self.active_stop].upper())

    def _toggle_eyedropper(self) -> None:
        if self._eyedropper_active:
            self._stop_eyedropper()
            return

        if sys.platform != "win32":
            self.lbl_eye_hint.configure(text="Screen eyedropper requires Windows; use map or swatches.")
            return

        self._eyedropper_active = True
        self._mouse_was_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
        self.btn_eyedropper.configure(
            text="Sampling... (Click)",
            bg=self.theme["misora_pink"],
            fg=best_contrast_fg(self.theme["misora_pink"]),
        )
        self.lbl_eye_hint.configure(text="Move cursor over any pixel on screen & Left-Click (Esc to cancel).")
        self._poll_eyedropper()

    def _poll_eyedropper(self) -> None:
        if not self._eyedropper_active or not self.winfo_exists():
            return

        try:
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32

            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            hdc = gdi32.GetDC(0)
            try:
                colorref = gdi32.GetPixel(hdc, pt.x, pt.y)
            finally:
                gdi32.ReleaseDC(0, hdc)

            if colorref != -1 and colorref != 0xFFFFFFFF:
                r = colorref & 0xFF
                g = (colorref >> 8) & 0xFF
                b = (colorref >> 16) & 0xFF
                self._set_color_hex(f"#{r:02x}{g:02x}{b:02x}")

            if user32.GetAsyncKeyState(0x1B) & 0x8000:
                self._stop_eyedropper()
                return

            mouse_down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)
            if mouse_down and not self._mouse_was_down:
                self._stop_eyedropper()
                self.lift()
                return
            self._mouse_was_down = mouse_down
        except Exception:
            self._stop_eyedropper()
            return

        self._eyedropper_after_id = self.after(35, self._poll_eyedropper)

    def _stop_eyedropper(self) -> None:
        self._eyedropper_active = False
        if self._eyedropper_after_id is not None:
            try:
                self.after_cancel(self._eyedropper_after_id)
            except Exception:
                pass
            self._eyedropper_after_id = None
        if self.winfo_exists():
            self.btn_eyedropper.configure(
                text="Eyedropper",
                bg=self.theme["bg_editor"],
                fg=best_contrast_fg(self.theme["bg_editor"], self.theme["fg_text"], "#ffffff"),
            )
            self.lbl_eye_hint.configure(text="")

    def _commit_single_color(self) -> None:
        self._stop_eyedropper()
        code = self.stop_colors[0][1:].upper()
        self.app.apply_ngui_wrapper(f"[{code}]", "[-]")
        self._on_close()

    def _commit_gradient_color(self) -> None:
        self._stop_eyedropper()
        c0 = self.stop_colors[0][1:].upper()
        c1 = self.stop_colors[1][1:].upper()
        self.app.apply_ngui_wrapper(f"[{c0}-{c1}]", "[-]")
        self._on_close()

    def _on_escape(self, _event: Optional[tk.Event] = None) -> None:
        if self._eyedropper_active:
            self._stop_eyedropper()
        else:
            self._on_close()

    def _on_close(self) -> None:
        self._stop_eyedropper()
        self.destroy()


class MisoraApp(tk.Tk):
    """Main Application Window for Misora: Unity3D Revision Tool."""

    def __init__(self, initial_path: Optional[str] = None):
        super().__init__()
        self.title("Misora: Unity3D Revision Tool & Story Editor")
        self.geometry("1280x820")
        self.minsize(980, 620)

        # Central Logger initialized early so startup & config load are recorded
        self.logger = MisoraLogger(DEBUG_LOG_PATH)
        self._install_exception_hooks()

        # Load persistent user preferences (fonts, theme colors, debug console settings)
        self.prefs: Dict[str, Any] = self._load_user_prefs()
        self.theme: Dict[str, str] = dict(self.prefs["theme"])
        THEME.update(self.theme)

        dbg_cfg = self.prefs.get("debug", {})
        self.logger.configure(
            level_name=dbg_cfg.get("level", "Info"),
            log_to_file=bool(dbg_cfg.get("log_to_file", False)),
            categories=dbg_cfg.get("categories"),
            log_file_path=DEBUG_LOG_PATH,
        )

        self.configure(bg=self.theme["bg_dark"])
        apply_window_icon(self)

        # State Variables
        self.current_file_path: Optional[Path] = None
        self.current_doc: Optional[StoryDocument] = None
        self.current_unity_env: Any = None
        self.current_text_obj: Any = None
        self.current_box_idx: int = 0
        self.is_bundle_file: bool = False
        self.is_dirty: bool = False
        self._plain_text_content: str = ""
        self.xuat_search_roots: List[Path] = []
        self.selected_search_folder: Optional[Path] = None

        # Steps 3-4: Undo journal, opened-files cache, path config
        self.undo_journal: MasterUndoJournal = MasterUndoJournal()
        self.open_documents: Dict[Path, Any] = {}   # path -> open doc info dict
        self.backup_folder: Optional[Path] = None   # None = auto (SCRIPT_DIR/backups)
        self.bepinex_project_folder: Optional[Path] = None
        self.datamine_exe: Optional[Path] = None
        self.external_editor_path: Optional[Path] = None
        self.notepadpp_path: Optional[Path] = None
        self._datamine_confirm_skip: bool = False
        self._left_dock_tab: str = "search"         # "search" | "files"
        self._left_dock_width: int = 340

        # Active NGUI Ribbon color state
        self._active_ngui_color: str = "#7b42bc"
        self._active_ngui_grad_end: str = "#ff7da7"
        self._color_picker_win: Optional[NguiColorPickerPopup] = None

        # Multi-box edit tracking for Continuous View & XUAT sync
        self._original_box_texts: Dict[int, str] = {}
        self._modified_boxes: Set[int] = set()
        self._cont_header_spans: Dict[int, Tuple[str, str]] = {}
        self._suppress_continuous_events: bool = False

        # Side Drawer (Customization & NGUI Glossary) state
        self._side_drawer_visible: bool = False
        self._side_drawer_tab: str = "customize"
        self._theme_swatch_buttons: Dict[str, tk.Button] = {}
        self._theme_hex_vars: Dict[str, tk.StringVar] = {}
        self._glossary_line_map: Dict[int, int] = {}
        self._selected_glossary_idx: int = 0
        self._filtered_glossary_items: List[Dict[str, str]] = list(NGUI_GLOSSARY_ITEMS)

        # Native Win32 Drag & Drop references (kept alive to prevent GC)
        self._wndprocs: Dict[int, Tuple[Any, Any]] = {}
        self._drop_hwnd: Any = None
        self._dnd_in_progress: bool = False

        # Debug Console state
        self._console_visible: bool = bool(dbg_cfg.get("console_visible", False))
        self.var_console_visible = tk.BooleanVar(value=self._console_visible)
        self.var_log_to_file = tk.BooleanVar(value=bool(dbg_cfg.get("log_to_file", False)))
        self.var_log_level = tk.StringVar(value=str(dbg_cfg.get("level", "Info")))
        self.var_console_autoscroll = tk.BooleanVar(value=True)
        self.var_log_categories: Dict[str, tk.BooleanVar] = {}
        saved_cats = dbg_cfg.get("categories", {}) if isinstance(dbg_cfg.get("categories"), dict) else {}
        for cat in LOG_CATEGORIES:
            enabled = True if cat == ALWAYS_ON_CATEGORY else bool(saved_cats.get(cat, True))
            self.var_log_categories[cat] = tk.BooleanVar(value=enabled)

        # Background search worker & highlighting state
        self.search_engine = ProjectSearchEngine()
        self.sync_manager = XUnitySyncManager()
        self.search_queue: queue.Queue = queue.Queue()
        self.search_cancel_flag: bool = False
        self.active_search_results: List[SearchResult] = []
        self.active_search_options: Optional[SearchOptions] = None
        self.search_file_groups: List[Dict[str, Any]] = []
        self._file_group_lookup: Dict[str, Dict[str, Any]] = {}
        self._result_line_map: Dict[int, Tuple[str, Any]] = {}
        self._result_idx_to_line: Dict[int, int] = {}
        self._selected_result_idx: Optional[int] = None

        # Auto-detect project paths
        self._detect_environment()

        # Build UI
        self._apply_styles()
        self._build_menu()
        self._build_search_bar()
        self._build_main_panels()
        self._build_side_drawer()
        self._build_debug_console()
        self._build_status_bar()
        self._bind_shortcuts()

        # Sync initial widget fonts & colors with saved preferences
        self._apply_theme_and_fonts_live(save=False)

        # Restore console visibility if saved
        if self._console_visible:
            self._set_console_visible(True, save=False)

        # Flush config on exit and unhook Win32 WNDPROC cleanly
        self.protocol("WM_DELETE_WINDOW", self._on_app_exit)
        self.bind("<Destroy>", self._on_root_destroy)

        # Enable native OS Drag & Drop safely on the outer frame HWND
        self._init_drag_and_drop()

        # Start periodic poll for background tasks & log console entries
        self.after(100, self._process_search_queue)
        self.after(120, self._flush_log_console)

        self.logger.info("UI / Theme / Config", f"Misora initialized. Config path: {CONFIG_PATH}")

        if initial_path and os.path.exists(initial_path):
            self.open_file(initial_path)

    # -------------------------------------------------------------------------
    # Global Exception Hooks & Exit Lifecycle
    # -------------------------------------------------------------------------
    def _install_exception_hooks(self) -> None:
        def _sys_excepthook(exc_type, exc_value, exc_tb):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_tb)
                return
            self.logger.exception("Unhandled Python exception:", exc_value)

        sys.excepthook = _sys_excepthook

    def report_callback_exception(self, exc, val, tb) -> None:  # type: ignore[override]
        self.logger.exception("Unhandled Tkinter callback exception:", val)

    def _on_app_exit(self) -> None:
        """Save configuration cleanly on window close and exit."""
        self.logger.info("UI / Theme / Config", "Saving configuration on exit...")
        self._save_user_prefs(silent=True)
        self._cleanup_drag_and_drop()
        self.destroy()

    def _on_root_destroy(self, event: tk.Event) -> None:
        if event.widget is self:
            self._cleanup_drag_and_drop()

    # -------------------------------------------------------------------------
    # Persistent Preferences & Contrast-Safe Theme Helpers (#2 & #13)
    # -------------------------------------------------------------------------
    def _load_user_prefs(self) -> Dict[str, Any]:
        """Load saved font, theme & debug settings from misora_config.json."""
        merged_theme = dict(DEFAULT_PREFS["theme"])
        merged_debug: Dict[str, Any] = {
            "console_visible": False,
            "log_to_file": False,
            "level": "Info",
            "categories": {cat: True for cat in LOG_CATEGORIES},
        }
        prefs: Dict[str, Any] = {
            "dialogue_font_family": DEFAULT_PREFS["dialogue_font_family"],
            "dialogue_font_size": DEFAULT_PREFS["dialogue_font_size"],
            "raw_font_size": DEFAULT_PREFS["raw_font_size"],
            "ui_font_size": DEFAULT_PREFS["ui_font_size"],
            "theme": merged_theme,
            "debug": merged_debug,
        }
        if CONFIG_PATH.is_file():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    if isinstance(raw.get("dialogue_font_family"), str) and raw["dialogue_font_family"].strip():
                        prefs["dialogue_font_family"] = raw["dialogue_font_family"].strip()
                    for k, lo, hi in (
                        ("dialogue_font_size", 8, 28),
                        ("raw_font_size", 7, 22),
                        ("ui_font_size", 8, 16),
                    ):
                        val = raw.get(k)
                        if isinstance(val, int) and not isinstance(val, bool) and lo <= val <= hi:
                            prefs[k] = val
                    saved_theme = raw.get("theme")
                    if isinstance(saved_theme, dict):
                        for tk_key in merged_theme:
                            hv = saved_theme.get(tk_key)
                            if isinstance(hv, str) and HEX_COLOR_RE.match(hv.strip()):
                                merged_theme[tk_key] = hv.strip().lower()
                    saved_dbg = raw.get("debug")
                    if isinstance(saved_dbg, dict):
                        if isinstance(saved_dbg.get("console_visible"), bool):
                            merged_debug["console_visible"] = saved_dbg["console_visible"]
                        if isinstance(saved_dbg.get("log_to_file"), bool):
                            merged_debug["log_to_file"] = saved_dbg["log_to_file"]
                        if saved_dbg.get("level") in LOG_LEVELS:
                            merged_debug["level"] = saved_dbg["level"]
                        scats = saved_dbg.get("categories")
                        if isinstance(scats, dict):
                            for cat in LOG_CATEGORIES:
                                if cat == ALWAYS_ON_CATEGORY:
                                    merged_debug["categories"][cat] = True
                                elif isinstance(scats.get(cat), bool):
                                    merged_debug["categories"][cat] = scats[cat]
                self.logger.debug("UI / Theme / Config", f"Loaded config from {CONFIG_PATH}")
                # Load Step 3-4 path/dock config (additive; no version bump needed)
                def _load_path(key: str) -> Optional[Path]:
                    v = raw.get(key)
                    return Path(v) if isinstance(v, str) and v else None
                self.backup_folder = _load_path("backup_folder")
                self.bepinex_project_folder = _load_path("bepinex_project_folder")
                self.datamine_exe = _load_path("datamine_exe")
                self.external_editor_path = _load_path("external_editor_path")
                self.notepadpp_path = _load_path("notepadpp_path")
                if isinstance(raw.get("left_dock_tab"), str):
                    self._left_dock_tab = raw["left_dock_tab"]
                if isinstance(raw.get("left_dock_width"), int):
                    self._left_dock_width = max(140, min(600, raw["left_dock_width"]))
                if isinstance(raw.get("datamine_confirm_skip"), bool):
                    self._datamine_confirm_skip = raw["datamine_confirm_skip"]
            except Exception as exc:
                self.logger.warning("UI / Theme / Config", f"Failed to parse {CONFIG_PATH}: {exc}")
        return prefs

    def _save_user_prefs(self, silent: bool = False) -> None:
        """Atomically persist current font, theme & debug preferences to misora_config.json."""
        try:
            dbg_snapshot = self.logger.get_config_snapshot()
            dbg_snapshot["console_visible"] = (
                bool(self.var_console_visible.get())
                if hasattr(self, "var_console_visible")
                else self._console_visible
            )
            self.prefs["debug"] = dbg_snapshot

            payload = {
                "config_version": 3,
                "dialogue_font_family": str(self.prefs["dialogue_font_family"]),
                "dialogue_font_size": int(self.prefs["dialogue_font_size"]),
                "raw_font_size": int(self.prefs["raw_font_size"]),
                "ui_font_size": int(self.prefs["ui_font_size"]),
                "theme": dict(self.theme),
                "debug": dbg_snapshot,
                # Step 3-4 path/dock state
                "backup_folder": str(self.backup_folder) if self.backup_folder else "",
                "bepinex_project_folder": str(self.bepinex_project_folder) if self.bepinex_project_folder else "",
                "datamine_exe": str(self.datamine_exe) if self.datamine_exe else "",
                "external_editor_path": str(self.external_editor_path) if self.external_editor_path else "",
                "notepadpp_path": str(self.notepadpp_path) if self.notepadpp_path else "",
                "left_dock_tab": self._left_dock_tab if hasattr(self, "_left_dock_tab") else "search",
                "left_dock_width": self._left_dock_width if hasattr(self, "_left_dock_width") else 340,
                "datamine_confirm_skip": self._datamine_confirm_skip if hasattr(self, "_datamine_confirm_skip") else False,
            }
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp_path, CONFIG_PATH)
            if not silent:
                self.logger.debug("UI / Theme / Config", f"Saved config to {CONFIG_PATH}")
        except Exception as e:
            self.logger.error("UI / Theme / Config", f"Failed to save config '{CONFIG_PATH}': {e}")

    def _detect_active_preset_name(self) -> str:
        """Return matching preset name if current theme equals a preset, else 'Custom'."""
        for name, preset in THEME_PRESETS.items():
            if all(self.theme.get(k, "").lower() == v.lower() for k, v in preset.items()):
                return name
        return "Custom"

    @staticmethod
    def _is_dark_color(hex_color: str) -> bool:
        """Return True if a #RRGGBB color has low WCAG relative luminance."""
        return wcag_relative_luminance(hex_color) < 0.179

    @staticmethod
    def _shift_hex(hex_color: str, delta: int) -> str:
        """Lighten or darken a #RRGGBB color by `delta` per channel."""
        if not HEX_COLOR_RE.match(hex_color):
            return hex_color
        r = max(0, min(255, int(hex_color[1:3], 16) + delta))
        g = max(0, min(255, int(hex_color[3:5], 16) + delta))
        b = max(0, min(255, int(hex_color[5:7], 16) + delta))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _tag_role(self, widget: tk.Widget, role: str) -> tk.Widget:
        """Attach a semantic theme role to a Tk widget for live re-theming."""
        setattr(widget, "_misora_role", role)
        return widget

    def _apply_theme_and_fonts_live(self, save: bool = True) -> None:
        """Re-apply current theme colors (with WCAG contrast) and font sizes across all active widgets."""
        THEME.update(self.theme)
        self._apply_styles()

        t = self.theme
        d_fam = self.prefs["dialogue_font_family"]
        d_sz = int(self.prefs["dialogue_font_size"])
        r_sz = int(self.prefs["raw_font_size"])
        u_sz = int(self.prefs["ui_font_size"])

        accent_fg = best_contrast_fg(t["misora_pink"])
        panel_fg = best_contrast_fg(t["bg_panel"], t["fg_text"], "#ffffff")
        editor_fg = best_contrast_fg(t["bg_editor"], t["fg_text"], "#ffffff")
        hl_fg = best_contrast_fg(t["highlight_bg"], t["fg_text"], "#ffffff")

        self.configure(bg=t["bg_dark"])

        for menu_obj in getattr(self, "_all_menus", []):
            try:
                menu_obj.configure(
                    bg=t["bg_panel"],
                    fg=panel_fg,
                    activebackground=t["misora_pink"],
                    activeforeground=accent_fg,
                )
            except Exception:
                pass

        def walk(w: tk.Widget) -> None:
            role = getattr(w, "_misora_role", None)
            try:
                if role == "dark":
                    w.configure(bg=t["bg_dark"])
                elif role == "panel":
                    w.configure(bg=t["bg_panel"])
                elif role == "ribbon":
                    w.configure(bg=t["bg_editor"], highlightbackground=t["border"])
                elif role == "panel_box":
                    w.configure(bg=t["bg_panel"], highlightbackground=t["border"])
                elif role == "editor_box":
                    w.configure(bg=t["bg_editor"])
                elif role == "sash":
                    w.configure(bg=t["border"])
                elif role == "label_panel":
                    w.configure(bg=t["bg_panel"], fg=panel_fg, font=("Segoe UI", u_sz))
                elif role == "label_muted":
                    w.configure(bg=t["bg_panel"], fg=t["fg_muted"], font=("Segoe UI", max(8, u_sz - 1)))
                elif role == "label_ribbon":
                    w.configure(bg=t["bg_editor"], fg=t["fg_muted"], font=("Segoe UI", max(8, u_sz - 1), "bold"))
                elif role == "label_accent":
                    w.configure(bg=t["bg_panel"], fg=t["misora_pink"], font=("Segoe UI", u_sz, "bold"))
                elif role == "label_voice":
                    w.configure(bg=t["bg_panel"], fg=t["accent_blue"], font=("Segoe UI", max(8, u_sz - 1)))
                elif role == "label_sep":
                    w.configure(bg=t["bg_panel"], fg=t["border"])
                elif role == "label_ribbon_sep":
                    w.configure(bg=t["bg_editor"], fg=t["border"])
                elif role == "check_panel":
                    w.configure(
                        bg=t["bg_panel"],
                        fg=panel_fg,
                        selectcolor=t["bg_dark"],
                        activebackground=t["bg_panel"],
                        activeforeground=panel_fg,
                        font=("Segoe UI", u_sz),
                    )
                elif role == "check_accent":
                    w.configure(
                        bg=t["bg_panel"],
                        fg=panel_fg,
                        selectcolor=t["bg_dark"],
                        activebackground=t["bg_panel"],
                        activeforeground=t["misora_pink"],
                        font=("Segoe UI", max(8, u_sz - 1), "bold"),
                    )
                elif role == "check_ribbon":
                    w.configure(
                        bg=t["bg_editor"],
                        fg=editor_fg,
                        selectcolor=t["bg_panel"],
                        activebackground=t["bg_editor"],
                        activeforeground=t["misora_pink"],
                        font=("Segoe UI", max(8, u_sz - 1), "bold"),
                    )
                elif role == "entry_editor":
                    w.configure(
                        bg=t["bg_editor"],
                        fg=editor_fg,
                        insertbackground=t["misora_pink"],
                        highlightbackground=t["border"],
                        highlightcolor=t["misora_pink"],
                    )
                elif role == "entry_speaker":
                    w.configure(
                        bg=t["bg_editor"],
                        fg=editor_fg,
                        insertbackground=t["misora_pink"],
                        selectbackground=t["highlight_bg"],
                        selectforeground=hl_fg,
                        font=(d_fam, max(9, d_sz - 1), "bold"),
                    )
            except Exception:
                pass

            for child in w.winfo_children():
                walk(child)

        walk(self)

        self.txt_results.configure(
            bg=t["bg_editor"],
            fg=editor_fg,
            font=("Segoe UI", u_sz),
        )
        self.txt_results.tag_configure("file_header", font=("Segoe UI", u_sz, "bold"), foreground=t["misora_pink"])
        self.txt_results.tag_configure("box_badge", font=("Consolas", max(8, u_sz - 1), "bold"), foreground=t["accent_blue"])
        self.txt_results.tag_configure("speaker_tag", font=("Segoe UI", u_sz, "bold"), foreground=editor_fg)
        self.txt_results.tag_configure("selected_row", background=t["highlight_bg"], foreground=hl_fg)
        self.txt_results.tag_configure(
            "match_hl",
            background=t["misora_pink"],
            foreground=accent_fg,
            font=("Segoe UI", u_sz, "bold"),
        )

        self.txt_dialogue.configure(
            font=(d_fam, d_sz),
            bg=t["bg_editor"],
            fg=editor_fg,
            insertbackground=t["misora_pink"],
            selectbackground=t["highlight_bg"],
            selectforeground=hl_fg,
        )
        self._configure_editor_rich_tags(self.txt_dialogue, d_fam, d_sz)

        self.txt_continuous.configure(
            font=(d_fam, d_sz),
            bg=t["bg_editor"],
            fg=editor_fg,
            insertbackground=t["misora_pink"],
            selectbackground=t["highlight_bg"],
            selectforeground=hl_fg,
        )
        self.txt_continuous.tag_configure("cont_divider", foreground=t["border"], font=("Consolas", max(7, d_sz - 3)))
        self.txt_continuous.tag_configure("cont_badge", foreground=t["misora_pink"], font=("Consolas", max(8, d_sz - 2), "bold"))
        self.txt_continuous.tag_configure("cont_speaker", foreground=editor_fg, font=(d_fam, max(9, d_sz - 1), "bold"))
        self.txt_continuous.tag_configure("cont_narrator", foreground=t["fg_muted"], font=(d_fam, max(8, d_sz - 2), "italic"))
        self.txt_continuous.tag_configure("cont_voice", foreground=t["accent_blue"], font=("Segoe UI", max(8, d_sz - 3)))
        self.txt_continuous.tag_configure("cont_active_header", background=t["highlight_bg"])
        self.txt_continuous.tag_configure("cont_body", foreground=editor_fg, font=(d_fam, d_sz))
        self._configure_editor_rich_tags(self.txt_continuous, d_fam, d_sz)

        raw_bg = self._shift_hex(t["bg_editor"], -6)
        self.txt_raw.configure(
            font=("Consolas", r_sz),
            bg=raw_bg,
            fg=t["fg_muted"],
            insertbackground=t["misora_pink"],
        )

        if hasattr(self, "txt_console"):
            self._apply_console_theme()

        if hasattr(self, "txt_glossary"):
            self.txt_glossary.configure(bg=t["bg_editor"], fg=editor_fg, font=("Segoe UI", u_sz))
            self.txt_glossary.tag_configure("gl_tag", font=("Consolas", u_sz, "bold"), foreground=t["misora_pink"])
            self.txt_glossary.tag_configure("gl_title", font=("Segoe UI", u_sz, "bold"), foreground=editor_fg)
            self.txt_glossary.tag_configure("gl_syntax", font=("Consolas", max(8, u_sz - 1)), foreground=t["accent_blue"])
            self.txt_glossary.tag_configure("gl_desc", font=("Segoe UI", max(8, u_sz - 1)), foreground=t["fg_muted"])
            self.txt_glossary.tag_configure("gl_selected", background=t["highlight_bg"], foreground=hl_fg)
            self._render_glossary_list()

        for key, btn in self._theme_swatch_buttons.items():
            if key in t:
                btn.configure(bg=t[key], activebackground=t[key])
            if key in self._theme_hex_vars and self._theme_hex_vars[key].get().lower() != t[key].lower():
                self._theme_hex_vars[key].set(t[key])

        if self.var_preview_compiled.get():
            self._update_views()
        else:
            self._highlight_ngui_tags()
            self._auto_resize_dialogue_box()

        if save:
            self._save_user_prefs()

    def _configure_editor_rich_tags(self, widget: tk.Text, d_fam: str, d_sz: int) -> None:
        """Configure syntax highlight & compiled NGUI preview tags on a dialogue text widget."""
        t = self.theme
        hl_fg = best_contrast_fg(t["highlight_bg"], t["misora_pink"], "#ffffff")
        widget.tag_configure(
            "ngui_tag",
            foreground=t["accent_yellow"],
            font=("Consolas", max(8, d_sz - 1)),
        )
        widget.tag_configure(
            "compiled_ruby",
            foreground=hl_fg,
            background=t["highlight_bg"],
            font=(d_fam, max(7, d_sz - 3), "bold"),
            offset=5,
        )
        widget.tag_configure(
            "compiled_player",
            foreground=best_contrast_fg(t["highlight_bg"], t["accent_blue"], "#ffffff"),
            background=t["highlight_bg"],
            font=(d_fam, d_sz, "bold"),
        )
        widget.tag_configure(
            "search_hit",
            background=t["highlight_bg"],
            foreground=hl_fg,
            underline=True,
        )
        for tag_name in list(widget.tag_names()):
            if tag_name.startswith("cstyle_"):
                widget.tag_delete(tag_name)
        widget.tag_raise("ngui_tag")
        widget.tag_raise("search_hit")

    # -------------------------------------------------------------------------
    # Native Windows Drag & Drop — Crash-Safe Single-HWND Subclassing (#1)
    # -------------------------------------------------------------------------
    def _init_drag_and_drop(self) -> None:
        """Register native Win32 WM_DROPFILES handler safely on the top-level outer HWND."""
        if sys.platform != "win32":
            return

        try:
            self.update_idletasks()
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32

            is_64bit = ctypes.sizeof(ctypes.c_void_p) == 8
            GWLP_WNDPROC = -4
            WM_DROPFILES = 0x0233
            WM_COPYDATA = 0x004A
            WM_COPYGLOBALDATA = 0x0049
            MSGFLT_ALLOW = 1

            LRESULT = ctypes.c_ssize_t
            LONG_PTR = ctypes.c_ssize_t

            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND

            shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
            shell32.DragAcceptFiles.restype = None

            shell32.DragQueryFileW.argtypes = [
                wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT
            ]
            shell32.DragQueryFileW.restype = wintypes.UINT

            shell32.DragFinish.argtypes = [wintypes.HANDLE]
            shell32.DragFinish.restype = None

            user32.CallWindowProcW.argtypes = [
                LONG_PTR, wintypes.HWND, wintypes.UINT,
                wintypes.WPARAM, wintypes.LPARAM
            ]
            user32.CallWindowProcW.restype = LRESULT

            get_wnd_proc = user32.GetWindowLongPtrW if is_64bit else user32.GetWindowLongW
            get_wnd_proc.argtypes = [wintypes.HWND, ctypes.c_int]
            get_wnd_proc.restype = LONG_PTR

            set_wnd_proc = user32.SetWindowLongPtrW if is_64bit else user32.SetWindowLongW
            set_wnd_proc.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
            set_wnd_proc.restype = LONG_PTR

            inner_hwnd = int(self.winfo_id())
            parent_hwnd = int(user32.GetParent(inner_hwnd) or 0)
            target_hwnd = parent_hwnd if parent_hwnd else inner_hwnd
            self._drop_hwnd = target_hwnd

            try:
                user32.ChangeWindowMessageFilterEx.argtypes = [
                    wintypes.HWND, wintypes.UINT, wintypes.DWORD, ctypes.c_void_p
                ]
                user32.ChangeWindowMessageFilterEx.restype = wintypes.BOOL
                for hwnd in {h for h in (target_hwnd, inner_hwnd) if h}:
                    for msg_id in (WM_DROPFILES, WM_COPYDATA, WM_COPYGLOBALDATA):
                        user32.ChangeWindowMessageFilterEx(hwnd, msg_id, MSGFLT_ALLOW, None)
            except Exception as filter_exc:
                self.logger.debug("Drag & Drop", f"ChangeWindowMessageFilterEx skipped: {filter_exc}")

            WNDPROC = ctypes.WINFUNCTYPE(
                LRESULT, wintypes.HWND, wintypes.UINT,
                wintypes.WPARAM, wintypes.LPARAM
            )

            self._wndprocs = {}

            def _make_wndproc(orig_proc_addr: int):
                def _wndproc(hwnd, msg, wparam, lparam):
                    try:
                        if msg == WM_DROPFILES:
                            hdrop = wintypes.HANDLE(wparam)
                            dropped: List[Path] = []
                            try:
                                count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                                for idx in range(count):
                                    length = shell32.DragQueryFileW(hdrop, idx, None, 0)
                                    if length > 0:
                                        buf = ctypes.create_unicode_buffer(length + 1)
                                        shell32.DragQueryFileW(hdrop, idx, buf, length + 1)
                                        if buf.value:
                                            dropped.append(Path(buf.value))
                            finally:
                                shell32.DragFinish(hdrop)

                            if dropped and not self._dnd_in_progress:
                                self._dnd_in_progress = True
                                self.after(10, self._handle_dropped_paths, dropped)
                            return 0
                    except Exception as cb_exc:
                        self.logger.exception("Drag & Drop WNDPROC error:", cb_exc)
                        return 0

                    return user32.CallWindowProcW(orig_proc_addr, hwnd, msg, wparam, lparam)

                return WNDPROC(_wndproc)

            shell32.DragAcceptFiles(target_hwnd, True)
            orig_addr = int(get_wnd_proc(target_hwnd, GWLP_WNDPROC) or 0)
            if orig_addr:
                cb = _make_wndproc(orig_addr)
                cb_addr = ctypes.cast(cb, ctypes.c_void_p).value
                set_wnd_proc(target_hwnd, GWLP_WNDPROC, cb_addr)
                self._wndprocs[target_hwnd] = (cb, orig_addr)
                self.logger.debug("Drag & Drop", f"Subclassed top-level HWND={hex(target_hwnd)}")
        except Exception as e:
            self.logger.warning("Drag & Drop", f"Drag-and-drop hook warning: {e}")

    def _cleanup_drag_and_drop(self) -> None:
        """Restore original WNDPROC on registered HWNDs prior to window destruction."""
        if sys.platform != "win32" or not self._wndprocs:
            return
        try:
            user32 = ctypes.windll.user32
            is_64bit = ctypes.sizeof(ctypes.c_void_p) == 8
            GWLP_WNDPROC = -4
            LONG_PTR = ctypes.c_ssize_t
            set_wnd_proc = user32.SetWindowLongPtrW if is_64bit else user32.SetWindowLongW
            set_wnd_proc.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
            set_wnd_proc.restype = LONG_PTR

            for hwnd, (_cb, orig_addr) in list(self._wndprocs.items()):
                try:
                    if user32.IsWindow(hwnd) and orig_addr:
                        set_wnd_proc(hwnd, GWLP_WNDPROC, orig_addr)
                except Exception:
                    pass
            self._wndprocs.clear()
        except Exception:
            pass

    def _handle_dropped_paths(self, paths: List[Path]) -> None:
        """Process files or folders dropped onto the Misora window safely."""
        try:
            if not paths:
                return
            self.logger.info("Drag & Drop", f"Received {len(paths)} dropped item(s): {[str(p) for p in paths]}")

            files = [p for p in paths if p.is_file()]
            dirs = [p for p in paths if p.is_dir()]

            if files:
                preferred_exts = {".unity3d", ".asset", ".txt", ".json", ".csv", ".tsv"}
                target_file = next((f for f in files if f.suffix.lower() in preferred_exts), files[0])
                self.open_file(target_file)
                extra = len(paths) - 1
                if extra > 0:
                    self.lbl_status.config(
                        text=self.lbl_status.cget("text") + f" | (+{extra} additional item(s) ignored)"
                    )
            elif dirs:
                folder = dirs[0].resolve()
                self.selected_search_folder = folder
                self.scope_var.set("folder")
                self.lbl_status.config(
                    text=f"Selected folder for search: {folder} (Press 'Find in Files' to search)"
                )
        except Exception as exc:
            self.logger.exception("Error while handling dropped path(s):", exc)
            messagebox.showerror("Drag & Drop Error", f"Failed to open dropped item:\n{exc}")
        finally:
            self._dnd_in_progress = False

    # -------------------------------------------------------------------------
    # Environment & WCAG Contrast-Safe ttk Styling (#13, #4, #7)
    # -------------------------------------------------------------------------
    def _detect_environment(self) -> None:
        """Auto-detect Priconne BepInEx RedirectedResources, XUAT Text folders, and Notepad++."""
        candidates = [
            Path(r"C:\[Gacha]\PriconneRe-TL\src\BepInEx\Translation\en"),
            Path("output"),
            Path("input"),
            SCRIPT_DIR.parent / "input",
            SCRIPT_DIR.parent / "output",
        ]
        if self.bepinex_project_folder and self.bepinex_project_folder.exists():
            candidates.insert(0, self.bepinex_project_folder)
        for c in candidates:
            if c.exists():
                text_dir = c / "Text"
                target = text_dir if text_dir.exists() else c
                if target not in self.xuat_search_roots:
                    self.xuat_search_roots.append(target)

        # Auto-detect Notepad++ if not already set
        if not self.notepadpp_path or not Path(self.notepadpp_path).exists():
            for npp_dir in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
                candidate = Path(npp_dir) / "Notepad++" / "notepad++.exe"
                if candidate.is_file():
                    self.notepadpp_path = candidate
                    break

    def _get_backup_dir(self) -> Path:
        """Return user-configured backup folder, defaulting to SCRIPT_DIR / 'backups'."""
        if self.backup_folder:
            p = Path(self.backup_folder)
            p.mkdir(parents=True, exist_ok=True)
            return p
        default_bak = SCRIPT_DIR / "backups"
        default_bak.mkdir(parents=True, exist_ok=True)
        return default_bak

    def _apply_styles(self) -> None:
        """Apply WCAG contrast-safe theme colors & UI font sizing to all ttk widgets."""
        t = self.theme
        u_sz = int(self.prefs["ui_font_size"])
        dark_panel = self._is_dark_color(t["bg_panel"])

        # Compute WCAG optimal foregrounds for every surface & interactive state
        fg_on_dark = best_contrast_fg(t["bg_dark"], t["fg_text"], "#ffffff")
        fg_on_panel = best_contrast_fg(t["bg_panel"], t["fg_text"], "#ffffff")
        fg_on_editor = best_contrast_fg(t["bg_editor"], t["fg_text"], "#ffffff")

        accent_bg = t["misora_pink"]
        accent_hover = t["misora_pink_hover"]
        accent_press = t["misora_pink_active"]
        fg_accent = best_contrast_fg(accent_bg)
        fg_accent_hover = best_contrast_fg(accent_hover)
        fg_accent_press = best_contrast_fg(accent_press)

        btn_bg = self._shift_hex(t["bg_panel"], 10 if dark_panel else -8)
        btn_hover = self._shift_hex(t["bg_panel"], 22 if dark_panel else -16)
        btn_press = self._shift_hex(t["bg_panel"], -6 if dark_panel else -24)
        fg_btn = best_contrast_fg(btn_bg, t["fg_text"], "#ffffff")
        fg_btn_hover = best_contrast_fg(btn_hover, t["fg_text"], "#ffffff")
        fg_btn_press = best_contrast_fg(btn_press, t["fg_text"], "#ffffff")

        small_bg = t["bg_editor"]
        fg_small = best_contrast_fg(small_bg, t["fg_text"], "#ffffff")

        hl_bg = t["highlight_bg"]
        fg_hl = best_contrast_fg(hl_bg, t["misora_pink"], "#ffffff")

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=t["bg_dark"], foreground=fg_on_dark, borderwidth=0)
        style.configure("TFrame", background=t["bg_dark"])
        style.configure("Panel.TFrame", background=t["bg_panel"])

        style.configure("TLabel", background=t["bg_dark"], foreground=fg_on_dark, font=("Segoe UI", u_sz))
        style.configure("Panel.TLabel", background=t["bg_panel"], foreground=fg_on_panel, font=("Segoe UI", u_sz))
        style.configure("Header.TLabel", font=("Segoe UI", u_sz + 1, "bold"), foreground=t["misora_pink"])
        style.configure("Muted.TLabel", foreground=t["fg_muted"], font=("Segoe UI", max(8, u_sz - 1)))

        style.configure("TCheckbutton", background=t["bg_dark"], foreground=fg_on_dark, font=("Segoe UI", u_sz))
        style.configure("TRadiobutton", background=t["bg_dark"], foreground=fg_on_dark, font=("Segoe UI", u_sz))

        # Primary Accent Action Button
        style.configure(
            "Pink.TButton",
            background=accent_bg,
            foreground=fg_accent,
            bordercolor=accent_press,
            darkcolor=accent_press,
            lightcolor=accent_hover,
            borderwidth=1,
            relief="raised",
            font=("Segoe UI", u_sz, "bold"),
            padding=(10, 4),
        )
        style.map(
            "Pink.TButton",
            background=[
                ("disabled", btn_bg),
                ("pressed", accent_press),
                ("active", accent_hover),
            ],
            foreground=[
                ("disabled", t["fg_muted"]),
                ("pressed", fg_accent_press),
                ("active", fg_accent_hover),
            ],
        )

        # Distinct Box Navigation Buttons (< Prev / Next >) (#4)
        style.configure(
            "Nav.TButton",
            background=btn_bg,
            foreground=fg_btn,
            bordercolor=t["misora_pink"],
            darkcolor=t["border"],
            lightcolor=t["misora_pink"],
            borderwidth=1,
            relief="raised",
            font=("Segoe UI", u_sz, "bold"),
            padding=(9, 3),
        )
        style.map(
            "Nav.TButton",
            background=[
                ("disabled", t["bg_editor"]),
                ("pressed", accent_press),
                ("active", accent_bg),
            ],
            foreground=[
                ("disabled", t["fg_muted"]),
                ("pressed", fg_accent_press),
                ("active", fg_accent),
            ],
        )

        # Standard Button
        style.configure(
            "TButton",
            background=btn_bg,
            foreground=fg_btn,
            bordercolor=t["border"],
            darkcolor=t["border"],
            lightcolor=btn_hover,
            borderwidth=1,
            relief="raised",
            font=("Segoe UI", u_sz),
            padding=(7, 3),
        )
        style.map(
            "TButton",
            background=[
                ("disabled", t["bg_editor"]),
                ("pressed", btn_press),
                ("active", btn_hover),
            ],
            foreground=[
                ("disabled", t["fg_muted"]),
                ("pressed", fg_btn_press),
                ("active", fg_btn_hover),
            ],
        )

        # Compact Utility Button
        style.configure(
            "Small.TButton",
            background=small_bg,
            foreground=fg_small,
            bordercolor=t["border"],
            borderwidth=1,
            relief="raised",
            font=("Segoe UI", max(8, u_sz - 1)),
            padding=(6, 1),
        )
        style.map(
            "Small.TButton",
            background=[("active", btn_hover), ("pressed", btn_press)],
            foreground=[("active", fg_btn_hover), ("pressed", fg_btn_press)],
        )

        # NGUI Ribbon — Prominent Action Buttons (Color, Grad, + Ruby) (#7)
        style.configure(
            "RibbonPrimary.TButton",
            background=accent_bg,
            foreground=fg_accent,
            bordercolor=accent_press,
            borderwidth=1,
            relief="raised",
            font=("Segoe UI", max(8, u_sz - 1), "bold"),
            padding=(7, 1),
        )
        style.map(
            "RibbonPrimary.TButton",
            background=[("active", accent_hover), ("pressed", accent_press)],
            foreground=[("active", fg_accent_hover), ("pressed", fg_accent_press)],
        )

        # NGUI Ribbon — Standard Secondary Button ([-], {player}) (#7)
        style.configure(
            "Ribbon.TButton",
            background=btn_bg,
            foreground=fg_btn,
            bordercolor=t["border"],
            borderwidth=1,
            relief="raised",
            font=("Segoe UI", max(8, u_sz - 1), "bold"),
            padding=(5, 1),
        )
        style.map(
            "Ribbon.TButton",
            background=[("active", hl_bg), ("pressed", btn_press)],
            foreground=[("active", fg_hl), ("pressed", fg_btn_press)],
        )

        # NGUI Ribbon — Tiny Mini-Buttons (B, I, U, S, Sub, Sup) (#7)
        style.configure(
            "RibbonMini.TButton",
            background=btn_bg,
            foreground=fg_btn,
            bordercolor=t["border"],
            borderwidth=1,
            relief="raised",
            font=("Segoe UI", max(7, u_sz - 2), "bold"),
            padding=(3, 0),
        )
        style.map(
            "RibbonMini.TButton",
            background=[("active", hl_bg), ("pressed", btn_press)],
            foreground=[("active", fg_hl), ("pressed", fg_btn_press)],
        )

        style.configure(
            "TCombobox",
            fieldbackground=t["bg_editor"],
            background=btn_bg,
            foreground=fg_on_editor,
            arrowcolor=t["misora_pink"],
        )

    # -------------------------------------------------------------------------
    # Menu Bar (Includes NGUI Glossary Top-Level Menu #6 & Debug Menu #14)
    # -------------------------------------------------------------------------
    def _build_menu(self) -> None:
        t = self.theme
        panel_fg = best_contrast_fg(t["bg_panel"], t["fg_text"], "#ffffff")
        accent_fg = best_contrast_fg(t["misora_pink"])

        self.var_continuous_view = tk.BooleanVar(value=False)
        self.var_preview_compiled = tk.BooleanVar(value=False)
        self._all_menus: List[tk.Menu] = []

        menubar = tk.Menu(
            self,
            bg=t["bg_panel"],
            fg=panel_fg,
            activebackground=t["misora_pink"],
            activeforeground=accent_fg,
        )
        self._all_menus.append(menubar)

        file_menu = tk.Menu(menubar, tearoff=0, bg=t["bg_panel"], fg=panel_fg, activebackground=t["misora_pink"], activeforeground=accent_fg)
        file_menu.add_command(label="Open File...", command=self.on_open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Open Folder...", command=self.on_open_folder, accelerator="Ctrl+Shift+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save & Patch Bundle", command=self.on_save, accelerator="Ctrl+S")
        file_menu.add_command(label="Reload Current File", command=self.on_reload, accelerator="F5")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_app_exit, accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)
        self._all_menus.append(file_menu)

        self.edit_menu = tk.Menu(menubar, tearoff=0, bg=t["bg_panel"], fg=panel_fg, activebackground=t["misora_pink"], activeforeground=accent_fg, postcommand=self._sync_edit_menu_states)
        self.edit_menu.add_command(label="Undo", command=self.on_undo, accelerator="Ctrl+Z")
        self.edit_menu.add_command(label="Redo", command=self.on_redo, accelerator="Ctrl+Y")
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="Previous Box", command=self.on_prev_box, accelerator="Alt+Left")
        self.edit_menu.add_command(label="Next Box", command=self.on_next_box, accelerator="Alt+Right")
        self.edit_menu.add_separator()
        self.edit_menu.add_command(label="Bold ([b]...[/b])", command=lambda: self.apply_ngui_wrapper("[b]", "[/b]"), accelerator="Ctrl+B")
        self.edit_menu.add_command(label="Italic ([i]...[/i])", command=lambda: self.apply_ngui_wrapper("[i]", "[/i]"), accelerator="Ctrl+I")
        self.edit_menu.add_command(label="Underline ([u]...[/u])", command=lambda: self.apply_ngui_wrapper("[u]", "[/u]"), accelerator="Ctrl+U")
        self.edit_menu.add_command(label="Wrap Selection with Ruby ([rub:...]...[/rub])", command=self.on_insert_ruby, accelerator="Ctrl+R")
        self.edit_menu.add_command(label="NGUI Color & Gradient Picker...", command=self.on_open_color_picker)
        self.edit_menu.add_command(label="Insert {playername}", command=self.on_insert_playername, accelerator="Ctrl+P")
        menubar.add_cascade(label="Edit", menu=self.edit_menu)
        self._all_menus.append(self.edit_menu)

        view_menu = tk.Menu(menubar, tearoff=0, bg=t["bg_panel"], fg=panel_fg, activebackground=t["misora_pink"], activeforeground=accent_fg)
        view_menu.add_checkbutton(
            label="Continuous Dialog View",
            variable=self.var_continuous_view,
            command=self._on_toggle_continuous_view,
            accelerator="Ctrl+Shift+C",
            selectcolor=t["misora_pink"]
        )
        view_menu.add_checkbutton(
            label="Preview Compiled NGUI Attributes",
            variable=self.var_preview_compiled,
            command=self._on_toggle_preview_compiled,
            selectcolor=t["misora_pink"]
        )
        view_menu.add_separator()
        view_menu.add_command(label="Toggle Customization Panel", command=lambda: self._toggle_side_drawer("customize"), accelerator="Ctrl+,")
        view_menu.add_command(label="Toggle NGUI Glossary Panel", command=lambda: self._toggle_side_drawer("glossary"), accelerator="F1")
        view_menu.add_checkbutton(
            label="Debug Console",
            variable=self.var_console_visible,
            command=self._on_toggle_console_menu,
            accelerator="F12",
            selectcolor=t["misora_pink"],
        )
        menubar.add_cascade(label="View", menu=view_menu)
        self._all_menus.append(view_menu)

        search_menu = tk.Menu(menubar, tearoff=0, bg=t["bg_panel"], fg=panel_fg, activebackground=t["misora_pink"], activeforeground=accent_fg)
        search_menu.add_command(label="Find...", command=self.on_show_find, accelerator="Ctrl+F")
        search_menu.add_command(label="Find in Files...", command=self.on_show_find_in_files, accelerator="Ctrl+Shift+F")
        search_menu.add_command(label="Replace...", command=self.on_show_replace, accelerator="Ctrl+H")
        search_menu.add_separator()
        search_menu.add_command(label="Clear Search Results", command=self.on_clear_search)
        menubar.add_cascade(label="Search", menu=search_menu)
        self._all_menus.append(search_menu)

        cust_menu = tk.Menu(menubar, tearoff=0, bg=t["bg_panel"], fg=panel_fg, activebackground=t["misora_pink"], activeforeground=accent_fg)
        cust_menu.add_command(label="Display & Theme Settings...", command=lambda: self._open_side_drawer("customize"), accelerator="Ctrl+,")
        cust_menu.add_separator()
        cust_menu.add_command(label="Increase Dialogue Font Size", command=lambda: self._adjust_dialogue_font_size(1))
        cust_menu.add_command(label="Decrease Dialogue Font Size", command=lambda: self._adjust_dialogue_font_size(-1))
        cust_menu.add_separator()

        preset_sub = tk.Menu(cust_menu, tearoff=0, bg=t["bg_panel"], fg=panel_fg, activebackground=t["misora_pink"], activeforeground=accent_fg)
        for preset_name in THEME_PRESETS:
            preset_sub.add_command(
                label=preset_name,
                command=lambda pn=preset_name: self._apply_theme_preset(pn),
            )
        cust_menu.add_cascade(label="Theme Presets", menu=preset_sub)
        self._all_menus.append(preset_sub)

        cust_menu.add_separator()
        cust_menu.add_command(label="Reset Display & Colors to Default", command=self._reset_customization_defaults)
        menubar.add_cascade(label="Customize", menu=cust_menu)
        self._all_menus.append(cust_menu)

        # NGUI GLOSSARY TOP-LEVEL MENU (#6)
        glossary_menu = tk.Menu(
            menubar,
            tearoff=0,
            bg=t["bg_panel"],
            fg=panel_fg,
            activebackground=t["misora_pink"],
            activeforeground=accent_fg,
        )
        glossary_menu.add_command(
            label="Open NGUI & Ruby Glossary Drawer",
            command=lambda: self._toggle_side_drawer("glossary"),
            accelerator="F1",
        )
        glossary_menu.add_separator()
        glossary_menu.add_command(
            label="Wrap with Ruby ([rub:...]...[/rub])",
            command=self.on_insert_ruby,
            accelerator="Ctrl+R",
        )
        glossary_menu.add_command(
            label="Color & Gradient Picker...",
            command=self.on_open_color_picker,
        )
        glossary_menu.add_command(
            label="Insert {playername}",
            command=self.on_insert_playername,
            accelerator="Ctrl+P",
        )
        glossary_menu.add_command(
            label="Reset Color Tag ([-])",
            command=lambda: self.apply_ngui_wrapper("[-]", ""),
        )
        menubar.add_cascade(label="NGUI Glossary", menu=glossary_menu)
        self._all_menus.append(glossary_menu)

        # FOLDERS & FILES MENU (#4B)
        folders_menu = tk.Menu(
            menubar,
            tearoff=0,
            bg=t["bg_panel"],
            fg=panel_fg,
            activebackground=t["misora_pink"],
            activeforeground=accent_fg,
        )
        folders_menu.add_command(
            label="Configure Paths & Backups...",
            command=self.on_open_paths_dialog,
        )
        folders_menu.add_separator()
        folders_menu.add_command(
            label="Open Backups Folder",
            command=self.on_open_backups_folder,
        )
        folders_menu.add_command(
            label="Open BepInEx Translation Folder",
            command=self.on_open_bepinex_folder,
        )
        folders_menu.add_command(
            label="Open Misora Program Folder",
            command=self.on_open_program_folder,
        )
        menubar.add_cascade(label="Folders & Files", menu=folders_menu)
        self._all_menus.append(folders_menu)

        # DATAMINE MENU (#4C)
        datamine_menu = tk.Menu(
            menubar,
            tearoff=0,
            bg=t["bg_panel"],
            fg=panel_fg,
            activebackground=t["misora_pink"],
            activeforeground=accent_fg,
        )
        datamine_menu.add_command(
            label="Launch Datamine Tool",
            command=self.on_launch_datamine,
            accelerator="F9",
        )
        datamine_menu.add_separator()
        datamine_menu.add_command(
            label="Select Datamine Executable / Script...",
            command=self.on_select_datamine_exe,
        )
        datamine_menu.add_command(
            label="Open Datamine Program Folder",
            command=self.on_open_datamine_folder,
        )
        menubar.add_cascade(label="Datamine", menu=datamine_menu)
        self._all_menus.append(datamine_menu)

        # DEBUG MENU (#14 & #4D)
        self.debug_menu = tk.Menu(
            menubar,
            tearoff=0,
            bg=t["bg_panel"],
            fg=panel_fg,
            activebackground=t["misora_pink"],
            activeforeground=accent_fg,
            postcommand=self._sync_debug_menu_states,
        )
        self.debug_menu.add_checkbutton(
            label="Console",
            variable=self.var_console_visible,
            command=self._on_toggle_console_menu,
            accelerator="F12",
            selectcolor=t["misora_pink"],
        )

        cat_sub = tk.Menu(self.debug_menu, tearoff=0, bg=t["bg_panel"], fg=panel_fg, activebackground=t["misora_pink"], activeforeground=accent_fg)
        for cat in LOG_CATEGORIES:
            if cat == ALWAYS_ON_CATEGORY:
                cat_sub.add_checkbutton(
                    label=f"{cat} (Always On)",
                    variable=self.var_log_categories[cat],
                    state="disabled",
                    selectcolor=t["misora_pink"],
                )
            else:
                cat_sub.add_checkbutton(
                    label=cat,
                    variable=self.var_log_categories[cat],
                    command=self._on_debug_settings_changed,
                    selectcolor=t["misora_pink"],
                )
        self.debug_menu.add_cascade(label="Log Categories", menu=cat_sub)
        self._all_menus.append(cat_sub)

        lvl_sub = tk.Menu(self.debug_menu, tearoff=0, bg=t["bg_panel"], fg=panel_fg, activebackground=t["misora_pink"], activeforeground=accent_fg)
        for lvl_name in LOG_LEVELS:
            lvl_sub.add_radiobutton(
                label=lvl_name,
                variable=self.var_log_level,
                value=lvl_name,
                command=self._on_debug_settings_changed,
                selectcolor=t["misora_pink"],
            )
        self.debug_menu.add_cascade(label="Log Level", menu=lvl_sub)
        self._all_menus.append(lvl_sub)

        # External Editor submenu (#4D)
        self._ext_editor_menu = tk.Menu(
            self.debug_menu,
            tearoff=0,
            bg=t["bg_panel"],
            fg=panel_fg,
            activebackground=t["misora_pink"],
            activeforeground=accent_fg,
            postcommand=self._sync_external_editor_menu,
        )
        self._sync_external_editor_menu()
        self.debug_menu.add_cascade(label="External Editor", menu=self._ext_editor_menu)
        self._all_menus.append(self._ext_editor_menu)

        self.debug_menu.add_separator()
        self.debug_menu.add_checkbutton(
            label="Log to File",
            variable=self.var_log_to_file,
            command=self._on_debug_settings_changed,
            selectcolor=t["misora_pink"],
        )
        self._idx_open_log = self.debug_menu.index("end") + 1
        self.debug_menu.add_command(label="Open Log File", command=self._on_open_debug_log_file)
        self._idx_clear_log = self.debug_menu.index("end") + 1
        self.debug_menu.add_command(label="Clear Log File", command=self._on_clear_debug_log_file)

        menubar.add_cascade(label="Debug", menu=self.debug_menu)
        self._all_menus.append(self.debug_menu)

        help_menu = tk.Menu(menubar, tearoff=0, bg=t["bg_panel"], fg=panel_fg, activebackground=t["misora_pink"], activeforeground=accent_fg)
        help_menu.add_command(label="NGUI & Ruby Glossary", command=lambda: self._open_side_drawer("glossary"), accelerator="F1")
        help_menu.add_separator()
        help_menu.add_command(label="About Misora", command=self.on_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self._all_menus.append(help_menu)

        self.config(menu=menubar)

    # -------------------------------------------------------------------------
    # Search & Replace Bar (Collapsible Notepad++ Style)
    # -------------------------------------------------------------------------
    def _build_search_bar(self) -> None:
        t = self.theme
        self.search_frame = self._tag_role(
            tk.Frame(self, bg=t["bg_panel"], bd=1, relief="solid", highlightbackground=t["border"], highlightthickness=1),
            "panel_box"
        )
        self.search_frame.pack(fill="x", padx=8, pady=(6, 4))
        self._search_bar_visible = True

        row1 = self._tag_role(tk.Frame(self.search_frame, bg=t["bg_panel"]), "panel")
        row1.pack(fill="x", padx=8, pady=4)

        self._tag_role(
            tk.Label(row1, text="Find:", font=("Segoe UI", 9, "bold"), bg=t["bg_panel"], fg=t["misora_pink"]),
            "label_accent"
        ).pack(side="left", padx=(0, 6))

        self.search_var = tk.StringVar()
        self.search_entry = self._tag_role(
            tk.Entry(
                row1,
                textvariable=self.search_var,
                font=("Consolas", 10),
                bg=t["bg_editor"],
                fg=t["fg_text"],
                insertbackground=t["misora_pink"],
                bd=1,
                relief="solid",
                highlightthickness=1,
                highlightcolor=t["misora_pink"]
            ),
            "entry_editor"
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<Return>", lambda e: self.on_start_search())
        self.search_entry.bind("<Escape>", lambda e: self._hide_search_bar())

        self.btn_find = ttk.Button(row1, text="Find in Files", style="Pink.TButton", command=self.on_start_search)
        self.btn_find.pack(side="left", padx=4)

        self.btn_cancel = ttk.Button(row1, text="Cancel", style="TButton", command=self.on_cancel_search, state="disabled")
        self.btn_cancel.pack(side="left", padx=4)

        btn_close_search = ttk.Button(row1, text="✕", style="Small.TButton", command=self._hide_search_bar, width=3)
        btn_close_search.pack(side="left", padx=(4, 0))

        # Row 1.5: Replace row (shown when Ctrl+H / Replace is activated)
        self.row_replace = self._tag_role(tk.Frame(self.search_frame, bg=t["bg_panel"]), "panel")
        self._tag_role(
            tk.Label(self.row_replace, text="Replace:", font=("Segoe UI", 9, "bold"), bg=t["bg_panel"], fg=t["accent_blue"]),
            "label_voice"
        ).pack(side="left", padx=(0, 6))

        self.replace_var = tk.StringVar()
        self.replace_entry = self._tag_role(
            tk.Entry(
                self.row_replace,
                textvariable=self.replace_var,
                font=("Consolas", 10),
                bg=t["bg_editor"],
                fg=t["fg_text"],
                insertbackground=t["misora_pink"],
                bd=1,
                relief="solid",
                highlightthickness=1,
                highlightcolor=t["accent_blue"]
            ),
            "entry_editor"
        )
        self.replace_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.replace_entry.bind("<Escape>", lambda e: self._hide_search_bar())
        self.replace_entry.bind("<Return>", lambda e: self.on_replace_next())

        self.btn_replace = ttk.Button(self.row_replace, text="Replace", style="TButton", command=self.on_replace_next)
        self.btn_replace.pack(side="left", padx=4)

        self.btn_replace_all = ttk.Button(self.row_replace, text="Replace All", style="TButton", command=self.on_replace_all)
        self.btn_replace_all.pack(side="left", padx=4)
        self._replace_row_visible = False

        row2 = self._tag_role(tk.Frame(self.search_frame, bg=t["bg_panel"]), "panel")
        row2.pack(fill="x", padx=8, pady=(0, 4))

        self.var_case = tk.BooleanVar(value=False)
        self.var_regex = tk.BooleanVar(value=False)
        self.var_ignore_ws = tk.BooleanVar(value=True)
        self.var_inc_bundles = tk.BooleanVar(value=True)
        self.var_inc_text = tk.BooleanVar(value=True)

        cb_case = self._tag_role(
            tk.Checkbutton(row2, text="Match Case", variable=self.var_case, bg=t["bg_panel"], fg=t["fg_text"], selectcolor=t["bg_dark"], activebackground=t["bg_panel"], activeforeground=t["fg_text"]),
            "check_panel"
        )
        cb_case.pack(side="left", padx=4)

        cb_rx = self._tag_role(
            tk.Checkbutton(row2, text="Regex", variable=self.var_regex, bg=t["bg_panel"], fg=t["fg_text"], selectcolor=t["bg_dark"], activebackground=t["bg_panel"], activeforeground=t["fg_text"]),
            "check_panel"
        )
        cb_rx.pack(side="left", padx=4)

        cb_ws = self._tag_role(
            tk.Checkbutton(row2, text="Ignore Whitespace & {playername}", variable=self.var_ignore_ws, bg=t["bg_panel"], fg=t["fg_text"], selectcolor=t["bg_dark"], activebackground=t["bg_panel"], activeforeground=t["fg_text"]),
            "check_panel"
        )
        cb_ws.pack(side="left", padx=4)

        self._tag_role(tk.Label(row2, text="|", bg=t["bg_panel"], fg=t["border"]), "label_sep").pack(side="left", padx=8)

        self._tag_role(tk.Label(row2, text="Scope:", bg=t["bg_panel"], fg=t["fg_muted"]), "label_muted").pack(side="left", padx=(0, 4))
        self.scope_var = tk.StringVar(value="project")

        rb_proj = self._tag_role(
            tk.Radiobutton(row2, text="Project", variable=self.scope_var, value="project", bg=t["bg_panel"], fg=t["fg_text"], selectcolor=t["bg_dark"], activebackground=t["bg_panel"], command=self._sync_scope_widgets),
            "check_panel"
        )
        rb_proj.pack(side="left", padx=2)

        rb_folder = self._tag_role(
            tk.Radiobutton(row2, text="Folder", variable=self.scope_var, value="folder", bg=t["bg_panel"], fg=t["fg_text"], selectcolor=t["bg_dark"], activebackground=t["bg_panel"], command=self._sync_scope_widgets),
            "check_panel"
        )
        rb_folder.pack(side="left", padx=2)

        # Folder path entry + browse button (visible when Scope == 'folder')
        self.folder_path_var = tk.StringVar(value="")
        self.folder_path_entry = self._tag_role(
            tk.Entry(
                row2,
                textvariable=self.folder_path_var,
                font=("Segoe UI", 8),
                width=16,
                bg=t["bg_editor"],
                fg=t["fg_text"],
                bd=1,
                relief="solid",
            ),
            "entry_editor"
        )
        self.btn_browse_search_folder = ttk.Button(row2, text="...", style="Small.TButton", command=self.on_open_folder, width=2)

        rb_cur = self._tag_role(
            tk.Radiobutton(row2, text="Current File", variable=self.scope_var, value="current", bg=t["bg_panel"], fg=t["fg_text"], selectcolor=t["bg_dark"], activebackground=t["bg_panel"], command=self._sync_scope_widgets),
            "check_panel"
        )
        rb_cur.pack(side="left", padx=2)

        self._tag_role(tk.Label(row2, text="|", bg=t["bg_panel"], fg=t["border"]), "label_sep").pack(side="left", padx=8)
        cb_bdl = self._tag_role(
            tk.Checkbutton(row2, text=".unity3d", variable=self.var_inc_bundles, bg=t["bg_panel"], fg=t["fg_text"], selectcolor=t["bg_dark"], activebackground=t["bg_panel"]),
            "check_panel"
        )
        cb_bdl.pack(side="left", padx=2)
        cb_txt = self._tag_role(
            tk.Checkbutton(row2, text=".txt", variable=self.var_inc_text, bg=t["bg_panel"], fg=t["fg_text"], selectcolor=t["bg_dark"], activebackground=t["bg_panel"]),
            "check_panel"
        )
        cb_txt.pack(side="left", padx=2)

        self.progress_bar = ttk.Progressbar(self.search_frame, mode="determinate")
        self.progress_bar.pack(fill="x", padx=8, pady=(0, 2))
        self.progress_bar.pack_forget()

    # -------------------------------------------------------------------------
    # Main Workspace (#4 Distinct Nav Buttons, #5/#6 Clean Header, #7 Inline Ribbon)
    # -------------------------------------------------------------------------
    def _build_main_panels(self) -> None:
        t = self.theme
        d_fam = self.prefs["dialogue_font_family"]
        d_sz = int(self.prefs["dialogue_font_size"])
        r_sz = int(self.prefs["raw_font_size"])
        u_sz = int(self.prefs["ui_font_size"])

        self.outer_v_paned = self._tag_role(
            tk.PanedWindow(
                self,
                orient=tk.VERTICAL,
                bg=t["border"],
                sashwidth=6,
                sashrelief="flat",
                opaqueresize=True,
            ),
            "sash",
        )
        self.outer_v_paned.pack(fill="both", expand=True, padx=8, pady=4)

        self.h_paned = self._tag_role(
            tk.PanedWindow(
                self.outer_v_paned,
                orient=tk.HORIZONTAL,
                bg=t["border"],
                sashwidth=6,
                sashrelief="flat",
                opaqueresize=True
            ),
            "sash"
        )
        self.outer_v_paned.add(self.h_paned, minsize=260, stretch="always")

        # LEFT PANEL: Upgraded Dual-Tab Dock (Search Results & Opened Files Cache #3B)
        self.left_frame = self._tag_role(tk.Frame(self.h_paned, bg=t["bg_panel"]), "panel")
        self.h_paned.add(self.left_frame, minsize=160, width=self._left_dock_width, stretch="never")

        # Dock Tab Switcher Bar
        self.dock_tab_bar = self._tag_role(tk.Frame(self.left_frame, bg=t["bg_panel"]), "panel")
        self.dock_tab_bar.pack(fill="x", padx=4, pady=(4, 2))

        self.btn_tab_search = tk.Button(
            self.dock_tab_bar,
            text="Search Results",
            font=("Segoe UI", max(8, u_sz - 1), "bold"),
            relief="flat",
            bd=1,
            cursor="hand2",
            command=lambda: self._switch_dock_tab("search"),
        )
        self.btn_tab_search.pack(side="left", padx=(2, 2))

        self.btn_tab_files = tk.Button(
            self.dock_tab_bar,
            text="Opened Files",
            font=("Segoe UI", max(8, u_sz - 1), "bold"),
            relief="flat",
            bd=1,
            cursor="hand2",
            command=lambda: self._switch_dock_tab("files"),
        )
        self.btn_tab_files.pack(side="left", padx=(2, 2))

        self.btn_dock_pin = ttk.Button(
            self.dock_tab_bar,
            text="📌",
            style="Small.TButton",
            command=self._toggle_dock_collapse,
            width=3,
        )
        self.btn_dock_pin.pack(side="right", padx=(2, 2))

        # --- TAB 1: Search Results ---
        self.tab_search_frame = self._tag_role(tk.Frame(self.left_frame, bg=t["bg_panel"]), "panel")

        left_header = self._tag_role(tk.Frame(self.tab_search_frame, bg=t["bg_panel"]), "panel")
        left_header.pack(fill="x", padx=6, pady=(4, 4))
        self.lbl_results_title = self._tag_role(
            tk.Label(
                left_header,
                text="Search Results (0 matches)",
                font=("Segoe UI", u_sz, "bold"),
                bg=t["bg_panel"],
                fg=t["misora_pink"],
                anchor="w"
            ),
            "label_accent"
        )
        self.lbl_results_title.pack(side="left", fill="x", expand=True)

        btn_clear_res = ttk.Button(left_header, text="Clear", style="Small.TButton", command=self.on_clear_search)
        btn_clear_res.pack(side="right")

        self.tree_container = self._tag_role(tk.Frame(self.tab_search_frame, bg=t["bg_editor"], bd=1, relief="solid"), "editor_box")
        self.tree_container.pack(fill="both", expand=True, padx=4, pady=(0, 6))
        self.tree_container.pack_propagate(False)

        res_scroll_y = tk.Scrollbar(self.tree_container, orient="vertical")
        res_scroll_y.pack(side="right", fill="y")
        res_scroll_x = tk.Scrollbar(self.tree_container, orient="horizontal")
        res_scroll_x.pack(side="bottom", fill="x")

        self.txt_results = tk.Text(
            self.tree_container,
            wrap="none",
            font=("Segoe UI", u_sz),
            bg=t["bg_editor"],
            fg=t["fg_text"],
            insertwidth=0,
            cursor="arrow",
            padx=6,
            pady=4,
            bd=0,
            relief="flat",
            exportselection=False,
            state="disabled",
            yscrollcommand=res_scroll_y.set,
            xscrollcommand=res_scroll_x.set,
        )
        self.txt_results.pack(side="left", fill="both", expand=True)
        res_scroll_y.config(command=self.txt_results.yview)
        res_scroll_x.config(command=self.txt_results.xview)

        self.txt_results.tag_configure(
            "file_header",
            font=("Segoe UI", u_sz, "bold"),
            foreground=t["misora_pink"],
            spacing1=4,
            spacing3=2,
        )
        self.txt_results.tag_configure(
            "box_badge",
            font=("Consolas", max(8, u_sz - 1), "bold"),
            foreground=t["accent_blue"],
        )
        self.txt_results.tag_configure(
            "speaker_tag",
            font=("Segoe UI", u_sz, "bold"),
            foreground=t["fg_text"],
        )
        self.txt_results.tag_configure(
            "selected_row",
            background=t["highlight_bg"],
        )
        self.txt_results.tag_configure(
            "match_hl",
            background=t["misora_pink"],
            foreground=best_contrast_fg(t["misora_pink"]),
            font=("Segoe UI", u_sz, "bold"),
        )
        self.txt_results.tag_raise("match_hl")

        self.txt_results.bind("<Button-1>", self._on_results_click)
        self.txt_results.bind("<Button-3>", self._on_results_right_click)
        self.txt_results.bind("<Up>", lambda e: self._on_results_step(-1))
        self.txt_results.bind("<Down>", lambda e: self._on_results_step(1))

        # --- TAB 2: Opened Files Cache ---
        self.tab_files_frame = self._tag_role(tk.Frame(self.left_frame, bg=t["bg_panel"]), "panel")

        files_header = self._tag_role(tk.Frame(self.tab_files_frame, bg=t["bg_panel"]), "panel")
        files_header.pack(fill="x", padx=6, pady=(4, 4))
        self.lbl_files_title = self._tag_role(
            tk.Label(
                files_header,
                text="Opened Files (0)",
                font=("Segoe UI", u_sz, "bold"),
                bg=t["bg_panel"],
                fg=t["misora_pink"],
                anchor="w"
            ),
            "label_accent"
        )
        self.lbl_files_title.pack(side="left", fill="x", expand=True)

        btn_open_more = ttk.Button(files_header, text="Open...", style="Small.TButton", command=self.on_open_file)
        btn_open_more.pack(side="right")

        self.files_container = self._tag_role(tk.Frame(self.tab_files_frame, bg=t["bg_editor"], bd=1, relief="solid"), "editor_box")
        self.files_container.pack(fill="both", expand=True, padx=4, pady=(0, 6))
        self.files_container.pack_propagate(False)

        files_scroll_y = tk.Scrollbar(self.files_container, orient="vertical")
        files_scroll_y.pack(side="right", fill="y")
        files_scroll_x = tk.Scrollbar(self.files_container, orient="horizontal")
        files_scroll_x.pack(side="bottom", fill="x")

        self.txt_opened_files = tk.Text(
            self.files_container,
            wrap="none",
            font=("Segoe UI", u_sz),
            bg=t["bg_editor"],
            fg=t["fg_text"],
            insertwidth=0,
            cursor="arrow",
            padx=6,
            pady=4,
            bd=0,
            relief="flat",
            exportselection=False,
            state="disabled",
            yscrollcommand=files_scroll_y.set,
            xscrollcommand=files_scroll_x.set,
        )
        self.txt_opened_files.pack(side="left", fill="both", expand=True)
        files_scroll_y.config(command=self.txt_opened_files.yview)
        files_scroll_x.config(command=self.txt_opened_files.xview)

        self.txt_opened_files.tag_configure("file_active", font=("Segoe UI", u_sz, "bold"), foreground=t["misora_pink"], background=t["highlight_bg"])
        self.txt_opened_files.tag_configure("file_dirty", font=("Segoe UI", u_sz, "bold"), foreground=t["accent_yellow"])
        self.txt_opened_files.tag_configure("file_normal", font=("Segoe UI", u_sz), foreground=t["fg_text"])
        self.txt_opened_files.tag_configure("file_dim", font=("Segoe UI", max(8, u_sz - 1)), foreground=t["fg_muted"])
        self.txt_opened_files.tag_configure("file_close", font=("Consolas", max(8, u_sz - 1), "bold"), foreground=t["misora_pink"])

        self.txt_opened_files.bind("<Button-1>", self._on_opened_files_click)
        self.txt_opened_files.bind("<Button-3>", self._on_opened_files_right_click)

        # Show initial dock tab
        self._switch_dock_tab(self._left_dock_tab)

        # CENTER PANEL: Dual-View Editor (Vertical Splitter)
        right_frame = self._tag_role(tk.Frame(self.h_paned, bg=t["bg_panel"]), "panel")
        self.h_paned.add(right_frame, minsize=420, stretch="always")

        self.v_paned = self._tag_role(
            tk.PanedWindow(
                right_frame,
                orient=tk.VERTICAL,
                bg=t["border"],
                sashwidth=6,
                sashrelief="flat",
                opaqueresize=True
            ),
            "sash"
        )
        self.v_paned.pack(fill="both", expand=True)

        # TOP VIEW: Game Display View (Page-by-Page OR Continuous Dialog Stream)
        top_view = self._tag_role(tk.Frame(self.v_paned, bg=t["bg_panel"]), "panel")
        self.v_paned.add(top_view, minsize=140, height=400, stretch="always")

        gd_header = self._tag_role(tk.Frame(top_view, bg=t["bg_panel"]), "panel")
        gd_header.pack(fill="x", padx=8, pady=(6, 4))

        self.lbl_gd_title = self._tag_role(
            tk.Label(
                gd_header,
                text="GAME DISPLAY VIEW (Clean Dialogue)",
                font=("Segoe UI", u_sz, "bold"),
                bg=t["bg_panel"],
                fg=t["misora_pink"]
            ),
            "label_accent"
        )
        self.lbl_gd_title.pack(side="left")

        # (#5 & #6: Customize and NGUI Glossary removed from header; distinct Nav buttons #4)
        self.lbl_box_counter = self._tag_role(
            tk.Label(gd_header, text="Box: 0 / 0", font=("Segoe UI", u_sz), bg=t["bg_panel"], fg=t["fg_muted"]),
            "label_muted"
        )
        self.lbl_box_counter.pack(side="right", padx=(8, 0))

        btn_next = ttk.Button(gd_header, text="Next >", style="Nav.TButton", command=self.on_next_box)
        btn_next.pack(side="right", padx=(3, 0))
        btn_prev = ttk.Button(gd_header, text="< Prev", style="Nav.TButton", command=self.on_prev_box)
        btn_prev.pack(side="right", padx=(6, 2))

        cb_cont = self._tag_role(
            tk.Checkbutton(
                gd_header,
                text="Continuous View",
                variable=self.var_continuous_view,
                command=self._on_toggle_continuous_view,
                font=("Segoe UI", max(8, u_sz - 1), "bold"),
                bg=t["bg_panel"],
                fg=t["fg_text"],
                selectcolor=t["bg_dark"],
                activebackground=t["bg_panel"],
                activeforeground=t["misora_pink"],
                cursor="hand2"
            ),
            "check_accent"
        )
        cb_cont.pack(side="right", padx=(6, 6))

        # (#7: Single Combined Row for Speaker + Compact NGUI Ribbon)
        speaker_ribbon_row = self._tag_role(tk.Frame(top_view, bg=t["bg_panel"]), "panel")
        speaker_ribbon_row.pack(fill="x", padx=10, pady=(2, 6))

        self._tag_role(
            tk.Label(speaker_ribbon_row, text="Speaker:", bg=t["bg_panel"], fg=t["fg_muted"]),
            "label_muted"
        ).pack(side="left", padx=(0, 4))

        self.speaker_var = tk.StringVar()
        self.entry_speaker = self._tag_role(
            tk.Entry(
                speaker_ribbon_row,
                textvariable=self.speaker_var,
                font=(d_fam, max(9, d_sz - 1), "bold"),
                bg=t["bg_editor"],
                fg=t["fg_text"],
                insertbackground=t["misora_pink"],
                selectbackground=t["highlight_bg"],
                selectforeground=t["misora_pink"],
                bd=1,
                relief="solid",
                width=18
            ),
            "entry_speaker"
        )
        self.entry_speaker.pack(side="left")
        self.entry_speaker.bind("<KeyRelease>", lambda e: self._on_speaker_edited())

        self.lbl_voice_cue = self._tag_role(
            tk.Label(speaker_ribbon_row, text="", bg=t["bg_panel"], fg=t["accent_blue"], font=("Segoe UI", max(8, u_sz - 1))),
            "label_voice"
        )
        self.lbl_voice_cue.pack(side="left", padx=(6, 6))

        # Compact NGUI Ribbon docked on the right side of the Speaker row (#7)
        ribbon = self._tag_role(
            tk.Frame(speaker_ribbon_row, bg=t["bg_editor"], bd=1, relief="solid", highlightbackground=t["border"], highlightthickness=1),
            "ribbon"
        )
        ribbon.pack(side="right", padx=(4, 0))

        # Prominent Color / Grad / + Ruby controls (#7)
        self.btn_ribbon_swatch = tk.Button(
            ribbon,
            width=2,
            bg=self._active_ngui_color,
            activebackground=self._active_ngui_color,
            relief="solid",
            bd=1,
            cursor="hand2",
            command=self.on_open_color_picker,
        )
        self.btn_ribbon_swatch.pack(side="left", padx=(4, 2), pady=2)

        ttk.Button(
            ribbon,
            text="Color",
            style="RibbonPrimary.TButton",
            command=self._apply_active_ribbon_color,
        ).pack(side="left", padx=1, pady=2)

        ttk.Button(
            ribbon,
            text="Grad",
            style="RibbonPrimary.TButton",
            command=self._apply_active_ribbon_gradient,
        ).pack(side="left", padx=1, pady=2)

        ttk.Button(
            ribbon,
            text="+ Ruby",
            style="RibbonPrimary.TButton",
            command=self.on_insert_ruby,
        ).pack(side="left", padx=(1, 2), pady=2)

        ttk.Button(
            ribbon,
            text="[-]",
            style="Ribbon.TButton",
            command=lambda: self.apply_ngui_wrapper("[-]", ""),
        ).pack(side="left", padx=1, pady=2)

        ttk.Button(
            ribbon,
            text="{player}",
            style="Ribbon.TButton",
            command=self.on_insert_playername,
        ).pack(side="left", padx=1, pady=2)

        self._tag_role(tk.Label(ribbon, text="|", bg=t["bg_editor"], fg=t["border"]), "label_ribbon_sep").pack(side="left", padx=3)

        # Tiny mini-buttons for B, I, U, S, Sub, Sup (#7)
        mini_style_buttons = [
            ("B", "[b]", "[/b]"),
            ("I", "[i]", "[/i]"),
            ("U", "[u]", "[/u]"),
            ("S", "[s]", "[/s]"),
            ("Sub", "[sub]", "[/sub]"),
            ("Sup", "[sup]", "[/sup]"),
        ]
        for lbl, o_tag, c_tag in mini_style_buttons:
            ttk.Button(
                ribbon,
                text=lbl,
                style="RibbonMini.TButton",
                command=lambda ot=o_tag, ct=c_tag: self.apply_ngui_wrapper(ot, ct),
            ).pack(side="left", padx=1, pady=2)

        self._tag_role(tk.Label(ribbon, text="|", bg=t["bg_editor"], fg=t["border"]), "label_ribbon_sep").pack(side="left", padx=3)

        cb_compiled = self._tag_role(
            tk.Checkbutton(
                ribbon,
                text="Compiled",
                variable=self.var_preview_compiled,
                command=self._on_toggle_preview_compiled,
                font=("Segoe UI", 8, "bold"),
                bg=t["bg_editor"],
                fg=t["misora_pink"],
                selectcolor=t["bg_panel"],
                activebackground=t["bg_editor"],
                activeforeground=t["misora_pink"],
                cursor="hand2",
            ),
            "check_ribbon"
        )
        cb_compiled.pack(side="left", padx=(2, 4), pady=2)

        # VIEW 1: Bounded Scrollable Page-by-Page Viewport
        self.gd_scroll_wrap = self._tag_role(tk.Frame(top_view, bg=t["bg_panel"]), "panel")
        self.gd_scroll_wrap.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        gd_vscroll = tk.Scrollbar(self.gd_scroll_wrap, orient="vertical")
        gd_vscroll.pack(side="right", fill="y")

        self.gd_canvas = self._tag_role(
            tk.Canvas(
                self.gd_scroll_wrap,
                bg=t["bg_panel"],
                highlightthickness=0,
                bd=0,
                yscrollcommand=gd_vscroll.set,
            ),
            "panel"
        )
        self.gd_canvas.pack(side="left", fill="both", expand=True)
        gd_vscroll.config(command=self._on_gd_scrollbar)

        self.gd_inner = self._tag_role(tk.Frame(self.gd_canvas, bg=t["bg_panel"]), "panel")
        self._gd_canvas_win = self.gd_canvas.create_window((0, 0), window=self.gd_inner, anchor="nw")

        self.gd_inner.bind("<Configure>", self._sync_gd_scroll_bounds)
        self.gd_canvas.bind("<Configure>", self._sync_gd_scroll_bounds)
        self.gd_canvas.bind("<MouseWheel>", self._on_gd_mousewheel)
        self.gd_inner.bind("<MouseWheel>", self._on_gd_mousewheel)

        text_container = self._tag_role(tk.Frame(self.gd_inner, bg=t["bg_panel"]), "panel")
        text_container.pack(fill="both", expand=True, padx=6, pady=(2, 10))

        self.txt_dialogue = tk.Text(
            text_container,
            wrap="word",
            height=7,
            font=(d_fam, d_sz),
            bg=t["bg_editor"],
            fg=t["fg_text"],
            insertbackground=t["misora_pink"],
            selectbackground=t["highlight_bg"],
            selectforeground=t["misora_pink"],
            padx=10,
            pady=8,
            spacing1=3,
            spacing3=3,
            bd=1,
            relief="solid",
        )
        self.txt_dialogue.pack(fill="both", expand=True)
        self._configure_editor_rich_tags(self.txt_dialogue, d_fam, d_sz)
        self.txt_dialogue.bind("<KeyRelease>", lambda e: self._on_dialogue_edited())
        self.txt_dialogue.bind("<MouseWheel>", self._on_gd_mousewheel)
        self.txt_dialogue.bind("<Control-b>", lambda e: self._shortcut_wrap("[b]", "[/b]"))
        self.txt_dialogue.bind("<Control-i>", lambda e: self._shortcut_wrap("[i]", "[/i]"))
        self.txt_dialogue.bind("<Control-u>", lambda e: self._shortcut_wrap("[u]", "[/u]"))

        # VIEW 2: Continuous Script Dialog Stream
        self.continuous_wrap = self._tag_role(tk.Frame(top_view, bg=t["bg_panel"]), "panel")

        cont_scroll_y = tk.Scrollbar(self.continuous_wrap, orient="vertical")
        cont_scroll_y.pack(side="right", fill="y")

        self.txt_continuous = tk.Text(
            self.continuous_wrap,
            wrap="word",
            undo=False,
            font=(d_fam, d_sz),
            bg=t["bg_editor"],
            fg=t["fg_text"],
            insertbackground=t["misora_pink"],
            selectbackground=t["highlight_bg"],
            selectforeground=t["misora_pink"],
            padx=14,
            pady=10,
            spacing1=3,
            spacing3=4,
            bd=1,
            relief="solid",
            yscrollcommand=cont_scroll_y.set,
        )
        self.txt_continuous.pack(side="left", fill="both", expand=True)
        cont_scroll_y.config(command=self.txt_continuous.yview)

        self.txt_continuous.tag_configure(
            "cont_divider",
            foreground=t["border"],
            font=("Consolas", max(7, d_sz - 3)),
            spacing1=4,
            spacing3=2,
        )
        self.txt_continuous.tag_configure(
            "cont_badge",
            foreground=t["misora_pink"],
            font=("Consolas", max(8, d_sz - 2), "bold"),
            spacing1=2,
            spacing3=4,
        )
        self.txt_continuous.tag_configure(
            "cont_speaker",
            foreground=t["fg_text"],
            font=(d_fam, max(9, d_sz - 1), "bold"),
            spacing1=2,
            spacing3=4,
        )
        self.txt_continuous.tag_configure(
            "cont_narrator",
            foreground=t["fg_muted"],
            font=(d_fam, max(8, d_sz - 2), "italic"),
            spacing1=2,
            spacing3=4,
        )
        self.txt_continuous.tag_configure(
            "cont_voice",
            foreground=t["accent_blue"],
            font=("Segoe UI", max(8, d_sz - 3)),
            spacing1=2,
            spacing3=4,
        )
        self.txt_continuous.tag_configure(
            "cont_active_header",
            background=t["highlight_bg"],
        )
        self.txt_continuous.tag_configure(
            "cont_body",
            foreground=t["fg_text"],
            font=(d_fam, d_sz),
            lmargin1=14,
            lmargin2=14,
            rmargin=10,
        )
        self._configure_editor_rich_tags(self.txt_continuous, d_fam, d_sz)

        self.txt_continuous.bind("<ButtonRelease-1>", self._on_continuous_cursor_moved)
        self.txt_continuous.bind("<Key>", self._on_continuous_key_guard)
        self.txt_continuous.bind("<KeyRelease>", self._on_continuous_key_release)
        self.txt_continuous.bind("<<Paste>>", self._on_continuous_paste_guard)
        self.txt_continuous.bind("<<Cut>>", self._on_continuous_cut_guard)
        self.txt_continuous.bind("<Control-b>", lambda e: self._shortcut_wrap("[b]", "[/b]"))
        self.txt_continuous.bind("<Control-i>", lambda e: self._shortcut_wrap("[i]", "[/i]"))
        self.txt_continuous.bind("<Control-u>", lambda e: self._shortcut_wrap("[u]", "[/u]"))

        # BOTTOM VIEW: Raw AST Script View (Technical Records)
        bottom_view = self._tag_role(tk.Frame(self.v_paned, bg=t["bg_panel"]), "panel")
        self.v_paned.add(bottom_view, minsize=80, height=200, stretch="never")

        raw_header = self._tag_role(tk.Frame(bottom_view, bg=t["bg_panel"]), "panel")
        raw_header.pack(fill="x", padx=8, pady=4)
        self._tag_role(
            tk.Label(raw_header, text="RAW SCRIPT VIEW (Technical AST Records)", font=("Segoe UI", u_sz, "bold"), bg=t["bg_panel"], fg=t["fg_muted"]),
            "label_muted"
        ).pack(side="left")

        raw_container = self._tag_role(tk.Frame(bottom_view, bg=t["bg_panel"]), "panel")
        raw_container.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        raw_scroll_y = tk.Scrollbar(raw_container)
        raw_scroll_y.pack(side="right", fill="y")
        raw_scroll_x = tk.Scrollbar(raw_container, orient="horizontal")
        raw_scroll_x.pack(side="bottom", fill="x")

        self.txt_raw = tk.Text(
            raw_container,
            wrap="none",
            font=("Consolas", r_sz),
            bg=self._shift_hex(t["bg_editor"], -6),
            fg=t["fg_muted"],
            insertbackground=t["misora_pink"],
            padx=8,
            pady=6,
            bd=1,
            relief="solid",
            yscrollcommand=raw_scroll_y.set,
            xscrollcommand=raw_scroll_x.set
        )
        self.txt_raw.pack(fill="both", expand=True)
        raw_scroll_y.config(command=self.txt_raw.yview)
        raw_scroll_x.config(command=self.txt_raw.xview)

    # -------------------------------------------------------------------------
    # Embedded Debug Console Panel (#14)
    # -------------------------------------------------------------------------
    def _build_debug_console(self) -> None:
        t = self.theme
        self.console_panel = self._tag_role(
            tk.Frame(self.outer_v_paned, bg=t["bg_panel"], bd=1, relief="solid"),
            "panel",
        )

        hdr = self._tag_role(tk.Frame(self.console_panel, bg=t["bg_panel"]), "panel")
        hdr.pack(fill="x", padx=8, pady=(4, 2))

        self._tag_role(
            tk.Label(hdr, text="DEBUG CONSOLE", font=("Segoe UI", 9, "bold"), bg=t["bg_panel"], fg=t["misora_pink"]),
            "label_accent",
        ).pack(side="left")

        ttk.Button(hdr, text="✕", style="Small.TButton", command=lambda: self._set_console_visible(False, save=True)).pack(side="right", padx=(4, 0))
        ttk.Button(hdr, text="Copy", style="Small.TButton", command=self._on_copy_console).pack(side="right", padx=2)
        ttk.Button(hdr, text="Clear", style="Small.TButton", command=self._on_clear_console).pack(side="right", padx=2)

        cb_auto = self._tag_role(
            tk.Checkbutton(
                hdr,
                text="Auto-scroll",
                variable=self.var_console_autoscroll,
                bg=t["bg_panel"],
                fg=t["fg_text"],
                selectcolor=t["bg_dark"],
                activebackground=t["bg_panel"],
            ),
            "check_panel",
        )
        cb_auto.pack(side="right", padx=6)

        cb_file = self._tag_role(
            tk.Checkbutton(
                hdr,
                text="Log to File",
                variable=self.var_log_to_file,
                command=self._on_debug_settings_changed,
                bg=t["bg_panel"],
                fg=t["fg_text"],
                selectcolor=t["bg_dark"],
                activebackground=t["bg_panel"],
            ),
            "check_panel",
        )
        cb_file.pack(side="right", padx=6)

        body = self._tag_role(tk.Frame(self.console_panel, bg=t["bg_editor"], bd=1, relief="solid"), "editor_box")
        body.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        y_scr = tk.Scrollbar(body, orient="vertical")
        y_scr.pack(side="right", fill="y")
        x_scr = tk.Scrollbar(body, orient="horizontal")
        x_scr.pack(side="bottom", fill="x")

        self.txt_console = tk.Text(
            body,
            wrap="none",
            height=8,
            font=("Consolas", 9),
            bg=t["bg_editor"],
            fg=t["fg_text"],
            padx=6,
            pady=4,
            bd=0,
            relief="flat",
            state="disabled",
            yscrollcommand=y_scr.set,
            xscrollcommand=x_scr.set,
        )
        self.txt_console.pack(side="left", fill="both", expand=True)
        y_scr.config(command=self.txt_console.yview)
        x_scr.config(command=self.txt_console.xview)
        self._apply_console_theme()

    def _apply_console_theme(self) -> None:
        t = self.theme
        editor_fg = best_contrast_fg(t["bg_editor"], t["fg_text"], "#ffffff")
        self.txt_console.configure(bg=t["bg_editor"], fg=editor_fg)
        self.txt_console.tag_configure("lvl_Debug", foreground=t["fg_muted"])
        self.txt_console.tag_configure("lvl_Info", foreground=editor_fg)
        self.txt_console.tag_configure("lvl_Warning", foreground=t["accent_yellow"], font=("Consolas", 9, "bold"))
        self.txt_console.tag_configure(
            "lvl_Error",
            foreground="#d93848" if not self._is_dark_color(t["bg_editor"]) else "#ff6b7a",
            font=("Consolas", 9, "bold"),
        )

    def _set_console_visible(self, visible: bool, save: bool = True) -> None:
        self._console_visible = bool(visible)
        self.var_console_visible.set(self._console_visible)
        panes = self.outer_v_paned.panes()
        panel_str = str(self.console_panel)
        if self._console_visible:
            if panel_str not in panes:
                self.outer_v_paned.add(self.console_panel, minsize=100, height=170, stretch="never")
                self._rerender_console_from_history()
        else:
            if panel_str in panes:
                self.outer_v_paned.forget(self.console_panel)
        if save:
            self._save_user_prefs(silent=True)

    def _on_toggle_console_menu(self) -> None:
        self._set_console_visible(self.var_console_visible.get(), save=True)

    def _toggle_console_shortcut(self) -> None:
        self._set_console_visible(not self._console_visible, save=True)

    def _on_debug_settings_changed(self) -> None:
        cats = {cat: (True if cat == ALWAYS_ON_CATEGORY else bool(var.get())) for cat, var in self.var_log_categories.items()}
        self.logger.configure(
            level_name=self.var_log_level.get(),
            log_to_file=bool(self.var_log_to_file.get()),
            categories=cats,
        )
        self._save_user_prefs(silent=True)
        self.logger.info(
            "UI / Theme / Config",
            f"Debug settings updated (level={self.var_log_level.get()}, log_to_file={self.var_log_to_file.get()})",
        )

    def _sync_debug_menu_states(self) -> None:
        exists_state = "normal" if DEBUG_LOG_PATH.is_file() else "disabled"
        try:
            self.debug_menu.entryconfig(self._idx_open_log, state=exists_state)
            self.debug_menu.entryconfig(self._idx_clear_log, state=exists_state)
        except Exception:
            pass

    def _on_open_debug_log_file(self) -> None:
        if not DEBUG_LOG_PATH.is_file():
            messagebox.showinfo("Debug Log", "Debug log file does not exist yet.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(DEBUG_LOG_PATH))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(DEBUG_LOG_PATH)])
        except Exception as exc:
            self.logger.error("Errors & Exceptions", f"Failed to open log file: {exc}")

    def _on_clear_debug_log_file(self) -> None:
        if self.logger.clear_log_file():
            self.logger.info("UI / Theme / Config", f"Cleared debug log file: {DEBUG_LOG_PATH}")

    def _on_clear_console(self) -> None:
        self.logger.clear_history()
        self.txt_console.config(state="normal")
        self.txt_console.delete("1.0", tk.END)
        self.txt_console.config(state="disabled")

    def _on_copy_console(self) -> None:
        content = self.txt_console.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(content)
        self.lbl_status.config(text="Copied Debug Console output to clipboard.")

    def _rerender_console_from_history(self) -> None:
        entries = self.logger.get_history()
        self.logger.drain_ui_entries()
        self.txt_console.config(state="normal")
        self.txt_console.delete("1.0", tk.END)
        for entry in entries:
            self.txt_console.insert(tk.END, entry.format_line() + "\n", (f"lvl_{entry.level}",))
        if self.var_console_autoscroll.get():
            self.txt_console.see(tk.END)
        self.txt_console.config(state="disabled")

    def _flush_log_console(self) -> None:
        entries = self.logger.drain_ui_entries()
        if entries and self._console_visible and hasattr(self, "txt_console"):
            self.txt_console.config(state="normal")
            for entry in entries:
                self.txt_console.insert(tk.END, entry.format_line() + "\n", (f"lvl_{entry.level}",))
            line_count = int(self.txt_console.index("end-1c").split(".")[0])
            if line_count > 2500:
                self.txt_console.delete("1.0", f"{line_count - 2000}.0")
            if self.var_console_autoscroll.get():
                self.txt_console.see(tk.END)
            self.txt_console.config(state="disabled")
        self.after(120, self._flush_log_console)

    # -------------------------------------------------------------------------
    # NGUI Attributes Ribbon Actions & Compiled Preview Compiler
    # -------------------------------------------------------------------------
    def _shortcut_wrap(self, open_tag: str, close_tag: str) -> str:
        self.apply_ngui_wrapper(open_tag, close_tag)
        return "break"

    def _set_ribbon_colors(self, primary_hex: str, secondary_hex: str) -> None:
        if HEX_COLOR_RE.match(primary_hex):
            self._active_ngui_color = primary_hex.lower()
            if hasattr(self, "btn_ribbon_swatch"):
                self.btn_ribbon_swatch.configure(
                    bg=self._active_ngui_color,
                    activebackground=self._active_ngui_color,
                )
        if HEX_COLOR_RE.match(secondary_hex):
            self._active_ngui_grad_end = secondary_hex.lower()

    def _apply_active_ribbon_color(self) -> None:
        code = self._active_ngui_color[1:].upper()
        self.apply_ngui_wrapper(f"[{code}]", "[-]")

    def _apply_active_ribbon_gradient(self) -> None:
        c0 = self._active_ngui_color[1:].upper()
        c1 = self._active_ngui_grad_end[1:].upper()
        self.apply_ngui_wrapper(f"[{c0}-{c1}]", "[-]")

    def on_open_color_picker(self) -> None:
        if self._color_picker_win is not None and self._color_picker_win.winfo_exists():
            self._color_picker_win.lift()
            self._color_picker_win.focus_set()
            return
        self._color_picker_win = NguiColorPickerPopup(
            self,
            primary_hex=self._active_ngui_color,
            secondary_hex=self._active_ngui_grad_end,
        )

    def apply_ngui_wrapper(self, open_tag: str, close_tag: str, default_inner: str = "") -> None:
        """Ensure Raw Edit mode is active, then wrap selection or insert NGUI tags at caret."""
        if self.var_preview_compiled.get():
            self.var_preview_compiled.set(False)
            self._update_views()
        self._insert_text_wrapper(open_tag, close_tag, default_inner=default_inner)

    def _on_toggle_preview_compiled(self) -> None:
        """Toggle between editable raw NGUI tags and compiled visual preview."""
        if self.var_preview_compiled.get():
            self.lbl_status.config(
                text="Compiled Attribute Preview ON (read-only) — uncheck 'Compiled' to edit raw tags."
            )
        else:
            self.lbl_status.config(
                text="Raw NGUI Tag Edit Mode active."
            )
        self._update_views()

    def _get_or_create_compiled_style_tag(
        self,
        widget: tk.Text,
        bold: bool,
        italic: bool,
        underline: bool,
        strike: bool,
        sub_mode: int,
        fg_color: Optional[str],
    ) -> str:
        """Return a cached Tkinter tag name configured with the requested compiled NGUI style."""
        d_fam = self.prefs["dialogue_font_family"]
        d_sz = int(self.prefs["dialogue_font_size"])
        eff_sz = max(7, d_sz - 2) if sub_mode != 0 else d_sz
        eff_offset = -3 if sub_mode < 0 else (4 if sub_mode > 0 else 0)
        color_key = fg_color.lower() if fg_color else "default"
        tag_name = f"cstyle_{int(bold)}_{int(italic)}_{int(underline)}_{int(strike)}_{sub_mode}_{color_key}_{d_fam}_{d_sz}"

        if tag_name not in widget.tag_names():
            weight = "bold" if bold else "normal"
            slant = "italic" if italic else "roman"
            font_tuple = (d_fam, eff_sz, weight, slant)
            cfg: Dict[str, Any] = {
                "font": font_tuple,
                "underline": underline,
                "overstrike": strike,
                "offset": eff_offset,
            }
            if fg_color:
                cfg["foreground"] = fg_color
            widget.tag_configure(tag_name, **cfg)
        return tag_name

    def _insert_compiled_ngui_text(
        self,
        widget: tk.Text,
        insert_pos: str,
        raw_text: str,
        base_tags: Tuple[str, ...] = (),
    ) -> None:
        """Parse NGUI/Priconne markup in `raw_text` and insert compiled rich text into `widget`."""
        mark_name = f"_compile_ins_{id(widget)}"
        widget.mark_set(mark_name, insert_pos)
        widget.mark_gravity(mark_name, tk.RIGHT)

        bold = False
        italic = False
        underline = False
        strike = False
        sub_mode = 0
        color_stack: List[Tuple[str, Optional[str]]] = []

        def emit_styled_run(chunk: str) -> None:
            if not chunk:
                return
            chunk = chunk.replace("\\n", "\n")
            if not color_stack:
                st = self._get_or_create_compiled_style_tag(
                    widget, bold, italic, underline, strike, sub_mode, None
                )
                widget.insert(mark_name, chunk, base_tags + (st,))
                return

            top_hex, bot_hex = color_stack[-1]
            if not bot_hex or len(chunk) <= 1:
                st = self._get_or_create_compiled_style_tag(
                    widget, bold, italic, underline, strike, sub_mode, top_hex
                )
                widget.insert(mark_name, chunk, base_tags + (st,))
                return

            r1, g1, b1 = int(top_hex[1:3], 16), int(top_hex[3:5], 16), int(top_hex[5:7], 16)
            r2, g2, b2 = int(bot_hex[1:3], 16), int(bot_hex[3:5], 16), int(bot_hex[5:7], 16)
            denom = max(1, len(chunk) - 1)
            for idx, ch in enumerate(chunk):
                ratio = idx / denom
                ri = int(round(r1 + (r2 - r1) * ratio))
                gi = int(round(g1 + (g2 - g1) * ratio))
                bi = int(round(b1 + (b2 - b1) * ratio))
                step_hex = f"#{ri:02x}{gi:02x}{bi:02x}"
                st = self._get_or_create_compiled_style_tag(
                    widget, bold, italic, underline, strike, sub_mode, step_hex
                )
                widget.insert(mark_name, ch, base_tags + (st,))

        last_idx = 0
        try:
            for m in NGUI_TOKEN_RE.finditer(raw_text):
                if m.start() > last_idx:
                    emit_styled_run(raw_text[last_idx:m.start()])

                tok = m.group(0)
                tok_low = tok.lower()

                if m.group(2) is not None:
                    ruby_txt = m.group(2).replace("\\n", "\n")
                    base_txt = m.group(3)
                    emit_styled_run(base_txt)
                    if ruby_txt:
                        widget.insert(mark_name, ruby_txt, base_tags + ("compiled_ruby",))
                elif tok_low == "[b]":
                    bold = True
                elif tok_low == "[/b]":
                    bold = False
                elif tok_low == "[i]":
                    italic = True
                elif tok_low == "[/i]":
                    italic = False
                elif tok_low == "[u]":
                    underline = True
                elif tok_low == "[/u]":
                    underline = False
                elif tok_low == "[s]":
                    strike = True
                elif tok_low == "[/s]":
                    strike = False
                elif tok_low == "[sub]":
                    sub_mode = -1
                elif tok_low == "[/sub]":
                    sub_mode = 0
                elif tok_low == "[sup]":
                    sub_mode = 1
                elif tok_low == "[/sup]":
                    sub_mode = 0
                elif tok_low == "[/]":
                    bold = False
                    italic = False
                    underline = False
                    strike = False
                    sub_mode = 0
                elif tok_low in ("[c]", "[/c]", "[/url]") or tok_low.startswith("[url="):
                    pass
                elif tok == "[-]":
                    if color_stack:
                        color_stack.pop()
                elif m.group(4) is not None:
                    c1 = "#" + m.group(4).lower()[:6]
                    c2 = ("#" + m.group(5).lower()[:6]) if m.group(5) else None
                    color_stack.append((c1, c2))
                elif tok in ("{playername}", "{0}"):
                    widget.insert(mark_name, "{playername}", base_tags + ("compiled_player",))
                else:
                    emit_styled_run(tok)

                last_idx = m.end()

            if last_idx < len(raw_text):
                emit_styled_run(raw_text[last_idx:])
        finally:
            try:
                widget.mark_unset(mark_name)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Embedded Side Drawer: Customization & NGUI Glossary Help
    # -------------------------------------------------------------------------
    def _build_side_drawer(self) -> None:
        """Build dockable right-hand side panel for Display Customization & NGUI Glossary."""
        t = self.theme
        self.side_drawer = self._tag_role(tk.Frame(self.h_paned, bg=t["bg_panel"]), "panel")

        drawer_top = self._tag_role(tk.Frame(self.side_drawer, bg=t["bg_panel"]), "panel")
        drawer_top.pack(fill="x", padx=6, pady=(6, 4))

        self.btn_tab_customize = ttk.Button(
            drawer_top,
            text="Customize",
            style="Pink.TButton",
            command=lambda: self._switch_side_drawer_tab("customize"),
        )
        self.btn_tab_customize.pack(side="left", padx=(0, 4))

        self.btn_tab_glossary = ttk.Button(
            drawer_top,
            text="NGUI Glossary",
            style="TButton",
            command=lambda: self._switch_side_drawer_tab("glossary"),
        )
        self.btn_tab_glossary.pack(side="left")

        btn_close_drawer = ttk.Button(
            drawer_top,
            text="✕",
            style="Small.TButton",
            command=self._close_side_drawer,
        )
        btn_close_drawer.pack(side="right")

        self.tab_customize_frame = self._tag_role(tk.Frame(self.side_drawer, bg=t["bg_panel"]), "panel")
        self._build_customize_tab(self.tab_customize_frame)

        self.tab_glossary_frame = self._tag_role(tk.Frame(self.side_drawer, bg=t["bg_panel"]), "panel")
        self._build_glossary_tab(self.tab_glossary_frame)

        self._switch_side_drawer_tab("customize")

    def _build_customize_tab(self, parent: tk.Frame) -> None:
        """Populate font size controls, theme presets, and custom color pickers."""
        t = self.theme
        wrap = self._tag_role(tk.Frame(parent, bg=t["bg_editor"], bd=1, relief="solid"), "editor_box")
        wrap.pack(fill="both", expand=True, padx=4, pady=(0, 6))

        canvas = self._tag_role(tk.Canvas(wrap, bg=t["bg_panel"], highlightthickness=0, bd=0), "panel")
        vscroll = tk.Scrollbar(wrap, orient="vertical", command=canvas.yview)
        vscroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=vscroll.set)

        body = self._tag_role(tk.Frame(canvas, bg=t["bg_panel"]), "panel")
        win_id = canvas.create_window((0, 0), window=body, anchor="nw")

        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=max(220, e.width)))

        self._tag_role(
            tk.Label(body, text="FONT & DISPLAY PREFERENCES", font=("Segoe UI", 9, "bold"), bg=t["bg_panel"], fg=t["misora_pink"]),
            "label_accent"
        ).pack(anchor="w", padx=8, pady=(8, 6))

        fam_row = self._tag_role(tk.Frame(body, bg=t["bg_panel"]), "panel")
        fam_row.pack(fill="x", padx=8, pady=3)
        self._tag_role(tk.Label(fam_row, text="Dialogue Font:", bg=t["bg_panel"], fg=t["fg_text"]), "label_panel").pack(side="left")

        self.var_font_family = tk.StringVar(value=self.prefs["dialogue_font_family"])
        cb_font = ttk.Combobox(
            fam_row,
            textvariable=self.var_font_family,
            values=["Segoe UI", "Meiryo UI", "Yu Gothic UI", "Consolas", "Arial"],
            state="readonly",
            width=15,
        )
        cb_font.pack(side="right")
        cb_font.bind("<<ComboboxSelected>>", lambda _e: self._on_font_pref_changed())

        self.var_dlg_font_sz = tk.IntVar(value=int(self.prefs["dialogue_font_size"]))
        self.var_raw_font_sz = tk.IntVar(value=int(self.prefs["raw_font_size"]))
        self.var_ui_font_sz = tk.IntVar(value=int(self.prefs["ui_font_size"]))

        font_rows = [
            ("Dialogue Size (pt):", self.var_dlg_font_sz, 8, 28),
            ("Raw Script Size (pt):", self.var_raw_font_sz, 7, 22),
            ("UI & Search Size (pt):", self.var_ui_font_sz, 8, 16),
        ]
        for label_txt, int_var, min_v, max_v in font_rows:
            r = self._tag_role(tk.Frame(body, bg=t["bg_panel"]), "panel")
            r.pack(fill="x", padx=8, pady=3)
            self._tag_role(tk.Label(r, text=label_txt, bg=t["bg_panel"], fg=t["fg_text"]), "label_panel").pack(side="left")
            sb = tk.Spinbox(
                r,
                from_=min_v,
                to=max_v,
                textvariable=int_var,
                width=6,
                font=("Consolas", 9),
                bg=t["bg_editor"],
                fg=t["fg_text"],
                buttonbackground=t["bg_panel"],
                relief="solid",
                bd=1,
                command=self._on_font_pref_changed,
            )
            sb.pack(side="right")
            sb.bind("<Return>", lambda _e: self._on_font_pref_changed())
            sb.bind("<FocusOut>", lambda _e: self._on_font_pref_changed())

        self._tag_role(
            tk.Label(body, text="THEME PRESETS", font=("Segoe UI", 9, "bold"), bg=t["bg_panel"], fg=t["misora_pink"]),
            "label_accent"
        ).pack(anchor="w", padx=8, pady=(12, 4))

        preset_row = self._tag_role(tk.Frame(body, bg=t["bg_panel"]), "panel")
        preset_row.pack(fill="x", padx=8, pady=3)
        self.var_preset = tk.StringVar(value=self._detect_active_preset_name())
        cb_preset = ttk.Combobox(
            preset_row,
            textvariable=self.var_preset,
            values=list(THEME_PRESETS.keys()),
            state="readonly",
            width=22,
        )
        cb_preset.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(
            preset_row,
            text="Apply",
            style="Small.TButton",
            command=lambda: self._apply_theme_preset(self.var_preset.get()),
        ).pack(side="right")

        self._tag_role(
            tk.Label(body, text="CUSTOM WINDOW COLORS", font=("Segoe UI", 9, "bold"), bg=t["bg_panel"], fg=t["misora_pink"]),
            "label_accent"
        ).pack(anchor="w", padx=8, pady=(12, 4))

        color_specs = [
            ("bg_dark", "Window Background"),
            ("bg_panel", "Panel Surface"),
            ("bg_editor", "Editor Surface"),
            ("misora_pink", "Primary Accent"),
            ("fg_text", "Primary Text"),
            ("fg_muted", "Secondary Text"),
            ("highlight_bg", "Selection / Hit BG"),
            ("border", "Divider / Border"),
        ]

        for key, label_txt in color_specs:
            row = self._tag_role(tk.Frame(body, bg=t["bg_panel"]), "panel")
            row.pack(fill="x", padx=8, pady=3)

            self._tag_role(tk.Label(row, text=label_txt, bg=t["bg_panel"], fg=t["fg_text"]), "label_panel").pack(side="left")

            swatch = tk.Button(
                row,
                width=3,
                bg=t[key],
                activebackground=t[key],
                relief="solid",
                bd=1,
                cursor="hand2",
                command=lambda k=key: self._pick_theme_color(k),
            )
            swatch.pack(side="right", padx=(4, 0))
            self._theme_swatch_buttons[key] = swatch

            hvar = tk.StringVar(value=t[key])
            self._theme_hex_vars[key] = hvar
            hex_ent = self._tag_role(
                tk.Entry(
                    row,
                    textvariable=hvar,
                    width=9,
                    font=("Consolas", 9),
                    bg=t["bg_editor"],
                    fg=t["fg_text"],
                    insertbackground=t["misora_pink"],
                    bd=1,
                    relief="solid",
                ),
                "entry_editor"
            )
            hex_ent.pack(side="right")
            hex_ent.bind("<Return>", lambda _e, k=key: self._commit_theme_hex(k))
            hex_ent.bind("<FocusOut>", lambda _e, k=key: self._commit_theme_hex(k))

        btn_row = self._tag_role(tk.Frame(body, bg=t["bg_panel"]), "panel")
        btn_row.pack(fill="x", padx=8, pady=(12, 10))
        ttk.Button(
            btn_row,
            text="Reset All to Defaults",
            style="TButton",
            command=self._reset_customization_defaults,
        ).pack(fill="x")

    def _build_glossary_tab(self, parent: tk.Frame) -> None:
        """Populate interactive NGUI Glossary & Syntax Reference panel."""
        t = self.theme
        u_sz = int(self.prefs["ui_font_size"])

        filter_row = self._tag_role(tk.Frame(parent, bg=t["bg_panel"]), "panel")
        filter_row.pack(fill="x", padx=6, pady=(2, 4))

        self._tag_role(tk.Label(filter_row, text="Filter:", bg=t["bg_panel"], fg=t["fg_muted"]), "label_muted").pack(side="left", padx=(0, 4))
        self.var_glossary_filter = tk.StringVar()
        ent_filter = self._tag_role(
            tk.Entry(
                filter_row,
                textvariable=self.var_glossary_filter,
                font=("Segoe UI", 9),
                bg=t["bg_editor"],
                fg=t["fg_text"],
                insertbackground=t["misora_pink"],
                bd=1,
                relief="solid",
            ),
            "entry_editor"
        )
        ent_filter.pack(side="left", fill="x", expand=True)
        ent_filter.bind("<KeyRelease>", lambda _e: self._filter_glossary())

        list_wrap = self._tag_role(tk.Frame(parent, bg=t["bg_editor"], bd=1, relief="solid"), "editor_box")
        list_wrap.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        g_scroll = tk.Scrollbar(list_wrap, orient="vertical")
        g_scroll.pack(side="right", fill="y")

        self.txt_glossary = tk.Text(
            list_wrap,
            wrap="word",
            font=("Segoe UI", u_sz),
            bg=t["bg_editor"],
            fg=t["fg_text"],
            insertwidth=0,
            cursor="hand2",
            padx=8,
            pady=6,
            bd=0,
            relief="flat",
            exportselection=False,
            state="disabled",
            yscrollcommand=g_scroll.set,
        )
        self.txt_glossary.pack(side="left", fill="both", expand=True)
        g_scroll.config(command=self.txt_glossary.yview)

        self.txt_glossary.tag_configure("gl_tag", font=("Consolas", u_sz, "bold"), foreground=t["misora_pink"])
        self.txt_glossary.tag_configure("gl_title", font=("Segoe UI", u_sz, "bold"), foreground=t["fg_text"])
        self.txt_glossary.tag_configure("gl_syntax", font=("Consolas", max(8, u_sz - 1)), foreground=t["accent_blue"])
        self.txt_glossary.tag_configure("gl_desc", font=("Segoe UI", max(8, u_sz - 1)), foreground=t["fg_muted"])
        self.txt_glossary.tag_configure("gl_selected", background=t["highlight_bg"])

        self.txt_glossary.bind("<Button-1>", self._on_glossary_click)
        self.txt_glossary.bind("<Double-Button-1>", self._on_glossary_double_click)

        ins_bar = self._tag_role(tk.Frame(parent, bg=t["bg_panel"]), "panel")
        ins_bar.pack(fill="x", padx=6, pady=(0, 6))

        ttk.Button(
            ins_bar,
            text="Insert / Wrap Selected Tag into Dialogue",
            style="Pink.TButton",
            command=self._insert_selected_glossary_tag,
        ).pack(fill="x")

        self._render_glossary_list()

    def _open_side_drawer(self, tab: str = "customize") -> None:
        if not self._side_drawer_visible:
            self.h_paned.add(self.side_drawer, minsize=260, width=330, stretch="never")
            self._side_drawer_visible = True
        self._switch_side_drawer_tab(tab)

    def _close_side_drawer(self) -> None:
        if self._side_drawer_visible:
            self.h_paned.forget(self.side_drawer)
            self._side_drawer_visible = False

    def _toggle_side_drawer(self, tab: str) -> None:
        if self._side_drawer_visible and self._side_drawer_tab == tab:
            self._close_side_drawer()
        else:
            self._open_side_drawer(tab)

    def _switch_side_drawer_tab(self, tab: str) -> None:
        self._side_drawer_tab = tab
        if tab == "customize":
            self.tab_glossary_frame.pack_forget()
            self.tab_customize_frame.pack(fill="both", expand=True)
            self.btn_tab_customize.configure(style="Pink.TButton")
            self.btn_tab_glossary.configure(style="TButton")
        else:
            self.tab_customize_frame.pack_forget()
            self.tab_glossary_frame.pack(fill="both", expand=True)
            self.btn_tab_customize.configure(style="TButton")
            self.btn_tab_glossary.configure(style="Pink.TButton")

    def _on_font_pref_changed(self) -> None:
        """Apply updated font family / size values from Customize panel."""
        fam = self.var_font_family.get().strip() or self.prefs["dialogue_font_family"]
        try:
            d_sz = max(8, min(28, int(self.var_dlg_font_sz.get())))
        except Exception:
            d_sz = int(self.prefs["dialogue_font_size"])
            self.var_dlg_font_sz.set(d_sz)

        try:
            r_sz = max(7, min(22, int(self.var_raw_font_sz.get())))
        except Exception:
            r_sz = int(self.prefs["raw_font_size"])
            self.var_raw_font_sz.set(r_sz)

        try:
            u_sz = max(8, min(16, int(self.var_ui_font_sz.get())))
        except Exception:
            u_sz = int(self.prefs["ui_font_size"])
            self.var_ui_font_sz.set(u_sz)

        self.prefs["dialogue_font_family"] = fam
        self.prefs["dialogue_font_size"] = d_sz
        self.prefs["raw_font_size"] = r_sz
        self.prefs["ui_font_size"] = u_sz
        self._apply_theme_and_fonts_live(save=True)

    def _adjust_dialogue_font_size(self, delta: int) -> None:
        cur = int(self.prefs["dialogue_font_size"])
        new_sz = max(8, min(28, cur + delta))
        self.prefs["dialogue_font_size"] = new_sz
        if hasattr(self, "var_dlg_font_sz"):
            self.var_dlg_font_sz.set(new_sz)
        self._apply_theme_and_fonts_live(save=True)

    def _pick_theme_color(self, key: str) -> None:
        cur = self.theme.get(key, "#ffffff")
        chosen = colorchooser.askcolor(color=cur, title=f"Select Color ({key})", parent=self)
        if chosen and chosen[1]:
            hex_val = chosen[1].lower()
            self.theme[key] = hex_val
            if key == "misora_pink":
                self.theme["misora_pink_hover"] = self._shift_hex(hex_val, 22)
                self.theme["misora_pink_active"] = self._shift_hex(hex_val, -26)
            if hasattr(self, "var_preset"):
                self.var_preset.set(self._detect_active_preset_name())
            self._apply_theme_and_fonts_live(save=True)

    def _commit_theme_hex(self, key: str) -> None:
        hvar = self._theme_hex_vars.get(key)
        if not hvar:
            return
        val = hvar.get().strip()
        if not val.startswith("#"):
            val = "#" + val
        if HEX_COLOR_RE.match(val):
            hex_val = val.lower()
            self.theme[key] = hex_val
            if key == "misora_pink":
                self.theme["misora_pink_hover"] = self._shift_hex(hex_val, 22)
                self.theme["misora_pink_active"] = self._shift_hex(hex_val, -26)
            if hasattr(self, "var_preset"):
                self.var_preset.set(self._detect_active_preset_name())
            self._apply_theme_and_fonts_live(save=True)
        else:
            hvar.set(self.theme[key])

    def _apply_theme_preset(self, preset_name: str) -> None:
        preset = THEME_PRESETS.get(preset_name)
        if not preset:
            return
        self.theme.update(preset)
        if hasattr(self, "var_preset"):
            self.var_preset.set(preset_name)
        self._apply_theme_and_fonts_live(save=True)
        self.lbl_status.config(text=f"Applied theme preset: {preset_name}")
        self.logger.info("UI / Theme / Config", f"Applied theme preset '{preset_name}'")

    def _reset_customization_defaults(self) -> None:
        self.prefs["dialogue_font_family"] = DEFAULT_PREFS["dialogue_font_family"]
        self.prefs["dialogue_font_size"] = DEFAULT_PREFS["dialogue_font_size"]
        self.prefs["raw_font_size"] = DEFAULT_PREFS["raw_font_size"]
        self.prefs["ui_font_size"] = DEFAULT_PREFS["ui_font_size"]
        self.theme.clear()
        self.theme.update(DEFAULT_PREFS["theme"])

        if hasattr(self, "var_font_family"):
            self.var_font_family.set(self.prefs["dialogue_font_family"])
            self.var_dlg_font_sz.set(self.prefs["dialogue_font_size"])
            self.var_raw_font_sz.set(self.prefs["raw_font_size"])
            self.var_ui_font_sz.set(self.prefs["ui_font_size"])
            self.var_preset.set("Misora Purple & White")

        self._apply_theme_and_fonts_live(save=True)
        self.lbl_status.config(text="Reset display fonts and theme colors to Misora Purple & White default.")
        self.logger.info("UI / Theme / Config", "Reset display fonts and theme colors to default.")

    def _filter_glossary(self) -> None:
        q = self.var_glossary_filter.get().strip().lower()
        if not q:
            self._filtered_glossary_items = list(NGUI_GLOSSARY_ITEMS)
        else:
            self._filtered_glossary_items = [
                item for item in NGUI_GLOSSARY_ITEMS
                if q in item["tag"].lower()
                or q in item["title"].lower()
                or q in item["syntax"].lower()
                or q in item["desc"].lower()
            ]
        self._selected_glossary_idx = 0
        self._render_glossary_list()

    def _render_glossary_list(self) -> None:
        self._glossary_line_map.clear()
        self.txt_glossary.config(state="normal")
        self.txt_glossary.delete("1.0", tk.END)

        line_no = 1
        for idx, item in enumerate(self._filtered_glossary_items):
            sel_tags = ("gl_selected",) if idx == self._selected_glossary_idx else ()
            start_line = line_no

            self.txt_glossary.insert(f"{line_no}.0", f"{item['tag']}  ", ("gl_tag",) + sel_tags)
            self.txt_glossary.insert(f"{line_no}.end", f"{item['title']}\n", ("gl_title",) + sel_tags)
            line_no += 1

            self.txt_glossary.insert(f"{line_no}.0", f"  Example: {item['syntax']}\n", ("gl_syntax",) + sel_tags)
            line_no += 1

            self.txt_glossary.insert(f"{line_no}.0", f"  {item['desc']}\n\n", ("gl_desc",) + sel_tags)
            for ln in range(start_line, line_no + 1):
                self._glossary_line_map[ln] = idx
            line_no += 2

        self.txt_glossary.config(state="disabled")

    def _on_glossary_click(self, event: tk.Event) -> str:
        idx_str = self.txt_glossary.index(f"@{event.x},{event.y}")
        line_no = int(idx_str.split(".")[0])
        item_idx = self._glossary_line_map.get(line_no)
        if item_idx is not None:
            self._selected_glossary_idx = item_idx
            self._render_glossary_list()
        return "break"

    def _on_glossary_double_click(self, event: tk.Event) -> str:
        self._on_glossary_click(event)
        self._insert_selected_glossary_tag()
        return "break"

    def _insert_selected_glossary_tag(self) -> None:
        """Insert or wrap selected dialogue text with the chosen NGUI tag."""
        if not self._filtered_glossary_items:
            return
        idx = max(0, min(self._selected_glossary_idx, len(self._filtered_glossary_items) - 1))
        item = self._filtered_glossary_items[idx]

        if item.get("action") == "ruby":
            self.on_insert_ruby()
            return

        open_tag = item["insert_open"]
        close_tag = item["insert_close"]
        self.apply_ngui_wrapper(open_tag, close_tag)

    def _insert_text_wrapper(self, open_tag: str, close_tag: str, default_inner: str = "") -> None:
        """Wrap the current selection (or insert at caret) in the active dialogue editor."""
        if self.var_continuous_view.get():
            target = self.txt_continuous
            box_idx = self._find_continuous_box_at_index("insert")
            if box_idx is None:
                self._focus_continuous_box(self.current_box_idx, move_cursor=True)
            try:
                sel_first = target.index("sel.first")
                sel_last = target.index("sel.last")
                b1 = self._find_continuous_box_at_index(sel_first)
                b2 = self._find_continuous_box_at_index(sel_last)
                if b1 is not None and b1 == b2:
                    selected_txt = target.get(sel_first, sel_last)
                    target.delete(sel_first, sel_last)
                    target.insert(sel_first, f"{open_tag}{selected_txt}{close_tag}")
                else:
                    target.insert(tk.INSERT, f"{open_tag}{default_inner}{close_tag}")
            except tk.TclError:
                target.insert(tk.INSERT, f"{open_tag}{default_inner}{close_tag}")
            self._sync_continuous_box_from_widget()
            target.focus_set()
        else:
            target = self.txt_dialogue
            try:
                sel_first = target.index("sel.first")
                sel_last = target.index("sel.last")
                selected_txt = target.get(sel_first, sel_last)
                target.delete(sel_first, sel_last)
                target.insert(sel_first, f"{open_tag}{selected_txt}{close_tag}")
            except tk.TclError:
                target.insert(tk.INSERT, f"{open_tag}{default_inner}{close_tag}")
            self._on_dialogue_edited()
            target.focus_set()

    def on_insert_ruby(self) -> None:
        """Open a compact modal prompt to wrap base text with [rub:ruby]base[/rub]."""
        if self.var_preview_compiled.get():
            self.var_preview_compiled.set(False)
            self._update_views()

        selected_base = ""
        if self.var_continuous_view.get():
            target = self.txt_continuous
            try:
                sel_first = target.index("sel.first")
                sel_last = target.index("sel.last")
                b1 = self._find_continuous_box_at_index(sel_first)
                b2 = self._find_continuous_box_at_index(sel_last)
                if b1 is not None and b1 == b2:
                    selected_base = target.get(sel_first, sel_last)
            except tk.TclError:
                pass
        else:
            target = self.txt_dialogue
            try:
                selected_base = target.get("sel.first", "sel.last")
            except tk.TclError:
                pass

        t = self.theme
        panel_fg = best_contrast_fg(t["bg_panel"], t["fg_text"], "#ffffff")
        editor_fg = best_contrast_fg(t["bg_editor"], t["fg_text"], "#ffffff")

        dlg = tk.Toplevel(self)
        dlg.title("Insert Ruby / Furigana ([rub:...]...[/rub])")
        dlg.configure(bg=t["bg_panel"])
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()

        self.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() // 2) - 190
        y = self.winfo_rooty() + (self.winfo_height() // 2) - 105
        dlg.geometry(f"380x210+{max(20, x)}+{max(20, y)}")

        tk.Label(
            dlg,
            text="Priconne NGUI Ruby Text ([rub:ruby]base[/rub])",
            font=("Segoe UI", 9, "bold"),
            bg=t["bg_panel"],
            fg=t["misora_pink"],
        ).pack(anchor="w", padx=14, pady=(12, 8))

        row_base = tk.Frame(dlg, bg=t["bg_panel"])
        row_base.pack(fill="x", padx=14, pady=4)
        tk.Label(row_base, text="Base Text (Main):", width=16, anchor="w", bg=t["bg_panel"], fg=panel_fg).pack(side="left")
        var_base = tk.StringVar(value=selected_base)
        ent_base = tk.Entry(
            row_base,
            textvariable=var_base,
            font=("Segoe UI", 10),
            bg=t["bg_editor"],
            fg=editor_fg,
            insertbackground=t["misora_pink"],
            bd=1,
            relief="solid",
        )
        ent_base.pack(side="left", fill="x", expand=True)

        row_ruby = tk.Frame(dlg, bg=t["bg_panel"])
        row_ruby.pack(fill="x", padx=14, pady=4)
        tk.Label(row_ruby, text="Ruby Text (Top):", width=16, anchor="w", bg=t["bg_panel"], fg=panel_fg).pack(side="left")
        var_ruby = tk.StringVar()
        ent_ruby = tk.Entry(
            row_ruby,
            textvariable=var_ruby,
            font=("Segoe UI", 10),
            bg=t["bg_editor"],
            fg=editor_fg,
            insertbackground=t["misora_pink"],
            bd=1,
            relief="solid",
        )
        ent_ruby.pack(side="left", fill="x", expand=True)

        lbl_preview = tk.Label(
            dlg,
            text=f"Preview: [rub:]{selected_base}[/rub]",
            font=("Consolas", 9),
            bg=t["bg_panel"],
            fg=t["accent_blue"],
            anchor="w",
        )
        lbl_preview.pack(fill="x", padx=14, pady=(8, 10))

        def _update_preview(*_args: Any) -> None:
            lbl_preview.config(text=f"Preview: [rub:{var_ruby.get()}]{var_base.get()}[/rub]")

        var_base.trace_add("write", _update_preview)
        var_ruby.trace_add("write", _update_preview)

        def _commit(_event: Optional[tk.Event] = None) -> None:
            r_txt = var_ruby.get().strip()
            b_txt = var_base.get()
            dlg.destroy()
            if not b_txt and not r_txt:
                return
            if selected_base:
                self._insert_text_wrapper(f"[rub:{r_txt}]", "[/rub]")
            else:
                self._insert_text_wrapper(f"[rub:{r_txt}]", "[/rub]", default_inner=b_txt)

        btn_row = tk.Frame(dlg, bg=t["bg_panel"])
        btn_row.pack(fill="x", padx=14, pady=(0, 12))
        ttk.Button(btn_row, text="Cancel", style="TButton", command=dlg.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btn_row, text="Insert Ruby Tag", style="Pink.TButton", command=_commit).pack(side="right")

        dlg.bind("<Return>", _commit)
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        (ent_ruby if selected_base else ent_base).focus_set()

    def _highlight_ngui_tags(self) -> None:
        """Apply non-destructive syntax coloring to NGUI & Priconne ruby tags."""
        if self.var_preview_compiled.get():
            return

        self.txt_dialogue.tag_remove("ngui_tag", "1.0", tk.END)
        text = self.txt_dialogue.get("1.0", "end-1c")
        for m in NGUI_TAG_RE.finditer(text):
            self.txt_dialogue.tag_add("ngui_tag", f"1.0 + {m.start()}c", f"1.0 + {m.end()}c")
        self.txt_dialogue.tag_raise("search_hit")

        self.txt_continuous.tag_remove("ngui_tag", "1.0", tk.END)
        if not self.current_doc or not self.current_doc.boxes:
            cont_tx = self.txt_continuous.get("1.0", "end-1c")
            for m in NGUI_TAG_RE.finditer(cont_tx):
                self.txt_continuous.tag_add("ngui_tag", f"1.0 + {m.start()}c", f"1.0 + {m.end()}c")
        else:
            marks = set(self.txt_continuous.mark_names())
            for i in range(len(self.current_doc.boxes)):
                s_mark = f"box_start_{i}"
                e_mark = f"box_end_{i}"
                if s_mark in marks and e_mark in marks:
                    box_tx = self.txt_continuous.get(s_mark, e_mark)
                    for m in NGUI_TAG_RE.finditer(box_tx):
                        self.txt_continuous.tag_add(
                            "ngui_tag",
                            f"{s_mark} + {m.start()}c",
                            f"{s_mark} + {m.end()}c",
                        )
        self.txt_continuous.tag_raise("ngui_tag")
        self.txt_continuous.tag_raise("search_hit")

    def _sync_gd_scroll_bounds(self, _event: Optional[tk.Event] = None) -> None:
        """Keep Game Display canvas width matched to viewport and clamp scrollregion."""
        canvas_w = max(240, self.gd_canvas.winfo_width())
        canvas_h = max(80, self.gd_canvas.winfo_height())
        self.gd_canvas.itemconfigure(self._gd_canvas_win, width=canvas_w)

        req_h = self.gd_inner.winfo_reqheight()
        bound_h = max(req_h, canvas_h)
        self.gd_canvas.configure(scrollregion=(0, 0, canvas_w, bound_h))

        if req_h <= canvas_h:
            self.gd_canvas.yview_moveto(0.0)

    def _on_gd_scrollbar(self, *args: Any) -> None:
        """Scrollbar callback clamped strictly within [0.0, 1.0]."""
        self.gd_canvas.yview(*args)
        top, _ = self.gd_canvas.yview()
        if top < 0.0:
            self.gd_canvas.yview_moveto(0.0)

    def _on_gd_mousewheel(self, event: tk.Event) -> Optional[str]:
        """Smoothly scroll Game Display canvas within bounded upper/lower limits."""
        canvas_h = self.gd_canvas.winfo_height()
        req_h = self.gd_inner.winfo_reqheight()
        if req_h <= canvas_h:
            self.gd_canvas.yview_moveto(0.0)
            return "break"

        delta = -1 if event.delta > 0 else 1
        top, bottom = self.gd_canvas.yview()
        if delta < 0 and top <= 0.0:
            self.gd_canvas.yview_moveto(0.0)
            return "break"
        if delta > 0 and bottom >= 1.0:
            return "break"

        self.gd_canvas.yview_scroll(delta * 2, "units")
        new_top, _ = self.gd_canvas.yview()
        if new_top < 0.0:
            self.gd_canvas.yview_moveto(0.0)
        return "break"

    def _auto_resize_dialogue_box(self) -> None:
        """Adjust dialogue editor line height to fit multi-line text comfortably inside scroll bounds."""
        content = self.txt_dialogue.get("1.0", "end-1c")
        lines = content.split("\n")
        est_visual_lines = sum(max(1, (len(ln) // 68) + 1) for ln in lines)
        target_lines = max(7, min(32, est_visual_lines + 1))
        self.txt_dialogue.configure(height=target_lines)
        self.gd_inner.update_idletasks()
        self._sync_gd_scroll_bounds()

    def _on_toggle_continuous_view(self) -> None:
        """Switch Game Display between Page-by-Page mode and Continuous Dialog Stream."""
        if self.var_continuous_view.get():
            self.gd_scroll_wrap.pack_forget()
            self.continuous_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 6))
            self.lbl_gd_title.config(text="GAME DISPLAY VIEW (Continuous Dialog Stream)")
        else:
            self.continuous_wrap.pack_forget()
            self.gd_scroll_wrap.pack(fill="both", expand=True, padx=4, pady=(0, 4))
            self.lbl_gd_title.config(text="GAME DISPLAY VIEW (Clean Dialogue)")

        self._update_views()

    # -------------------------------------------------------------------------
    # Status & Action Bar
    # -------------------------------------------------------------------------
    def _build_status_bar(self) -> None:
        t = self.theme
        action_bar = self._tag_role(
            tk.Frame(self, bg=t["bg_panel"], bd=1, relief="solid", highlightbackground=t["border"], highlightthickness=1),
            "panel_box"
        )
        action_bar.pack(fill="x", padx=8, pady=(0, 6))

        self.lbl_status = self._tag_role(
            tk.Label(action_bar, text="Ready. Drag & Drop or open a .unity3d bundle or folder to begin.", font=("Segoe UI", 9), bg=t["bg_panel"], fg=t["fg_muted"]),
            "label_muted"
        )
        self.lbl_status.pack(side="left", padx=8, pady=6)

        self.var_sync_xuat = tk.BooleanVar(value=True)
        cb_sync = self._tag_role(
            tk.Checkbutton(
                action_bar,
                text="Also update matching XUAT .txt dictionary on Save",
                variable=self.var_sync_xuat,
                bg=t["bg_panel"],
                fg=t["fg_text"],
                selectcolor=t["bg_dark"],
                activebackground=t["bg_panel"]
            ),
            "check_panel"
        )
        cb_sync.pack(side="right", padx=(8, 12))

        btn_revert = ttk.Button(action_bar, text="Revert Box", style="TButton", command=self.on_revert_box)
        btn_revert.pack(side="right", padx=4)

        self.btn_save = ttk.Button(action_bar, text="Save & Patch Bundle (Ctrl+S)", style="Pink.TButton", command=self.on_save)
        self.btn_save.pack(side="right", padx=4)

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda e: self.on_open_file())
        self.bind("<Control-O>", lambda e: self.on_open_folder())
        self.bind("<Control-s>", lambda e: self.on_save())
        self.bind("<Control-q>", lambda e: self._on_app_exit())
        self.bind("<Control-r>", lambda e: self.on_insert_ruby())
        self.bind("<Control-p>", lambda e: self.on_insert_playername())
        self.bind("<Control-f>", lambda e: self.on_show_find())
        self.bind("<Control-F>", lambda e: self.on_show_find_in_files())
        self.bind("<Control-h>", lambda e: self.on_show_replace())
        self.bind("<Control-z>", lambda e: self.on_undo())
        self.bind("<Control-y>", lambda e: self.on_redo())
        self.bind("<Control-Shift-Z>", lambda e: self.on_redo())
        self.bind("<Control-Shift-z>", lambda e: self.on_redo())
        self.bind("<Control-C>", lambda e: self._toggle_continuous_shortcut())
        self.bind("<Control-comma>", lambda e: self._toggle_side_drawer("customize"))
        self.bind("<F1>", lambda e: self._toggle_side_drawer("glossary"))
        self.bind("<F5>", lambda e: self.on_reload())
        self.bind("<F9>", lambda e: self.on_launch_datamine())
        self.bind("<F12>", lambda e: self._toggle_console_shortcut())
        self.bind("<Alt-Left>", lambda e: self.on_prev_box())
        self.bind("<Alt-Right>", lambda e: self.on_next_box())

    def _toggle_continuous_shortcut(self) -> None:
        self.var_continuous_view.set(not self.var_continuous_view.get())
        self._on_toggle_continuous_view()

    # -------------------------------------------------------------------------
    # Document Loading & Box Display (Page Mode + Continuous Stream Mode)
    # -------------------------------------------------------------------------
    def open_file(self, file_path: Union[str, Path], reload_from_disk: bool = False) -> None:
        """Open and display a .unity3d bundle or plain-text script file."""
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            self.logger.error("File I/O", f"Cannot find file: {file_path}")
            messagebox.showerror("File Error", f"Cannot find file: {file_path}")
            return

        # Check in-memory opened files cache if not explicitly reloading from disk
        if not reload_from_disk and file_path in self.open_documents:
            entry = self.open_documents[file_path]
            self.current_file_path = file_path
            self.current_doc = entry.get("doc")
            self.current_unity_env = entry.get("env")
            self.current_text_obj = entry.get("obj")
            self.is_bundle_file = entry.get("is_bundle", False)
            self.is_dirty = entry.get("dirty", False)
            self._plain_text_content = entry.get("plain_text", "")
            self.current_box_idx = 0
            if self.current_doc and self.current_doc.boxes:
                self._original_box_texts = {i: b.clean_text for i, b in enumerate(self.current_doc.boxes)}
            self._update_views()
            self._refresh_opened_files_list()
            self.lbl_status.config(text=f"Switched to {file_path.name}")
            return

        ext = file_path.suffix.lower()
        self.current_file_path = file_path
        self.is_dirty = False
        self._modified_boxes.clear()
        self._original_box_texts.clear()
        self._plain_text_content = ""

        if ext in (".unity3d", ".asset"):
            try:
                doc, env, obj, asset_name = load_bundle_story(file_path)
                self.current_doc = doc
                self.current_unity_env = env
                self.current_text_obj = obj
                self.is_bundle_file = True
                self.current_box_idx = 0
                self._original_box_texts = {i: b.clean_text for i, b in enumerate(doc.boxes)}
                self._update_views()
                size_kb = file_path.stat().st_size / 1024
                self.lbl_status.config(text=f"Loaded Bundle: {file_path.name} ({asset_name}) | Size: {size_kb:.1f} KB | {len(doc.boxes)} dialogue boxes")
                self.logger.info("File I/O", f"Opened bundle '{file_path}' (asset={asset_name}, boxes={len(doc.boxes)})")
                self.open_documents[file_path] = {
                    "doc": doc,
                    "env": env,
                    "obj": obj,
                    "is_bundle": True,
                    "dirty": False,
                    "plain_text": "",
                    "boxes_count": len(doc.boxes),
                }
                self._refresh_opened_files_list()
            except Exception as e:
                self.logger.exception(f"Failed to open bundle '{file_path.name}':", e)
                messagebox.showerror("Bundle Load Error", f"Failed to open '{file_path.name}':\n{e}")
        else:
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                if content.startswith("#!priconne-story"):
                    doc = StoryDocument.from_v2_text(content)
                    self.current_doc = doc
                    self.is_bundle_file = False
                    self.current_box_idx = 0
                    self._original_box_texts = {i: b.clean_text for i, b in enumerate(doc.boxes)}
                    self._update_views()
                    self.lbl_status.config(text=f"Loaded Script: {file_path.name} | {len(doc.boxes)} dialogue boxes")
                    self.logger.info("File I/O", f"Opened v2 script '{file_path}' (boxes={len(doc.boxes)})")
                    self.open_documents[file_path] = {
                        "doc": doc,
                        "env": None,
                        "obj": None,
                        "is_bundle": False,
                        "dirty": False,
                        "plain_text": "",
                        "boxes_count": len(doc.boxes),
                    }
                    self._refresh_opened_files_list()
                else:
                    self.current_doc = None
                    self.is_bundle_file = False
                    self._plain_text_content = content
                    self._update_views()
                    self.lbl_status.config(text=f"Opened Text File: {file_path.name}")
                    self.logger.info("File I/O", f"Opened plain text file '{file_path}' ({len(content)} chars)")
                    self.open_documents[file_path] = {
                        "doc": None,
                        "env": None,
                        "obj": None,
                        "is_bundle": False,
                        "dirty": False,
                        "plain_text": content,
                        "boxes_count": 0,
                    }
                    self._refresh_opened_files_list()
            except Exception as e:
                self.logger.exception(f"Failed to read '{file_path.name}':", e)
                messagebox.showerror("File Load Error", f"Failed to read '{file_path.name}':\n{e}")

    def _update_views(self) -> None:
        """Update Game Display View (Page or Continuous, Raw or Compiled Preview) and Raw AST View."""
        compiled = self.var_preview_compiled.get()

        if not self.current_doc:
            self.speaker_var.set("")
            self.lbl_box_counter.config(text="Box: 0 / 0")
            self.lbl_voice_cue.config(text="")

            self.txt_dialogue.config(state="normal")
            self.txt_dialogue.delete("1.0", tk.END)
            if compiled:
                self._insert_compiled_ngui_text(self.txt_dialogue, "1.0", self._plain_text_content)
                self.txt_dialogue.config(state="disabled")
            else:
                self.txt_dialogue.insert("1.0", self._plain_text_content)
                self._highlight_ngui_tags()
                self._highlight_dialogue_matches()
            self._auto_resize_dialogue_box()

            self.txt_continuous.config(state="normal")
            self.txt_continuous.delete("1.0", tk.END)
            if compiled:
                self._insert_compiled_ngui_text(self.txt_continuous, "1.0", self._plain_text_content)
                self.txt_continuous.config(state="disabled")
            else:
                self.txt_continuous.insert("1.0", self._plain_text_content)
                self._highlight_ngui_tags()
                self._highlight_continuous_matches()

            self.txt_raw.delete("1.0", tk.END)
            if self.current_file_path:
                self.txt_raw.insert("1.0", f"(Plain text file: {self.current_file_path})")
            return

        if not self.current_doc.boxes:
            self.speaker_var.set("")
            self.lbl_voice_cue.config(text="")
            self.txt_dialogue.config(state="normal")
            self.txt_dialogue.delete("1.0", tk.END)
            self.txt_continuous.config(state="normal")
            self.txt_continuous.delete("1.0", tk.END)
            self.txt_raw.delete("1.0", tk.END)
            self.lbl_box_counter.config(text="Box: 0 / 0")
            self._auto_resize_dialogue_box()
            return

        total_boxes = len(self.current_doc.boxes)
        self.current_box_idx = max(0, min(self.current_box_idx, total_boxes - 1))
        box = self.current_doc.boxes[self.current_box_idx]

        self.speaker_var.set(box.speaker)
        self.lbl_box_counter.config(text=f"Box: {self.current_box_idx + 1} / {total_boxes}")
        self.lbl_voice_cue.config(text=f"Voice Cue: {box.voice_cue}" if box.voice_cue else "")

        if self.var_continuous_view.get():
            self._render_continuous_view()
            self._focus_continuous_box(self.current_box_idx, move_cursor=True)
        else:
            self.txt_dialogue.config(state="normal")
            self.txt_dialogue.delete("1.0", tk.END)
            if compiled:
                self._insert_compiled_ngui_text(self.txt_dialogue, "1.0", box.clean_text)
                self.txt_dialogue.config(state="disabled")
            else:
                self.txt_dialogue.insert("1.0", box.clean_text)
                self._highlight_ngui_tags()
                self._highlight_dialogue_matches()
            self.gd_canvas.yview_moveto(0.0)
            self._auto_resize_dialogue_box()

        self._update_raw_view()

    def _update_raw_view(self) -> None:
        """Render Raw AST View and highlight records associated with current_box_idx."""
        self.txt_raw.delete("1.0", tk.END)
        if not self.current_doc:
            return

        active_box = (
            self.current_doc.boxes[self.current_box_idx]
            if self.current_doc.boxes and 0 <= self.current_box_idx < len(self.current_doc.boxes)
            else None
        )
        active_rec_indices = {s.rec_index for s in active_box.segs} if active_box else set()

        raw_lines = []
        first_active_line = None
        for i, r in enumerate(self.current_doc.records):
            args_str = "  ".join(f"'{a}'" for a in r.args)
            is_active = i in active_rec_indices
            if is_active and first_active_line is None:
                first_active_line = i + 1
            marker = " >> " if is_active else "    "
            raw_lines.append(f"{marker}[{i:03d}] {r.cmd_name:<14} {args_str}")

        self.txt_raw.insert("1.0", "\n".join(raw_lines))
        if first_active_line is not None:
            self.txt_raw.see(f"{first_active_line}.0")

    def _render_continuous_view(self) -> None:
        """Render all dialogue boxes sequentially with dividers, badges, and editable spans."""
        compiled = self.var_preview_compiled.get()
        self._suppress_continuous_events = True
        try:
            self.txt_continuous.config(state="normal")
            for mark_name in list(self.txt_continuous.mark_names()):
                if mark_name.startswith(("box_start_", "box_end_")):
                    self.txt_continuous.mark_unset(mark_name)
            self._cont_header_spans.clear()
            self.txt_continuous.delete("1.0", tk.END)

            if not self.current_doc or not self.current_doc.boxes:
                return

            for i, box in enumerate(self.current_doc.boxes):
                if i > 0:
                    self.txt_continuous.insert(tk.END, "\n")
                    self.txt_continuous.insert(tk.END, "─" * 68 + "\n", ("cont_divider",))

                hdr_start = self.txt_continuous.index("end-1c")
                badge = f"[Box #{i + 1:03d}]"
                speaker_disp = box.speaker if box.speaker else "(Narration)"
                speaker_tag = "cont_speaker" if box.speaker else "cont_narrator"
                voice_disp = f"   ♪ {box.voice_cue}" if box.voice_cue else ""

                self.txt_continuous.insert(tk.END, badge + "  ", ("cont_badge",))
                self.txt_continuous.insert(tk.END, speaker_disp, (speaker_tag,))
                if voice_disp:
                    self.txt_continuous.insert(tk.END, voice_disp, ("cont_voice",))
                self.txt_continuous.insert(tk.END, "\n")
                hdr_end = self.txt_continuous.index("end-1c")
                self._cont_header_spans[i] = (hdr_start, hdr_end)

                if i == self.current_box_idx:
                    self.txt_continuous.tag_add("cont_active_header", hdr_start, hdr_end)

                body_start = self.txt_continuous.index("end-1c")
                self.txt_continuous.mark_set(f"box_start_{i}", body_start)
                self.txt_continuous.mark_gravity(f"box_start_{i}", tk.LEFT)

                if compiled:
                    self._insert_compiled_ngui_text(self.txt_continuous, tk.END, box.clean_text, ("cont_body",))
                else:
                    self.txt_continuous.insert(tk.END, box.clean_text, ("cont_body",))

                body_end = self.txt_continuous.index("end-1c")
                self.txt_continuous.mark_set(f"box_end_{i}", body_end)
                self.txt_continuous.mark_gravity(f"box_end_{i}", tk.LEFT)

                self.txt_continuous.insert(tk.END, "\n")
                self.txt_continuous.mark_gravity(f"box_end_{i}", tk.RIGHT)

            if compiled:
                self.txt_continuous.config(state="disabled")
            else:
                self._highlight_ngui_tags()
                self._highlight_continuous_matches()
        finally:
            self._suppress_continuous_events = False

    def _focus_continuous_box(
        self,
        box_idx: int,
        move_cursor: bool = True,
        char_offset: int = 0,
        explicit_span: Optional[Tuple[int, int]] = None
    ) -> None:
        """Scroll Continuous View to `box_idx`, highlight its header, and sync metadata."""
        if not self.current_doc or not self.current_doc.boxes:
            return
        total = len(self.current_doc.boxes)
        box_idx = max(0, min(box_idx, total - 1))
        self.current_box_idx = box_idx
        box = self.current_doc.boxes[box_idx]

        self.speaker_var.set(box.speaker)
        self.lbl_box_counter.config(text=f"Box: {box_idx + 1} / {total}")
        self.lbl_voice_cue.config(text=f"Voice Cue: {box.voice_cue}" if box.voice_cue else "")

        self.txt_continuous.tag_remove("cont_active_header", "1.0", tk.END)
        span = self._cont_header_spans.get(box_idx)
        if span:
            self.txt_continuous.tag_add("cont_active_header", span[0], span[1])

        start_mark = f"box_start_{box_idx}"
        if start_mark in self.txt_continuous.mark_names():
            target_idx = f"{start_mark} + {max(0, char_offset)}c"
            if move_cursor and not self.var_preview_compiled.get():
                self.txt_continuous.mark_set("insert", target_idx)
            if span:
                self.txt_continuous.see(span[0])
            self.txt_continuous.see(target_idx)

            if explicit_span is not None and not self.var_preview_compiled.get():
                s, e = explicit_span
                if e > s:
                    self.txt_continuous.tag_remove("search_hit", "1.0", tk.END)
                    self.txt_continuous.tag_add(
                        "search_hit",
                        f"{start_mark} + {s}c",
                        f"{start_mark} + {e}c",
                    )

        self._update_raw_view()

    def _find_continuous_box_at_index(self, tk_index: str) -> Optional[int]:
        """Return the box index containing `tk_index` inside its editable body, or None."""
        if not self.current_doc or not self.current_doc.boxes:
            return None
        marks = set(self.txt_continuous.mark_names())
        for i in range(len(self.current_doc.boxes)):
            s_mark = f"box_start_{i}"
            e_mark = f"box_end_{i}"
            if s_mark in marks and e_mark in marks:
                if (
                    self.txt_continuous.compare(tk_index, ">=", s_mark)
                    and self.txt_continuous.compare(tk_index, "<=", e_mark)
                ):
                    return i
        return None

    def _nearest_continuous_box_to_index(self, tk_index: str) -> int:
        """Find the closest box index for a click/cursor landing on a divider or header line."""
        if not self.current_doc or not self.current_doc.boxes:
            return 0
        marks = set(self.txt_continuous.mark_names())
        chosen = 0
        for i in range(len(self.current_doc.boxes)):
            s_mark = f"box_start_{i}"
            if s_mark in marks:
                if self.txt_continuous.compare(tk_index, "<=", s_mark):
                    return i
                chosen = i
        return chosen

    def _on_continuous_cursor_moved(self, event: Optional[tk.Event] = None) -> None:
        """Sync active box indicator, speaker bar, and Raw AST View when clicking in Continuous View."""
        if self._suppress_continuous_events or not self.current_doc or not self.current_doc.boxes:
            return
        click_idx = f"@{event.x},{event.y}" if event is not None else "insert"
        box_idx = self._find_continuous_box_at_index(click_idx)
        if box_idx is None:
            box_idx = self._nearest_continuous_box_to_index(click_idx)
            if not self.var_preview_compiled.get():
                start_mark = f"box_start_{box_idx}"
                if start_mark in self.txt_continuous.mark_names():
                    self.txt_continuous.mark_set("insert", start_mark)

        if box_idx != self.current_box_idx:
            self._focus_continuous_box(box_idx, move_cursor=False)

    def _on_continuous_key_guard(self, event: tk.Event) -> Optional[str]:
        """Protect read-only dividers & box headers from accidental deletion or corruption."""
        if self.var_preview_compiled.get():
            return "break"
        if self._suppress_continuous_events or not self.current_doc or not self.current_doc.boxes:
            return "break"

        keysym = event.keysym
        ctrl = bool(event.state & 0x4)

        nav_keys = {
            "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
            "Caps_Lock", "Num_Lock", "Scroll_Lock", "Escape",
            "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
        }
        if keysym in nav_keys:
            self.after_idle(self._on_continuous_cursor_moved)
            return None

        if ctrl and keysym.lower() in {"c", "a", "f", "o", "s", "q", "r", "p", "b", "i", "u"}:
            return None

        if ctrl and keysym.lower() in {"z", "y"}:
            return "break"

        try:
            sel_first = self.txt_continuous.index("sel.first")
            sel_last = self.txt_continuous.index("sel.last")
            b1 = self._find_continuous_box_at_index(sel_first)
            b2 = self._find_continuous_box_at_index(sel_last)
            if b1 is None or b1 != b2:
                return "break"
        except tk.TclError:
            pass

        box_idx = self._find_continuous_box_at_index("insert")
        if box_idx is None:
            nearest = self._nearest_continuous_box_to_index("insert")
            self._focus_continuous_box(nearest, move_cursor=True)
            if keysym in ("BackSpace", "Delete"):
                return "break"
            box_idx = nearest

        s_mark = f"box_start_{box_idx}"
        e_mark = f"box_end_{box_idx}"

        if keysym == "BackSpace" and self.txt_continuous.compare("insert", "==", s_mark):
            return "break"
        if keysym == "Delete" and self.txt_continuous.compare("insert", "==", e_mark):
            return "break"

        return None

    def _on_continuous_paste_guard(self, _event: tk.Event) -> Optional[str]:
        """Ensure paste operations inside Continuous View only target a single box body."""
        if self.var_preview_compiled.get() or not self.current_doc or not self.current_doc.boxes:
            return "break"
        try:
            sel_first = self.txt_continuous.index("sel.first")
            sel_last = self.txt_continuous.index("sel.last")
            b1 = self._find_continuous_box_at_index(sel_first)
            b2 = self._find_continuous_box_at_index(sel_last)
            if b1 is None or b1 != b2:
                return "break"
        except tk.TclError:
            pass

        if self._find_continuous_box_at_index("insert") is None:
            nearest = self._nearest_continuous_box_to_index("insert")
            self._focus_continuous_box(nearest, move_cursor=True)

        self.after_idle(self._sync_continuous_box_from_widget)
        return None

    def _on_continuous_cut_guard(self, _event: tk.Event) -> Optional[str]:
        """Prevent cutting across box headers/dividers."""
        if self.var_preview_compiled.get():
            return "break"
        try:
            sel_first = self.txt_continuous.index("sel.first")
            sel_last = self.txt_continuous.index("sel.last")
            b1 = self._find_continuous_box_at_index(sel_first)
            b2 = self._find_continuous_box_at_index(sel_last)
            if b1 is None or b1 != b2:
                return "break"
        except tk.TclError:
            return "break"

        self.after_idle(self._sync_continuous_box_from_widget)
        return None

    def _on_continuous_key_release(self, _event: tk.Event) -> None:
        """Persist inline edits from Continuous View back into StoryDocument."""
        if self._suppress_continuous_events or self.var_preview_compiled.get():
            return
        self._sync_continuous_box_from_widget()

    def _sync_continuous_box_from_widget(self) -> None:
        """Read edited text for the active box in Continuous View and update StoryDocument."""
        if self.var_preview_compiled.get() or not self.current_doc or not self.current_doc.boxes:
            return

        box_idx = self._find_continuous_box_at_index("insert")
        if box_idx is None:
            return

        if box_idx != self.current_box_idx:
            self._focus_continuous_box(box_idx, move_cursor=False)

        s_mark = f"box_start_{box_idx}"
        e_mark = f"box_end_{box_idx}"
        if s_mark not in self.txt_continuous.mark_names() or e_mark not in self.txt_continuous.mark_names():
            return

        new_tx = self.txt_continuous.get(s_mark, e_mark)
        self.txt_continuous.tag_add("cont_body", s_mark, e_mark)

        if self.current_doc.boxes[box_idx].clean_text != new_tx:
            old_sp = self.current_doc.boxes[box_idx].speaker
            old_tx = self.current_doc.boxes[box_idx].clean_text
            self.undo_journal.record(
                BoxEditDelta(
                    box_index=box_idx,
                    old_speaker=old_sp,
                    new_speaker=old_sp,
                    old_text=old_tx,
                    new_text=new_tx,
                    file_path=str(self.current_file_path or ""),
                ),
                label=f"Edit box #{box_idx + 1}"
            )
            self.is_dirty = True
            self._modified_boxes.add(box_idx)
            if self.current_file_path and self.current_file_path in self.open_documents:
                self.open_documents[self.current_file_path]["dirty"] = True
                self._refresh_opened_files_list()
            try:
                self.current_doc.inject_box(box_idx, None, new_tx)
                self._update_raw_view()
            except Exception:
                pass

        self._highlight_ngui_tags()
        self._highlight_continuous_matches()

    def _highlight_dialogue_matches(self, explicit_span: Optional[Tuple[int, int]] = None) -> None:
        """Highlight active search keyword spans inside the single-box dialogue editor."""
        if self.var_preview_compiled.get():
            return

        self.txt_dialogue.tag_remove("search_hit", "1.0", tk.END)

        if explicit_span is not None:
            s, e = explicit_span
            if e > s:
                start_idx = f"1.0 + {s}c"
                end_idx = f"1.0 + {e}c"
                self.txt_dialogue.tag_add("search_hit", start_idx, end_idx)
                self.txt_dialogue.see(start_idx)
                return

        if not self.active_search_options or not self.active_search_options.query.strip():
            return

        text = self.txt_dialogue.get("1.0", "end-1c")
        if not text:
            return

        try:
            matcher = self.search_engine._compile_matcher(self.active_search_options)
            matches = matcher(text)
            for s, e, _ in matches:
                if e > s:
                    self.txt_dialogue.tag_add("search_hit", f"1.0 + {s}c", f"1.0 + {e}c")
            if matches:
                self.txt_dialogue.see(f"1.0 + {matches[0][0]}c")
        except Exception:
            pass

    def _highlight_continuous_matches(self) -> None:
        """Highlight active search keyword spans across all boxes in Continuous Dialog View."""
        if self.var_preview_compiled.get():
            return

        self.txt_continuous.tag_remove("search_hit", "1.0", tk.END)
        if not self.active_search_options or not self.active_search_options.query.strip():
            return

        try:
            matcher = self.search_engine._compile_matcher(self.active_search_options)
        except Exception:
            return

        if not self.current_doc or not self.current_doc.boxes:
            text = self.txt_continuous.get("1.0", "end-1c")
            for s, e, _ in matcher(text):
                if e > s:
                    self.txt_continuous.tag_add("search_hit", f"1.0 + {s}c", f"1.0 + {e}c")
            return

        marks = set(self.txt_continuous.mark_names())
        for i in range(len(self.current_doc.boxes)):
            s_mark = f"box_start_{i}"
            e_mark = f"box_end_{i}"
            if s_mark in marks and e_mark in marks:
                box_tx = self.txt_continuous.get(s_mark, e_mark)
                for s, e, _ in matcher(box_tx):
                    if e > s:
                        self.txt_continuous.tag_add(
                            "search_hit",
                            f"{s_mark} + {s}c",
                            f"{s_mark} + {e}c",
                        )

    def _on_speaker_edited(self) -> None:
        """Triggered when editing the pinned Speaker entry in either Page or Continuous mode."""
        self.is_dirty = True
        if self.current_file_path and self.current_file_path in self.open_documents:
            self.open_documents[self.current_file_path]["dirty"] = True
            self._refresh_opened_files_list()
        if not self.current_doc or not self.current_doc.boxes:
            return

        idx = self.current_box_idx
        old_sp = self.current_doc.boxes[idx].speaker
        old_tx = self.current_doc.boxes[idx].clean_text
        new_sp = self.speaker_var.get()
        self._modified_boxes.add(idx)

        if self.var_continuous_view.get():
            if self.var_preview_compiled.get():
                cur_tx = self.current_doc.boxes[idx].clean_text
            else:
                s_mark = f"box_start_{idx}"
                e_mark = f"box_end_{idx}"
                cur_tx = (
                    self.txt_continuous.get(s_mark, e_mark)
                    if s_mark in self.txt_continuous.mark_names()
                    else self.current_doc.boxes[idx].clean_text
                )
            if old_sp != new_sp:
                self.undo_journal.record(
                    BoxEditDelta(
                        box_index=idx,
                        old_speaker=old_sp,
                        new_speaker=new_sp,
                        old_text=old_tx,
                        new_text=cur_tx,
                        file_path=str(self.current_file_path or ""),
                    ),
                    label=f"Rename speaker #{idx + 1}"
                )
            try:
                self.current_doc.inject_box(idx, new_sp, cur_tx)
                self._refresh_continuous_box_header(idx)
                self._update_raw_view()
            except Exception:
                pass
        else:
            new_tx = (
                self.current_doc.boxes[idx].clean_text
                if self.var_preview_compiled.get()
                else self.txt_dialogue.get("1.0", "end-1c")
            )
            if old_sp != new_sp:
                self.undo_journal.record(
                    BoxEditDelta(
                        box_index=idx,
                        old_speaker=old_sp,
                        new_speaker=new_sp,
                        old_text=old_tx,
                        new_text=new_tx,
                        file_path=str(self.current_file_path or ""),
                    ),
                    label=f"Rename speaker #{idx + 1}"
                )
            try:
                self.current_doc.inject_box(idx, new_sp, new_tx)
                self._update_raw_view()
            except Exception:
                pass

    def _refresh_continuous_box_header(self, box_idx: int) -> None:
        """Update a single box header in Continuous View in-place when its speaker changes."""
        if not self.current_doc or not (0 <= box_idx < len(self.current_doc.boxes)):
            return
        span = self._cont_header_spans.get(box_idx)
        if not span:
            return

        was_disabled = str(self.txt_continuous.cget("state")) == "disabled"
        self._suppress_continuous_events = True
        try:
            if was_disabled:
                self.txt_continuous.config(state="normal")
            box = self.current_doc.boxes[box_idx]
            hdr_start, hdr_end = span
            self.txt_continuous.delete(hdr_start, hdr_end)

            badge = f"[Box #{box_idx + 1:03d}]"
            speaker_disp = box.speaker if box.speaker else "(Narration)"
            speaker_tag = "cont_speaker" if box.speaker else "cont_narrator"
            voice_disp = f"   ♪ {box.voice_cue}" if box.voice_cue else ""

            self.txt_continuous.insert(hdr_start, badge + "  ", ("cont_badge",))
            cur = self.txt_continuous.index(f"{hdr_start} + {len(badge) + 2}c")
            self.txt_continuous.insert(cur, speaker_disp, (speaker_tag,))
            cur = self.txt_continuous.index(f"{cur} + {len(speaker_disp)}c")
            if voice_disp:
                self.txt_continuous.insert(cur, voice_disp, ("cont_voice",))
                cur = self.txt_continuous.index(f"{cur} + {len(voice_disp)}c")
            self.txt_continuous.insert(cur, "\n")
            new_end = self.txt_continuous.index(f"{cur} + 1c")

            self._cont_header_spans[box_idx] = (hdr_start, new_end)
            if box_idx == self.current_box_idx:
                self.txt_continuous.tag_add("cont_active_header", hdr_start, new_end)
        finally:
            if was_disabled:
                self.txt_continuous.config(state="disabled")
            self._suppress_continuous_events = False

    def _on_dialogue_edited(self) -> None:
        """Triggered on every keystroke in the single-box Game Display dialogue editor."""
        if self.var_preview_compiled.get():
            return
        self.is_dirty = True
        if self.current_file_path and self.current_file_path in self.open_documents:
            self.open_documents[self.current_file_path]["dirty"] = True
            self._refresh_opened_files_list()

        if self.current_doc and self.current_doc.boxes:
            idx = self.current_box_idx
            old_sp = self.current_doc.boxes[idx].speaker
            old_tx = self.current_doc.boxes[idx].clean_text
            new_sp = self.speaker_var.get()
            new_tx = self.txt_dialogue.get("1.0", "end-1c")
            if old_tx != new_tx or old_sp != new_sp:
                self.undo_journal.record(
                    BoxEditDelta(
                        box_index=idx,
                        old_speaker=old_sp,
                        new_speaker=new_sp,
                        old_text=old_tx,
                        new_text=new_tx,
                        file_path=str(self.current_file_path or ""),
                    ),
                    label=f"Edit box #{idx + 1}"
                )
            self._modified_boxes.add(idx)
            try:
                self.current_doc.inject_box(idx, new_sp, new_tx)
                self._update_raw_view()
            except Exception:
                pass
        else:
            old_content = self._plain_text_content
            new_content = self.txt_dialogue.get("1.0", "end-1c")
            if old_content != new_content:
                self.undo_journal.record(
                    PlainTextDelta(
                        file_path=str(self.current_file_path or ""),
                        old_content=old_content,
                        new_content=new_content,
                    ),
                    label=f"Edit {self.current_file_path.name if self.current_file_path else 'text'}"
                )
            self._plain_text_content = new_content

        self._auto_resize_dialogue_box()
        self._highlight_ngui_tags()
        self._highlight_dialogue_matches()

    def on_prev_box(self) -> None:
        if self.current_doc and self.current_box_idx > 0:
            self.current_box_idx -= 1
            if self.var_continuous_view.get():
                self._focus_continuous_box(self.current_box_idx, move_cursor=True)
            else:
                self._update_views()

    def on_next_box(self) -> None:
        if self.current_doc and self.current_box_idx < len(self.current_doc.boxes) - 1:
            self.current_box_idx += 1
            if self.var_continuous_view.get():
                self._focus_continuous_box(self.current_box_idx, move_cursor=True)
            else:
                self._update_views()

    def on_revert_box(self) -> None:
        if self.current_file_path:
            self.open_file(self.current_file_path)

    def on_insert_playername(self) -> None:
        self.apply_ngui_wrapper("{playername}", "")

    # -------------------------------------------------------------------------
    # Save & Patch Actions (Byte-Exact In-Place Repack)
    # -------------------------------------------------------------------------
    def on_save(self) -> None:
        """Repack and save the active file in-place, with optional XUAT dictionary sync."""
        if not self.current_file_path:
            messagebox.showinfo("Nothing to Save", "No active file is open.")
            return

        backup_dir = self._get_backup_dir()

        if not self.is_bundle_file and not self.current_doc:
            try:
                if self.current_file_path.is_file() and backup_dir:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    bak_path = backup_dir / f"{self.current_file_path.stem}.bak_{ts}{self.current_file_path.suffix}"
                    shutil.copy2(self.current_file_path, bak_path)
                content = self.txt_dialogue.get("1.0", "end-1c")
                self.current_file_path.write_text(content, encoding="utf-8")
                self.is_dirty = False
                self._plain_text_content = content
                if self.current_file_path in self.open_documents:
                    self.open_documents[self.current_file_path]["dirty"] = False
                    self._refresh_opened_files_list()
                self.lbl_status.config(text=f"[SAVED] {self.current_file_path.name} saved successfully!")
                self.logger.info("File I/O", f"Saved plain text file '{self.current_file_path}' (backup in {backup_dir.name})")
            except Exception as e:
                self.logger.exception(f"Failed to save text file '{self.current_file_path}':", e)
                messagebox.showerror("Save Failed", f"Failed to save text file:\n{e}")
            return

        if self.var_preview_compiled.get():
            new_sp = self.speaker_var.get()
            cur_tx = self.current_doc.boxes[self.current_box_idx].clean_text
            self.current_doc.inject_box(self.current_box_idx, new_sp, cur_tx)
        elif self.var_continuous_view.get():
            self._sync_continuous_box_from_widget()
            new_sp = self.speaker_var.get()
            cur_tx = self.current_doc.boxes[self.current_box_idx].clean_text
            self.current_doc.inject_box(self.current_box_idx, new_sp, cur_tx)
        else:
            new_sp = self.speaker_var.get()
            new_tx = self.txt_dialogue.get("1.0", "end-1c")
            self.current_doc.inject_box(self.current_box_idx, new_sp, new_tx)
            self._modified_boxes.add(self.current_box_idx)

        try:
            if self.is_bundle_file:
                written_size = save_bundle_story(
                    self.current_unity_env,
                    self.current_text_obj,
                    self.current_doc,
                    self.current_file_path,
                    backup_dir=backup_dir
                )
                self.is_dirty = False
                if self.current_file_path in self.open_documents:
                    self.open_documents[self.current_file_path]["dirty"] = False
                    self._refresh_opened_files_list()
                self.lbl_status.config(text=f"[SAVED & PATCHED] {self.current_file_path.name} ({written_size / 1024:.1f} KB) in-place successfully!")
                self.logger.info("File I/O", f"Patched bundle '{self.current_file_path}' ({written_size} bytes)")
            else:
                if self.current_file_path.is_file() and backup_dir:
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    bak_path = backup_dir / f"{self.current_file_path.stem}.bak_{ts}{self.current_file_path.suffix}"
                    shutil.copy2(self.current_file_path, bak_path)
                v2_text = self.current_doc.to_v2_text()
                self.current_file_path.write_text(v2_text, encoding="utf-8")
                self.is_dirty = False
                if self.current_file_path in self.open_documents:
                    self.open_documents[self.current_file_path]["dirty"] = False
                    self._refresh_opened_files_list()
                self.lbl_status.config(text=f"[SAVED] {self.current_file_path.name} saved successfully!")
                self.logger.info("File I/O", f"Saved v2 script '{self.current_file_path}'")

            if self.var_sync_xuat.get() and self.xuat_search_roots:
                boxes_to_sync = sorted(self._modified_boxes) if self._modified_boxes else [self.current_box_idx]
                synced_files: Set[str] = set()
                for b_idx in boxes_to_sync:
                    if not (0 <= b_idx < len(self.current_doc.boxes)):
                        continue
                    box_obj = self.current_doc.boxes[b_idx]
                    orig_key = self._original_box_texts.get(b_idx, box_obj.clean_text)
                    matches = self.sync_manager.find_and_update(
                        japanese_key=orig_key,
                        new_english_text=box_obj.clean_text,
                        search_roots=self.xuat_search_roots,
                        backup=True,
                        backup_dir=backup_dir
                    )
                    for m in matches:
                        synced_files.add(m.file_path.name)
                    self._original_box_texts[b_idx] = box_obj.clean_text

                if synced_files:
                    files_str = ", ".join(sorted(synced_files))
                    self.lbl_status.config(text=self.lbl_status.cget("text") + f" | Synced XUAT file(s): {files_str}")
                    self.logger.info("XUAT Sync", f"Synced XUAT file(s): {files_str}")

            self._modified_boxes.clear()

        except Exception as e:
            self.logger.exception(f"Save/Patch failed for '{self.current_file_path}':", e)
            messagebox.showerror("Save Failed", f"Failed to repack or save:\n{e}")

    def on_reload(self) -> None:
        if self.current_file_path:
            self.open_file(self.current_file_path)

    # -------------------------------------------------------------------------
    # Search Engine, Background Worker & Substring Result Highlighting
    # -------------------------------------------------------------------------
    def on_start_search(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            return

        opts = SearchOptions(
            query=query,
            match_case=self.var_case.get(),
            use_regex=self.var_regex.get(),
            ignore_whitespace=self.var_ignore_ws.get(),
            include_bundles=self.var_inc_bundles.get(),
            include_text=self.var_inc_text.get()
        )
        self.active_search_options = opts

        scope = self.scope_var.get()
        target_paths: List[Path] = []

        if scope == "current":
            if self.current_file_path:
                target_paths = [self.current_file_path]
            else:
                messagebox.showinfo("Search", "No file is currently open.")
                return
        elif scope == "folder":
            if self.selected_search_folder and self.selected_search_folder.is_dir():
                target_paths = [self.selected_search_folder]
            else:
                fld = filedialog.askdirectory(title="Select Folder to Search In")
                if not fld:
                    return
                self.selected_search_folder = Path(fld)
                target_paths = [self.selected_search_folder]
        else:
            target_paths = list(self.xuat_search_roots)
            for p in (Path("input"), Path("output"), SCRIPT_DIR.parent / "input", SCRIPT_DIR.parent / "output"):
                if p.exists() and p not in target_paths:
                    target_paths.append(p)

        self._reset_search_results_state()
        self.lbl_results_title.config(text="Searching...")
        self.btn_find.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.progress_bar.pack(fill="x", padx=8, pady=(0, 2))
        self.progress_bar["value"] = 0
        self.search_cancel_flag = False
        self.logger.info("Search", f"Started search query='{query}' scope={scope} roots={len(target_paths)}")

        t = threading.Thread(target=self._run_background_search, args=(target_paths, opts), daemon=True)
        t.start()

    def _reset_search_results_state(self) -> None:
        self.active_search_results.clear()
        self.search_file_groups.clear()
        self._file_group_lookup.clear()
        self._result_line_map.clear()
        self._result_idx_to_line.clear()
        self._selected_result_idx = None

        self.txt_results.config(state="normal")
        self.txt_results.delete("1.0", tk.END)
        self.txt_results.config(state="disabled")

    def on_cancel_search(self) -> None:
        self.search_cancel_flag = True
        self.btn_cancel.config(state="disabled")
        self.lbl_status.config(text="Cancelling search...")
        self.logger.info("Search", "Search cancelled by user.")

    def _run_background_search(self, paths: List[Path], options: SearchOptions) -> None:
        """Executed inside a background daemon thread."""
        total_found = 0

        def on_prog(cur, tot, filename):
            self.search_queue.put(("progress", cur, tot, filename))

        for target in paths:
            if self.search_cancel_flag:
                break
            if target.is_file():
                results = self.search_engine.search_file(target, options)
            else:
                results = self.search_engine.search_directory(
                    target, options, recursive=True,
                    on_progress=on_prog,
                    should_cancel=lambda: self.search_cancel_flag
                )

            total_found += len(results)
            self.search_queue.put(("batch", results))

        self.search_queue.put(("finished", total_found))

    def _process_search_queue(self) -> None:
        """Polls results from background worker thread and renders highlighted hits."""
        try:
            while True:
                msg = self.search_queue.get_nowait()
                kind = msg[0]

                if kind == "progress":
                    _, cur, tot, fname = msg
                    if tot > 0:
                        pct = int((cur / tot) * 100)
                        self.progress_bar["value"] = pct
                        self.lbl_status.config(text=f"Searching ({cur}/{tot}): {fname}")

                elif kind == "batch":
                    batch_results: List[SearchResult] = msg[1]
                    if batch_results:
                        for r in batch_results:
                            res_idx = len(self.active_search_results)
                            self.active_search_results.append(r)
                            fkey = str(r.file_path)
                            grp = self._file_group_lookup.get(fkey)
                            if grp is None:
                                grp = {
                                    "key": fkey,
                                    "path": r.file_path,
                                    "collapsed": False,
                                    "indices": [],
                                }
                                self._file_group_lookup[fkey] = grp
                                self.search_file_groups.append(grp)
                            grp["indices"].append(res_idx)
                        self._render_search_results()

                elif kind == "finished":
                    total = len(self.active_search_results)
                    self.lbl_results_title.config(text=f"Search Results ({total} matches)")
                    self.lbl_status.config(text=f"Search complete. Found {total} matches.")
                    self.btn_find.config(state="normal")
                    self.btn_cancel.config(state="disabled")
                    self.progress_bar.pack_forget()
                    self.logger.info("Search", f"Search finished. Total matches={total}")
                    if not self.var_preview_compiled.get():
                        if self.var_continuous_view.get():
                            self._highlight_continuous_matches()
                        else:
                            self._highlight_dialogue_matches()

        except queue.Empty:
            pass

        self.after(100, self._process_search_queue)

    def _render_search_results(self) -> None:
        """Render grouped search hits with WCAG contrast-safe inline keyword highlighting."""
        y_frac = self.txt_results.yview()[0]
        self._result_line_map.clear()
        self._result_idx_to_line.clear()

        self.txt_results.config(state="normal")
        self.txt_results.delete("1.0", tk.END)

        line_no = 1
        for grp in self.search_file_groups:
            fp: Path = grp["path"]
            indices: List[int] = grp["indices"]
            collapsed: bool = grp["collapsed"]
            arrow = "▶" if collapsed else "▼"
            count_word = "match" if len(indices) == 1 else "matches"
            header_text = f"{arrow} {fp.name} ({len(indices)} {count_word})\n"

            self.txt_results.insert(f"{line_no}.0", header_text, ("file_header",))
            self._result_line_map[line_no] = ("header", grp["key"])
            line_no += 1

            if collapsed:
                continue

            for res_idx in indices:
                r = self.active_search_results[res_idx]
                box_str = f"[Box #{r.box_index + 1}]" if r.box_index is not None else f"[Line {r.line_number}]"
                prefix_indent = "  "
                speaker_prefix = f" {r.speaker}: " if r.speaker else " "
                snippet = r.match_snippet

                row_tags = ("selected_row",) if res_idx == self._selected_result_idx else ()

                self.txt_results.insert(f"{line_no}.0", prefix_indent, row_tags)
                self.txt_results.insert(f"{line_no}.end", box_str, ("box_badge",) + row_tags)
                if r.speaker:
                    self.txt_results.insert(f"{line_no}.end", speaker_prefix, ("speaker_tag",) + row_tags)
                else:
                    self.txt_results.insert(f"{line_no}.end", speaker_prefix, row_tags)

                snip_col_start = len(prefix_indent) + len(box_str) + len(speaker_prefix)
                self.txt_results.insert(f"{line_no}.end", snippet + "\n", row_tags)

                if r.match_in_speaker and r.speaker:
                    sp_offset = len(prefix_indent) + len(box_str) + 1
                    hs = sp_offset + max(0, r.snippet_start)
                    he = sp_offset + max(r.snippet_start, r.snippet_end)
                    if he > hs:
                        self.txt_results.tag_add("match_hl", f"{line_no}.{hs}", f"{line_no}.{he}")
                else:
                    hs = snip_col_start + max(0, r.snippet_start)
                    he = snip_col_start + max(r.snippet_start, r.snippet_end)
                    if he > hs:
                        self.txt_results.tag_add("match_hl", f"{line_no}.{hs}", f"{line_no}.{he}")

                self._result_line_map[line_no] = ("item", res_idx)
                self._result_idx_to_line[res_idx] = line_no
                line_no += 1

        self.txt_results.config(state="disabled")
        self.txt_results.yview_moveto(y_frac)

    def _on_results_click(self, event: tk.Event) -> str:
        """Handle clicking a file header (collapse/expand) or a match row (jump & highlight)."""
        self.txt_results.focus_set()
        idx_str = self.txt_results.index(f"@{event.x},{event.y}")
        line_no = int(idx_str.split(".")[0])
        entry = self._result_line_map.get(line_no)
        if not entry:
            return "break"

        kind, payload = entry
        if kind == "header":
            grp = self._file_group_lookup.get(payload)
            if grp is not None:
                grp["collapsed"] = not grp["collapsed"]
                self._render_search_results()
        elif kind == "item":
            self._select_result_index(int(payload), jump=True)
        return "break"

    def _on_results_step(self, delta: int) -> str:
        """Navigate up/down through visible search hits using keyboard arrow keys."""
        if not self.active_search_results:
            return "break"

        if self._selected_result_idx is None:
            next_idx = 0
        else:
            next_idx = max(0, min(len(self.active_search_results) - 1, self._selected_result_idx + delta))

        self._select_result_index(next_idx, jump=True)
        return "break"

    def _select_result_index(self, idx: int, jump: bool = True) -> None:
        """Highlight selected search row and jump to the matching file/box."""
        if not (0 <= idx < len(self.active_search_results)):
            return

        self._selected_result_idx = idx
        res = self.active_search_results[idx]

        grp = self._file_group_lookup.get(str(res.file_path))
        if grp and grp["collapsed"]:
            grp["collapsed"] = False
            self._render_search_results()
        else:
            self.txt_results.config(state="normal")
            self.txt_results.tag_remove("selected_row", "1.0", tk.END)
            target_line = self._result_idx_to_line.get(idx)
            if target_line is not None:
                self.txt_results.tag_add("selected_row", f"{target_line}.0", f"{target_line}.end")
                self.txt_results.see(f"{target_line}.0")
            self.txt_results.config(state="disabled")

        if not jump:
            return

        if self.var_preview_compiled.get():
            self.var_preview_compiled.set(False)

        if not self.current_file_path or self.current_file_path != res.file_path:
            self.open_file(res.file_path)

        if res.box_index is not None and self.current_doc:
            self.current_box_idx = res.box_index
            if self.var_continuous_view.get():
                self._update_views()
                if res.match_in_speaker:
                    self._focus_continuous_box(res.box_index, move_cursor=True)
                    self.entry_speaker.focus_set()
                    self.entry_speaker.selection_range(res.start_pos, res.end_pos)
                else:
                    self._focus_continuous_box(
                        res.box_index,
                        move_cursor=True,
                        char_offset=res.start_pos,
                        explicit_span=(res.start_pos, res.end_pos),
                    )
                    self.txt_continuous.focus_set()
            else:
                self._update_views()
                if res.match_in_speaker:
                    self.entry_speaker.focus_set()
                    self.entry_speaker.selection_range(res.start_pos, res.end_pos)
                else:
                    self._highlight_dialogue_matches((res.start_pos, res.end_pos))
                    self.txt_dialogue.focus_set()
        elif not self.current_doc and res.line_number > 0:
            self._update_views()
            target_widget = self.txt_continuous if self.var_continuous_view.get() else self.txt_dialogue
            target_widget.tag_remove("search_hit", "1.0", tk.END)
            s_idx = f"{res.line_number}.{res.start_pos}"
            e_idx = f"{res.line_number}.{res.end_pos}"
            target_widget.tag_add("search_hit", s_idx, e_idx)
            target_widget.see(s_idx)
            target_widget.focus_set()

    def on_clear_search(self) -> None:
        self.active_search_options = None
        self._reset_search_results_state()
        self.txt_dialogue.tag_remove("search_hit", "1.0", tk.END)
        self.txt_continuous.tag_remove("search_hit", "1.0", tk.END)
        self.lbl_results_title.config(text="Search Results (0 matches)")

    # -------------------------------------------------------------------------
    # Dialogs & Helpers
    # -------------------------------------------------------------------------
    def on_open_file(self) -> None:
        f = filedialog.askopenfilename(
            title="Open Story Asset or Script",
            filetypes=[
                ("Priconne Assets & Scripts", "*.unity3d;*.asset;*.txt;*.json"),
                ("Unity3D Bundles", "*.unity3d;*.asset"),
                ("Text Scripts", "*.txt;*.json"),
                ("All Files", "*.*")
            ]
        )
        if f:
            self.open_file(f)

    def on_open_folder(self) -> None:
        f = filedialog.askdirectory(title="Open Project or Asset Folder")
        if f:
            self.selected_search_folder = Path(f)
            self.folder_path_var.set(str(f))
            self.scope_var.set("folder")
            self._sync_scope_widgets()
            self.lbl_status.config(text=f"Selected folder for search: {f}")

    def _sync_scope_widgets(self) -> None:
        """Show or hide folder path entry and browse button based on scope selection."""
        if hasattr(self, "folder_path_entry") and hasattr(self, "btn_browse_search_folder"):
            if self.scope_var.get() == "folder":
                self.folder_path_entry.pack(side="left", padx=2)
                self.btn_browse_search_folder.pack(side="left", padx=(0, 4))
                if self.selected_search_folder:
                    self.folder_path_var.set(str(self.selected_search_folder))
            else:
                self.folder_path_entry.pack_forget()
                self.btn_browse_search_folder.pack_forget()

    # -------------------------------------------------------------------------
    # Search & Replace Actions (Find, Replace, Replace All, Multi-File Confirmation)
    # -------------------------------------------------------------------------
    def on_show_find(self) -> None:
        if not getattr(self, "_search_bar_visible", False):
            self.search_frame.pack(before=self.outer_v_paned, fill="x", padx=8, pady=(6, 4))
            self._search_bar_visible = True
        if getattr(self, "_replace_row_visible", False):
            self.row_replace.pack_forget()
            self._replace_row_visible = False
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)

    def on_show_find_in_files(self) -> None:
        self.scope_var.set("project")
        self.on_show_find()

    def on_show_replace(self) -> None:
        if not getattr(self, "_search_bar_visible", False):
            self.search_frame.pack(before=self.outer_v_paned, fill="x", padx=8, pady=(6, 4))
            self._search_bar_visible = True
        if not getattr(self, "_replace_row_visible", False):
            children = self.search_frame.winfo_children()
            row1 = children[0] if children else None
            if row1:
                self.row_replace.pack(fill="x", padx=8, pady=(0, 4), after=row1)
            else:
                self.row_replace.pack(fill="x", padx=8, pady=(0, 4))
            self._replace_row_visible = True
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)

    def _hide_search_bar(self) -> None:
        if hasattr(self, "search_frame"):
            self.search_frame.pack_forget()
            self._search_bar_visible = False
            target = self.txt_continuous if self.var_continuous_view.get() else self.txt_dialogue
            target.focus_set()

    def on_replace_next(self) -> None:
        """Find and replace the next occurrence in the active file."""
        find_text = self.search_var.get()
        replace_text = self.replace_var.get()
        if not find_text:
            return

        if not self.current_file_path:
            messagebox.showinfo("Replace", "No active file open to replace in.")
            return

        if self.current_doc and self.current_doc.boxes:
            box = self.current_doc.boxes[self.current_box_idx]
            if find_text in box.clean_text:
                old_sp = box.speaker
                old_tx = box.clean_text
                new_tx = box.clean_text.replace(find_text, replace_text, 1)
                self.undo_journal.record(
                    BoxEditDelta(
                        box_index=self.current_box_idx,
                        old_speaker=old_sp,
                        new_speaker=old_sp,
                        old_text=old_tx,
                        new_text=new_tx,
                        file_path=str(self.current_file_path),
                    ),
                    label=f"Replace in box #{self.current_box_idx + 1}"
                )
                self.current_doc.inject_box(self.current_box_idx, None, new_tx)
                self.is_dirty = True
                self._modified_boxes.add(self.current_box_idx)
                if self.current_file_path in self.open_documents:
                    self.open_documents[self.current_file_path]["dirty"] = True
                    self._refresh_opened_files_list()
                self._update_views()
                self.lbl_status.config(text=f"Replaced 1 occurrence in Box #{self.current_box_idx + 1}")
                return

            total = len(self.current_doc.boxes)
            for i in range(1, total):
                next_idx = (self.current_box_idx + i) % total
                if find_text in self.current_doc.boxes[next_idx].clean_text:
                    self.current_box_idx = next_idx
                    self._update_views()
                    self.lbl_status.config(text=f"Found match in Box #{next_idx + 1}. Press Replace again to replace.")
                    return
            messagebox.showinfo("Replace", f"No more occurrences of '{find_text}' found.")
        elif not self.current_doc and self.current_file_path:
            cur_tx = self._plain_text_content
            if find_text in cur_tx:
                new_tx = cur_tx.replace(find_text, replace_text, 1)
                self.undo_journal.record(
                    PlainTextDelta(
                        file_path=str(self.current_file_path),
                        old_content=cur_tx,
                        new_content=new_tx,
                    ),
                    label=f"Replace in {self.current_file_path.name}"
                )
                self._plain_text_content = new_tx
                self.is_dirty = True
                if self.current_file_path in self.open_documents:
                    self.open_documents[self.current_file_path]["dirty"] = True
                    self._refresh_opened_files_list()
                self._update_views()
                self.lbl_status.config(text=f"Replaced 1 occurrence in {self.current_file_path.name}")
            else:
                messagebox.showinfo("Replace", f"'{find_text}' not found in current file.")

    def on_replace_all(self) -> None:
        """Replace all occurrences in current file or across project/folder."""
        find_text = self.search_var.get()
        replace_text = self.replace_var.get()
        if not find_text:
            return

        scope = self.scope_var.get()
        if scope == "current":
            if not self.current_file_path:
                messagebox.showinfo("Replace All", "No active file open.")
                return
            if self.current_doc and self.current_doc.boxes:
                count = 0
                self.undo_journal.begin_batch(f"Replace All '{find_text}' in {self.current_file_path.name}")
                for idx, box in enumerate(self.current_doc.boxes):
                    if find_text in box.clean_text:
                        old_sp = box.speaker
                        old_tx = box.clean_text
                        new_tx = box.clean_text.replace(find_text, replace_text)
                        self.undo_journal.record(
                            BoxEditDelta(
                                box_index=idx,
                                old_speaker=old_sp,
                                new_speaker=old_sp,
                                old_text=old_tx,
                                new_text=new_tx,
                                file_path=str(self.current_file_path),
                            )
                        )
                        self.current_doc.inject_box(idx, None, new_tx)
                        self._modified_boxes.add(idx)
                        count += 1
                self.undo_journal.end_batch()
                if count > 0:
                    self.is_dirty = True
                    if self.current_file_path in self.open_documents:
                        self.open_documents[self.current_file_path]["dirty"] = True
                        self._refresh_opened_files_list()
                    self._update_views()
                    self.lbl_status.config(text=f"Replaced in {count} box(es) in {self.current_file_path.name}")
                    self.logger.info("Search", f"Replaced all '{find_text}' -> '{replace_text}' in {count} boxes of {self.current_file_path.name}")
                else:
                    messagebox.showinfo("Replace All", f"'{find_text}' not found in current file.")
            elif not self.current_doc and self.current_file_path:
                cur_tx = self._plain_text_content
                if find_text in cur_tx:
                    occurrences = cur_tx.count(find_text)
                    new_tx = cur_tx.replace(find_text, replace_text)
                    self.undo_journal.record(
                        PlainTextDelta(
                            file_path=str(self.current_file_path),
                            old_content=cur_tx,
                            new_content=new_tx,
                        ),
                        label=f"Replace All in {self.current_file_path.name}"
                    )
                    self._plain_text_content = new_tx
                    self.is_dirty = True
                    if self.current_file_path in self.open_documents:
                        self.open_documents[self.current_file_path]["dirty"] = True
                        self._refresh_opened_files_list()
                    self._update_views()
                    self.lbl_status.config(text=f"Replaced {occurrences} occurrence(s) in {self.current_file_path.name}")
                else:
                    messagebox.showinfo("Replace All", f"'{find_text}' not found in current file.")
        else:
            # Multi-file Replace All
            target_roots: List[Path] = []
            if scope == "folder":
                fp = self.folder_path_var.get().strip() or (str(self.selected_search_folder) if self.selected_search_folder else "")
                if fp and Path(fp).exists():
                    target_roots = [Path(fp)]
                else:
                    messagebox.showerror("Replace All", "Please select a valid folder for Folder scope.")
                    return
            else:
                target_roots = list(self.xuat_search_roots)

            inc_bdl = self.var_inc_bundles.get()
            inc_txt = self.var_inc_text.get()

            matching_files: Dict[Path, int] = {}
            total_matches = 0
            candidate_files: List[Path] = []
            for root in target_roots:
                if root.is_file():
                    candidate_files.append(root)
                elif root.is_dir():
                    if inc_bdl:
                        candidate_files.extend(root.rglob("*.unity3d"))
                        candidate_files.extend(root.rglob("*.asset"))
                    if inc_txt:
                        candidate_files.extend(root.rglob("*.txt"))

            for cf in candidate_files:
                try:
                    if cf.suffix.lower() in (".unity3d", ".asset"):
                        raw = cf.read_bytes()
                        c = raw.count(find_text.encode("utf-8", "ignore"))
                        if c > 0:
                            matching_files[cf] = c
                            total_matches += c
                    else:
                        txt = cf.read_text(encoding="utf-8", errors="ignore")
                        c = txt.count(find_text)
                        if c > 0:
                            matching_files[cf] = c
                            total_matches += c
                except Exception:
                    pass

            if not matching_files:
                messagebox.showinfo("Replace All", f"No matches for '{find_text}' found across {len(candidate_files)} files.")
                return

            confirm_msg = (
                f"Replace All across multiple files:\n\n"
                f"Search query: '{find_text}'\n"
                f"Replacement:  '{replace_text}'\n\n"
                f"Found ~{total_matches} match(es) across {len(matching_files)} file(s).\n\n"
                f"Proceed with replacement?"
            )
            ans = messagebox.askyesno(
                "Confirm Multi-File Replace All",
                confirm_msg,
                default=messagebox.NO,
                icon=messagebox.WARNING
            )
            if not ans:
                return

            replaced_files_count = 0
            per_file_deltas: List[Tuple[str, str, str]] = []

            for fpath in matching_files:
                try:
                    if fpath.suffix.lower() in (".unity3d", ".asset"):
                        doc, env, obj, _ = load_bundle_story(fpath)
                        modified = False
                        for idx, box in enumerate(doc.boxes):
                            if find_text in box.clean_text:
                                new_box_tx = box.clean_text.replace(find_text, replace_text)
                                doc.inject_box(idx, None, new_box_tx)
                                modified = True
                        if modified:
                            save_bundle_story(env, obj, doc, fpath, backup_dir=self._get_backup_dir())
                            replaced_files_count += 1
                    else:
                        old_txt = fpath.read_text(encoding="utf-8", errors="replace")
                        if find_text in old_txt:
                            new_txt = old_txt.replace(find_text, replace_text)
                            bak_dir = self._get_backup_dir()
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            bak_path = bak_dir / f"{fpath.stem}.bak_{ts}{fpath.suffix}"
                            shutil.copy2(fpath, bak_path)
                            fpath.write_text(new_txt, encoding="utf-8")
                            per_file_deltas.append((str(fpath), old_txt, new_txt))
                            replaced_files_count += 1
                except Exception as ex:
                    self.logger.error("Search", f"Failed replacing in {fpath}: {ex}")

            if per_file_deltas:
                self.undo_journal.record(
                    BulkFileDelta(
                        description=f"Replace '{find_text}' -> '{replace_text}' in {len(per_file_deltas)} files",
                        per_file=per_file_deltas,
                    )
                )

            if self.current_file_path and self.current_file_path in matching_files:
                self.open_file(self.current_file_path, reload_from_disk=True)

            self.lbl_status.config(text=f"Bulk Replace Complete: Updated {replaced_files_count} file(s).")
            self.logger.info("Search", f"Bulk replaced '{find_text}' -> '{replace_text}' in {replaced_files_count} file(s)")
            messagebox.showinfo("Replace All Complete", f"Successfully replaced '{find_text}' across {replaced_files_count} file(s).")

    # -------------------------------------------------------------------------
    # Undo / Redo Actions (#3A)
    # -------------------------------------------------------------------------
    def on_undo(self) -> None:
        """Undo the most recent operation from MasterUndoJournal."""
        op = self.undo_journal.pop_undo()
        if not op:
            self.lbl_status.config(text="Nothing to undo.")
            return
        for delta in reversed(op.deltas):
            self._apply_delta(delta, reverse=True)
        self.lbl_status.config(text=f"Undid: {op.label}")
        self.logger.info("Edit", f"Undid operation: {op.label}")

    def on_redo(self) -> None:
        """Redo the most recent undone operation from MasterUndoJournal."""
        op = self.undo_journal.pop_redo()
        if not op:
            self.lbl_status.config(text="Nothing to redo.")
            return
        for delta in op.deltas:
            self._apply_delta(delta, reverse=False)
        self.lbl_status.config(text=f"Redid: {op.label}")
        self.logger.info("Edit", f"Redid operation: {op.label}")

    def _apply_delta(self, delta: Any, reverse: bool = False) -> None:
        """Apply a recorded delta forwards or backwards."""
        if isinstance(delta, BoxEditDelta):
            target_sp = delta.old_speaker if reverse else delta.new_speaker
            target_tx = delta.old_text if reverse else delta.new_text
            target_file = Path(delta.file_path) if delta.file_path else None
            if target_file and target_file != self.current_file_path:
                self.open_file(target_file)
            if self.current_doc and 0 <= delta.box_index < len(self.current_doc.boxes):
                self.current_doc.inject_box(delta.box_index, target_sp, target_tx)
                self.current_box_idx = delta.box_index
                self.is_dirty = True
                self._modified_boxes.add(delta.box_index)
                if self.current_file_path in self.open_documents:
                    self.open_documents[self.current_file_path]["dirty"] = True
                    self._refresh_opened_files_list()
                self._update_views()
        elif isinstance(delta, PlainTextDelta):
            target_tx = delta.old_content if reverse else delta.new_content
            target_file = Path(delta.file_path) if delta.file_path else None
            if target_file and target_file != self.current_file_path:
                self.open_file(target_file)
            self._plain_text_content = target_tx
            self.is_dirty = True
            if self.current_file_path in self.open_documents:
                self.open_documents[self.current_file_path]["dirty"] = True
                self._refresh_opened_files_list()
            self._update_views()
        elif isinstance(delta, BulkFileDelta):
            for fpath_str, old_tx, new_tx in delta.per_file:
                fp = Path(fpath_str)
                text_to_set = old_tx if reverse else new_tx
                try:
                    fp.write_text(text_to_set, encoding="utf-8")
                except Exception as ex:
                    self.logger.error("File I/O", f"Failed applying bulk delta to {fp}: {ex}")
            if self.current_file_path:
                self.open_file(self.current_file_path, reload_from_disk=True)

    def _sync_edit_menu_states(self) -> None:
        """Dynamically update Undo/Redo labels and states in Edit menu."""
        if not hasattr(self, "edit_menu"):
            return
        try:
            can_u = self.undo_journal.can_undo()
            u_lbl = self.undo_journal.undo_label()
            self.edit_menu.entryconfigure(0, label=f"Undo {u_lbl}" if u_lbl else "Undo", state="normal" if can_u else "disabled")
            can_r = self.undo_journal.can_redo()
            r_lbl = self.undo_journal.redo_label()
            self.edit_menu.entryconfigure(1, label=f"Redo {r_lbl}" if r_lbl else "Redo", state="normal" if can_r else "disabled")
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Left Dock Tabs & Opened Files Cache Actions (#3B)
    # -------------------------------------------------------------------------
    def _switch_dock_tab(self, tab_name: str) -> None:
        """Switch left dock between Search Results and Opened Files."""
        self._left_dock_tab = tab_name
        t = self.theme
        active_fg = best_contrast_fg(t["misora_pink"])
        normal_fg = best_contrast_fg(t["bg_panel"], t["fg_text"], "#ffffff")

        if tab_name == "files":
            self.tab_search_frame.pack_forget()
            self.tab_files_frame.pack(fill="both", expand=True)
            self.btn_tab_files.configure(bg=t["misora_pink"], fg=active_fg)
            self.btn_tab_search.configure(bg=t["bg_panel"], fg=normal_fg)
            self._refresh_opened_files_list()
        else:
            self.tab_files_frame.pack_forget()
            self.tab_search_frame.pack(fill="both", expand=True)
            self.btn_tab_search.configure(bg=t["misora_pink"], fg=active_fg)
            self.btn_tab_files.configure(bg=t["bg_panel"], fg=normal_fg)

    def _toggle_dock_collapse(self) -> None:
        """Toggle left dock between collapsed and expanded width."""
        current_w = self.left_frame.winfo_width()
        if current_w > 50:
            self._left_dock_width = current_w
            self.h_paned.sash_place(0, 20, 0)
        else:
            self.h_paned.sash_place(0, self._left_dock_width or 340, 0)

    def _refresh_opened_files_list(self) -> None:
        """Re-render the list of cached opened files in the Opened Files dock tab."""
        if not hasattr(self, "txt_opened_files"):
            return
        self.txt_opened_files.config(state="normal")
        self.txt_opened_files.delete("1.0", tk.END)
        self._opened_files_line_map: Dict[int, Path] = {}

        count = len(self.open_documents)
        self.lbl_files_title.config(text=f"Opened Files ({count})")

        for idx, (fpath, info) in enumerate(self.open_documents.items(), start=1):
            line_no = idx
            self._opened_files_line_map[line_no] = fpath
            is_active = (fpath == self.current_file_path)
            is_dirty = info.get("dirty", False) or (is_active and self.is_dirty)

            prefix = "● " if is_active else "  "
            dirty_mark = "* " if is_dirty else "  "
            tag_name = "file_active" if is_active else ("file_dirty" if is_dirty else "file_normal")

            self.txt_opened_files.insert(tk.END, prefix, ("file_close",))
            self.txt_opened_files.insert(tk.END, dirty_mark, ("file_dirty" if is_dirty else "file_dim",))
            self.txt_opened_files.insert(tk.END, fpath.name, (tag_name,))

            boxes = info.get("boxes_count", 0)
            detail = f" ({boxes} boxes)" if boxes else f" ({fpath.suffix})"
            self.txt_opened_files.insert(tk.END, detail, ("file_dim",))
            self.txt_opened_files.insert(tk.END, "  [×]\n", ("file_close",))

        self.txt_opened_files.config(state="disabled")

    def _on_opened_files_click(self, event: tk.Event) -> str:
        """Clicking an opened file switches to it; clicking [×] closes it."""
        idx_str = self.txt_opened_files.index(f"@{event.x},{event.y}")
        line_no = int(idx_str.split(".")[0])
        col_no = int(idx_str.split(".")[1])
        fpath = getattr(self, "_opened_files_line_map", {}).get(line_no)
        if not fpath:
            return "break"

        line_text = self.txt_opened_files.get(f"{line_no}.0", f"{line_no}.end")
        if "[×]" in line_text and col_no >= line_text.rfind("[×]"):
            self.close_file(fpath)
        else:
            if fpath != self.current_file_path:
                self.open_file(fpath)
        return "break"

    def close_file(self, file_path: Path) -> None:
        """Close an opened file from in-memory cache, prompting if dirty."""
        file_path = Path(file_path).resolve()
        info = self.open_documents.get(file_path)
        is_dirty = (file_path == self.current_file_path and self.is_dirty) or (info and info.get("dirty", False))

        if is_dirty:
            ans = messagebox.askyesnocancel("Unsaved Changes", f"'{file_path.name}' has unsaved changes.\nSave before closing?")
            if ans is None:
                return
            if ans:
                if file_path == self.current_file_path:
                    self.on_save()
                else:
                    self.open_file(file_path)
                    self.on_save()

        if file_path in self.open_documents:
            del self.open_documents[file_path]

        if file_path == self.current_file_path:
            if self.open_documents:
                next_file = next(iter(self.open_documents))
                self.open_file(next_file)
            else:
                self.current_file_path = None
                self.current_doc = None
                self.current_unity_env = None
                self.current_text_obj = None
                self.is_bundle_file = False
                self.is_dirty = False
                self._plain_text_content = ""
                self._update_views()
                self.lbl_status.config(text="Ready. No files open.")

        self._refresh_opened_files_list()

    # -------------------------------------------------------------------------
    # Right-Click Context Menus & External Editor Launching (#4D)
    # -------------------------------------------------------------------------
    def _on_results_right_click(self, event: tk.Event) -> str:
        """Right-click in search results shows file actions context menu."""
        idx_str = self.txt_results.index(f"@{event.x},{event.y}")
        line_no = int(idx_str.split(".")[0])
        entry = self._result_line_map.get(line_no)
        target_path: Optional[Path] = None
        if entry:
            kind, payload = entry
            if kind == "header":
                target_path = Path(payload)
            elif kind == "item":
                res_idx = int(payload)
                if 0 <= res_idx < len(self.active_search_results):
                    target_path = self.active_search_results[res_idx].file_path
        if target_path and target_path.exists():
            self._show_file_context_menu(event, target_path)
        return "break"

    def _on_opened_files_right_click(self, event: tk.Event) -> str:
        """Right-click in opened files list shows file actions context menu."""
        idx_str = self.txt_opened_files.index(f"@{event.x},{event.y}")
        line_no = int(idx_str.split(".")[0])
        fpath = getattr(self, "_opened_files_line_map", {}).get(line_no)
        if fpath and fpath.exists():
            self._show_file_context_menu(event, fpath)
        return "break"

    def _show_file_context_menu(self, event: tk.Event, target_path: Path) -> None:
        """Show right-click context menu with Open Containing Folder, Open With, Copy Path."""
        t = self.theme
        panel_fg = best_contrast_fg(t["bg_panel"], t["fg_text"], "#ffffff")
        accent_fg = best_contrast_fg(t["misora_pink"])

        menu = tk.Menu(self, tearoff=0, bg=t["bg_panel"], fg=panel_fg, activebackground=t["misora_pink"], activeforeground=accent_fg)

        menu.add_command(label=f"Open '{target_path.name}' in Misora", command=lambda: self.open_file(target_path))
        menu.add_command(label="Open Containing Folder", command=lambda: self._open_containing_folder(target_path))
        menu.add_separator()

        open_with = tk.Menu(menu, tearoff=0, bg=t["bg_panel"], fg=panel_fg, activebackground=t["misora_pink"], activeforeground=accent_fg)
        open_with.add_command(label="Notepad", command=lambda: self._launch_editor_on_file("notepad.exe", target_path))
        if self.notepadpp_path and Path(self.notepadpp_path).exists():
            open_with.add_command(label="Notepad++", command=lambda: self._launch_editor_on_file(str(self.notepadpp_path), target_path))
        if self.external_editor_path and Path(self.external_editor_path).exists():
            open_with.add_command(label=f"Custom: {Path(self.external_editor_path).stem}", command=lambda: self._launch_editor_on_file(str(self.external_editor_path), target_path))
        open_with.add_separator()
        open_with.add_command(label="Choose another app...", command=lambda: self._choose_app_and_open(target_path))
        menu.add_cascade(label="Open With", menu=open_with)

        menu.add_separator()
        menu.add_command(label="Copy Full Path", command=lambda: self._copy_to_clipboard(str(target_path)))
        if target_path in self.open_documents:
            menu.add_command(label="Close File", command=lambda: self.close_file(target_path))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_containing_folder(self, target_path: Path) -> None:
        """Reveal file in Windows Explorer."""
        try:
            if target_path.exists():
                subprocess.Popen(["explorer.exe", f"/select,{target_path}"])
            else:
                subprocess.Popen(["explorer.exe", str(target_path.parent)])
        except Exception as e:
            self.logger.error("File I/O", f"Failed to reveal in explorer: {e}")

    def _launch_editor_on_file(self, exe: str, target_path: Path) -> None:
        """Launch an external editor on target_path, warning if unsaved in Misora."""
        if target_path == self.current_file_path and self.is_dirty:
            warn = messagebox.askokcancel(
                "Unsaved Changes",
                f"'{target_path.name}' has unsaved changes in Misora.\nOpening in an external editor will show the version currently on disk.\nContinue?"
            )
            if not warn:
                return
        try:
            subprocess.Popen([exe, str(target_path)], shell=False)
            self.logger.info("External Tools", f"Opened {target_path.name} in {exe}")
        except Exception as ex:
            self.logger.exception(f"Failed to launch {exe}:", ex)
            messagebox.showerror("Launch Error", f"Failed to launch external editor:\n{ex}")

    def _choose_app_and_open(self, target_path: Path) -> None:
        """One-time browse for application to open file."""
        app = filedialog.askopenfilename(title="Choose Application to Open File", filetypes=[("Executables", "*.exe;*.bat;*.cmd"), ("All Files", "*.*")])
        if app:
            self._launch_editor_on_file(app, target_path)

    def _copy_to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.lbl_status.config(text=f"Copied to clipboard: {text}")

    def _sync_external_editor_menu(self) -> None:
        if not hasattr(self, "_ext_editor_menu"):
            return
        self._ext_editor_menu.delete(0, "end")
        self._ext_editor_menu.add_command(label="Set / Change Editor Program...", command=self.on_set_external_editor)
        self._ext_editor_menu.add_command(label="Clear Editor Selection", command=self.on_clear_external_editor)
        self._ext_editor_menu.add_separator()
        cur_desc = f"Current: {self.external_editor_path.name}" if self.external_editor_path else "Current: (None - default)"
        self._ext_editor_menu.add_command(label=cur_desc, state="disabled")

    def on_set_external_editor(self) -> None:
        f = filedialog.askopenfilename(
            title="Select External Text Editor Executable",
            filetypes=[("Executables", "*.exe;*.bat;*.cmd"), ("All Files", "*.*")]
        )
        if f:
            self.external_editor_path = Path(f)
            self._save_user_prefs(silent=True)
            self.lbl_status.config(text=f"External editor set to: {self.external_editor_path.name}")
            self.logger.info("External Tools", f"Configured external editor: {self.external_editor_path}")

    def on_clear_external_editor(self) -> None:
        self.external_editor_path = None
        self._save_user_prefs(silent=True)
        self.lbl_status.config(text="External editor selection cleared.")

    # -------------------------------------------------------------------------
    # Datamine Tool Launcher (#4C)
    # -------------------------------------------------------------------------
    def on_launch_datamine(self) -> None:
        """Launch the external Datamine executable or Python script with confirmation."""
        if not self.datamine_exe or not Path(self.datamine_exe).exists():
            ans = messagebox.askyesno("Datamine Tool Not Set", "No datamine executable has been configured yet.\nWould you like to select one now?")
            if ans:
                self.on_select_datamine_exe()
            return

        exe_path = Path(self.datamine_exe)
        if not self._datamine_confirm_skip:
            dlg = tk.Toplevel(self)
            dlg.title("Confirm Datamine Launch")
            dlg.geometry("440x180")
            dlg.transient(self)
            dlg.grab_set()
            dlg.resizable(False, False)
            t = self.theme
            dlg.configure(bg=t["bg_panel"])

            confirmed = [False]
            skip_var = tk.BooleanVar(value=False)

            msg = f"Launch external datamine tool?\n\nProgram: {exe_path.name}\nPath: {exe_path}"
            tk.Label(dlg, text=msg, bg=t["bg_panel"], fg=best_contrast_fg(t["bg_panel"]), justify="left", wraplength=400).pack(padx=16, pady=(16, 8), fill="x")

            cb = tk.Checkbutton(dlg, text="Don't ask again this session", variable=skip_var, bg=t["bg_panel"], fg=best_contrast_fg(t["bg_panel"]), selectcolor=t["bg_dark"])
            cb.pack(padx=16, pady=4, anchor="w")

            btn_frame = tk.Frame(dlg, bg=t["bg_panel"])
            btn_frame.pack(fill="x", padx=16, pady=(8, 12), side="bottom")

            def _cancel():
                dlg.destroy()

            def _ok():
                confirmed[0] = True
                if skip_var.get():
                    self._datamine_confirm_skip = True
                dlg.destroy()

            btn_cancel = ttk.Button(btn_frame, text="Cancel", style="TButton", command=_cancel)
            btn_cancel.pack(side="right", padx=4)
            btn_ok = ttk.Button(btn_frame, text="Launch Tool", style="Pink.TButton", command=_ok)
            btn_ok.pack(side="right", padx=4)
            btn_cancel.focus_set()

            self.wait_window(dlg)
            if not confirmed[0]:
                return

        try:
            cwd = str(exe_path.parent)
            if exe_path.suffix.lower() == ".py":
                cmd = [sys.executable, str(exe_path)]
            else:
                cmd = [str(exe_path)]
            subprocess.Popen(cmd, cwd=cwd, shell=False)
            self.logger.info("External Tools", f"Launched datamine tool: {exe_path}")
            self.lbl_status.config(text=f"Launched datamine tool: {exe_path.name}")
        except Exception as exc:
            self.logger.exception("Failed to launch datamine tool:", exc)
            messagebox.showerror("Datamine Launch Failed", f"Could not launch {exe_path.name}:\n{exc}")

    def on_select_datamine_exe(self) -> None:
        f = filedialog.askopenfilename(
            title="Select Datamine Executable or Script",
            filetypes=[
                ("Executables & Scripts", "*.exe;*.py;*.bat;*.cmd"),
                ("Applications", "*.exe"),
                ("Python Scripts", "*.py"),
                ("All Files", "*.*")
            ]
        )
        if f:
            self.datamine_exe = Path(f)
            self._save_user_prefs(silent=True)
            self.lbl_status.config(text=f"Datamine tool set to: {self.datamine_exe.name}")
            self.logger.info("External Tools", f"Configured datamine executable: {self.datamine_exe}")

    def on_open_datamine_folder(self) -> None:
        if self.datamine_exe and Path(self.datamine_exe).exists():
            subprocess.Popen(["explorer.exe", str(Path(self.datamine_exe).parent)])
        else:
            messagebox.showinfo("Datamine Folder", "No datamine executable is currently configured.")

    # -------------------------------------------------------------------------
    # Folders & Files Configuration Dialog (#4B)
    # -------------------------------------------------------------------------
    def on_open_backups_folder(self) -> None:
        bak_dir = self._get_backup_dir()
        subprocess.Popen(["explorer.exe", str(bak_dir)])

    def on_open_bepinex_folder(self) -> None:
        if self.bepinex_project_folder and Path(self.bepinex_project_folder).exists():
            subprocess.Popen(["explorer.exe", str(self.bepinex_project_folder)])
        else:
            ans = messagebox.askyesno("BepInEx Folder", "BepInEx translation folder is not set. Configure it now?")
            if ans:
                self.on_open_paths_dialog()

    def on_open_program_folder(self) -> None:
        subprocess.Popen(["explorer.exe", str(SCRIPT_DIR)])

    def on_open_paths_dialog(self) -> None:
        """Dialog to configure Backup Folder, BepInEx Folder, Config, and External Programs."""
        t = self.theme
        dlg = tk.Toplevel(self)
        dlg.title("Configure Paths, Backups & Folders")
        dlg.geometry("620x460")
        dlg.minsize(560, 400)
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg=t["bg_panel"])

        fg_panel = best_contrast_fg(t["bg_panel"])
        fg_editor = best_contrast_fg(t["bg_editor"])

        content = tk.Frame(dlg, bg=t["bg_panel"], padx=16, pady=12)
        content.pack(fill="both", expand=True)

        def make_row(parent, label_text):
            r = tk.Frame(parent, bg=t["bg_panel"])
            r.pack(fill="x", pady=4)
            lbl = tk.Label(r, text=label_text, font=("Segoe UI", 9, "bold"), bg=t["bg_panel"], fg=t["misora_pink"], width=22, anchor="w")
            lbl.pack(side="left")
            ent = tk.Entry(r, font=("Segoe UI", 9), bg=t["bg_editor"], fg=fg_editor, bd=1, relief="solid")
            ent.pack(side="left", fill="x", expand=True, padx=4)
            return r, ent

        # 1. Backup Folder
        r1, ent_backup = make_row(content, "Backup Folder:")
        cur_bak = str(self.backup_folder) if self.backup_folder else str(SCRIPT_DIR / "backups")
        ent_backup.insert(0, cur_bak)
        var_use_default_bak = tk.BooleanVar(value=(self.backup_folder is None))

        def _browse_bak():
            d = filedialog.askdirectory(title="Select Backup Folder")
            if d:
                ent_backup.delete(0, tk.END)
                ent_backup.insert(0, d)
                var_use_default_bak.set(False)

        ttk.Button(r1, text="Browse...", style="Small.TButton", command=_browse_bak).pack(side="left", padx=2)
        cb_bak = tk.Checkbutton(content, text="Use default backups folder (SCRIPT_DIR/backups)", variable=var_use_default_bak, bg=t["bg_panel"], fg=fg_panel, selectcolor=t["bg_dark"])
        cb_bak.pack(anchor="w", padx=(160, 0), pady=(0, 6))

        # 2. BepInEx Project Folder
        r2, ent_bepinex = make_row(content, "BepInEx Project Folder:")
        if self.bepinex_project_folder:
            ent_bepinex.insert(0, str(self.bepinex_project_folder))

        def _browse_bepinex():
            d = filedialog.askdirectory(title="Select BepInEx Translation Folder")
            if d:
                ent_bepinex.delete(0, tk.END)
                ent_bepinex.insert(0, d)

        ttk.Button(r2, text="Browse...", style="Small.TButton", command=_browse_bepinex).pack(side="left", padx=2)

        # 3. Datamine Executable
        r3, ent_datamine = make_row(content, "Datamine Tool:")
        if self.datamine_exe:
            ent_datamine.insert(0, str(self.datamine_exe))

        def _browse_datamine():
            f = filedialog.askopenfilename(title="Select Datamine Executable", filetypes=[("Executables & Scripts", "*.exe;*.py;*.bat;*.cmd"), ("All Files", "*.*")])
            if f:
                ent_datamine.delete(0, tk.END)
                ent_datamine.insert(0, f)

        ttk.Button(r3, text="Browse...", style="Small.TButton", command=_browse_datamine).pack(side="left", padx=2)

        # 4. External Editor
        r4, ent_editor = make_row(content, "External Text Editor:")
        if self.external_editor_path:
            ent_editor.insert(0, str(self.external_editor_path))

        def _browse_editor():
            f = filedialog.askopenfilename(title="Select External Editor", filetypes=[("Executables", "*.exe;*.bat;*.cmd"), ("All Files", "*.*")])
            if f:
                ent_editor.delete(0, tk.END)
                ent_editor.insert(0, f)

        ttk.Button(r4, text="Browse...", style="Small.TButton", command=_browse_editor).pack(side="left", padx=2)

        # Separator & File references
        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=10)

        # 5. Config File
        r5 = tk.Frame(content, bg=t["bg_panel"])
        r5.pack(fill="x", pady=2)
        tk.Label(r5, text="Config File:", font=("Segoe UI", 9, "bold"), bg=t["bg_panel"], fg=t["fg_muted"], width=22, anchor="w").pack(side="left")
        tk.Label(r5, text=str(CONFIG_PATH), font=("Consolas", 8), bg=t["bg_panel"], fg=fg_panel, anchor="w").pack(side="left", fill="x", expand=True)
        ttk.Button(r5, text="Reveal", style="Small.TButton", command=lambda: subprocess.Popen(["explorer.exe", f"/select,{CONFIG_PATH}"])).pack(side="right", padx=2)

        # 6. Debug Log
        r6 = tk.Frame(content, bg=t["bg_panel"])
        r6.pack(fill="x", pady=2)
        tk.Label(r6, text="Debug Log:", font=("Segoe UI", 9, "bold"), bg=t["bg_panel"], fg=t["fg_muted"], width=22, anchor="w").pack(side="left")
        tk.Label(r6, text=str(DEBUG_LOG_PATH), font=("Consolas", 8), bg=t["bg_panel"], fg=fg_panel, anchor="w").pack(side="left", fill="x", expand=True)
        ttk.Button(r6, text="Open", style="Small.TButton", command=self._on_open_debug_log_file).pack(side="right", padx=2)

        # Buttons at bottom
        btn_bar = tk.Frame(dlg, bg=t["bg_panel"], padx=16, pady=12)
        btn_bar.pack(fill="x", side="bottom")

        def _save_and_close():
            if var_use_default_bak.get():
                self.backup_folder = None
            else:
                b_val = ent_backup.get().strip()
                self.backup_folder = Path(b_val) if b_val else None

            bep_val = ent_bepinex.get().strip()
            self.bepinex_project_folder = Path(bep_val) if bep_val else None
            if self.bepinex_project_folder and self.bepinex_project_folder.exists():
                text_dir = self.bepinex_project_folder / "Text"
                root = text_dir if text_dir.exists() else self.bepinex_project_folder
                if root not in self.xuat_search_roots:
                    self.xuat_search_roots.insert(0, root)

            dm_val = ent_datamine.get().strip()
            self.datamine_exe = Path(dm_val) if dm_val else None

            ed_val = ent_editor.get().strip()
            self.external_editor_path = Path(ed_val) if ed_val else None

            self._save_user_prefs()
            self.lbl_status.config(text="Updated paths and backup configuration.")
            dlg.destroy()

        ttk.Button(btn_bar, text="Cancel", style="TButton", command=dlg.destroy).pack(side="right", padx=4)
        ttk.Button(btn_bar, text="Save & Apply", style="Pink.TButton", command=_save_and_close).pack(side="right", padx=4)

    def on_about(self) -> None:
        about_text = (
            "Misora: Unity3D Revision Tool & Story Editor\n"
            "Version 1.2.0\n\n"
            "A specialized text editor for Princess Connect! Re:Dive.\n\n"
            "MIT License - Created for the Priconne Modding Community."
        )
        messagebox.showinfo("About Misora", about_text)


def main():
    initial_file = sys.argv[1] if len(sys.argv) > 1 else None
    app = MisoraApp(initial_file)
    app.mainloop()


if __name__ == "__main__":
    main()