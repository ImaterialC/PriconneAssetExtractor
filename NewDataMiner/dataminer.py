#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewDataMiner.dataminer - High-level API for targeted extraction, mining, database discovery, and update checking
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import MinerConfig
from .database import GameDatabase
from .db_updater import DatabaseUpdater, UpdateCheckResult
from .downloader import AssetDownloader
from .extractor import AssetExtractor
from .manifest_manager import ManifestManager
from .models import AssetCategory, DownloadScope, ManifestEntry
from .resource_cross_ref import DiscoveredResource, ResourceCrossReferencer


class DataMiner:
    """
    Main entry point for the New Universal Japanese Game Data Miner.
    Prioritizes targeted discovery, preview, database integration, update checking, and safe downloading.
    """
    def __init__(self, config: Optional[MinerConfig] = None, db_path: Optional[Path] = None):
        self.config = config or MinerConfig()
        self.manifest_manager = ManifestManager(self.config)
        self.downloader = AssetDownloader(self.config)
        self.extractor = AssetExtractor(self.config)
        self.database = GameDatabase(db_path=db_path)
        self.cross_ref = ResourceCrossReferencer(self.database, self.manifest_manager)
        self.updater = DatabaseUpdater(self.database.db_path)

    # -------------------------------------------------------------------------
    # Manifest Search & Downloads
    # -------------------------------------------------------------------------

    def search(
        self,
        query: str = "",
        category: Optional[AssetCategory | str] = None,
        manifest: Optional[str] = None,
        max_results: int = 500
    ) -> List[ManifestEntry]:
        """Search across all manifests offline without downloading any bundles."""
        return self.manifest_manager.search(query, category, manifest, max_results)

    def preview_scope(self, entries: List[ManifestEntry]) -> DownloadScope:
        """Returns download scope summary (count, total size, categories)."""
        return self.manifest_manager.get_scope(entries)

    def download_targets(
        self,
        entries: List[ManifestEntry],
        dest_dir: Optional[Path] = None,
        confirm: bool = True
    ) -> List[Path]:
        """
        Downloads the specified entries after confirming scope.
        Prevents blind massive downloads.
        """
        scope = self.preview_scope(entries)
        print(f"\n[Target Preview] Selected {scope.summary()}")

        if confirm and scope.total_bytes > 50 * 1024 * 1024:  # If > 50MB
            ans = input(f"Proceed with downloading {scope.human_size}? [y/N]: ").strip().lower()
            if ans != "y":
                print("[!] Download cancelled by user.")
                return []

        print(f"Downloading {len(entries)} file(s)...")

        def on_done(entry: ManifestEntry, p: Path, count: int, total: int):
            print(f"  [{count}/{total}] DL {entry.name} ({entry.human_size}) -> {p.name}")

        return self.downloader.download_batch(entries, dest_dir=dest_dir, on_item_complete=on_done)

    def extract_targets(
        self,
        downloaded_paths: List[Path],
        dest_dir: Optional[Path] = None
    ) -> List[Path]:
        """
        Extracts multi-asset contents (Unity3D, Movies, Audio).
        """
        extracted = []
        for p in downloaded_paths:
            ext = p.suffix.lower()
            if ext in (".unity3d", ".asset"):
                extracted.extend(self.extractor.extract_unity_bundle(p, dest_dir))
            elif ext == ".usm":
                mp4 = self.extractor.extract_movie(p, dest_dir)
                if mp4:
                    extracted.append(mp4)
            elif ext in (".awb", ".acb"):
                extracted.extend(self.extractor.extract_sound(p, dest_dir))
        return extracted

    # -------------------------------------------------------------------------
    # Database Discovery & Cross-Referencing APIs (P3)
    # -------------------------------------------------------------------------

    def discover_stories(self, query: str, limit: int = 25) -> List[DiscoveredResource]:
        """Cross-reference story titles/IDs to manifest script, icon, and voice assets."""
        return self.cross_ref.discover_story(query, limit=limit)

    def discover_units(self, query: str, limit: int = 25) -> List[DiscoveredResource]:
        """Cross-reference unit IDs/names to manifest battle, voice, spine, and icon assets."""
        return self.cross_ref.discover_unit(query, limit=limit)

    def discover_skills(self, query: str, limit: int = 25) -> List[DiscoveredResource]:
        """Cross-reference skills to manifest icon assets."""
        return self.cross_ref.discover_skills(query, limit=limit)

    def discover_dialogues(self, query: str, limit: int = 25) -> List[DiscoveredResource]:
        """Cross-reference homescreen/guildhouse dialogues to manifest voice assets."""
        return self.cross_ref.discover_dialogues(query, limit=limit)

    def list_database_tables(self) -> List[Dict[str, Any]]:
        """List all tables in master.db with row counts."""
        return self.database.list_tables()

    def export_table_sql(self, table_name: str, out_path: Path, max_rows: Optional[int] = None) -> int:
        """Export specified table schema and records to a .sql file."""
        return self.database.export_table_sql(table_name, out_path, max_rows=max_rows)

    # -------------------------------------------------------------------------
    # Database Update Checking & Retrieval (P4)
    # -------------------------------------------------------------------------

    def check_database_updates(self) -> UpdateCheckResult:
        """Lightweight check to see if a newer master.db is available."""
        return self.updater.check_for_updates()

    def apply_database_update(self, on_progress: Optional[Callable[[int, int], None]] = None) -> Path:
        """Safely download, validate, and install the updated master.db."""
        return self.updater.download_and_apply_update(on_progress=on_progress)
