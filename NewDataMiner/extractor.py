#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewDataMiner.extractor - Multi-asset extractor (Textures, Text, Movies, Sounds, Spine)
"""
from __future__ import annotations

import json
import os
import subprocess
import warnings
from pathlib import Path
from typing import List, Optional

try:
    import UnityPy
    import UnityPy.config
    UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"
    warnings.filterwarnings("ignore")
except ImportError:
    UnityPy = None

from .config import MinerConfig


class AssetExtractor:
    """
    Universal extractor for Princess Connect! Re:Dive assets.
    Handles Unity3D bundles (Textures, Text, Audio, Subtitles), USM movies, and AWB/ACB audio.
    """
    def __init__(self, config: Optional[MinerConfig] = None):
        self.config = config or MinerConfig()
        self.config.ensure_dirs()

    def extract_unity_bundle(
        self,
        bundle_path: Path,
        dest_dir: Optional[Path] = None,
        extract_images: bool = True,
        extract_texts: bool = True,
        deserialize_story_json: bool = False
    ) -> List[Path]:
        """
        Extracts textures, sprites, and text assets from a .unity3d bundle.
        """
        if not UnityPy:
            raise RuntimeError("UnityPy is required to extract Unity3D asset bundles.")

        bundle_path = Path(bundle_path)
        out_root = dest_dir or (self.config.extract_dir / bundle_path.stem)
        out_root.mkdir(parents=True, exist_ok=True)

        extracted_files: List[Path] = []
        env = UnityPy.load(bundle_path.as_posix())

        for obj in env.objects:
            # 1. Textures & Sprites
            if extract_images and obj.type.name in ("Texture2D", "Sprite"):
                try:
                    data = obj.read()
                    name = getattr(data, "m_Name", None) or f"{bundle_path.stem}_{obj.path_id}"
                    out_path = out_root / f"{name}.png"
                    if not out_path.exists():
                        image = data.image
                        image.save(out_path, lossless=True)
                        extracted_files.append(out_path)
                except Exception as ex:
                    print(f"[!] Error extracting image from {bundle_path.name}: {ex}")

            # 2. Text Assets (scripts, configs, bytes)
            elif extract_texts and obj.type.name == "TextAsset":
                try:
                    data = obj.read()
                    name = getattr(data, "m_Name", None) or f"{bundle_path.stem}_{obj.path_id}"
                    raw_bytes = bytes(data.m_Script.encode("utf-8", "surrogateescape"))

                    if deserialize_story_json and ("storydata" in bundle_path.name.lower() or "story" in name.lower()):
                        # Optional: JSON deserialization
                        try:
                            from src.story_deserializer import deserialize_story
                            out_path = out_root / f"{name}.json"
                            if not out_path.exists():
                                out_path.write_text(json.dumps(deserialize_story(raw_bytes), indent=2, ensure_ascii=False), encoding="utf-8")
                                extracted_files.append(out_path)
                        except Exception:
                            out_path = out_root / f"{name}.txt"
                            if not out_path.exists():
                                out_path.write_bytes(raw_bytes)
                                extracted_files.append(out_path)
                    else:
                        out_path = out_root / f"{name}.txt"
                        if not out_path.exists():
                            out_path.write_bytes(raw_bytes)
                            extracted_files.append(out_path)
                except Exception as ex:
                    print(f"[!] Error extracting text from {bundle_path.name}: {ex}")

        return extracted_files

    def extract_movie(self, usm_path: Path, dest_dir: Optional[Path] = None) -> Optional[Path]:
        """
        Converts a .usm video file into .mp4 using UsmToolkit.
        """
        usm_path = Path(usm_path)
        out_root = dest_dir or self.config.extract_dir / "movies"
        out_root.mkdir(parents=True, exist_ok=True)
        out_mp4 = out_root / f"{usm_path.stem}.mp4"

        if out_mp4.exists():
            return out_mp4

        toolkit = self.config.usmtoolkit_path
        if not toolkit.exists():
            print(f"[!] UsmToolkit not found at: {toolkit}")
            return None

        cmd = [
            str(toolkit.resolve()),
            "convert",
            "-c", str(usm_path.resolve()),
            "-o", str(out_root.resolve())
        ]
        try:
            subprocess.run(cmd, cwd=str(toolkit.parent), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if out_mp4.exists():
                return out_mp4
        except Exception as ex:
            print(f"[!] Movie extraction failed: {ex}")
        return None

    def extract_sound(self, awb_path: Path, dest_dir: Optional[Path] = None) -> List[Path]:
        """
        Converts a .awb sound file into .wav tracks using vgmstream.
        """
        awb_path = Path(awb_path)
        out_root = dest_dir or self.config.extract_dir / "sound" / awb_path.stem
        out_root.mkdir(parents=True, exist_ok=True)

        vgm = self.config.vgmstream_path
        if not vgm.exists():
            print(f"[!] vgmstream not found at: {vgm}")
            return []

        cmd = [
            str(vgm.resolve()),
            "-S", "0",
            str(awb_path.resolve()),
            "-o", f"{out_root.resolve()}/?n_?s.wav"
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return list(out_root.glob("*.wav"))
        except Exception as ex:
            print(f"[!] Sound extraction failed: {ex}")
            return []
