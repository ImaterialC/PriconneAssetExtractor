# MISORA — PROJECT STATE
*Last updated: 2026-11-18 — Bug #12 (NGUI Color Window) and Bug #3 (Continuous Ctrl+Z/Y Undo) fixed*

---

## SESSION HANDOFF / RESUME INSTRUCTIONS
**Current step:** Bug #12 (NGUI Color & Gradient Picker) verified and hardened:
- SV map & Gradient preview rendered with Pillow `ImageTk.PhotoImage`
- Hue bar rendered with Tk native `tk.PhotoImage.put()` (bypasses 125%+ DPI narrow canvas clipping)
- Window geometry set to explicit `400x320` minimum (ensures swatches, hex entry, and insert buttons are never truncated)
- Canvas images retain explicit C-level references (`canvas.image = img`)
- Detailed logging added on popup creation
- Unit tests: 11/11 passing
- **IMPORTANT NOTE FOR USER:** The app must be fully closed (close existing Misora window) before launching `misora.bat` so Python loads the new files from disk.

**Next action:** Apply DnD improvements (Bug #1: folder multi-file confirmation prompt, large-file safety warning, binary non-text file filter).  
Awaiting user confirmation to apply DnD improvements.

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

## KNOWN BUG STATUS

| # | Bug | Status |
|---|-----|--------|
| 1 | DnD crashes (ctypes WM_DROPFILES) | FIXED & VERIFIED by user: Multi-file works; needs folder multi-file prompt & non-text format guard |
| 2 | Config persists only fonts/theme | PARTIAL — paths persist; some toggles missing (geometry, Continuous/Preview, sync-XUAT) |
| 3 | Undo/Redo absent; Ctrl+Z/Y blocked | DONE — Ctrl+Z (undo) and Ctrl+Y / Ctrl+Shift+Z (redo) unblocked in Continuous key guard |
| 4 | Theme misses some windows | UNVERIFIED — needs live test |
| 5 | Button labels unreadable on accents | DONE — wcag_relative_luminance + best_contrast_fg implemented |
| 6 | Ribbon buttons too wide | PARTIAL — all width=10; spec wants variable widths |
| 7 | Pin icon only on Search Results | UNVERIFIED — needs live check |
| 8 | Embedded Debug console | DONE — console removed; F12 shows toast |
| 9 | Continuous→Page lands wrong box | UNVERIFIED — needs live test |
| 10 | Up arrow doesn't cross to prev box | DONE in code — lines 4867-4879 + 5291-5298 |
| 11 | Delete blocked on multi-box selection | PARTIAL — on_clear_dialogue_skeleton exists; spec details unverified |
| 12 | Eyedropper & Color window broken | DONE — Swapped to Pillow ImageTk.PhotoImage + DPI-aware ImageGrab, fixed window geometry (394x310) |
| 13 | NGUI_TOKEN_RE corrupted | NOT PRESENT — compiles clean |
| 14 | Gradient separator comma vs hyphen | DECIDED: Ribbon inserts comma `[RRGGBB,RRGGBB]`; parser accepts both `[-,]` |
| 15 | Plain .txt save "Nothing to Save" | LIKELY FIXED — code path exists; needs live test |
| 16 | RRGGBBAA crashes preview; \n not rendered | UNVERIFIED |
| 17 | Stale dark misora_config.json override | NOT PRESENT — current config is Purple & White |

---

## DECISIONS LOG

| Decision | Detail |
|----------|--------|
| Theme default | Misora Purple & White confirmed in THEME_PRESETS and misora_config.json |
| Gradient separator in regex | Both `[-,]` accepted in NGUI_TAG_RE and NGUI_TOKEN_RE |
| Gradient ribbon insert | Ribbon inserts comma format `[RRGGBB,RRGGBB]` per Section 4-D and user agreement |
| Eyedropper & Color Map | Pillow `ImageTk.PhotoImage` + `ImageGrab` approved & installed |
| DnD approach | Existing ctypes hook works for multi-file; add folder scan prompt + binary filter |
| Test suite | 11 tests (11/11 pass); 3 more tests from brief DoD not yet written |

---

## PRIORITIZED TODO (checkboxes)

### P0 — Stability (FIRST, before anything else)

- [ ] **P0-1** Fix Ctrl+Z/Y blocked in Continuous key guard  
  File: `misora.py` line 4901-4902  
  Change: `if ctrl and keysym.lower() in {"z", "y"}: return "break"` → pass through or call on_undo/on_redo  
  Risk: LOW — single line, well-understood

- [ ] **P0-2** Verify .txt save works (live test with a .txt file)  
  If broken: check `is_bundle_file` initialization for .txt files

- [ ] **P0-3** Verify DnD does not crash (live drag-drop test)  
  If crashes: **PROPOSE** tkinterdnd2 swap to user, await approval

- [ ] **P0-4** Complete config persistence: add missing fields  
  Missing: window geometry, Continuous/Preview toggle, sync-XUAT checkbox, sash positions  
  Low risk; straightforward serialization additions

- [ ] **P0-5** Verify unit tests still pass after each P0 step

### P1 — UI Correctness

- [ ] **P1-1** Verify Ctrl+Z/Y undo works correctly after P0-1 fix
- [ ] **P1-2** Verify theme coverage — Toplevels + dialogs open during re-theme  
  If broken: audit `_apply_theme_to_all` to ensure all Toplevels registered
- [ ] **P1-3** Ribbon widths — verify natural width spec vs current width=10  
  If wrong: change to width-less buttons with padx instead
- [ ] **P1-4** Pin icon: audit all dockable panels; add pin/unpin if missing
- [ ] **P1-5** Continuous↔Page toggle box sync — live test  
  If broken: fix `_on_toggle_view` to preserve current_box_idx
- [ ] **P1-6** Up arrow — live test both Page and Continuous views
- [ ] **P1-7** Multi-box Delete — verify confirm dialog + skeleton preserved + undo
- [ ] **P1-8** Eyedropper — live test at 100% DPI; if DPI scaling broken, **PROPOSE** Pillow ImageGrab
- [ ] **P1-9** Ask user: which gradient separator does real corpus use (comma or hyphen)?
- [ ] **P1-10** RRGGBBAA in preview — test + fix truncation; literal \n as line break in preview

### P2 — Workflow

- [ ] **P2-1** Replace dialog — verify present and working
- [ ] **P2-2** Right-click context menus — Opened Files panel
- [ ] **P2-3** "Open Containing Folder" action
- [ ] **P2-4** NGUI Glossary location — verify it's a top-level MENU (not side drawer button)
- [ ] **P2-5** Toasts toggle in settings — verify persisted
- [ ] **P2-6** Datamine confirmation dialog details
- [ ] **P2-7** Verify "Open Files" scope searches in-memory docs

### P3 — Deferred

- Translator window and AI Prompt Builder: largely done per code audit; edge cases last
- Token/API providers: explicitly deferred by user

### NEW TESTS (from Definition of Done)

- [ ] Empty-body codec round-trip test
- [ ] Clipboard marker round-trip test  
- [ ] Undo batch integrity test

---

## ASK-FIRST ITEMS (pending user response)

1. **Gradient separator in real XUAT dictionaries**: Do your `.txt` files use `[RRGGBB,RRGGBB]` (comma) or `[RRGGBB-RRGGBB]` (hyphen)? This determines what the ribbon inserts.
2. **DnD swap proposal**: If Bug #1 is confirmed crashing, approve `tkinterdnd2` replacement?
3. **Eyedropper Pillow swap proposal**: If Bug #12 fails at 125%/150% DPI, approve `Pillow` ImageGrab?

---

## WORK STYLE NOTES

- Git is available (`main` branch, clean except `misora_config.json` modified + 2 untracked .bak files).
- **Before each step**: `git add -A && git commit -m "snapshot: before <step>"` for easy revert.
- **After each step**: compile + test, update this file, report briefly, WAIT for "go".
