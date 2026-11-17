#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewDataMiner.manifest_manager - Manifest parsing, indexing, and fast search
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set
import urllib.request

from .config import AssetPoolType, ManifestType, MinerConfig
from .models import AssetCategory, DownloadScope, ManifestEntry


class ManifestManager:
    """
    Manages local and remote manifests.
    Parses manifest files into memory for instant, targeted resource discovery.
    """
    def __init__(self, config: Optional[MinerConfig] = None):
        self.config = config or MinerConfig()
        self.version: int = self._load_version()
        self.entries: List[ManifestEntry] = []
        self._by_name: Dict[str, List[ManifestEntry]] = {}
        self._by_category: Dict[AssetCategory, List[ManifestEntry]] = {}
        self._by_manifest: Dict[str, List[ManifestEntry]] = {}
        self.is_loaded = False

    @property
    def total_entries(self) -> int:
        return len(self.entries)

    def _load_version(self) -> int:
        v_file = self.config.base_dir / "versions.json"
        if v_file.exists():
            try:
                data = json.loads(v_file.read_text(encoding="utf-8"))
                return int(data.get(self.config.host.value, self.config.default_version))
            except Exception:
                pass
        return self.config.default_version

    def _determine_category(self, manifest_name: str, path: str) -> AssetCategory:
        m = manifest_name.lower()
        p = path.lower()
        if "sound" in m or p.endswith((".acb", ".awb")):
            return AssetCategory.SOUND
        if "movie" in m or p.endswith(".usm"):
            return AssetCategory.MOVIE
        if "story" in m or "storydata" in p:
            return AssetCategory.STORY
        if "unit" in m or "unit_" in p:
            return AssetCategory.UNIT
        if "icon" in m or "icon_" in p:
            return AssetCategory.ICON
        if "banner" in m or "banner_" in p:
            return AssetCategory.BANNER
        if "spine" in m or "spine_" in p:
            return AssetCategory.SPINE
        if "bg" in m or p.startswith("bg_") or "/bg" in p:
            return AssetCategory.BG
        if "comic" in m:
            return AssetCategory.COMIC
        return AssetCategory.OTHER

    def load_manifests(self, force_reload: bool = False) -> int:
        """Loads and indexes all cached manifests."""
        if self.is_loaded and not force_reload:
            return len(self.entries)

        self.entries.clear()
        self._by_name.clear()
        self._by_category.clear()
        self._by_manifest.clear()

        manifest_files: List[Tuple[Path, AssetPoolType]] = []

        # 1. Check manifests directory
        if self.config.manifest_dir.exists():
            for p in self.config.manifest_dir.glob("*_assetmanifest"):
                manifest_files.append((p, AssetPoolType.ASSET))

        # 2. Check root manifests (sound, movie, masterdata)
        for cand, ptype in [
            (self.config.base_dir / "soundmanifest", AssetPoolType.SOUND),
            (self.config.base_dir / "movie2manifest", AssetPoolType.MOVIE),
            (self.config.manifest_dir / "soundmanifest", AssetPoolType.SOUND),
            (self.config.manifest_dir / "movie2manifest", AssetPoolType.MOVIE),
        ]:
            if cand.exists() and (cand, ptype) not in manifest_files:
                manifest_files.append((cand, ptype))

        for m_path, pool_type in manifest_files:
            m_name = m_path.name
            try:
                content = m_path.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or "," not in line:
                        continue
                    parts = line.split(",")
                    if len(parts) < 5:
                        continue
                    item_path = parts[0].strip()
                    item_hash = parts[2].strip() if len(parts) > 2 else ""
                    try:
                        item_size = int(parts[4].strip())
                    except ValueError:
                        item_size = 0

                    item_name = Path(item_path).name
                    cat = self._determine_category(m_name, item_path)
                    entry = ManifestEntry(
                        path=item_path,
                        name=item_name,
                        hash=item_hash,
                        size=item_size,
                        manifest_name=m_name,
                        category=cat,
                        pool_type=pool_type
                    )
                    self.entries.append(entry)
                    self._by_name.setdefault(item_name.lower(), []).append(entry)
                    self._by_category.setdefault(cat, []).append(entry)
                    self._by_manifest.setdefault(m_name.lower(), []).append(entry)
            except Exception as e:
                print(f"[!] Error reading manifest {m_name}: {e}")

        self.is_loaded = True
        return len(self.entries)

    def search(
        self,
        query: str = "",
        category: Optional[AssetCategory | str] = None,
        manifest: Optional[str] = None,
        max_results: int = 500
    ) -> List[ManifestEntry]:
        """
        Fast targeted search across all manifests.
        Supports query string (case-insensitive substring or regex).
        """
        if not self.is_loaded:
            self.load_manifests()

        results: List[ManifestEntry] = []
        pattern = None
        if query:
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except Exception:
                pattern = None

        q_lower = query.lower() if query else ""
        target_cat = AssetCategory(category) if isinstance(category, str) and category in [c.value for c in AssetCategory] else category
        target_m = manifest.lower() if manifest else ""

        # Pool selection optimization
        if target_cat and target_cat in self._by_category:
            candidate_pool = self._by_category[target_cat]
        elif target_m and target_m in self._by_manifest:
            candidate_pool = self._by_manifest[target_m]
        else:
            candidate_pool = self.entries

        for e in candidate_pool:
            if target_cat and e.category != target_cat:
                continue
            if target_m and target_m not in e.manifest_name.lower():
                continue
            if query:
                if pattern:
                    if not (pattern.search(e.name) or pattern.search(e.path)):
                        continue
                else:
                    if q_lower not in e.name.lower() and q_lower not in e.path.lower():
                        continue

            results.append(e)
            if len(results) >= max_results:
                break

        return results

    def get_scope(self, entries: List[ManifestEntry]) -> DownloadScope:
        return DownloadScope(entries)
