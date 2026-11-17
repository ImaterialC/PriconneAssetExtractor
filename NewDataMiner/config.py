#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewDataMiner.config - Configuration & Network Endpoints
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PricoHost(str, Enum):
    JP = "prd-priconne-redive.akamaized.net"


class ManifestType(str, Enum):
    ASSET = "dl/Resources/{version}/Jpn/AssetBundles/Windows/manifest/{name}"
    MOVIE = "dl/Resources/{version}/Jpn/Movie/PC/High/manifest/{name}"
    SOUND = "dl/Resources/{version}/Jpn/Sound/manifest/{name}"


class AssetPoolType(str, Enum):
    ASSET = "dl/pool/AssetBundles"
    MOVIE = "dl/pool/Movie"
    SOUND = "dl/pool/Sound"


@dataclass
class MinerConfig:
    host: PricoHost = PricoHost.JP
    default_version: int = 10071600
    base_dir: Path = Path(__file__).resolve().parent.parent
    manifest_dir: Path = Path(__file__).resolve().parent.parent / "manifest"
    download_dir: Path = Path(__file__).resolve().parent.parent / "downloads"
    extract_dir: Path = Path(__file__).resolve().parent.parent / "extracted"
    usmtoolkit_path: Path = Path(__file__).resolve().parent.parent / "usmtoolkit" / "UsmToolkit.exe"
    vgmstream_path: Path = Path(__file__).resolve().parent.parent / "usmtoolkit" / "vgmstream" / "vgmstream-cli.exe"
    max_workers: int = 4
    timeout: int = 30
    chunk_size: int = 65536

    def ensure_dirs(self) -> None:
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.extract_dir.mkdir(parents=True, exist_ok=True)
