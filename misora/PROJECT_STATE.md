# MISORA — PROJECT STATE
*Last updated: 2026-11-19 — Mapped User Feedback on Phase 1 & Detailed Fix Plan for Phase 1.2*

---

## SESSION HANDOFF / RESUME INSTRUCTIONS

### Current Feedback Mapping & Resolution Flow (Turn 10 Review):
1. **#1 Resolved: Menu "Open Folder..." Flow (VERIFIED FIXED)**
   - `File -> Open Folder...` and drag-and-drop folder drop are unified into `_process_opened_folder()`.
   - Correctly prompts (*Yes: Open all into tabs / No: Set search scope only / Cancel: Abort*), handles single-file auto-opening, sets Current File(s) scope, and enforces batch safety limits. Confirmed resolved by user.

2. **#2 View Menu Toggles for Line Numbers & Column Ruler (ACTIVE ISSUE)**
   - Checkboxes under `View` menu (*Show Line Numbers (Vertical)*, *Show Column Ruler (Horizontal)*) do not reliably toggle widget display in live GUI.
   - Root causes:
     - On Windows, `selectcolor=t["misora_pink"]` in `tk.Menu.add_checkbutton` interferes with native Windows checkmark drawing.
     - `_on_toggle_line_numbers()` and `_on_toggle_column_ruler()` packing must handle both Page View (`text_container` / `clean_editor_row`) and Continuous View (`continuous_wrap` / `cont_editor_row`), followed by an immediate layout refresh (`_sync_gd_scroll_bounds()` and canvas scrollregion update).

3. **#3 Custom Themes Non-Functional in Customize Side Drawer (ACTIVE ISSUE)**
   - Custom colors do not apply or revert when selected from the side drawer.
   - Root causes:
     - `THEME_PRESETS` combobox `values` list does not include `"Custom"`, so when `_detect_active_preset_name()` returns `"Custom"`, readonly combobox reverts or fails to reflect custom state.
     - Clicking `[Apply]` on the preset combobox overwrites custom color values back to the preset.
     - Hex entries in the drawer need high visual contrast and smooth two-way binding so swatch clicks and hex edits apply live without focus-out reverts.

4. **#4 Undo Pink Artifact, Redo Failure, and Missing Ribbon Buttons (ACTIVE ISSUE)**
   - User verified: Undo works, but leaves a pink highlight box artifact at the end of dialogue lines (Image 3 & 4: `media_1795022250438_63fac6b0.png` & `media_1795022505233_869af5c7.jpg`).
   - Redo reports "Nothing to redo." on status bar.
   - Ribbon Undo (`↶`) and Redo (`↷`) buttons are completely missing from view.
   - Technical root causes:
     - **Pink Artifact:** In `core/story_ast.py`, `inject_box()` had default argument `fill: str = " "` for non-target segments. When dialogue boxes with multiple binary segments (e.g. Box 39 with 8 segments) are edited or restored by undo, 7 spaces are injected at the tail of the string. `_highlight_secret_whitespace()` tagged these trailing spaces with an opaque pink rectangle (`background="#ffd6d6"`).
     - **Redo Failure:** `<KeyRelease>` fires on modifier and arrow key releases, and `undo=True` in Tkinter causes desync. Need strict equality guard and `undo=False` on `txt_dialogue`.
     - **Missing Buttons:** Ribbon buttons were ballooned to 969px total width by `ttk.Button` minimum width constraints, pushing `[↶]`, `[↷]`, and `[Preview]` completely off-screen to the right!

5. **#5 Ribbon Button Dimensions & Visual Spec (Image 2 Alignment)**
   - User provided exact visual specification in Image 2 (`media_1795022139451_3bf3b6d4.png`):
     - Primary attribute buttons (`Color`, `Grad`, `Ruby`): ~45px wide, purple accent styling.
     - Secondary attribute buttons (`[-]`, `{player}`): ~45px wide (compact, matching label).
     - Mini formatting buttons (`B`, `I`, `U`, `S`, `Sub`, `Sup`): ~21px wide.
     - Explicit Undo (`↶`) and Redo (`↷`) buttons placed right after `Sub` `Sup`, ~21px wide, styled with green accent arrows as shown in Image 2 mockup.
   - Technical cause: Windows native `ttk.Button` theme enforces a 63px minimum width even on single-letter labels. Replacing with compact `tk.Button` widgets allows exact pixel/character sizing (~21px for mini, ~45px for primary), reducing ribbon total width from 969px to ~400px so all buttons and preview controls fit comfortably.

6. **# Extra: Editor Border Thickness Artifact (Image 4)**
   - In Image 4, the border around `txt_dialogue` appears thick (2px) and dark.
   - Cause: `txt_dialogue` has `bd=1, relief="solid"` plus default Tkinter `highlightthickness=1`. When focused, both borders render together, doubling visual thickness. Setting `highlightthickness=0` restores a clean, uniform 1px border.

---

## BACKUP & SAFETY ARCHIVE
- **Disk snapshot archive:** `misora/_archive/20261118_takeover_baseline/`
- **Git commits:**
  - `bcc57c6`: Initial takeover audit.
  - `db599f9`: Fixed `misora.bat` invocation bug.
  - `d96da3d`: Updated `misora.bat` to auto-detect Python 3.12 with UnityPy.
  - `fc2c6ba`: Fixed Bug #12 (Color Picker Pillow & Eyedropper) and Bug #3 (Continuous Ctrl+Z/Y undo).
  - `9b88571`: Project Folder <-> Find UI linking, multi-framework support, settings saved notifications.
  - `d3af46c`: Comprehensive audit overhaul.
  - `fa2170e`: Initial Phase 1 bug fix pass.
- **Old session backups preserved:** `misora.py.bak_20261118_142038`, `misora.py.bak2_20261118_142158`.

---

## KNOWN BUG STATUS (COMPREHENSIVE AUDIT)

| # | Bug / Issue Area | Real User Status | Technical Cause & Fix Plan |
|---|---|---|---|
| **B1** | **Open Folder from Menu (`File -> Open Folder...`)** | **RESOLVED** | Unified with `_process_opened_folder()`: prompts (*Yes / No / Cancel*), auto-opens single files, sets scope, batch safety. Verified by user. |
| **B2** | **"Show Line Numbers" (Vertical)** | **ACTIVE** | `selectcolor` on native Windows `tk.Menu` interferes with checkmark indicator; packing toggle must refresh canvas scrollregion and geometry immediately. |
| **B3** | **"Show Column Ruler" (Horizontal)** | **ACTIVE** | Must correctly pack before `clean_editor_row` and sync layout in both Page View and Continuous View. |
| **B4** | **Continuous View instability & cursor loss** | **ACTIVE** | Cursor position desync between Page View and Continuous View; full widget wipe on edit instead of local span replacement. |
| **B5** | **Custom Themes non-functional in side drawer** | **ACTIVE** | Preset combobox missing `"Custom"` in values; preset `[Apply]` overwrites custom colors; hex entries lack high-contrast live sync. |
| **B6** | **Undo Pink Artifact & Redo Failure** | **ACTIVE** | `inject_box()` had `fill: str = " "` injecting 7 trailing spaces into multi-segment boxes; `_highlight_secret_whitespace()` painted them pink (`#ffd6d6`); `txt_dialogue` needs `undo=False` to prevent Tkinter internal undo desync. |
| **B7** | **Ribbon Dimensions & Missing Undo/Redo Buttons** | **ACTIVE** | `ttk.Button` on Windows enforces 63px min width, inflating ribbon to 969px and clipping `↶`, `↷`, and `Preview`. Switch to compact `tk.Button` with ~45px for primary, ~21px for mini, and add green `↶` / `↷` buttons per Image 2. |
| **B8** | **Thick Border on Editor Text Widget** | **ACTIVE** | Default `highlightthickness=1` on `txt_dialogue` doubles the 1px relief border when focused. Set `highlightthickness=0` for clean 1px border. |
| **B9** | **Plain `.txt` save verification & backups** | **PENDING** | Verify and test plain `.txt` translation dictionaries with dirty tracking and backups. |

---

## DECISIONS LOG

| Decision | Detail |
|----------|--------|
| Folder Open Consistency | `File -> Open Folder...` and drag-and-drop folder drop use identical prompt logic (*Yes / No / Cancel*) and batch thresholds. |
| Master Undo Journal | Tkinter native widget undo (`undo=False`) disabled on all text editors; `MasterUndoJournal` is the single source of truth for AST and UI. |
| No Trailing Space Injection | `inject_box()` non-target binary segment fill changed from `" "` (space) to `""` (empty string) to prevent phantom trailing spaces on multi-segment boxes. |
| Secret Whitespace Visualization | Remove intrusive opaque pink background from `secret_whitespace` tag so trailing whitespace does not appear as a rendering glitch. |
| Ribbon Compact Buttons | Implement ribbon buttons with `tk.Button` to bypass Windows ttk 63px minimum constraint; enforce ~45px for primary and ~21px for mini buttons (`B`, `I`, `U`, `S`, `Sub`, `Sup`, `↶`, `↷`). |
| 1px Crisp Editor Borders | All text editors (`txt_dialogue`, `txt_raw`, `txt_continuous`) set to `highlightthickness=0, bd=1, relief="solid"` for sharp 1px borders. |
| Custom Theme "Custom" State | Add `"Custom"` to `THEME_PRESETS` combobox values and synchronize hex entries bidirectionally. |

---

## PHASED ROADMAP & PRIORITIZED ACTION PLAN

### Phase 1: Core GUI Bug Fixes (Fix What Is Broken First)
- [x] **1.1 Unify Menu "Open Folder" with DnD Flow** (DONE & VERIFIED BY USER)
- [x] **1.2 Fix Ribbon Button Dimensions & Add Undo/Redo Buttons (Image 2 Spec)** (DONE)
  - Switched ribbon buttons to compact `tk.Button` widgets.
  - Primary buttons (`Color`, `Grad`, `Ruby`, `[-]`, `{player}`): ~40-45px wide.
  - Mini formatting buttons (`B`, `I`, `U`, `S`, `Sub`, `Sup`): ~20-29px wide.
  - Added green accent `↶` (Undo) and `↷` (Redo) buttons directly following `Sub` `Sup`.
  - Total ribbon width reduced from 969px to 421px so all buttons and Preview fit comfortably without clipping.
- [x] **1.3 Fix Undo Pink Highlight Artifact & Redo Execution** (DONE)
  - Changed `inject_box()` default `fill: str = ""` in `core/story_ast.py` to prevent multi-segment trailing space injection.
  - Removed intrusive pink background from `secret_whitespace` tag in `misora.py`.
  - Set `undo=False` on `txt_dialogue` and ensured Redo executes reliably from keyboard, menu, and new ribbon button.
- [x] **1.4 Fix View Menu Toggles for Line Numbers & Column Ruler** (DONE)
  - Removed problematic `selectcolor` on `tk.Menu` checkbuttons for Windows native compatibility.
  - Added canvas and scrollregion synchronization (`_sync_gd_scroll_bounds()`) and feedback toasts.
- [x] **1.5 Fix Custom Themes in Customize Side Drawer** (DONE)
  - Added `"Custom"` to `THEME_PRESETS` combobox values.
  - Ensured swatch clicks and hex edits apply live, update presets, and persist to `misora_config.json`.
- [x] **1.6 Restore Crisp 1px Editor Border** (DONE)
  - Set `highlightthickness=0, bd=1, relief="solid"` on `txt_dialogue`, `txt_continuous`, and `txt_raw`.

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
