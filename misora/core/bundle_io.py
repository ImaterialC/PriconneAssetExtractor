#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora.core.bundle_io - In-memory loading, extraction, and repacking of Unity3D bundles.
Self-contained module utilizing UnityPy for zero-temporary-file in-place asset modification.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import UnityPy
from .story_ast import StoryDocument

# Priconne bundles omit standard Unity version headers, so fallback is essential
UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"


class BundleIOError(Exception):
    pass


def _script_attr_of(asset_data: Any) -> Tuple[str, Union[str, bytes]]:
    """Determine the text/script attribute name on a TextAsset."""
    for attr in ("m_Script", "script", "text"):
        val = getattr(asset_data, attr, None)
        if val is not None:
            return attr, val
    raise BundleIOError("TextAsset has no valid script or m_Script attribute.")


def extract_raw_story_bytes(text_asset_obj: Any) -> bytes:
    """Extract binary story script bytes from a TextAsset object."""
    d = text_asset_obj.read()
    _, val = _script_attr_of(d)
    if isinstance(val, str):
        return val.encode("utf-8", "surrogateescape")
    return bytes(val)


def load_bundle_story(path: Union[str, Path]) -> Tuple[StoryDocument, Any, Any, str]:
    """
    Load a .unity3d bundle file directly into memory.
    Returns:
        (StoryDocument, UnityPy.Environment, TextAsset_Object, asset_name)
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    try:
        env = UnityPy.load(str(path))
    except Exception as e:
        raise BundleIOError(f"Failed to open Unity3D bundle '{path.name}': {e}")

    target_obj = None
    target_name = ""

    for obj in env.objects:
        if obj.type.name == "TextAsset":
            try:
                data = obj.read()
                nm = getattr(data, "m_Name", "") or ""
                if nm.startswith("storydata") or "story" in nm.lower() or not target_obj:
                    target_obj = obj
                    target_name = nm
            except Exception:
                pass

    if not target_obj:
        raise BundleIOError(f"No TextAsset found inside bundle '{path.name}'.")

    raw_bytes = extract_raw_story_bytes(target_obj)
    doc = StoryDocument.from_binary(raw_bytes)
    return doc, env, target_obj, target_name


def save_bundle_story(
    env: Any,
    text_asset_obj: Any,
    doc: StoryDocument,
    out_path: Union[str, Path],
    backup_dir: Optional[Path] = None,
) -> int:
    """
    Repack the modified StoryDocument back into the Unity3D bundle file in-place.
    Performs verified round-trip check and returns written file size.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if backup_dir is not None and out_path.is_file():
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak_path = backup_dir / f"{out_path.stem}.bak_{ts}{out_path.suffix}"
        shutil.copy2(out_path, bak_path)

    new_data = doc.to_binary()
    d = text_asset_obj.read()
    attr, cur_val = _script_attr_of(d)

    modes = ["str", "bytes"] if isinstance(cur_val, str) else ["bytes", "str"]
    success = False
    last_err = ""

    for mode in modes:
        try:
            val_to_set = new_data.decode("utf-8", "surrogateescape") if mode == "str" else new_data
            setattr(d, attr, val_to_set)
            d.save()

            saved_bytes = env.file.save(packer="original")
            out_path.write_bytes(saved_bytes)

            # Verification: Reload output bundle and check byte exactness
            env_check = UnityPy.load(str(out_path))
            for o in env_check.objects:
                if o.type.name == "TextAsset":
                    check_bytes = extract_raw_story_bytes(o)
                    if check_bytes == new_data:
                        success = True
                        break
            if success:
                break
        except Exception as ex:
            last_err = str(ex)

    if not success:
        raise BundleIOError(f"Bundle write verification failed for '{out_path.name}': {last_err}")

    return out_path.stat().st_size
