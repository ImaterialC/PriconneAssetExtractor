#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asset_registry.py - BepInEx Workspace Scanning, Identity Mapping & Duplicate Detection
Part of the Princess Connect! Re:Dive Asset Toolchain (P1 Architecture)

Handles:
- BepInEx project root resolution and strictly bounded sub-workspace scanning.
- Multi-representation asset identification (relative path, flattened redirected name, basename).
- Pre-conversion duplicate detection against RedirectedResources.
- Disambiguation of identical basenames across disparate directories.
- Redesigned naming strategies with collision prevention and preview.
"""
from __future__ import annotations

import enum
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class MatchLevel(str, enum.Enum):
    EXACT_FLATTENED = "exact_flattened"      # e.g., storydata_0000011.unity3d == storydata_0000011.unity3d
    EXACT_RELATIVE = "exact_relative"        # e.g., storydata/0000011.unity3d == storydata/0000011.unity3d
    NORMALIZED_ID = "normalized_id"          # e.g., category 'storydata' and id '0000011' match
    BASENAME_UNIQUE = "basename_unique"      # Basename matches exactly one file in RedirectedResources
    BASENAME_AMBIGUOUS = "basename_ambiguous"  # Basename matches multiple files in RedirectedResources!
    NONE = "none"


class AssetStatus(str, enum.Enum):
    NEW = "NEW"                                      # Ready for conversion
    ALREADY_IMPLEMENTED = "ALREADY_IMPLEMENTED"      # In RedirectedResources; skip by default
    REPROCESS_REQUESTED = "REPROCESS_REQUESTED"      # Implemented, but user explicitly asked to re-convert
    COLLISION_WARNING = "COLLISION_WARNING"          # Multiple assets map to the same name or ambiguous match
    UNRESOLVED = "UNRESOLVED"                        # Cannot determine a safe name or target


class NamingStrategy(str, enum.Enum):
    AUTO_REDIRECT = "auto_redirect"          # Standard flattened: <folder>_<basename> (or storydata_<basename>)
    PRESERVE_ORIGINAL = "preserve_original"  # Keep original basename as-is
    MATCH_EXISTING = "match_existing"        # Use existing filename in RedirectedResources if matched; else auto
    CUSTOM_PATTERN = "custom_pattern"        # Use configurable format string


@dataclass
class BepInExWorkspace:
    """Manages BepInEx root and strictly bounded sub-workspaces."""
    bepinex_root: Optional[Path] = None
    xuat_text_dir: Optional[Path] = None
    redirected_resources_dir: Optional[Path] = None

    @classmethod
    def resolve(cls, root_or_subpath: Optional[str | Path] = None) -> BepInExWorkspace:
        r"""
        Resolves BepInEx workspace from either:
        - BepInEx root (e.g. C:\[Gacha]\PriconneRe-TL\src\BepInEx)
        - Text subfolder (e.g. ...\Translation\en\Text)
        - RedirectedResources subfolder (e.g. ...\Translation\en\RedirectedResources)
        """
        if not root_or_subpath:
            return cls()

        p = Path(root_or_subpath).resolve()
        norm_parts = [part.lower() for part in p.parts]

        # Case 1: Pointing directly to Translation/en/Text or a subfolder within it
        if "translation" in norm_parts and "text" in norm_parts:
            # Find index of 'text' after 'translation'
            t_idx = norm_parts.index("translation")
            try:
                text_idx = norm_parts.index("text", t_idx)
                text_dir = Path(*p.parts[:text_idx + 1])
                bep_root = Path(*p.parts[:t_idx])
                redir_dir = bep_root / "Translation" / "en" / "RedirectedResources"
                return cls(bepinex_root=bep_root, xuat_text_dir=text_dir, redirected_resources_dir=redir_dir)
            except ValueError:
                pass

        # Case 2: Pointing directly to Translation/en/RedirectedResources
        if "translation" in norm_parts and "redirectedresources" in norm_parts:
            t_idx = norm_parts.index("translation")
            r_idx = norm_parts.index("redirectedresources", t_idx)
            redir_dir = Path(*p.parts[:r_idx + 1])
            bep_root = Path(*p.parts[:t_idx])
            text_dir = bep_root / "Translation" / "en" / "Text"
            return cls(bepinex_root=bep_root, xuat_text_dir=text_dir, redirected_resources_dir=redir_dir)

        # Case 3: Pointing to BepInEx root
        if (p / "Translation").exists() or (p / "plugins").exists() or (p / "config").exists():
            return cls(
                bepinex_root=p,
                xuat_text_dir=p / "Translation" / "en" / "Text",
                redirected_resources_dir=p / "Translation" / "en" / "RedirectedResources"
            )

        # Fallback: Assume given directory is the BepInEx root or base directory
        return cls(
            bepinex_root=p,
            xuat_text_dir=p / "Translation" / "en" / "Text",
            redirected_resources_dir=p / "Translation" / "en" / "RedirectedResources"
        )

    def is_valid_bepinex(self) -> bool:
        return bool(self.bepinex_root and self.bepinex_root.exists())

    def redirected_exists(self) -> bool:
        return bool(self.redirected_resources_dir and self.redirected_resources_dir.exists())

    def text_exists(self) -> bool:
        return bool(self.xuat_text_dir and self.xuat_text_dir.exists())


@dataclass
class AssetIdentity:
    """
    Normalized multi-representation asset identity.
    Represents an asset regardless of how it was presented (raw path, flattened name, or basename).
    """
    file_path: Path
    root_path: Path
    relative_path: Path
    basename: str
    stem: str
    ext: str
    folder: str
    category: str
    asset_id: str
    flattened_name: str

    @classmethod
    def create(cls, file_path: Path, root_path: Optional[Path] = None) -> AssetIdentity:
        orig_p = Path(file_path)
        file_path = orig_p.resolve()
        if root_path:
            root = Path(root_path).resolve()
            try:
                rel = file_path.relative_to(root)
            except ValueError:
                rel = Path(file_path.name)
            folder = rel.parent.name if rel.parent != Path(".") and rel.parent.name else ""
        else:
            if len(orig_p.parts) > 1:
                folder = orig_p.parts[-2]
                rel = Path(folder) / orig_p.name
                root = file_path.parent.parent
            else:
                folder = ""
                rel = Path(file_path.name)
                root = file_path.parent

        basename = file_path.name
        stem = file_path.stem
        ext = file_path.suffix.lower()

        # Normalize category and asset_id
        # Handles cases like:
        # 1. stem = "storydata_0000011" -> category="storydata", asset_id="0000011"
        # 2. folder = "storydata", stem = "0000011" -> category="storydata", asset_id="0000011"
        # 3. stem = "5e15c968-0000011" -> category="storydata", asset_id="0000011"
        category = ""
        asset_id = stem

        if "_" in stem:
            parts = stem.split("_", 1)
            # e.g. storydata_0000011, unit_100111, icon_unit_100111
            if len(parts) == 2 and parts[0] in ("storydata", "story", "unit", "icon", "movie", "bg", "sound"):
                category = parts[0]
                asset_id = parts[1]
            elif stem.startswith("storydata_"):
                category = "storydata"
                asset_id = stem[len("storydata_"):]

        if not category and folder:
            category = folder.lower()

        if not category:
            # Default to storydata if it looks like a story script (numeric or quest prefix)
            if re.match(r"^\d{7}$", stem) or re.match(r"^[A-Za-z]\d+-\d+", stem):
                category = "storydata"
            else:
                category = "storydata"

        # Build flattened redirected filename
        if stem.startswith(f"{category}_"):
            flattened_name = f"{stem}{ext}"
        elif category:
            flattened_name = f"{category}_{stem}{ext}"
        else:
            flattened_name = f"{stem}{ext}"

        return cls(
            file_path=file_path,
            root_path=root,
            relative_path=rel,
            basename=basename,
            stem=stem,
            ext=ext,
            folder=folder,
            category=category,
            asset_id=asset_id,
            flattened_name=flattened_name
        )

    @classmethod
    def from_path(cls, file_path: str | Path, root_path: Optional[str | Path] = None) -> AssetIdentity:
        """Alias for create() to support intuitive instantiation from path."""
        return cls.create(Path(file_path), Path(root_path) if root_path else None)


class RedirectIndex:
    """
    Indexes an existing BepInEx Translation\\en\\RedirectedResources directory.
    Strictly bounded: only scans the redirected resources folder, never parents or siblings.
    Supports fast O(1) multi-representation lookups and collision detection.
    """
    def __init__(self, redirected_dir: Optional[Path] = None):
        self.redirected_dir = Path(redirected_dir).resolve() if redirected_dir else None
        self.by_filename: Dict[str, Path] = {}                   # "storydata_0000011.unity3d" -> Path
        self.by_basename: Dict[str, List[Path]] = {}             # "0000011.unity3d" -> [Path, ...]
        self.by_category_id: Dict[Tuple[str, str], List[Path]] = {} # ("storydata", "0000011") -> [Path, ...]
        self.total_count = 0
        if self.redirected_dir and self.redirected_dir.exists():
            self._scan()

    def _scan(self) -> None:
        """Performs non-recursive scan of RedirectedResources (all bundles reside here)."""
        if not self.redirected_dir or not self.redirected_dir.is_dir():
            return

        # STRICT BOUNDARY: only scan within self.redirected_dir
        # Do not scan subdirectories or parent directories
        for entry in os.scandir(self.redirected_dir):
            if entry.is_file():
                ext = os.path.splitext(entry.name)[1].lower()
                if ext in (".unity3d", ".asset"):
                    p = Path(entry.path)
                    fn_lower = entry.name.lower()
                    self.by_filename[fn_lower] = p

                    base_lower = p.name.lower()
                    self.by_basename.setdefault(base_lower, []).append(p)

                    # Extract category and id from redirected filename (e.g. storydata_0000011.unity3d)
                    stem = p.stem.lower()
                    if "_" in stem:
                        cat, _, aid = stem.partition("_")
                        self.by_category_id.setdefault((cat, aid), []).append(p)
                    self.total_count += 1

    def find_match(self, asset: AssetIdentity) -> Tuple[MatchLevel, Optional[Path], List[Path]]:
        """
        Looks up an asset identity against the index using multi-representation matching.
        Returns (MatchLevel, best_match_path, all_candidate_matches).
        """
        # 1. Exact match on flattened redirected filename
        flat_lower = asset.flattened_name.lower()
        if flat_lower in self.by_filename:
            match = self.by_filename[flat_lower]
            return MatchLevel.EXACT_FLATTENED, match, [match]

        # 2. Match on normalized (category, asset_id)
        cat_id_key = (asset.category.lower(), asset.asset_id.lower())
        cat_matches = self.by_category_id.get(cat_id_key, [])
        if len(cat_matches) == 1:
            return MatchLevel.NORMALIZED_ID, cat_matches[0], cat_matches
        elif len(cat_matches) > 1:
            return MatchLevel.BASENAME_AMBIGUOUS, None, cat_matches

        # 3. Match on exact original basename (e.g. 0000011.unity3d)
        base_lower = asset.basename.lower()
        if base_lower in self.by_filename:
            match = self.by_filename[base_lower]
            return MatchLevel.EXACT_RELATIVE, match, [match]

        # 4. Check if any file ends with _<basename> (e.g. storydata_0000011.unity3d vs 0000011.unity3d)
        suffix_matches = [p for name, p in self.by_filename.items() if name.endswith(f"_{base_lower}")]
        if len(suffix_matches) == 1:
            return MatchLevel.BASENAME_UNIQUE, suffix_matches[0], suffix_matches
        elif len(suffix_matches) > 1:
            return MatchLevel.BASENAME_AMBIGUOUS, None, suffix_matches

        return MatchLevel.NONE, None, []

    def contains(self, asset: AssetIdentity) -> bool:
        """Convenience method returning True if the asset is already in RedirectedResources."""
        level, best_match, _ = self.find_match(asset)
        return level in (MatchLevel.EXACT_FLATTENED, MatchLevel.NORMALIZED_ID, MatchLevel.EXACT_RELATIVE, MatchLevel.BASENAME_UNIQUE)


@dataclass
class AssetCandidate:
    """Represents a file evaluated before conversion, with full preview information."""
    identity: AssetIdentity
    match_level: MatchLevel
    existing_redirect: Optional[Path]
    proposed_filename: str
    status: AssetStatus
    action: str  # "CONVERT" or "SKIP"
    reason: str
    warnings: List[str] = field(default_factory=list)


class NamingManager:
    """Handles proposed output naming strategies, preview generation, and collision detection."""

    @staticmethod
    def compute_name(
        asset: AssetIdentity,
        strategy: NamingStrategy = NamingStrategy.AUTO_REDIRECT,
        matched_redirect: Optional[Path] = None,
        custom_pattern: str = "{default}"
    ) -> str:
        """
        Computes the proposed output filename according to the selected strategy.
        """
        if strategy == NamingStrategy.MATCH_EXISTING and matched_redirect:
            return matched_redirect.name

        if strategy == NamingStrategy.PRESERVE_ORIGINAL:
            return asset.basename

        if strategy == NamingStrategy.AUTO_REDIRECT:
            return asset.flattened_name

        if strategy == NamingStrategy.CUSTOM_PATTERN and custom_pattern:
            sample_vars = {
                "name": asset.stem,
                "ext": asset.ext.lstrip("."),
                "folder": asset.folder or asset.category,
                "path": "_".join(asset.relative_path.parent.parts) if asset.relative_path.parent != Path(".") else "",
                "id": asset.asset_id,
                "category": asset.category,
                "default": asset.flattened_name.rsplit(".", 1)[0]
            }
            try:
                formatted = custom_pattern.format(**sample_vars)
                clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", formatted).strip(" .")
                if not clean.endswith(asset.ext):
                    clean = f"{clean}{asset.ext}"
                return clean
            except Exception:
                return asset.flattened_name

        return asset.flattened_name


class PreConversionScanner:
    """
    Evaluates a collection of input assets against RedirectedResources before conversion.
    Detects duplicates, collisions, and ambiguous mappings, and produces a complete review.
    """
    def __init__(
        self,
        workspace: BepInExWorkspace,
        strategy: NamingStrategy = NamingStrategy.AUTO_REDIRECT,
        custom_pattern: str = "{default}",
        reprocess_keys: Optional[Set[str]] = None
    ):
        self.workspace = workspace
        self.strategy = strategy
        self.custom_pattern = custom_pattern
        self.reprocess_keys = reprocess_keys or set()
        self.redirect_index = RedirectIndex(workspace.redirected_resources_dir)

    def scan_candidates(
        self,
        input_files: List[Path],
        input_root: Optional[Path] = None
    ) -> List[AssetCandidate]:
        candidates: List[AssetCandidate] = []
        proposed_counts: Dict[str, List[AssetIdentity]] = {}

        # 1. Identify and match each candidate
        for f in input_files:
            ident = AssetIdentity.create(f, input_root)
            level, matched_p, all_cands = self.redirect_index.find_match(ident)
            prop_name = NamingManager.compute_name(ident, self.strategy, matched_p, self.custom_pattern)
            proposed_counts.setdefault(prop_name.lower(), []).append(ident)

            warns = []
            status = AssetStatus.NEW
            action = "CONVERT"
            reason = "New asset, not yet present in RedirectedResources."

            if level == MatchLevel.BASENAME_AMBIGUOUS:
                status = AssetStatus.COLLISION_WARNING
                action = "SKIP"
                reason = f"Ambiguous basename '{ident.basename}' matches multiple existing files: {[p.name for p in all_cands]}"
                warns.append(reason)
            elif matched_p:
                ident_key = ident.stem.lower()
                rel_key = str(ident.relative_path).lower()
                if ident_key in self.reprocess_keys or rel_key in self.reprocess_keys:
                    status = AssetStatus.REPROCESS_REQUESTED
                    action = "CONVERT"
                    reason = f"Already in RedirectedResources ({matched_p.name}), but reprocess was explicitly requested."
                else:
                    status = AssetStatus.ALREADY_IMPLEMENTED
                    action = "SKIP"
                    reason = f"Already implemented in RedirectedResources as '{matched_p.name}' ({level.value})."

            candidates.append(AssetCandidate(
                identity=ident,
                match_level=level,
                existing_redirect=matched_p,
                proposed_filename=prop_name,
                status=status,
                action=action,
                reason=reason,
                warnings=warns
            ))

        # 2. Check for destination filename collisions among input candidates
        for c in candidates:
            clash_list = proposed_counts.get(c.proposed_filename.lower(), [])
            if len(clash_list) > 1:
                c.status = AssetStatus.COLLISION_WARNING
                c.action = "SKIP"
                other_paths = [str(x.relative_path) for x in clash_list if x != c.identity]
                c.reason = f"Output collision: multiple input assets map to '{c.proposed_filename}': {other_paths}"
                c.warnings.append(c.reason)

        return candidates

    def render_summary(self, candidates: List[AssetCandidate]) -> str:
        """Renders an English summary table of the scan results."""
        total = len(candidates)
        already_impl = sum(1 for c in candidates if c.status == AssetStatus.ALREADY_IMPLEMENTED)
        to_convert = sum(1 for c in candidates if c.action == "CONVERT")
        collisions = sum(1 for c in candidates if c.status == AssetStatus.COLLISION_WARNING)
        reprocess = sum(1 for c in candidates if c.status == AssetStatus.REPROCESS_REQUESTED)

        redir_count = self.redirect_index.total_count
        redir_path_str = str(self.workspace.redirected_resources_dir) if self.workspace.redirected_resources_dir else "(not set)"

        lines = [
            "=" * 86,
            "             PRE-CONVERSION REDIRECTED RESOURCES SCAN REPORT",
            "=" * 86,
            f" RedirectedResources Dir : {redir_path_str}",
            f" Indexed Existing Bundles: {redir_count:,}",
            f" Candidate Assets        : {total}",
            f"   - [READY] To Convert   : {to_convert} (New: {to_convert - reprocess}, Reprocess: {reprocess})",
            f"   - [SKIP]  Already Done : {already_impl} (Present in patch)",
            f"   - [WARN]  Collisions   : {collisions} (Skipped for safety)",
            "=" * 86,
            f"{'Original Relative Path':<30} {'Proposed Output':<32} {'Status':<22} {'Action'}",
            "-" * 94,
        ]

        for c in candidates:
            rel = str(c.identity.relative_path)
            if len(rel) > 28:
                rel = "..." + rel[-25:]
            prop = c.proposed_filename
            if len(prop) > 30:
                prop = prop[:27] + "..."
            lines.append(f"{rel:<30} {prop:<32} {c.status.value:<22} {c.action}")
            if c.warnings:
                for w in c.warnings:
                    lines.append(f"    ! WARNING: {w}")

        lines.extend([
            "-" * 94,
            "Safe Default: Already implemented assets are skipped to prevent redundant conversion.",
            "Use '--reprocess <name>' or interactive menu to force re-conversion of specific assets.",
            "=" * 86,
        ])
        return "\n".join(lines)
