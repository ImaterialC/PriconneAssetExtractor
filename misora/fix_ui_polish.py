"""
Fix script: UI polish pass
1. Remove explicit width from B/I/U/S/Sub/Sup ribbon mini buttons (let label determine width)
2. Remove explicit width from {player} button
3. Extend walk() in _apply_theme_and_fonts_live to recurse into child Toplevel windows
"""
import re

src_path = r'D:\priconne-asset-extractor-main\misora\misora.py'
with open(src_path, encoding='utf-8') as f:
    src = f.read()

original = src

# ─── Fix 1 & 2: Remove width= from mini_style_buttons loop and {player} button ───
# Change mini buttons: remove width=w_len (pass None instead, omit width kwarg)
old_mini = '''        mini_style_buttons = [
            ("B", "[b]", "[/b]", 1),
            ("I", "[i]", "[/i]", 1),
            ("U", "[u]", "[/u]", 1),
            ("S", "[s]", "[/s]", 1),
            ("Sub", "[sub]", "[/sub]", 3),
            ("Sup", "[sup]", "[/sup]", 3),
        ]
        for lbl, o_tag, c_tag, w_len in mini_style_buttons:
            ttk.Button(
                ribbon,
                text=lbl,
                style="RibbonMini.TButton",
                width=w_len,
                command=lambda ot=o_tag, ct=c_tag: self.apply_ngui_wrapper(ot, ct),
            ).pack(side="left", padx=1, pady=1)'''

new_mini = '''        mini_style_buttons = [
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
            ).pack(side="left", padx=1, pady=1)'''

if old_mini in src:
    src = src.replace(old_mini, new_mini)
    print("✓ Fix 1: Removed width from mini_style_buttons loop")
else:
    print("✗ Fix 1: Pattern not found!")

# Fix 2: {player} button width=6 → remove width kwarg
old_player = '        ttk.Button(ribbon, text="{player}", style="Ribbon.TButton", width=6, command=self.on_insert_playername).pack(side="left", padx=1, pady=1)'
new_player = '        ttk.Button(ribbon, text="{player}", style="Ribbon.TButton", command=self.on_insert_playername).pack(side="left", padx=1, pady=1)'

if old_player in src:
    src = src.replace(old_player, new_player)
    print("✓ Fix 2: Removed width from {player} button")
else:
    print("✗ Fix 2: Pattern not found!")

# ─── Fix 3: Extend walk() to also recurse into child Toplevel windows ───
old_walk_call = '''        walk(self)

        self.txt_results.configure('''

new_walk_call = '''        walk(self)
        # Also re-theme any currently-open child Toplevel windows
        for child_win in self.winfo_children():
            if isinstance(child_win, tk.Toplevel) and child_win.winfo_exists():
                try:
                    child_win.configure(bg=t["bg_panel"])
                except Exception:
                    pass
                walk(child_win)

        self.txt_results.configure('''

if old_walk_call in src:
    src = src.replace(old_walk_call, new_walk_call)
    print("✓ Fix 3: Extended walk() to recurse into child Toplevel windows")
else:
    print("✗ Fix 3: Pattern not found!")

# ─── Fix 4: RibbonMini padding tweak — tighter so width is truly label-driven ───
# The style already has padding=(1,0) which is fine. No change needed here.
# But we should ensure no leftover `width=w_len` in undo/redo buttons either (they use width=2).
# Those are fixed to 2 chars which is intentional for icon chars. Leave them.

if src == original:
    print("\n⚠ No changes were made — all patterns already matched or not found.")
else:
    with open(src_path, 'w', encoding='utf-8') as f:
        f.write(src)
    changed = sum(1 for a, b in zip(original.splitlines(), src.splitlines()) if a != b)
    print(f"\n✓ Wrote {src_path} ({changed} lines changed)")
