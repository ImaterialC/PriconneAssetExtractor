#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora.core.xunity_sync - Bi-directional synchronization between Unity3D bundle corrections
and plain-text XUnity Auto Translator (XUAT) dictionary files.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .story_ast import norm_search, unescape_arg


@dataclass
class SyncMatch:
    file_path: Path
    line_number: int
    raw_key: str
    old_translation: str
    new_translation: str
    success: bool = False


class XUnitySyncManager:
    """
    Locates and updates corresponding translation lines inside XUAT text files
    to prevent future batch repacks from re-introducing outdated or mistaken strings.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = Path(project_root) if project_root else None

    def find_and_update(
        self,
        japanese_key: str,
        new_english_text: str,
        search_roots: List[Path],
        backup: bool = True,
        backup_dir: Optional[Path] = None,
    ) -> List[SyncMatch]:
        """
        Search for matching translation entries across search_roots and update them in-place.
        Accounts for XUnity whitespace insensitivity and player name placeholders.
        """
        norm_target = norm_search(japanese_key)
        matches: List[SyncMatch] = []

        for root in search_roots:
            root = Path(root)
            if not root.exists():
                continue

            txt_files = list(root.rglob("*.txt")) if root.is_dir() else [root]
            for tf in txt_files:
                if tf.name.endswith((".missing.txt", ".report.txt", "_SUMMARY.txt", "_warnings.txt")):
                    continue

                try:
                    lines = tf.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:
                    continue

                file_modified = False
                new_lines = []

                for idx, line in enumerate(lines, 1):
                    trimmed = line.strip()
                    if "=" in trimmed and not trimmed.startswith(("#", "//", "r:", "sr:")):
                        k_part, v_part = trimmed.split("=", 1)
                        if norm_search(k_part) == norm_target:
                            m = SyncMatch(
                                file_path=tf,
                                line_number=idx,
                                raw_key=k_part,
                                old_translation=v_part,
                                new_translation=new_english_text,
                                success=False
                            )
                            # Update line
                            line = f"{k_part}={new_english_text}"
                            file_modified = True
                            m.success = True
                            matches.append(m)
                    new_lines.append(line)

                if file_modified:
                    if backup:
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        if backup_dir is not None:
                            bd = Path(backup_dir)
                            bd.mkdir(parents=True, exist_ok=True)
                            bak_path = bd / f"{tf.stem}.bak_{ts}{tf.suffix}"
                        else:
                            bak_path = tf.with_suffix(f".bak_{ts}")
                        shutil.copy2(tf, bak_path)
                    tf.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        return matches
