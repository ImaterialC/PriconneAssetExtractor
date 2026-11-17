#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora.assets.icon - Embedded icon and theme assets for Misora.
"""
import base64
import os
from pathlib import Path

# Misora Signature Color Palette
THEME = {
    "bg_dark": "#1a1a22",
    "bg_panel": "#242430",
    "bg_editor": "#181820",
    "border": "#353545",
    "fg_text": "#e8e8f2",
    "fg_muted": "#8f8fa8",
    "misora_pink": "#ff7da7",
    "misora_pink_hover": "#ff98b8",
    "misora_pink_active": "#e05886",
    "accent_blue": "#68b5f3",
    "accent_green": "#7ee787",
    "accent_yellow": "#e3b341",
    "highlight_bg": "#432338",
}

def get_asset_path(filename: str) -> Path:
    return Path(__file__).parent / filename
