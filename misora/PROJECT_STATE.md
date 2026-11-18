# MISORA — PROJECT STATE
*Last updated: 2026-11-18 — Project Folder <-> Find UI Linking, Multi-Framework Agnostic Naming, and Settings Saved Notification complete*

---

## SESSION HANDOFF / RESUME INSTRUCTIONS
**Current step:**
1. Bug #12 (NGUI Color & Gradient Picker): Confirmed working and complete by user ("yes it complete and work well").
2. Find UI Layout & Window Snapping UX:
   - Placed `[...]` browse button to the LEFT of the directory entry (`[...] [ Directory Path Entry (expand=True) ]`).
   - Directory entry expanded across remaining horizontal space (`fill="x", expand=True`) so resizing / window snapping gracefully shrinks the entry without clipping the browse button.
3. Project Scope Directory Path & Two-Way Linking:
   - When Scope is `Project`: displays project path (from `project_folder`, `bepinex_project_folder`, or detected translation root).
   - Linked two-way between Find UI Scope: Project directory entry and `Configure Paths, Backups & Folders` dialog (`Project / Mod Folder`). Edits in either update the other immediately and persist to `misora_config.json`.
   - When Scope is `Folder`: displays `selected_search_folder`, and `[...]` lets the user browse search folder.
   - When Scope is `Current File(s)`: displays active document directory, entry is read-only, `[...]` is disabled.
4. Framework-Agnostic Terminology & Multi-Framework Mod Support:
   - Deprecated "BepInEx"-specific labels across the UI in favor of framework-agnostic terminology: "Project / Mod Folder", "Project Translation Folder", supporting MelonLoader, BepInEx, XUAT, and custom mod structures.
   - Preserved full backward-compatibility for `bepinex_project_folder` attribute and JSON config keys.
   - Extended directory search logic for `Open Text Translation Folder` and `Open Redirected Resources Folder` to check standard paths across frameworks (`Text`, `Translation/en/Text`, `UserData/Text`, `RedirectedResources`, `Mods/RedirectedResources`, `UserData/RedirectedResources`).
5. Settings Saved Notifications:
   - Added popup confirmation (`messagebox.showinfo("Settings Saved", ...)`) upon saving settings in `Configure Paths, Backups & Folders`, `MTL Settings`, and `AI Prompt Settings`.
6. DnD Folder Drop UX:
   - Overhauled flow: Yes (open all into tabs, switch scope to Current File(s)), No (set search scope to folder, populate path entry, open nothing), Cancel (abort, keep prior selection).
7. Unit tests: 16/16 passing across `tests/test_misora_core.py` and `tests/test_misora_ui_integration.py`.

**Next action:** Await user verification of the Project Folder linking and framework-agnostic mod folder support.

---

## BACKUP & SAFETY ARCHIVE
- **Disk snapshot archive:** `misora/_archive/20261118_takeover_baseline/` (contains exact pristine copies of `misora.py`, `assets/`, `core/`, `tests/`, etc.).
- **Git commits:**
  - `bcc57c6`: Initial takeover `PROJECT_STATE.md` audit.
  - `db599f9`: Fixed `misora.bat` invocation bug.
  - `d96da3d`: Updated `misora.bat` to auto-detect Python 3.12 where UnityPy is installed (resolves Python 3.15 default conflict).
  - `fc2c6ba`: Fixed Bug #12 (Color Picker Pillow & Eyedropper) and Bug #3 (Continuous Ctrl+Z/Y undo).
- **Old session backups preserved:** `misora.py.bak_20261118_142038`, `misora.py.bak2_20261118_142158`.

---

## AUDIT FINDINGS

### A. File inventory
```
misora/
  misora.py           360 KB  main GUI  ← ON DISK, compiles clean
  misora.py.bak_*    .bak files from prior session (safe to leave, never delete)
  misora_config.json  3.6 KB  current config (Misora Purple & White theme, paths present)
  misora_debug.log    0.1 KB  one-line log (last run 06:56)
  README.md           6 KB
  register/unregister_association.bat (file association helpers)
  requirements.txt    "UnityPy>=1.20.0" only
  assets/icon.py, splash.py, Splash_1/2/3.jpg, __init__.py
  core/bundle_io.py, logger.py, mtl_engine.py, search_engine.py,
       story_ast.py, undo_journal.py, xunity_sync.py, __init__.py
  tests/test_misora_core.py
```
**No duplicate/orphaned files** (_2 suffixes, zips, etc.) found on disk.  
No `__pycache__` cleanup needed (auto-generated, fine as-is).

### B. Compile check
All `.py` files compile without error (`py -3.12 -m py_compile` → exit 0).  
**Bug #13 (NGUI_TOKEN_RE corruption) is NOT present.** The regex is correct.

### C. Unit tests
```
Ran 11 tests in 0.012s — OK (11/11 pass)
```
Baseline 5/5 pass + 6 extended tests added in prior sessions (undo, MTL, etc.).

### D. search_engine alignment
`SearchResult` has `snippet_start`, `snippet_end`, `match_in_speaker` — all present and used correctly in misora.py. ✓

### E. Config state
`misora_config.json` is Misora Purple & White (correct default). Contains paths, search folder, dock state, MTL config — well-structured. Config load/save code reads and writes all these fields. **Bug #2 (config only saves fonts/theme) is PARTIALLY FIXED** — paths and functional settings DO persist now. Needs verification end-to-end.

### F. App launch
App launches without startup errors. Logger reports initialization cleanly.

### G. DnD
Still using ctypes WM_DROPFILES subclassing (not tkinterdnd2). Code looks structurally correct (argtypes set, callback kept alive via `self._wndprocs` dict). Whether it crashes in practice needs live DnD testing — cannot test headlessly.

### H. Undo/Redo
**Bug #3 confirmed:** Line 4901-4902: `if ctrl and keysym.lower() in {"z", "y"}: return "break"` — Ctrl+Z/Y are BLOCKED in Continuous key guard. The fix is a single-line change.

### I. Plain .txt save
**Bug #15 appears FIXED** in code: `_on_save` (line 5396-5414) has a dedicated `if not self.is_bundle_file and not self.current_doc:` branch that writes the txt file. However, there may be a flag (`is_bundle_file`) initialization issue. Needs live testing.

### J. Up arrow navigation
**Bug #10 appears FIXED** in code (line 5291-5298): `_on_dialogue_key_up` navigates to prev box when at top line. Continuous view also has Up handling at line 4867-4879. Needs live testing.

### K. Eyedropper
Bug #12: Eyedropper uses GetDC(0)/GetPixel which has DPI issues at 125%/150%. Code exists and runs (no dead button) but may read wrong pixels at non-100% DPI. The SetProcessDpiAwareness(1) call at line 779 may help but is not guaranteed. This is a PARTIAL fix — Pillow ImageGrab would be more reliable. **Requires user approval before changing to Pillow.**

### L. Gradient separator
Bug #14: Ribbon `_apply_active_ribbon_gradient` (line 3460) inserts `[{c0}-{c1}]` with hyphen. Color picker `_commit_gradient_color` (line 869) also inserts with hyphen. NGUI_TAG_RE and NGUI_TOKEN_RE both accept `[-,]` (both comma and hyphen) for parsing. **The corpus separator is UNKNOWN — need user to confirm which form `.txt` dictionaries use.** Currently inserts hyphen; parsing accepts both.

### M. Embedded console
Bug #8: No embedded console panel found. The code has `_toggle_console_shortcut` (F12) which shows a toast "Logs stream to the persistent Windows console." — this means the embedded console was already removed in a prior session. `misora.bat` runs `python.exe` (line confirmed in bat file = needs verification).

### N. Theme coverage
Bug #4: Need to verify live. Code has `_tag_role()` system + `_apply_theme_to_all()`. Not fully audited.

### O. Ribbon widths
Bug #6: Buttons use `width=10` fixed. Spec says max = natural width of "Sub"/"Sup" for formatting buttons, natural width of "{player}" for color/grad/ruby/[-]/{player}. Currently all `width=10` — needs live inspection to confirm if this is correct or too wide.

---

## GAP MATRIX (Section 4 features)

| Feature | Status | Evidence |
|---------|--------|----------|
| **A. CORE EDITOR & BINARY** | | |
| Open .unity3d bundles | DONE | load_bundle_story, bundle_io.py |
| Edit speaker + dialogue | DONE | inject_box, misora.py |
| Ctrl+S repack <100ms, byte-exact | DONE | save_bundle_story |
| {0} in repacked bundles | DONE | story_ast.py inject_box |
| Plain .txt editable & saveable | PARTIAL | Code exists; flag check suspect |
| Bi-directional XUAT sync on save | DONE | xunity_sync.py |
| .bak backups | DONE | _get_backup_dir, shutil.copy2 |
| Dual view: Game Display + Raw AST | DONE | txt_dialogue + txt_raw |
| {playername} insertion (Ctrl+P) | DONE | on_insert_playername |
| F5 reload | DONE | on_reload |
| Revert Box | UNVERIFIED | Need live test |
| **B. SEARCH & REPLACE** | | |
| Scopes: Current/Folder/Project | DONE | scope_var, ProjectSearchEngine |
| Regex + match case | DONE | SearchOptions |
| Ignore-whitespace+playername | DONE | norm_search, search_engine |
| Background thread + progress + cancel | DONE | threading, progress_bar |
| Scope row directory text box | DONE | folder_path_entry (line 2477) |
| Results grouped by file, collapsible | PARTIAL | txt_results exists; collapsible? |
| Click jumps to file+box+highlights | DONE | _on_results_click |
| Speaker match highlight | DONE | match_in_speaker used |
| Replace mini-dialog | UNVERIFIED | Need code search |
| Whole-project replace WARNING | UNVERIFIED | Need code search |
| "Open Files" scope | UNVERIFIED | Need code search |
| **C. VIEWS & NAVIGATION** | | |
| Page view Prev/Next BUTTONS | DONE | ttk.Button "< Prev"/"Next >" |
| Continuous Dialog View | DONE | txt_continuous, marks |
| Toggling Continuous↔Page keeps box | PARTIAL | Bug #9 reported |
| Down at box end → next box | DONE | _on_continuous_key_guard line 4880 |
| Up at box start → prev box | DONE | line 4867 (Continuous) + 5291 (Page) |
| Ctrl+A works in Continuous | UNVERIFIED | |
| Delete multi-box → confirm dialog | PARTIAL | on_clear_dialogue_skeleton exists |
| Multi-box delete skeleton | UNVERIFIED | |
| One undo batch for delete | UNVERIFIED | |
| Line-number gutter | DONE | show_line_numbers, var_show_line_numbers |
| Horizontal column ruler | DONE | show_column_ruler |
| Gutter/ruler toggleable in View menu | DONE | var_show_line_numbers, persisted |
| Continuous box dividers visible | PARTIAL | Styling unverified live |
| Bounded scrolling in Game Display | UNVERIFIED | |
| **D. NGUI TOOLING** | | |
| Ribbon B/I/U/S/Sub/Sup buttons | DONE | mini_style_buttons loop |
| Ribbon widths (uniform per spec) | PARTIAL | All width=10, spec wants narrower |
| Color/Grad/Ruby/[-]/{player} buttons | DONE | Present in ribbon |
| Ribbon targets focused field | UNVERIFIED | Need code search |
| Color picker popup | DONE | NguiColorPickerPopup |
| Eyedropper DPI fix | PARTIAL | SetProcessDpiAwareness(1); may still fail at 125/150% |
| Gradient separator comma vs hyphen | PARTIAL | Inserts hyphen; parses both; corpus form unknown |
| "Preview Compiled" toggle | DONE | var_preview_compiled |
| RRGGBBAA → truncate alpha for Tk | UNVERIFIED | |
| Literal \n renders as line break in preview | UNVERIFIED | |
| Ruby builder + glossary | DONE | on_insert_ruby |
| NGUI Glossary top-level MENU | UNVERIFIED | May be side drawer button instead |
| **E. THEME & UI** | | |
| Default Misora Purple & White | DONE | config matches, THEME_PRESETS correct |
| Procedural window icon | DONE | apply_window_icon |
| ONE live re-theme pass | PARTIAL | _apply_theme_to_all exists; Toplevel coverage unknown |
| Contrast-safe text | DONE | wcag_relative_luminance, best_contrast_fg |
| "Find in Files"/"Save & Patch" pink-on-pink | UNVERIFIED | Live check needed |
| Customize = top-level MENU | DONE | Customize menu in menubar |
| Every dockable panel pin/unpin | PARTIAL | Bug #7: pin only on Search Results |
| Pin states persist | UNVERIFIED | |
| **F. CONFIG & PERSISTENCE** | | |
| ONE config schema | DONE | misora_config.json v4 |
| Fonts, theme, search folder+scope | DONE | In save payload |
| BepInEx folder, backup folder | DONE | In save payload |
| Datamine + editor paths | DONE | In save payload |
| Panel pin/collapse/sash states | PARTIAL | left_dock_width saved; sash positions? |
| Window geometry | MISSING | Not found in save payload |
| Continuous/Preview toggles | MISSING | Not found in save payload |
| Sync-XUAT checkbox | MISSING | var_sync_xuat not in payload |
| View-menu gutter toggles | DONE | show_line_numbers/show_column_ruler |
| Debug settings | DONE | debug dict |
| Save on change + WM_DELETE_WINDOW | PARTIAL | WM_DELETE_WINDOW calls _save_user_prefs |
| Merge-migrate old configs | DONE | field-by-field validation |
| **G. UNDO / CLIPBOARD / TOASTS** | | |
| MASTER UNDO/REDO buttons | DONE | Edit menu + Ctrl+Z/Y bindings on window |
| Ctrl+Z/Y in Continuous | BROKEN | Bug #3: return "break" at line 4901 |
| Undo restores text + marks | UNVERIFIED | |
| Typing coalesced | DONE | undo_journal.py coalescing |
| Cross-box clipboard | DONE | _on_continuous_copy, [[BOX:N]] markers |
| Paste distributes chunks | DONE | _on_continuous_paste_guard |
| Marker-count check on paste | UNVERIFIED | |
| Toast notifications | DONE | show_toast |
| Toast toggle in settings | UNVERIFIED | |
| One pipeline with logger | PARTIAL | Toasts exist; logger also exists |
| **H. MENUS & INTEGRATIONS** | | |
| Left dock Search Results default | DONE | left_dock_tab persisted |
| Left dock Opened Files | DONE | tab_files_frame |
| Click switches editor in Opened Files | DONE | _refresh_opened_files_list |
| Dirty file close prompts save | UNVERIFIED | |
| Right-click context menus | PARTIAL | _on_results_right_click exists; Opened Files? |
| "Open Containing Folder" | UNVERIFIED | |
| "Open With" Notepad/Notepad++ | UNVERIFIED | |
| "Folders & Files" menu → Paths window | DONE | on_open_paths_config |
| Backup folder + same-as-program | UNVERIFIED | |
| BepInEx project folder | DONE | bepinex_project_folder |
| Datamine menu | DONE | on_launch_datamine |
| Datamine confirmation dialog | DONE | _datamine_confirm_skip |
| Non-blocking subprocess.Popen | DONE | subprocess.Popen used |
| Debug menu | DONE | debug_menu |
| Log Categories | DONE | LOG_CATEGORIES |
| Log to File | DONE | var_log_to_file |
| Embedded console REMOVED | DONE | No embedded console panel |
| python.exe (not pythonw.exe) | UNVERIFIED | misora.bat not fully read |
| Central logger → stdout/stderr | DONE | MisoraLogger |
| .unity3d file association | DONE | register/unregister_association.bat + winreg code |
| **I. TRANSLATOR & AI** | | |
| Translator window | DONE | MTLEngine, on_open_translator_assistant |
| Background threads + timeouts | DONE | translate_async |
| Per-box cache | UNVERIFIED | |
| Custom MTL HTTP template | DONE | mtl_engine.py |
| AI Prompt Builder | DONE | on_copy_ai_prompt |
| [[Box #NNNN]] marker format | DONE | Tests confirm marker format |

---

## KNOWN BUG STATUS (COMPREHENSIVE AUDIT)

| # | Bug / Issue Area | Real User Status | Technical Cause & Fix Plan |
|---|---|---|---|
| **B1** | **Open Folder from Menu (`File -> Open Folder...`)** | **BROKEN** | Unlike folder DnD, menu open only opens 1st file or sets search scope without the *Yes (open all) / No (scope only) / Cancel* prompt or batch safety checks. Unify menu open with the DnD folder workflow. |
| **B2** | **"Show Line Numbers" (Vertical)** | **BROKEN** | Toggling checkbox runs `pack_forget()` then `pack(side="left")` without `before=`, causing the gutter to pack after/behind the text editor or fail to re-anchor. Must pack `before=txt_dialogue` in Page view and `before=txt_continuous` in Continuous view. |
| **B3** | **"Show Column Ruler" / Horizontal character count** | **BROKEN** | Column ruler text widget repacks at bottom or disappears because `pack(side="top")` lacks `before=clean_editor_row`. Must pack `before=clean_editor_row`. |
| **B4** | **Continuous View instability & cursor loss** | **BROKEN** | Inline edits and undo wipe the entire continuous widget (`delete("1.0", tk.END)`), re-rendering all boxes from scratch instead of applying local span updates. Multi-box selection deletion returns `"break"` without feedback. |
| **B5** | **Custom Themes non-functional & reverting** | **BROKEN** | Side drawer custom color swatch buttons and hex entries are never updated during theme refreshes. On `<FocusOut>`, `_commit_theme_hex()` triggers with stale initial values, immediately overwriting and reverting custom color selections. |
| **B6** | **Undo and Redo not working in editor** | **BROKEN** | `txt_dialogue` has native `undo=True` enabled, executing Tkinter's internal un-tracked undo buffer instead of `MasterUndoJournal`, desyncing the editor widget from `StoryDocument`. Must disable native widget undo (`undo=False`) and route Ctrl+Z / Ctrl+Y strictly through `MasterUndoJournal`. |
| **B7** | **Ribbon button widths too wide** | **PARTIAL** | Hardcoded `width=10` on `Color`, `Grad`, `Ruby`, `[-]`, and `{player}` creates oversized buttons (especially `[-]`). Remove fixed width and use natural text width with padding. |
| **B8** | **Plain `.txt` save verification & backups** | **NEEDS TEST** | Ensure editing raw `.txt` files properly tracks dirty state, creates timestamped backups in the backup directory, and repacks without error. |

---

## DECISIONS LOG

| Decision | Detail |
|----------|--------|
| Folder Open Consistency | `File -> Open Folder...` and drag-and-drop folder drop must use the exact same prompt (*Yes / No / Cancel*) and batch thresholds. |
| Master Undo Journal | Tkinter native widget undo (`undo=True`) must be disabled (`undo=False`) so `MasterUndoJournal` is the single source of truth for all undo/redo operations across AST and UI. |
| Theme State Synchronization | Theme changes must dynamically update all swatch button colors and `StringVar` hex entries in the Customize drawer, preventing focus-out reverts. |
| Ruler & Gutter Packing | Line numbers gutter and horizontal column ruler must use explicit `before=` anchoring so toggling preserves layout hierarchy without displacing the editor. |
| NGUI Gradient Format | Ribbon inserts comma format `[RRGGBB,RRGGBB]`; parser accepts both `[-,]`. |

---

## PHASED ROADMAP & PRIORITIZED ACTION PLAN

### Phase 1: Core GUI Bug Fixes (Fix What Is Broken First)
- [x] **1.1 Unify Menu "Open Folder" with DnD Flow** (DONE)  
  Updated `on_open_folder()` and `_process_opened_folder()` to detect story files, prompt (*Yes: Open all into tabs / No: Set search scope only / Cancel: Abort*), and enforce batch safety limits.
- [x] **1.2 Fix Vertical Line Numbers & Horizontal Column Ruler Toggles** (DONE)  
  Fixed packing order with `before=` anchors and `_is_widget_packed()` for `gutter_clean`, `ruler_clean`, `gutter_cont`, and `ruler_cont`.
- [x] **1.3 Fix Custom Theme Color Picker & Persistence** (DONE)  
  Synchronized `_theme_swatch_buttons` and `_theme_hex_vars`; prevented stale focus-out overwrites in `_commit_theme_hex()`.
- [x] **1.4 Fix Undo / Redo in Dialogue & Continuous Editors** (DONE)  
  Bound `<Control-z>` and `<Control-y>` directly on `txt_dialogue` via `_shortcut_undo()` and `_shortcut_redo()` returning `"break"` to prevent Tkinter class desync; preserved scroll position during continuous view re-renders.
- [x] **1.5 Fix Ribbon Button Widths** (DONE)  
  Removed hardcoded `width=10` from ribbon buttons (`[-]`, `{player}`, `Color`, `Grad`, `Ruby`), replacing with natural label width and clean padding.

### Phase 2: Workflow & Editor Usability
- [ ] **2.1 Right-Click Context Menu for "Opened Files" Dock**  
  Add context menu: *Close*, *Close Others*, *Close All*, *Save (Ctrl+S)*, *Reveal in Explorer*, *Copy Full Path*.
- [ ] **2.2 Seamless Cursor & Box Sync between Continuous View & Page View**  
  Smoothly transition active box and cursor offset when toggling between Continuous View and single-box Page View.
- [ ] **2.3 Plain `.txt` Save Verification & Automated Backups**  
  Verify and add unit tests for opening, editing, dirty-tracking, timestamped backups, and saving plain `.txt` translation dictionaries.

### Phase 3: Machine Translation (MTL) & AI Prompt Integration
- [ ] **3.1 MTL Engines & Connectivity**  
  DeepL Free/Pro API integration, local/Sugoi HTTP translation server support, and connection verification testing.
- [ ] **3.2 Tag Masking & Entity Shielding**  
  Strict protection of `{playername}`, NGUI color/gradient/bold tags, and Ruby markup during translation passes.
- [ ] **3.3 AI / LLM Prompt Header Exporter & Customizer**  
  Customizable translation rules, character context, speaker metadata formatting, and 1-click clipboard export for LLMs.
- [ ] **3.4 Dedicated Floating Translation Assistant Workspace**  
  Side-by-side Japanese original vs. translated drafts, comparison cards, and 1-click application to the active dialogue box.
- [ ] **3.5 Batch Story Translation Sweep**  
  Automated translation of untranslated boxes in a story with progress reporting and cancellation support.

---

## WORK STYLE NOTES
- Before each step: verify clean compile (`py -3.12 -m py_compile misora.py`).
- Run all unit tests (`py -3.12 -m unittest discover -s tests`).
- Document all resolutions in this file and present concise status reports to the user.
