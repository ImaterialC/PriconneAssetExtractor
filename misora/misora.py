#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Misora: Unity3D Revision Tool & Story Editor
=============================================
A specialized GUI text editor for inspecting, searching, and in-place patching
of Princess Connect! Re:Dive Unity3D story bundles (.unity3d) and XUAT translation files.

Features:
- Direct in-memory bundle loading and instant (<100ms) byte-exact repacking.
- Dual-View Editor: Clean Game Display View + Technical Raw AST Script View.
- Notepad++ style multi-file search across bundles and plain text with regex,
  case-sensitivity, and XUnity whitespace & {playername} placeholder normalization.
- Bi-directional sync with source XUAT text dictionaries.
"""
from __future__ import annotations

import os
import queue
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Union

# Ensure both Misora root and toolkit parent are in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

try:
    from misora.assets.icon import THEME
    from misora.core import (
        Box, BundleIOError, ProjectSearchEngine, Record, SearchOptions,
        SearchResult, StoryDocument, XUnitySyncManager, load_bundle_story,
        save_bundle_story
    )
except ImportError:
    from assets.icon import THEME
    from core import (
        Box, BundleIOError, ProjectSearchEngine, Record, SearchOptions,
        SearchResult, StoryDocument, XUnitySyncManager, load_bundle_story,
        save_bundle_story
    )


class MisoraApp(tk.Tk):
    """Main Application Window for Misora: Unity3D Revision Tool."""

    def __init__(self, initial_path: Optional[str] = None):
        super().__init__()
        self.title("Misora: Unity3D Revision Tool & Story Editor")
        self.geometry("1260x800")
        self.minsize(960, 600)
        self.configure(bg=THEME["bg_dark"])

        # State Variables
        self.current_file_path: Optional[Path] = None
        self.current_doc: Optional[StoryDocument] = None
        self.current_unity_env: Any = None
        self.current_text_obj: Any = None
        self.current_box_idx: int = 0
        self.is_bundle_file: bool = False
        self.is_dirty: bool = False
        self.xuat_search_roots: List[Path] = []

        # Background search worker
        self.search_engine = ProjectSearchEngine()
        self.sync_manager = XUnitySyncManager()
        self.search_queue: queue.Queue = queue.Queue()
        self.search_cancel_flag: bool = False
        self.active_search_results: List[SearchResult] = []

        # Auto-detect project paths
        self._detect_environment()

        # Build UI
        self._apply_styles()
        self._build_menu()
        self._build_search_bar()
        self._build_main_panels()
        self._build_status_bar()
        self._bind_shortcuts()

        # Start periodic poll for background tasks
        self.after(100, self._process_search_queue)

        if initial_path and os.path.exists(initial_path):
            self.open_file(initial_path)

    # -------------------------------------------------------------------------
    # Environment & Styling
    # -------------------------------------------------------------------------
    def _detect_environment(self) -> None:
        """Auto-detect Priconne BepInEx RedirectedResources and XUAT Text folders."""
        candidates = [
            Path(r"C:\[Gacha]\PriconneRe-TL\src\BepInEx\Translation\en"),
            Path("output"),
            Path("input"),
            SCRIPT_DIR.parent / "input",
            SCRIPT_DIR.parent / "output",
        ]
        for c in candidates:
            if c.exists():
                text_dir = c / "Text"
                if text_dir.exists():
                    self.xuat_search_roots.append(text_dir)
                else:
                    self.xuat_search_roots.append(c)

    def _apply_styles(self) -> None:
        """Apply modern dark theme with Misora pink accent styling."""
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Configure TTK widgets
        style.configure(".", background=THEME["bg_dark"], foreground=THEME["fg_text"], borderwidth=0)
        style.configure("TFrame", background=THEME["bg_dark"])
        style.configure("Panel.TFrame", background=THEME["bg_panel"])

        # Label styling
        style.configure("TLabel", background=THEME["bg_dark"], foreground=THEME["fg_text"], font=("Segoe UI", 9))
        style.configure("Panel.TLabel", background=THEME["bg_panel"], foreground=THEME["fg_text"])
        style.configure("Header.TLabel", font=("Segoe UI", 10, "bold"), foreground=THEME["misora_pink"])
        style.configure("Muted.TLabel", foreground=THEME["fg_muted"], font=("Segoe UI", 8))

        # Checkbutton & Radiobutton
        style.configure("TCheckbutton", background=THEME["bg_dark"], foreground=THEME["fg_text"])
        style.configure("TRadiobutton", background=THEME["bg_dark"], foreground=THEME["fg_text"])

        # Pink Primary Action Button
        style.configure(
            "Pink.TButton",
            background=THEME["misora_pink"],
            foreground="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padding=(10, 4)
        )
        style.map(
            "Pink.TButton",
            background=[("active", THEME["misora_pink_hover"]), ("pressed", THEME["misora_pink_active"])],
            foreground=[("disabled", THEME["fg_muted"])]
        )

        # Standard Neutral Button
        style.configure(
            "TButton",
            background=THEME["bg_panel"],
            foreground=THEME["fg_text"],
            font=("Segoe UI", 9),
            padding=(6, 3)
        )
        style.map(
            "TButton",
            background=[("active", "#383848"), ("pressed", "#202028")]
        )

        # Treeview styling
        style.configure(
            "Treeview",
            background=THEME["bg_editor"],
            foreground=THEME["fg_text"],
            fieldbackground=THEME["bg_editor"],
            font=("Segoe UI", 9),
            rowheight=24,
            borderwidth=1,
            relief="solid"
        )
        style.map(
            "Treeview",
            background=[("selected", THEME["highlight_bg"])],
            foreground=[("selected", THEME["misora_pink"])]
        )
        style.configure(
            "Treeview.Heading",
            background=THEME["bg_panel"],
            foreground=THEME["fg_muted"],
            font=("Segoe UI", 8, "bold")
        )

    # -------------------------------------------------------------------------
    # Menu Bar
    # -------------------------------------------------------------------------
    def _build_menu(self) -> None:
        menubar = tk.Menu(self, bg=THEME["bg_panel"], fg=THEME["fg_text"], activebackground=THEME["misora_pink"], activeforeground="#ffffff")

        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg_panel"], fg=THEME["fg_text"], activebackground=THEME["misora_pink"])
        file_menu.add_command(label="Open File...", command=self.on_open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Open Folder...", command=self.on_open_folder, accelerator="Ctrl+Shift+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save & Patch Bundle", command=self.on_save, accelerator="Ctrl+S")
        file_menu.add_command(label="Reload Current File", command=self.on_reload, accelerator="F5")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit, accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=file_menu)

        # Edit Menu
        edit_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg_panel"], fg=THEME["fg_text"], activebackground=THEME["misora_pink"])
        edit_menu.add_command(label="Previous Box", command=self.on_prev_box, accelerator="Alt+Left")
        edit_menu.add_command(label="Next Box", command=self.on_next_box, accelerator="Alt+Right")
        edit_menu.add_separator()
        edit_menu.add_command(label="Insert {playername}", command=self.on_insert_playername, accelerator="Ctrl+P")
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # Search Menu
        search_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg_panel"], fg=THEME["fg_text"], activebackground=THEME["misora_pink"])
        search_menu.add_command(label="Focus Search", command=lambda: self.search_entry.focus(), accelerator="Ctrl+F")
        search_menu.add_command(label="Clear Search Results", command=self.on_clear_search)
        menubar.add_cascade(label="Search", menu=search_menu)

        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg_panel"], fg=THEME["fg_text"], activebackground=THEME["misora_pink"])
        help_menu.add_command(label="About Misora", command=self.on_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    # -------------------------------------------------------------------------
    # Search Bar (Notepad++ Style)
    # -------------------------------------------------------------------------
    def _build_search_bar(self) -> None:
        search_frame = tk.Frame(self, bg=THEME["bg_panel"], bd=1, relief="solid", highlightbackground=THEME["border"], highlightthickness=1)
        search_frame.pack(fill="x", padx=8, pady=(6, 4))

        # Top row: Query Entry & Action Buttons
        row1 = tk.Frame(search_frame, bg=THEME["bg_panel"])
        row1.pack(fill="x", padx=8, pady=4)

        tk.Label(row1, text="Find:", font=("Segoe UI", 9, "bold"), bg=THEME["bg_panel"], fg=THEME["misora_pink"]).pack(side="left", padx=(0, 6))

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            row1,
            textvariable=self.search_var,
            font=("Consolas", 10),
            bg=THEME["bg_editor"],
            fg=THEME["fg_text"],
            insertbackground=THEME["misora_pink"],
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightcolor=THEME["misora_pink"]
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<Return>", lambda e: self.on_start_search())

        self.btn_find = ttk.Button(row1, text="Find in Files", style="Pink.TButton", command=self.on_start_search)
        self.btn_find.pack(side="left", padx=4)

        self.btn_cancel = ttk.Button(row1, text="Cancel", style="TButton", command=self.on_cancel_search, state="disabled")
        self.btn_cancel.pack(side="left", padx=4)

        # Second row: Options & Scope Controls
        row2 = tk.Frame(search_frame, bg=THEME["bg_panel"])
        row2.pack(fill="x", padx=8, pady=(0, 4))

        # Options Checkboxes
        self.var_case = tk.BooleanVar(value=False)
        self.var_regex = tk.BooleanVar(value=False)
        self.var_ignore_ws = tk.BooleanVar(value=True)
        self.var_inc_bundles = tk.BooleanVar(value=True)
        self.var_inc_text = tk.BooleanVar(value=True)

        cb_case = tk.Checkbutton(row2, text="Match Case", variable=self.var_case, bg=THEME["bg_panel"], fg=THEME["fg_text"], selectcolor=THEME["bg_dark"], activebackground=THEME["bg_panel"], activeforeground=THEME["fg_text"])
        cb_case.pack(side="left", padx=4)

        cb_rx = tk.Checkbutton(row2, text="Regex", variable=self.var_regex, bg=THEME["bg_panel"], fg=THEME["fg_text"], selectcolor=THEME["bg_dark"], activebackground=THEME["bg_panel"], activeforeground=THEME["fg_text"])
        cb_rx.pack(side="left", padx=4)

        cb_ws = tk.Checkbutton(row2, text="Ignore Whitespace & {playername}", variable=self.var_ignore_ws, bg=THEME["bg_panel"], fg=THEME["fg_text"], selectcolor=THEME["bg_dark"], activebackground=THEME["bg_panel"], activeforeground=THEME["fg_text"])
        cb_ws.pack(side="left", padx=4)

        # Separator
        tk.Label(row2, text="|", bg=THEME["bg_panel"], fg=THEME["border"]).pack(side="left", padx=8)

        # Scope Selection
        tk.Label(row2, text="Scope:", bg=THEME["bg_panel"], fg=THEME["fg_muted"]).pack(side="left", padx=(0, 4))
        self.scope_var = tk.StringVar(value="project")

        rb_proj = tk.Radiobutton(row2, text="Project", variable=self.scope_var, value="project", bg=THEME["bg_panel"], fg=THEME["fg_text"], selectcolor=THEME["bg_dark"], activebackground=THEME["bg_panel"])
        rb_proj.pack(side="left", padx=2)

        rb_folder = tk.Radiobutton(row2, text="Folder", variable=self.scope_var, value="folder", bg=THEME["bg_panel"], fg=THEME["fg_text"], selectcolor=THEME["bg_dark"], activebackground=THEME["bg_panel"])
        rb_folder.pack(side="left", padx=2)

        rb_cur = tk.Radiobutton(row2, text="Current File", variable=self.scope_var, value="current", bg=THEME["bg_panel"], fg=THEME["fg_text"], selectcolor=THEME["bg_dark"], activebackground=THEME["bg_panel"])
        rb_cur.pack(side="left", padx=2)

        # File Types Checkboxes
        tk.Label(row2, text="|", bg=THEME["bg_panel"], fg=THEME["border"]).pack(side="left", padx=8)
        cb_bdl = tk.Checkbutton(row2, text=".unity3d", variable=self.var_inc_bundles, bg=THEME["bg_panel"], fg=THEME["fg_text"], selectcolor=THEME["bg_dark"], activebackground=THEME["bg_panel"])
        cb_bdl.pack(side="left", padx=2)
        cb_txt = tk.Checkbutton(row2, text=".txt", variable=self.var_inc_text, bg=THEME["bg_panel"], fg=THEME["fg_text"], selectcolor=THEME["bg_dark"], activebackground=THEME["bg_panel"])
        cb_txt.pack(side="left", padx=2)

        # Progress bar
        self.progress_bar = ttk.Progressbar(search_frame, mode="determinate")
        self.progress_bar.pack(fill="x", padx=8, pady=(0, 2))
        self.progress_bar.pack_forget()  # Hidden by default

    # -------------------------------------------------------------------------
    # Main Workspace (Split View)
    # -------------------------------------------------------------------------
    def _build_main_panels(self) -> None:
        # Horizontal Splitter between Left (Search Tree) and Right (Editor)
        self.h_paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=THEME["border"], sashwidth=4)
        self.h_paned.pack(fill="both", expand=True, padx=8, pady=4)

        # Left Panel: Search Results
        left_frame = tk.Frame(self.h_paned, bg=THEME["bg_panel"])
        self.h_paned.add(left_frame, minsize=320, width=380)

        left_header = tk.Frame(left_frame, bg=THEME["bg_panel"])
        left_header.pack(fill="x", padx=8, pady=6)
        self.lbl_results_title = tk.Label(left_header, text="Search Results (0 matches)", font=("Segoe UI", 9, "bold"), bg=THEME["bg_panel"], fg=THEME["misora_pink"])
        self.lbl_results_title.pack(side="left")

        # Treeview for Search Matches
        tree_container = tk.Frame(left_frame, bg=THEME["bg_panel"])
        tree_container.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        tree_scroll_y = tk.Scrollbar(tree_container)
        tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x = tk.Scrollbar(tree_container, orient="horizontal")
        tree_scroll_x.pack(side="bottom", fill="x")

        self.tree_results = ttk.Treeview(
            tree_container,
            columns=("speaker", "text"),
            show="tree",
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set
        )
        self.tree_results.pack(fill="both", expand=True)
        tree_scroll_y.config(command=self.tree_results.yview)
        tree_scroll_x.config(command=self.tree_results.xview)
        self.tree_results.bind("<<TreeviewSelect>>", self.on_select_search_result)

        # Right Panel: Dual-View Editor (Vertical Splitter)
        right_frame = tk.Frame(self.h_paned, bg=THEME["bg_panel"])
        self.h_paned.add(right_frame, minsize=500)

        self.v_paned = tk.PanedWindow(right_frame, orient=tk.VERTICAL, bg=THEME["border"], sashwidth=4)
        self.v_paned.pack(fill="both", expand=True)

        # TOP VIEW: Game Display View (Clean Dialogue)
        top_view = tk.Frame(self.v_paned, bg=THEME["bg_panel"])
        self.v_paned.add(top_view, minsize=220, height=360)

        # Game Display Controls Header
        gd_header = tk.Frame(top_view, bg=THEME["bg_panel"])
        gd_header.pack(fill="x", padx=8, pady=6)

        tk.Label(gd_header, text="GAME DISPLAY VIEW (Clean Dialogue)", font=("Segoe UI", 9, "bold"), bg=THEME["bg_panel"], fg=THEME["misora_pink"]).pack(side="left")

        self.lbl_box_counter = tk.Label(gd_header, text="Box: 0 / 0", font=("Segoe UI", 9), bg=THEME["bg_panel"], fg=THEME["fg_muted"])
        self.lbl_box_counter.pack(side="right", padx=(8, 0))

        btn_next = ttk.Button(gd_header, text="Next >", style="TButton", command=self.on_next_box)
        btn_next.pack(side="right", padx=2)
        btn_prev = ttk.Button(gd_header, text="< Prev", style="TButton", command=self.on_prev_box)
        btn_prev.pack(side="right", padx=2)

        # Speaker & Voice Header Row
        speaker_row = tk.Frame(top_view, bg=THEME["bg_panel"])
        speaker_row.pack(fill="x", padx=8, pady=(0, 6))

        tk.Label(speaker_row, text="Speaker:", bg=THEME["bg_panel"], fg=THEME["fg_muted"]).pack(side="left", padx=(0, 6))
        self.speaker_var = tk.StringVar()
        self.entry_speaker = tk.Entry(
            speaker_row,
            textvariable=self.speaker_var,
            font=("Segoe UI", 9, "bold"),
            bg=THEME["bg_editor"],
            fg=THEME["fg_text"],
            insertbackground=THEME["misora_pink"],
            bd=1,
            relief="solid",
            width=28
        )
        self.entry_speaker.pack(side="left")
        self.entry_speaker.bind("<KeyRelease>", lambda e: self._on_dialogue_edited())

        self.lbl_voice_cue = tk.Label(speaker_row, text="", bg=THEME["bg_panel"], fg=THEME["accent_blue"], font=("Segoe UI", 8))
        self.lbl_voice_cue.pack(side="left", padx=12)

        # Large Clean Dialogue Editor
        text_container = tk.Frame(top_view, bg=THEME["bg_panel"])
        text_container.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        txt_scroll = tk.Scrollbar(text_container)
        txt_scroll.pack(side="right", fill="y")

        self.txt_dialogue = tk.Text(
            text_container,
            wrap="word",
            font=("Segoe UI", 11),
            bg=THEME["bg_editor"],
            fg=THEME["fg_text"],
            insertbackground=THEME["misora_pink"],
            selectbackground=THEME["highlight_bg"],
            selectforeground=THEME["misora_pink"],
            bd=1,
            relief="solid",
            yscrollcommand=txt_scroll.set
        )
        self.txt_dialogue.pack(fill="both", expand=True)
        txt_scroll.config(command=self.txt_dialogue.yview)
        self.txt_dialogue.bind("<KeyRelease>", lambda e: self._on_dialogue_edited())

        # BOTTOM VIEW: Raw AST Script View (Technical Records)
        bottom_view = tk.Frame(self.v_paned, bg=THEME["bg_panel"])
        self.v_paned.add(bottom_view, minsize=140, height=220)

        raw_header = tk.Frame(bottom_view, bg=THEME["bg_panel"])
        raw_header.pack(fill="x", padx=8, pady=4)
        tk.Label(raw_header, text="RAW SCRIPT VIEW (Technical AST Records)", font=("Segoe UI", 9, "bold"), bg=THEME["bg_panel"], fg=THEME["fg_muted"]).pack(side="left")

        raw_container = tk.Frame(bottom_view, bg=THEME["bg_panel"])
        raw_container.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        raw_scroll_y = tk.Scrollbar(raw_container)
        raw_scroll_y.pack(side="right", fill="y")
        raw_scroll_x = tk.Scrollbar(raw_container, orient="horizontal")
        raw_scroll_x.pack(side="bottom", fill="x")

        self.txt_raw = tk.Text(
            raw_container,
            wrap="none",
            font=("Consolas", 9),
            bg="#14141a",
            fg="#a0a0b8",
            insertbackground=THEME["misora_pink"],
            bd=1,
            relief="solid",
            yscrollcommand=raw_scroll_y.set,
            xscrollcommand=raw_scroll_x.set
        )
        self.txt_raw.pack(fill="both", expand=True)
        raw_scroll_y.config(command=self.txt_raw.yview)
        raw_scroll_x.config(command=self.txt_raw.xview)

    # -------------------------------------------------------------------------
    # Status & Action Bar
    # -------------------------------------------------------------------------
    def _build_status_bar(self) -> None:
        action_bar = tk.Frame(self, bg=THEME["bg_panel"], bd=1, relief="solid", highlightbackground=THEME["border"], highlightthickness=1)
        action_bar.pack(fill="x", padx=8, pady=(0, 6))

        # Status text on the left
        self.lbl_status = tk.Label(action_bar, text="Ready. Drag & Drop or open a .unity3d bundle or folder to begin.", font=("Segoe UI", 9), bg=THEME["bg_panel"], fg=THEME["fg_muted"])
        self.lbl_status.pack(side="left", padx=8, pady=6)

        # Sync checkbox and Save button on the right
        self.var_sync_xuat = tk.BooleanVar(value=True)
        cb_sync = tk.Checkbutton(
            action_bar,
            text="Also update matching XUAT .txt dictionary on Save",
            variable=self.var_sync_xuat,
            bg=THEME["bg_panel"],
            fg=THEME["fg_text"],
            selectcolor=THEME["bg_dark"],
            activebackground=THEME["bg_panel"]
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
        self.bind("<Control-p>", lambda e: self.on_insert_playername())
        self.bind("<Control-f>", lambda e: self.search_entry.focus())
        self.bind("<F5>", lambda e: self.on_reload())
        self.bind("<Alt-Left>", lambda e: self.on_prev_box())
        self.bind("<Alt-Right>", lambda e: self.on_next_box())

    # -------------------------------------------------------------------------
    # Document Loading & Box Display
    # -------------------------------------------------------------------------
    def open_file(self, file_path: Union[str, Path]) -> None:
        """Open and display a .unity3d bundle or plain-text script file."""
        file_path = Path(file_path).resolve()
        if not file_path.is_file():
            messagebox.showerror("File Error", f"Cannot find file: {file_path}")
            return

        ext = file_path.suffix.lower()
        self.current_file_path = file_path
        self.is_dirty = False

        if ext in (".unity3d", ".asset"):
            try:
                doc, env, obj, asset_name = load_bundle_story(file_path)
                self.current_doc = doc
                self.current_unity_env = env
                self.current_text_obj = obj
                self.is_bundle_file = True
                self.current_box_idx = 0
                self._update_views()
                size_kb = file_path.stat().st_size / 1024
                self.lbl_status.config(text=f"Loaded Bundle: {file_path.name} ({asset_name}) | Size: {size_kb:.1f} KB | {len(doc.boxes)} dialogue boxes")
            except Exception as e:
                messagebox.showerror("Bundle Load Error", f"Failed to open '{file_path.name}':\n{e}")
        else:
            # Plain text file (.txt, .json)
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                if content.startswith("#!priconne-story"):
                    doc = StoryDocument.from_v2_text(content)
                    self.current_doc = doc
                    self.is_bundle_file = False
                    self.current_box_idx = 0
                    self._update_views()
                    self.lbl_status.config(text=f"Loaded Script: {file_path.name} | {len(doc.boxes)} dialogue boxes")
                else:
                    # Generic text file: display in dialogue editor directly
                    self.txt_dialogue.delete("1.0", tk.END)
                    self.txt_dialogue.insert("1.0", content)
                    self.txt_raw.delete("1.0", tk.END)
                    self.txt_raw.insert("1.0", f"(Plain text file: {file_path})")
                    self.lbl_status.config(text=f"Opened Text File: {file_path.name}")
            except Exception as e:
                messagebox.showerror("File Load Error", f"Failed to read '{file_path.name}':\n{e}")

    def _update_views(self) -> None:
        """Update both Game Display View and Raw AST View with current box data."""
        if not self.current_doc or not self.current_doc.boxes:
            self.speaker_var.set("")
            self.txt_dialogue.delete("1.0", tk.END)
            self.txt_raw.delete("1.0", tk.END)
            self.lbl_box_counter.config(text="Box: 0 / 0")
            return

        total_boxes = len(self.current_doc.boxes)
        self.current_box_idx = max(0, min(self.current_box_idx, total_boxes - 1))
        box = self.current_doc.boxes[self.current_box_idx]

        # 1. Update Game Display View
        self.speaker_var.set(box.speaker)
        self.txt_dialogue.delete("1.0", tk.END)
        self.txt_dialogue.insert("1.0", box.clean_text)
        self.lbl_box_counter.config(text=f"Box: {self.current_box_idx + 1} / {total_boxes}")
        self.lbl_voice_cue.config(text=f"Voice Cue: {box.voice_cue}" if box.voice_cue else "")

        # 2. Update Raw AST View
        self.txt_raw.delete("1.0", tk.END)
        raw_lines = []
        for i, r in enumerate(self.current_doc.records):
            args_str = "  ".join(f"'{a}'" for a in r.args)
            marker = " >> " if any(s.rec_index == i for s in box.segs) else "    "
            raw_lines.append(f"{marker}[{i:03d}] {r.cmd_name:<14} {args_str}")

        self.txt_raw.insert("1.0", "\n".join(raw_lines))

    def _on_dialogue_edited(self) -> None:
        """Triggered on every keystroke in the Game Display dialogue editor."""
        self.is_dirty = True
        if self.current_doc and self.current_doc.boxes:
            new_sp = self.speaker_var.get()
            new_tx = self.txt_dialogue.get("1.0", "end-1c")
            try:
                self.current_doc.inject_box(self.current_box_idx, new_sp, new_tx)
            except Exception:
                pass

    def on_prev_box(self) -> None:
        if self.current_doc and self.current_box_idx > 0:
            self.current_box_idx -= 1
            self._update_views()

    def on_next_box(self) -> None:
        if self.current_doc and self.current_box_idx < len(self.current_doc.boxes) - 1:
            self.current_box_idx += 1
            self._update_views()

    def on_revert_box(self) -> None:
        if self.current_file_path:
            self.open_file(self.current_file_path)

    def on_insert_playername(self) -> None:
        self.txt_dialogue.insert(tk.INSERT, "{playername}")
        self._on_dialogue_edited()

    # -------------------------------------------------------------------------
    # Save & Patch Actions (Byte-Exact In-Place Repack)
    # -------------------------------------------------------------------------
    def on_save(self) -> None:
        """Repack and save the active file in-place, with optional XUAT dictionary sync."""
        if not self.current_file_path or not self.current_doc:
            messagebox.showinfo("Nothing to Save", "No active file is open.")
            return

        # Ensure current editor text is injected
        new_sp = self.speaker_var.get()
        new_tx = self.txt_dialogue.get("1.0", "end-1c")
        self.current_doc.inject_box(self.current_box_idx, new_sp, new_tx)

        try:
            if self.is_bundle_file:
                # Direct in-memory repack into .unity3d container
                written_size = save_bundle_story(
                    self.current_unity_env,
                    self.current_text_obj,
                    self.current_doc,
                    self.current_file_path
                )
                self.is_dirty = False
                self.lbl_status.config(text=f"[SAVED & PATCHED] {self.current_file_path.name} ({written_size / 1024:.1f} KB) in-place successfully!")
            else:
                # Save plain v2 script text
                v2_text = self.current_doc.to_v2_text()
                self.current_file_path.write_text(v2_text, encoding="utf-8")
                self.is_dirty = False
                self.lbl_status.config(text=f"[SAVED] {self.current_file_path.name} saved successfully!")

            # Bi-directional XUAT sync
            if self.var_sync_xuat.get() and self.xuat_search_roots:
                cur_box = self.current_doc.boxes[self.current_box_idx]
                matches = self.sync_manager.find_and_update(
                    japanese_key=cur_box.clean_text,
                    new_english_text=new_tx,
                    search_roots=self.xuat_search_roots,
                    backup=True
                )
                if matches:
                    files_str = ", ".join(m.file_path.name for m in matches)
                    self.lbl_status.config(text=self.lbl_status.cget("text") + f" | Synced XUAT file(s): {files_str}")

        except Exception as e:
            messagebox.showerror("Save Failed", f"Failed to repack or save:\n{e}")

    def on_reload(self) -> None:
        if self.current_file_path:
            self.open_file(self.current_file_path)

    # -------------------------------------------------------------------------
    # Search Engine & Background Worker
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

        scope = self.scope_var.get()
        target_paths: List[Path] = []

        if scope == "current":
            if self.current_file_path:
                target_paths = [self.current_file_path]
            else:
                messagebox.showinfo("Search", "No file is currently open.")
                return
        elif scope == "folder":
            fld = filedialog.askdirectory(title="Select Folder to Search In")
            if not fld:
                return
            target_paths = [Path(fld)]
        else:
            # Whole Project: search BepInEx RedirectedResources, input/, output/, Text/
            target_paths = list(self.xuat_search_roots)
            for p in (Path("input"), Path("output"), SCRIPT_DIR.parent / "input", SCRIPT_DIR.parent / "output"):
                if p.exists() and p not in target_paths:
                    target_paths.append(p)

        # Clear existing results
        self.tree_results.delete(*self.tree_results.get_children())
        self.active_search_results.clear()
        self.lbl_results_title.config(text="Searching...")
        self.btn_find.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.progress_bar.pack(fill="x", padx=8, pady=(0, 2))
        self.progress_bar["value"] = 0
        self.search_cancel_flag = False

        # Launch background search thread
        t = threading.Thread(target=self._run_background_search, args=(target_paths, opts), daemon=True)
        t.start()

    def on_cancel_search(self) -> None:
        self.search_cancel_flag = True
        self.btn_cancel.config(state="disabled")
        self.lbl_status.config(text="Cancelling search...")

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
        """Polls results from background worker thread and populates Treeview."""
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
                    for r in batch_results:
                        self.active_search_results.append(r)
                        # Insert into tree: file node then line node
                        parent_id = str(r.file_path)
                        if not self.tree_results.exists(parent_id):
                            self.tree_results.insert("", "end", iid=parent_id, text=f"📄 {r.file_path.name}", open=True)

                        box_str = f"Box #{r.box_index + 1}" if r.box_index is not None else f"Line {r.line_number}"
                        label = f"[{box_str}] {r.speaker + ': ' if r.speaker else ''}{r.match_snippet}"
                        item_id = f"item_{len(self.active_search_results) - 1}"
                        self.tree_results.insert(parent_id, "end", iid=item_id, text=label)

                elif kind == "finished":
                    total = len(self.active_search_results)
                    self.lbl_results_title.config(text=f"Search Results ({total} matches)")
                    self.lbl_status.config(text=f"Search complete. Found {total} matches.")
                    self.btn_find.config(state="normal")
                    self.btn_cancel.config(state="disabled")
                    self.progress_bar.pack_forget()

        except queue.Empty:
            pass

        self.after(100, self._process_search_queue)

    def on_select_search_result(self, event) -> None:
        """When an item in the search results tree is clicked, open and focus that line."""
        sel = self.tree_results.selection()
        if not sel:
            return

        item_id = sel[0]
        if item_id.startswith("item_"):
            idx = int(item_id[5:])
            res = self.active_search_results[idx]

            # Open file if different
            if not self.current_file_path or self.current_file_path != res.file_path:
                self.open_file(res.file_path)

            # Focus exact box
            if res.box_index is not None and self.current_doc:
                self.current_box_idx = res.box_index
                self._update_views()
                # Focus dialogue editor
                self.txt_dialogue.focus()

    def on_clear_search(self) -> None:
        self.tree_results.delete(*self.tree_results.get_children())
        self.active_search_results.clear()
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
            self.scope_var.set("folder")
            self.lbl_status.config(text=f"Selected folder for search: {f}")

    def on_about(self) -> None:
        about_text = (
            "Misora: Unity3D Revision Tool & Story Editor\n"
            "Version 1.0.0\n\n"
            "A specialized text editor for Princess Connect! Re:Dive.\n"
            "Enables zero-pipeline, in-memory searching and byte-exact patching\n"
            "of packed .unity3d story bundles and XUAT translation dictionaries.\n\n"
            "MIT License - Created for the Priconne Modding Community."
        )
        messagebox.showinfo("About Misora", about_text)


def main():
    initial_file = sys.argv[1] if len(sys.argv) > 1 else None
    app = MisoraApp(initial_file)
    app.mainloop()


if __name__ == "__main__":
    main()
