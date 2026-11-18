#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora.assets.splash - Minimal, Lightweight Splash Screen
==========================================================
Displays a fast 600x400 placeholder window while Misora Editor initializes.
Uses lightweight 600x400 JPEG artwork (Splash_1.jpg, Splash_2.jpg, Splash_3.jpg)
with zero resizing overhead and minimal canvas elements so it displays instantly.
"""
from __future__ import annotations

import random
import tkinter as tk
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

SPLASH_DIR = Path(__file__).resolve().parent
SPLASH_IMAGES = ["Splash_1.jpg", "Splash_2.jpg", "Splash_3.jpg"]
SPLASH_W = 600
SPLASH_H = 400


class MisoraSplashScreen:
    """
    Lightweight, instant splash placeholder for Misora Editor.
    Fixed 600x400 window with minimal text and a thin progress line.
    """

    def __init__(self):
        self._root = tk.Tk()
        self._root.overrideredirect(True)

        # Center on screen
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = max(0, (sw - SPLASH_W) // 2)
        y = max(0, (sh - SPLASH_H) // 2)
        self._root.geometry(f"{SPLASH_W}x{SPLASH_H}+{x}+{y}")

        self._canvas = tk.Canvas(
            self._root,
            width=SPLASH_W,
            height=SPLASH_H,
            highlightthickness=0,
            bd=0,
            bg="#1a0a2e",
        )
        self._canvas.pack(fill="both", expand=True)

        self._photo: Optional[object] = None
        self._load_artwork()

        # Artwork image
        if self._photo:
            self._canvas.create_image(0, 0, anchor="nw", image=self._photo)

        # Subtle dark glass bar at bottom for text legibility
        self._canvas.create_rectangle(0, SPLASH_H - 80, SPLASH_W, SPLASH_H, fill="#120624", outline="")
        self._canvas.create_line(0, SPLASH_H - 80, SPLASH_W, SPLASH_H - 80, fill="#7b42bc", width=1)

        # Title: "Misora Editor" (prominent, with shadow)
        self._canvas.create_text(
            21, SPLASH_H - 51,
            anchor="w",
            text="Misora Editor",
            font=("Segoe UI", 20, "bold"),
            fill="#0a0314",
        )
        self._canvas.create_text(
            20, SPLASH_H - 52,
            anchor="w",
            text="Misora Editor",
            font=("Segoe UI", 20, "bold"),
            fill="#ffffff",
        )

        # Version & Tool descriptor (small)
        self._canvas.create_text(
            SPLASH_W - 20, SPLASH_H - 52,
            anchor="e",
            text="Priconne Unity3D Story Tool · v1.3.1",
            font=("Segoe UI", 8),
            fill="#d4c4ec",
        )

        # Loading status message (small)
        self._msg_id = self._canvas.create_text(
            20, SPLASH_H - 24,
            anchor="w",
            text="Starting…",
            font=("Segoe UI", 8),
            fill="#e8dbfa",
        )

        # Minimal bottom progress bar (4px height)
        self._canvas.create_rectangle(0, SPLASH_H - 4, SPLASH_W, SPLASH_H, fill="#221833", outline="")
        self._bar_id = self._canvas.create_rectangle(0, SPLASH_H - 4, 0, SPLASH_H, fill="#a66cff", outline="")

        self._root.update()

    def _load_artwork(self) -> None:
        """Load one of Splash_1.jpg, Splash_2.jpg, Splash_3.jpg directly without resizing."""
        candidates = list(SPLASH_IMAGES)
        random.shuffle(candidates)

        for name in candidates:
            img_path = SPLASH_DIR / name
            if not img_path.exists():
                continue
            if _HAS_PIL:
                try:
                    img = Image.open(img_path)
                    self._photo = ImageTk.PhotoImage(img, master=self._root)
                    return
                except Exception:
                    pass
            # Fallback to PhotoImage if supported
            try:
                self._photo = tk.PhotoImage(file=str(img_path), master=self._root)
                return
            except Exception:
                pass

    def set_progress(self, val: float, msg: str = "") -> None:
        """Update progress bar fill and small status text."""
        val = max(0.0, min(1.0, float(val)))
        bar_w = int(SPLASH_W * val)
        self._canvas.coords(self._bar_id, 0, SPLASH_H - 4, bar_w, SPLASH_H)
        if msg:
            self._canvas.itemconfig(self._msg_id, text=msg)
        self._root.update_idletasks()

    def process_events(self) -> None:
        """Process pending UI events."""
        try:
            self._root.update_idletasks()
        except Exception:
            pass

    def close(self, callback=None) -> None:
        """Destroy the splash window immediately."""
        try:
            self._root.destroy()
        except Exception:
            pass
        if callable(callback):
            try:
                callback()
            except Exception:
                pass
