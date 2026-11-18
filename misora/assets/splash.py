#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora.assets.splash - Misora Splash Screen
============================================
Displays an animated splash screen before the main application loads.
Randomly picks one of the Splash_A/B/C artwork images, overlays the
Misora logo + version text, and animates a gradient progress bar.

Runs entirely within the standard library (tkinter, random, math, time).
No external dependencies.
"""
from __future__ import annotations

import math
import random
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


SPLASH_IMAGES = ["Splash_1.jpg", "Splash_2.jpg", "Splash_3.jpg", "Splash_1.png", "Splash_2.png", "Splash_3.png", "Splash_A.png", "Splash_B.png", "Splash_C.png"]
SPLASH_DIR = Path(__file__).resolve().parent

# Splash window size
SPLASH_W = 760
SPLASH_H = 420

# Theme colors
PURPLE_DARK  = "#4a1a80"
PURPLE_MID   = "#7b42bc"
PURPLE_LIGHT = "#a66cff"
WHITE        = "#ffffff"
PINK_ACCENT  = "#e040fb"
GLASS_BG     = "#1a0a2e"

# Loading messages that cycle while importing
_LOADING_MESSAGES = [
    "Preparing story editor…",
    "Loading bundle I/O engine…",
    "Initializing search engine…",
    "Configuring theme palette…",
    "Starting undo journal…",
    "Loading MTL engine…",
    "Applying WCAG contrast engine…",
    "Building NGUI ribbon…",
    "Ready.",
]


class MisoraSplashScreen:
    """
    Standalone splash window that displays artwork, logo, version and a
    progress bar while the heavy MisoraApp initializes in the background.

    Usage::

        splash = MisoraSplashScreen()
        # ... do heavy imports / init work in a background thread ...
        splash.set_progress(0.5, "Loading search engine…")
        # ... more work ...
        splash.close()
    """

    def __init__(self):
        self._root = tk.Tk()
        self._root.withdraw()  # hide until positioned

        self._closed = False
        self._progress_val = 0.0
        self._progress_msg = "Starting…"
        self._frame = 0
        self._shimmer_offset = 0.0

        self._build_window()
        self._root.update()
        self._root.deiconify()

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build_window(self):
        r = self._root
        r.overrideredirect(True)   # borderless
        r.configure(bg=GLASS_BG)
        r.resizable(False, False)
        r.attributes("-topmost", True)
        r.attributes("-alpha", 0.0)   # start transparent, fade in

        # Center on screen
        sw = r.winfo_screenwidth()
        sh = r.winfo_screenheight()
        x  = (sw - SPLASH_W) // 2
        y  = (sh - SPLASH_H) // 2
        r.geometry(f"{SPLASH_W}x{SPLASH_H}+{x}+{y}")

        # Main canvas fills everything
        self._canvas = tk.Canvas(
            r,
            width=SPLASH_W,
            height=SPLASH_H,
            bd=0, highlightthickness=0,
            bg=GLASS_BG,
        )
        self._canvas.pack(fill="both", expand=True)

        # Load & scale the artwork
        self._photo: Optional[tk.PhotoImage] = None
        self._load_artwork()

        # Build all canvas items (order matters: back → front)
        self._build_canvas_items()

        # Start fade-in and animation loop
        self._fade_in()
        self._animate()

    def _load_artwork(self):
        """Try to load a random splash artwork image into a PhotoImage with high-quality scaling."""
        candidates = random.sample(SPLASH_IMAGES, len(SPLASH_IMAGES))
        for name in candidates:
            img_path = SPLASH_DIR / name
            if not img_path.exists():
                continue
            if _HAS_PIL:
                try:
                    pil_img = Image.open(img_path)
                    # Resize to fit/fill SPLASH_W x SPLASH_H with aspect-preserving crop or fit
                    iw, ih = pil_img.size
                    scale = max(SPLASH_W / iw, SPLASH_H / ih)
                    nw, nh = int(iw * scale), int(ih * scale)
                    resample = getattr(Image, "Resampling", Image).LANCZOS
                    resized = pil_img.resize((nw, nh), resample=resample)
                    # Center crop to exact splash dimensions
                    left = (nw - SPLASH_W) // 2
                    top = (nh - SPLASH_H) // 2
                    cropped = resized.crop((left, top, left + SPLASH_W, top + SPLASH_H))
                    self._photo = ImageTk.PhotoImage(cropped, master=self._root)
                    self._photo_raw = self._photo
                    return
                except Exception:
                    pass
            # Fallback to stdlib tk.PhotoImage (PNG/GIF/PPM only)
            if img_path.suffix.lower() in (".png", ".gif", ".ppm"):
                try:
                    raw = tk.PhotoImage(file=str(img_path), master=self._root)
                    rw, rh = raw.width(), raw.height()
                    scale_x = max(1, rw // SPLASH_W)
                    scale_y = max(1, rh // SPLASH_H)
                    scale = max(scale_x, scale_y)
                    self._photo = raw.subsample(scale, scale) if scale > 1 else raw
                    self._photo_raw = raw
                    return
                except Exception:
                    pass
        self._photo = None

    def _build_canvas_items(self):
        c = self._canvas

        # ── Artwork background ──────────────────────────────────────────
        if self._photo:
            pw, ph = self._photo.width(), self._photo.height()
            # Center the image; it may be larger or smaller than canvas
            img_x = (SPLASH_W - pw) // 2
            img_y = (SPLASH_H - ph) // 2
            c.create_image(img_x, img_y, anchor="nw", image=self._photo, tags="artwork")
        else:
            # Fallback gradient rectangle
            c.create_rectangle(0, 0, SPLASH_W, SPLASH_H, fill=PURPLE_DARK, outline="", tags="artwork")

        # ── Dark gradient overlay at bottom for text legibility ─────────
        # Drawn as many thin rects fading from transparent (top) → opaque
        overlay_top = SPLASH_H - 180
        steps = 40
        for i in range(steps):
            alpha_ratio = i / steps
            # interpolate from fully transparent (#00000000) → semi-opaque glass
            r_val = int(0x1a * alpha_ratio)
            g_val = int(0x0a * alpha_ratio)
            b_val = int(0x2e * alpha_ratio)
            # Extra purple tint at bottom
            b_val = min(255, b_val + int(0x20 * alpha_ratio))
            color = f"#{r_val:02x}{g_val:02x}{b_val:02x}"
            y0 = overlay_top + (i * 180 // steps)
            y1 = overlay_top + ((i + 1) * 180 // steps)
            c.create_rectangle(0, y0, SPLASH_W, y1, fill=color, outline="", tags="overlay")

        # Solid bottom bar
        c.create_rectangle(0, SPLASH_H - 70, SPLASH_W, SPLASH_H, fill=GLASS_BG, outline="", tags="overlay_solid")

        # ── Purple accent line ──────────────────────────────────────────
        c.create_line(0, SPLASH_H - 72, SPLASH_W, SPLASH_H - 72, fill=PURPLE_LIGHT, width=1, tags="accent_line")

        # ── Logo text: "MISORA" ─────────────────────────────────────────
        # Shadow
        c.create_text(
            24 + 2, SPLASH_H - 162 + 2,
            anchor="sw",
            text="MISORA",
            font=("Segoe UI", 38, "bold"),
            fill="#0a0314",
            tags="logo_shadow",
        )
        # Foreground with purple-to-white gradient simulation (two layers)
        c.create_text(
            24, SPLASH_H - 162,
            anchor="sw",
            text="MISORA",
            font=("Segoe UI", 38, "bold"),
            fill=WHITE,
            tags="logo_text",
        )

        # ── Subtitle ────────────────────────────────────────────────────
        c.create_text(
            26, SPLASH_H - 123,
            anchor="sw",
            text="Unity3D Revision Tool & Story Editor",
            font=("Segoe UI", 11),
            fill="#d4c4ec",
            tags="subtitle_text",
        )

        # ── Version tag ─────────────────────────────────────────────────
        c.create_text(
            SPLASH_W - 16, SPLASH_H - 123,
            anchor="se",
            text="Version 1.3.0",
            font=("Segoe UI", 9),
            fill="#9b7ec8",
            tags="version_text",
        )

        # ── Progress bar track ──────────────────────────────────────────
        BAR_X0 = 16
        BAR_X1 = SPLASH_W - 16
        BAR_Y0 = SPLASH_H - 46
        BAR_Y1 = SPLASH_H - 32
        BAR_R  = 6  # corner radius

        self._bar_x0 = BAR_X0
        self._bar_y0 = BAR_Y0
        self._bar_x1 = BAR_X1
        self._bar_y1 = BAR_Y1

        # Track background
        self._draw_rounded_rect(c, BAR_X0, BAR_Y0, BAR_X1, BAR_Y1, BAR_R, fill="#2a1050", outline=PURPLE_MID, tag="bar_track")

        # Progress fill (initially 0 width)
        self._bar_fill_id = self._draw_rounded_rect(c, BAR_X0, BAR_Y0, BAR_X0, BAR_Y1, BAR_R, fill=PURPLE_MID, outline="", tag="bar_fill")

        # Shimmer overlay over the fill (animated)
        self._bar_shimmer_id = c.create_rectangle(BAR_X0, BAR_Y0, BAR_X0, BAR_Y1, fill=WHITE, outline="", stipple="gray25", tags="bar_shimmer")

        # ── Progress message text ────────────────────────────────────────
        self._msg_id = c.create_text(
            BAR_X0, BAR_Y0 - 6,
            anchor="sw",
            text=self._progress_msg,
            font=("Segoe UI", 8),
            fill="#9b7ec8",
            tags="progress_msg",
        )

        # ── Decorative corner dots ───────────────────────────────────────
        dot_sz = 4
        for dx, dy in [(0, 0), (SPLASH_W, 0), (0, SPLASH_H), (SPLASH_W, SPLASH_H)]:
            c.create_oval(dx - dot_sz, dy - dot_sz, dx + dot_sz, dy + dot_sz,
                          fill=PURPLE_LIGHT, outline="", tags="corner_dot")

        # ── Thin border outline ──────────────────────────────────────────
        c.create_rectangle(1, 1, SPLASH_W - 1, SPLASH_H - 1,
                           outline=PURPLE_MID, width=1, tags="border_rect")

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _draw_rounded_rect(self, canvas, x0, y0, x1, y1, r, fill, outline, tag):
        """Draw a rounded-corner rectangle on the canvas, return the polygon id."""
        pts = [
            x0 + r, y0,  x1 - r, y0,
            x1,     y0,  x1,     y0 + r,
            x1,     y1 - r, x1,  y1,
            x1 - r, y1,  x0 + r, y1,
            x0,     y1,  x0,     y1 - r,
            x0,     y0 + r, x0,  y0,
        ]
        return canvas.create_polygon(pts, fill=fill, outline=outline, smooth=True, tags=tag)

    # ------------------------------------------------------------------
    # Fade-in animation
    # ------------------------------------------------------------------

    def _fade_in(self, alpha=0.0):
        if self._closed:
            return
        alpha = min(1.0, alpha + 0.08)
        self._root.attributes("-alpha", alpha)
        if alpha < 1.0:
            self._root.after(20, lambda: self._fade_in(alpha))

    def _fade_out(self, alpha=1.0, callback=None):
        if self._closed:
            if callback:
                callback()
            return
        alpha = max(0.0, alpha - 0.08)
        self._root.attributes("-alpha", alpha)
        if alpha > 0.0:
            self._root.after(20, lambda: self._fade_out(alpha, callback))
        else:
            self._closed = True
            self._root.destroy()
            if callback:
                callback()

    # ------------------------------------------------------------------
    # Progress bar animation
    # ------------------------------------------------------------------

    def _animate(self):
        """Continuously redraw the progress bar fill + shimmer."""
        if self._closed:
            return
        self._frame += 1

        c = self._canvas
        x0 = self._bar_x0
        y0 = self._bar_y0
        y1 = self._bar_y1
        track_w = self._bar_x1 - x0

        fill_x1 = x0 + int(track_w * min(1.0, self._progress_val))

        # Recolor the bar using a purple → pink gradient based on progress
        progress = min(1.0, self._progress_val)
        # interpolate purple → pink
        r_col = int(0x7b + (0xe0 - 0x7b) * progress)
        g_col = int(0x42 + (0x40 - 0x42) * progress)
        b_col = int(0xbc + (0xfb - 0xbc) * progress)
        bar_color = f"#{r_col:02x}{g_col:02x}{b_col:02x}"

        # Redraw fill
        c.delete("bar_fill")
        if fill_x1 > x0 + 2:
            self._draw_rounded_rect(c, x0, y0, fill_x1, y1, 6, fill=bar_color, outline="", tag="bar_fill")
            c.tag_lower("bar_fill", "bar_shimmer")

        # Shimmer sweep
        shimmer_w = 60
        self._shimmer_offset = (self._shimmer_offset + 2.5) % (track_w + shimmer_w)
        sh_x0 = int(x0 + self._shimmer_offset - shimmer_w)
        sh_x1 = sh_x0 + shimmer_w
        # Clip shimmer to fill region
        sh_x0 = max(x0, sh_x0)
        sh_x1 = min(fill_x1, sh_x1)
        c.coords("bar_shimmer", sh_x0, y0, sh_x1, y1)

        # Pulse the logo text color
        pulse = (math.sin(self._frame * 0.05) + 1.0) / 2.0  # 0..1
        lum = int(0xd4 + (0xff - 0xd4) * pulse)
        logo_col = f"#{lum:02x}{lum:02x}{lum:02x}"
        c.itemconfig("logo_text", fill=logo_col)

        # Update status message
        c.itemconfig("progress_msg", text=self._progress_msg)

        self._root.after(16, self._animate)   # ~60 fps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_progress(self, value: float, message: str = ""):
        """Update progress (0.0–1.0) and optional status message."""
        self._progress_val = max(0.0, min(1.0, value))
        if message:
            self._progress_msg = message
        if not self._closed:
            try:
                self._root.update()
            except Exception:
                pass

    def process_events(self):
        """Pump the Tk event loop — call this between heavy import steps."""
        if not self._closed:
            try:
                self._root.update_idletasks()
                self._root.update()
            except Exception:
                pass

    def close(self, callback=None):
        """Fade out and destroy the splash window."""
        if self._closed:
            if callback:
                callback()
            return
        self._fade_out(callback=callback)
        while not self._closed:
            try:
                self._root.update()
            except Exception:
                break

    def mainloop_until_done(self, work_fn, done_fn):
        """
        Run ``work_fn()`` in a background thread while keeping splash alive,
        then call ``done_fn()`` on the main thread and close the splash.
        Called only when the splash IS the first Tk root (standalone mode).
        """
        result = [None]

        def _worker():
            try:
                result[0] = work_fn()
            finally:
                self._root.after(0, _finish)

        def _finish():
            self.close(callback=done_fn)

        threading.Thread(target=_worker, daemon=True).start()
        self._root.mainloop()
