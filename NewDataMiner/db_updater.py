#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewDataMiner.db_updater - Database update checking, validation, and safe atomic installation
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import urllib.request
import urllib.parse


DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_ROBO_NINON_URL = "https://roboninon.win/db/download"


@dataclass
class LocalDatabaseInfo:
    path: Path
    exists: bool = False
    size_bytes: int = 0
    sha256: str = ""
    version: Optional[str] = None
    last_modified: Optional[str] = None

    @property
    def human_size(self) -> str:
        s = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024.0:
                return f"{s:.1f} {unit}"
            s /= 1024.0
        return f"{s:.1f} TB"


@dataclass
class RemoteDatabaseInfo:
    source_name: str
    url: str
    version: Optional[str] = None
    size_bytes: Optional[int] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    filename: Optional[str] = None

    @property
    def human_size(self) -> str:
        if not self.size_bytes:
            return "Unknown"
        s = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024.0:
                return f"{s:.1f} {unit}"
            s /= 1024.0
        return f"{s:.1f} TB"


@dataclass
class UpdateCheckResult:
    update_available: bool
    local_info: LocalDatabaseInfo
    remote_info: RemoteDatabaseInfo
    reason: str


class DatabaseUpdater:
    """
    Manages lightweight remote update checks, safe atomic downloads,
    and database integrity validation for master.db.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        remote_url: str = DEFAULT_ROBO_NINON_URL,
        source_name: str = "Robo Ninon (Deobfuscated)"
    ):
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path(__file__).resolve().parent.parent / "master.db"

        self.meta_path = self.db_path.parent / f"{self.db_path.name}.meta.json"
        self.remote_url = remote_url
        self.source_name = source_name

    # -------------------------------------------------------------------------
    # Local Inspection
    # -------------------------------------------------------------------------

    def get_local_info(self, compute_hash: bool = False) -> LocalDatabaseInfo:
        """Inspect the local master.db and its metadata sidecar."""
        if not self.db_path.is_file():
            return LocalDatabaseInfo(path=self.db_path, exists=False)

        stat = self.db_path.stat()
        size = stat.st_size
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(stat.st_mtime))

        meta = self._load_meta()
        version = meta.get("version")

        # Fallback: extract version from meta or filename if available
        if not version:
            # Check if version was saved or check table count
            version = meta.get("last_version")

        sha256 = ""
        if compute_hash:
            h = hashlib.sha256()
            with open(self.db_path, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    h.update(chunk)
            sha256 = h.hexdigest()
        else:
            sha256 = meta.get("sha256", "")

        return LocalDatabaseInfo(
            path=self.db_path,
            exists=True,
            size_bytes=size,
            sha256=sha256,
            version=version,
            last_modified=mtime_str
        )

    def _load_meta(self) -> Dict[str, Any]:
        if self.meta_path.is_file():
            try:
                with open(self.meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_meta(self, data: Dict[str, Any]) -> None:
        try:
            with open(self.meta_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Lightweight Remote Check
    # -------------------------------------------------------------------------

    def check_for_updates(self, timeout_sec: int = 10) -> UpdateCheckResult:
        """
        Perform a lightweight remote update check without downloading the database.
        Uses HTTP HEAD request to read Content-Disposition, Content-Length, and ETag.
        """
        local_info = self.get_local_info()

        req = urllib.request.Request(
            self.remote_url,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            method="HEAD"
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                headers = {k.lower(): v for k, v in resp.headers.items()}
                content_length = int(headers.get("content-length", 0)) if "content-length" in headers else None
                etag = headers.get("etag")
                last_modified = headers.get("last-modified")

                content_disp = headers.get("content-disposition", "")
                filename = ""
                version = None

                # Extract filename and version from Content-Disposition header
                # e.g., attachment; filename="PriconneMasterDatabase_10071600.db"
                if "filename=" in content_disp:
                    m_fn = re.search(r'filename=["\']?([^"\';]+)["\']?', content_disp)
                    if m_fn:
                        filename = m_fn.group(1)
                        # Extract 8-digit database version e.g. 10071600
                        m_ver = re.search(r'(\d{8})', filename)
                        if m_ver:
                            version = m_ver.group(1)

                remote_info = RemoteDatabaseInfo(
                    source_name=self.source_name,
                    url=self.remote_url,
                    version=version,
                    size_bytes=content_length,
                    etag=etag,
                    last_modified=last_modified,
                    filename=filename
                )

        except Exception as e:
            # Remote check failed
            return UpdateCheckResult(
                update_available=False,
                local_info=local_info,
                remote_info=RemoteDatabaseInfo(source_name=self.source_name, url=self.remote_url),
                reason=f"Failed to check remote source: {e}"
            )

        # Evaluate update availability
        if not local_info.exists:
            return UpdateCheckResult(
                update_available=True,
                local_info=local_info,
                remote_info=remote_info,
                reason="Local master.db is missing. Initial download required."
            )

        # Version comparison
        if remote_info.version and local_info.version:
            if remote_info.version > local_info.version:
                return UpdateCheckResult(
                    update_available=True,
                    local_info=local_info,
                    remote_info=remote_info,
                    reason=f"Newer database version found: {remote_info.version} (local: {local_info.version})"
                )
            elif remote_info.version == local_info.version:
                return UpdateCheckResult(
                    update_available=False,
                    local_info=local_info,
                    remote_info=remote_info,
                    reason=f"Current database is up to date (version {local_info.version})."
                )

        # File size comparison fallback
        if remote_info.size_bytes and remote_info.size_bytes > 0:
            if remote_info.size_bytes != local_info.size_bytes:
                return UpdateCheckResult(
                    update_available=True,
                    local_info=local_info,
                    remote_info=remote_info,
                    reason=f"Database file size changed: remote {remote_info.human_size} vs local {local_info.human_size}."
                )

        return UpdateCheckResult(
            update_available=False,
            local_info=local_info,
            remote_info=remote_info,
            reason="Database matches remote size and headers. Up to date."
        )

    # -------------------------------------------------------------------------
    # Validation & Safe Atomic Download
    # -------------------------------------------------------------------------

    def validate_database_file(self, file_path: Path) -> Tuple[bool, str]:
        """
        Verify SQLite file format, integrity check, and minimum required schema.
        """
        if not file_path.is_file():
            return False, "File does not exist."

        if file_path.stat().st_size < 1024 * 1024:  # At least 1MB
            return False, f"File size too small ({file_path.stat().st_size} bytes)."

        try:
            conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # 1. Quick SQLite integrity check
            cursor.execute("PRAGMA quick_check")
            check_res = cursor.fetchone()
            if not check_res or check_res[0].lower() != "ok":
                conn.close()
                return False, f"SQLite integrity check failed: {check_res}"

            # 2. Check table count
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            table_count = cursor.fetchone()[0]
            if table_count < 50:
                conn.close()
                return False, f"Insufficient tables in database ({table_count} tables, expected > 50)."

            # 3. Check for essential tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('unit_data', 'story_detail')")
            found_tables = {row[0] for row in cursor.fetchall()}
            if "unit_data" not in found_tables:
                conn.close()
                return False, "Missing critical table 'unit_data'."

            conn.close()
            return True, f"Integrity check passed ({table_count} tables verified)."

        except Exception as e:
            return False, f"SQLite validation exception: {e}"

    def download_and_apply_update(
        self,
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Path:
        """
        Safely download the updated database to a temporary staging file,
        validate its SQLite integrity, backup the existing database, and
        atomically activate the new database.
        """
        temp_dest = self.db_path.parent / f"{self.db_path.name}.downloading"
        backup_path = self.db_path.parent / f"{self.db_path.name}.bak"

        # Check remote headers first to know expected size and version
        req = urllib.request.Request(
            self.remote_url,
            headers={"User-Agent": DEFAULT_USER_AGENT}
        )

        remote_ver = None
        hasher = hashlib.sha256()

        print(f"Connecting to {self.source_name} ({self.remote_url})...")
        with urllib.request.urlopen(req, timeout=30) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            total_size = int(headers.get("content-length", 0))

            content_disp = headers.get("content-disposition", "")
            if m_ver := re.search(r'(\d{8})', content_disp):
                remote_ver = m_ver.group(1)

            downloaded = 0
            with open(temp_dest, "wb") as f:
                while chunk := resp.read(64 * 1024):
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    if on_progress:
                        on_progress(downloaded, total_size)

        # 1. Validate downloaded staging file
        valid, msg = self.validate_database_file(temp_dest)
        if not valid:
            if temp_dest.is_file():
                temp_dest.unlink()
            raise ValueError(f"Downloaded database failed validation: {msg}")

        # 2. Backup existing database if present
        if self.db_path.is_file():
            shutil.copy2(self.db_path, backup_path)
            print(f"[Backup] Saved current database to: {backup_path.name}")

        # 3. Atomic replacement
        # On Windows, replace safely
        if self.db_path.is_file():
            self.db_path.unlink()
        temp_dest.rename(self.db_path)

        # 4. Save metadata
        sha256_hash = hasher.hexdigest()
        meta_data = {
            "source_name": self.source_name,
            "source_url": self.remote_url,
            "version": remote_ver,
            "size_bytes": self.db_path.stat().st_size,
            "sha256": sha256_hash,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        }
        self._save_meta(meta_data)
        print(f"[OK] Successfully installed master.db (version: {remote_ver or 'N/A'}, size: {meta_data['size_bytes']:,} bytes)")

        return self.db_path
