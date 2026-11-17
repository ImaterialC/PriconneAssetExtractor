#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Misora Theme Palette & Embedded Window Icon
===========================================
Official Misora Purple & White UI palette and procedural 32x32 window icon
(zero external image file dependencies).
"""
from __future__ import annotations

import tkinter as tk
from typing import Dict

THEME: Dict[str, str] = {
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
}


def create_misora_icon(size: int = 32) -> tk.PhotoImage:
    """Generate a crisp 32x32 Purple & White 'M' emblem PhotoImage."""
    img = tk.PhotoImage(width=size, height=size)
    bg_outer = "#612ea0"
    bg_inner = "#7b42bc"
    border_hi = "#d4c4ec"
    fg_white = "#ffffff"

    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            # Rounded-corner mask
            if (x in (0, size - 1) and y in (0, 1, size - 2, size - 1)) or (
                y in (0, size - 1) and x in (0, 1, size - 2, size - 1)
            ):
                row.append(bg_outer)
                continue

            if x in (1, size - 2) or y in (1, size - 2):
                row.append(border_hi)
                continue

            # Stylized white 'M' monogram centered in the badge
            in_left_stem = 7 <= x <= 10 and 8 <= y <= 23
            in_right_stem = 21 <= x <= 24 and 8 <= y <= 23
            in_left_diag = (11 <= x <= 15) and (abs((y - 9) - (x - 10) * 2) <= 1) and (8 <= y <= 19)
            in_right_diag = (16 <= x <= 20) and (abs((y - 9) - (21 - x) * 2) <= 1) and (8 <= y <= 19)

            if in_left_stem or in_right_stem or in_left_diag or in_right_diag:
                row.append(fg_white)
            else:
                row.append(bg_inner)
        rows.append("{" + " ".join(row) + "}")

    img.put(" ".join(rows))
    return img


def apply_window_icon(window: tk.Tk) -> None:
    """Attach the Misora Purple & White emblem to the Tkinter root window."""
    try:
        icon_img = create_misora_icon(32)
        window.iconphoto(True, icon_img)
        setattr(window, "_misora_icon_ref", icon_img)
    except Exception:
        pass