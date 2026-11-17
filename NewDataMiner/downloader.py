#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewDataMiner.downloader - Resumable, targeted concurrent asset downloader
"""
from __future__ import annotations

import concurrent.futures
from pathlib import Path
from typing import Callable, List, Optional
import urllib.request

from .config import MinerConfig
from .models import DownloadScope, ManifestEntry


class AssetDownloader:
    """
    Downloads assets from the Japanese game CDN with size checks and concurrent workers.
    """
    def __init__(self, config: Optional[MinerConfig] = None):
        self.config = config or MinerConfig()
        self.config.ensure_dirs()

    def download_entry(
        self,
        entry: ManifestEntry,
        dest_dir: Optional[Path] = None,
        progress_cb: Optional[Callable[[ManifestEntry, int, int], None]] = None
    ) -> Path:
        """
        Downloads a single entry into dest_dir, maintaining relative subpath structure.
        Skips if file already exists with identical size.
        """
        target_root = dest_dir or self.config.download_dir
        # Store using the entry's logical relative path (e.g. a/storydata_0000011.unity3d)
        local_path = target_root / Path(entry.path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        if local_path.exists() and local_path.stat().st_size == entry.size and entry.size > 0:
            if progress_cb:
                progress_cb(entry, entry.size, entry.size)
            return local_path

        req = urllib.request.Request(
            entry.url,
            headers={"User-Agent": "BestHTTP for Unity 1.12.2"}
        )

        with urllib.request.urlopen(req, timeout=self.config.timeout) as resp, open(local_path, "wb") as out_f:
            downloaded = 0
            while True:
                chunk = resp.read(self.config.chunk_size)
                if not chunk:
                    break
                out_f.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(entry, downloaded, entry.size)

        return local_path

    def download_batch(
        self,
        entries: List[ManifestEntry],
        dest_dir: Optional[Path] = None,
        on_item_complete: Optional[Callable[[ManifestEntry, Path, int, int], None]] = None
    ) -> List[Path]:
        """
        Downloads a batch of entries concurrently.
        """
        downloaded_paths: List[Path] = []
        total = len(entries)
        completed = 0

        def worker(entry: ManifestEntry) -> Tuple[ManifestEntry, Path]:
            p = self.download_entry(entry, dest_dir)
            return entry, p

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = [executor.submit(worker, e) for e in entries]
            for future in concurrent.futures.as_completed(futures):
                try:
                    entry, path = future.result()
                    completed += 1
                    downloaded_paths.append(path)
                    if on_item_complete:
                        on_item_complete(entry, path, completed, total)
                except Exception as ex:
                    print(f"[!] Download failed: {ex}")

        return downloaded_paths
