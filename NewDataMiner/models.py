#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewDataMiner.models - Data structures for manifests, assets, and download scopes
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from .config import AssetPoolType, MinerConfig


class AssetCategory(str, enum.Enum):
    STORY = "story"
    UNIT = "unit"
    ICON = "icon"
    BANNER = "banner"
    BG = "bg"
    SPINE = "spine"
    SOUND = "sound"
    MOVIE = "movie"
    COMIC = "comic"
    OTHER = "other"


@dataclass
class ManifestEntry:
    path: str               # e.g., "a/storydata_0000011.unity3d"
    name: str               # e.g., "storydata_0000011.unity3d"
    hash: str               # e.g., "5e15c9685c0e9bbc1b97759d352d6488"
    size: int               # in bytes
    manifest_name: str      # e.g., "storydata2_assetmanifest"
    category: AssetCategory = AssetCategory.OTHER
    pool_type: AssetPoolType = AssetPoolType.ASSET

    @property
    def url(self) -> str:
        prefix = self.hash[:2]
        return f"https://{MinerConfig.host.value}/{self.pool_type.value}/{prefix}/{self.hash}"

    @property
    def human_size(self) -> str:
        s = float(self.size)
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024.0:
                return f"{s:.1f} {unit}"
            s /= 1024.0
        return f"{s:.1f} TB"


@dataclass
class DownloadScope:
    entries: List[ManifestEntry] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.entries)

    @property
    def total_bytes(self) -> int:
        return sum(e.size for e in self.entries)

    @property
    def human_size(self) -> str:
        s = float(self.total_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024.0:
                return f"{s:.1f} {unit}"
            s /= 1024.0
        return f"{s:.1f} TB"

    def summary(self) -> str:
        by_cat = {}
        for e in self.entries:
            by_cat[e.category.value] = by_cat.get(e.category.value, 0) + 1
        cat_str = ", ".join(f"{k}: {v}" for k, v in sorted(by_cat.items()))
        return f"{self.total_count:,} file(s) ({self.human_size}) [{cat_str}]"
