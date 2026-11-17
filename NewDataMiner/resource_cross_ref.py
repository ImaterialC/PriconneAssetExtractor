#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewDataMiner.resource_cross_ref - Cross-referencing database entities to game asset manifests
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .database import GameDatabase
from .manifest_manager import ManifestManager
from .models import AssetCategory, DownloadScope, ManifestEntry


class DiscoveryStatus(str, enum.Enum):
    CONFIRMED_MAPPING = "Confirmed Mapping"
    POSSIBLE_MAPPING = "Possible Mapping"
    UNRESOLVED = "Unresolved"
    NOT_IN_DATABASE = "Not Present in Current Database"
    DATABASE_RECORD_FOUND = "Database Record Found"
    ASSET_REFERENCE_FOUND = "Asset Reference Found"


@dataclass
class DiscoveredResource:
    entity_type: str                  # "story", "unit", "dialogue", "skill", "asset"
    entity_id: str                    # e.g., "1058001" or "105801"
    title: str                        # Human readable title / name
    status: DiscoveryStatus
    matched_entries: List[ManifestEntry] = field(default_factory=list)
    db_metadata: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @property
    def download_scope(self) -> DownloadScope:
        return DownloadScope(entries=self.matched_entries)


class ResourceCrossReferencer:
    """
    Connects GameDatabase records with ManifestManager asset manifests
    to enable intelligent discovery, scope preview, and targeted extraction.
    """

    def __init__(self, db: GameDatabase, manifest_manager: ManifestManager):
        self.db = db
        self.mm = manifest_manager

    def discover_story(self, query: str, limit: int = 25) -> List[DiscoveredResource]:
        """
        Search for stories in the database and resolve their matching
        storydata script bundles, icons, and voice audio assets.
        """
        results: List[DiscoveredResource] = []
        stories = self.db.search_stories(query, limit=limit) if self.db.is_available() else []

        # If no DB records found or DB offline, check if query matches manifest story assets directly
        if not stories:
            manifest_matches = self.mm.search(query, category=AssetCategory.STORY)
            if manifest_matches:
                for entry in manifest_matches[:limit]:
                    results.append(DiscoveredResource(
                        entity_type="story",
                        entity_id=entry.name.replace("storydata_", "").replace(".unity3d", ""),
                        title=entry.name,
                        status=DiscoveryStatus.NOT_IN_DATABASE if self.db.is_available() else DiscoveryStatus.ASSET_REFERENCE_FOUND,
                        matched_entries=[entry],
                        notes="Asset found in manifest, but not cataloged in database."
                    ))
            return results

        for story in stories:
            story_id = str(story.get("story_id", ""))
            title = story.get("title", "")
            sub_title = story.get("sub_title", "")
            display_title = f"{title} - {sub_title}" if sub_title else title

            # Look up manifest entries matching this story ID
            # Deterministic storydata script asset: storydata_<story_id>.unity3d
            exact_script_name = f"storydata_{story_id}.unity3d"
            script_matches = [e for e in self.mm.search(exact_script_name) if e.name == exact_script_name]

            # Also find associated voice and icon assets
            all_story_assets = self.mm.search(story_id)

            if script_matches:
                status = DiscoveryStatus.CONFIRMED_MAPPING
                notes = f"Found script bundle '{exact_script_name}' plus {len(all_story_assets) - len(script_matches)} related asset(s)."
            elif all_story_assets:
                status = DiscoveryStatus.POSSIBLE_MAPPING
                notes = f"Script bundle not found, but {len(all_story_assets)} related asset(s) match story ID."
            else:
                status = DiscoveryStatus.UNRESOLVED
                notes = "Database entry exists, but no matching assets found in loaded manifests."

            results.append(DiscoveredResource(
                entity_type="story",
                entity_id=story_id,
                title=display_title,
                status=status,
                matched_entries=all_story_assets,
                db_metadata=story,
                notes=notes
            ))

        return results

    def discover_unit(self, query: str, limit: int = 25) -> List[DiscoveredResource]:
        """
        Search for units in the database and resolve their matching
        battle bundles, voices, spine models, and face icons.
        """
        results: List[DiscoveredResource] = []
        units = self.db.search_units(query, limit=limit) if self.db.is_available() else []

        if not units:
            manifest_matches = self.mm.search(query, category=AssetCategory.UNIT)
            if manifest_matches:
                for entry in manifest_matches[:limit]:
                    results.append(DiscoveredResource(
                        entity_type="unit",
                        entity_id="unknown",
                        title=entry.name,
                        status=DiscoveryStatus.NOT_IN_DATABASE if self.db.is_available() else DiscoveryStatus.ASSET_REFERENCE_FOUND,
                        matched_entries=[entry],
                        notes="Asset found in manifest, but not cataloged in database."
                    ))
            return results

        for unit in units:
            unit_id = str(unit.get("unit_id", ""))
            name_en = unit.get("unit_name", "")
            name_jp = unit.get("unit_name_jp", "")
            voice_va = unit.get("voice", "")
            guild = unit.get("guild", "")

            title_parts = [name_en or name_jp]
            if name_jp and name_jp != name_en:
                title_parts.append(f"({name_jp})")
            if voice_va:
                title_parts.append(f"[CV: {voice_va}]")
            if guild:
                title_parts.append(f"[{guild}]")
            display_title = " ".join(title_parts)

            # Look up manifest entries matching this unit ID
            matched_entries = self.mm.search(unit_id)

            if matched_entries:
                status = DiscoveryStatus.CONFIRMED_MAPPING
                notes = f"Matched {len(matched_entries)} asset(s) (voices, spine, battle models, icons)."
            else:
                status = DiscoveryStatus.UNRESOLVED
                notes = "Character found in database, but no matching assets found in manifests."

            results.append(DiscoveredResource(
                entity_type="unit",
                entity_id=unit_id,
                title=display_title,
                status=status,
                matched_entries=matched_entries,
                db_metadata=unit,
                notes=notes
            ))

        return results

    def discover_skills(self, query: str, limit: int = 25) -> List[DiscoveredResource]:
        """
        Search for skills in the database and resolve icon assets.
        """
        results: List[DiscoveredResource] = []
        if not self.db.is_available():
            return []

        skills = self.db.search_skills(query, limit=limit)
        for skill in skills:
            skill_id = str(skill.get("skill_id", ""))
            name = skill.get("name", "")
            name_jp = skill.get("name_jp", "")
            icon_type = skill.get("icon_type", "")

            display_name = f"{name} ({name_jp})" if name_jp and name_jp != name else name
            matched_entries = []
            if icon_type:
                # Skill icon pattern in manifests: icon_skill_<icon_type>.unity3d
                icon_pattern = f"icon_skill_{icon_type}"
                matched_entries = self.mm.search(icon_pattern)

            status = DiscoveryStatus.CONFIRMED_MAPPING if matched_entries else DiscoveryStatus.DATABASE_RECORD_FOUND
            notes = f"Icon type {icon_type} -> {len(matched_entries)} asset(s) found." if icon_type else "No icon type recorded."

            results.append(DiscoveredResource(
                entity_type="skill",
                entity_id=skill_id,
                title=display_name,
                status=status,
                matched_entries=matched_entries,
                db_metadata=skill,
                notes=notes
            ))

        return results

    def discover_dialogues(self, query: str, limit: int = 25) -> List[DiscoveredResource]:
        """
        Search for homescreen and guildhouse dialogues and map them to voice assets.
        """
        results: List[DiscoveredResource] = []
        if not self.db.is_available():
            return []

        dialogues = self.db.search_dialogues(query, limit=limit)
        all_lines = []
        for row in dialogues.get("homescreen", []):
            row["source"] = "Homescreen Dialogue"
            all_lines.append(row)
        for row in dialogues.get("guildhouse", []):
            row["source"] = "Guildhouse Chirping"
            all_lines.append(row)

        for line in all_lines[:limit]:
            unit_id = str(line.get("unit_id", ""))
            voice_id = str(line.get("voice_id", ""))
            desc = line.get("description", "").replace("\n", " ")
            source = line.get("source", "Dialogue")

            title = f"[{source}] Unit {unit_id} (Voice #{voice_id}): {desc[:40]}..."

            # Map voice assets for unit
            # Homescreen voice is typically vo_cmn_<unit_id>; guildhouse is vo_room_<unit_id>
            expected_prefix = "vo_cmn_" if "Homescreen" in source else "vo_room_"
            sound_matches = [
                e for e in self.mm.search(unit_id, category=AssetCategory.SOUND)
                if expected_prefix in e.name
            ]

            if sound_matches:
                status = DiscoveryStatus.CONFIRMED_MAPPING
                notes = f"Associated voice bundle: {', '.join(e.name for e in sound_matches[:2])}"
            else:
                status = DiscoveryStatus.POSSIBLE_MAPPING
                notes = f"Voice bundle for unit {unit_id} not explicitly located."

            results.append(DiscoveredResource(
                entity_type="dialogue",
                entity_id=f"{unit_id}_{voice_id}",
                title=title,
                status=status,
                matched_entries=sound_matches,
                db_metadata=line,
                notes=notes
            ))

        return results
