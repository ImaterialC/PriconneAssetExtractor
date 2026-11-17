#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
browse_master_db.py - Interactive search and browser for Princess Connect! Re:Dive master.db
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from NewDataMiner.dataminer import DataMiner
from NewDataMiner.resource_cross_ref import DiscoveredResource, DiscoveryStatus


def print_discovery_table(resources: list[DiscoveredResource], max_show: int = 25) -> None:
    if not resources:
        print("  (No matching records found)")
        return

    print("=" * 95)
    print(f"{'Type':<8} {'ID':<10} {'Status':<20} {'Assets':<8} {'Title / Details':<45}")
    print("-" * 95)
    for r in resources[:max_show]:
        matched_str = str(len(r.matched_entries)) if r.matched_entries else "-"
        detail = r.title
        if "cv" in r.db_metadata and r.db_metadata["cv"]:
            detail += f" [CV: {r.db_metadata['cv']}]"
        if "guild" in r.db_metadata and r.db_metadata["guild"]:
            detail += f" [{r.db_metadata['guild']}]"
        print(f"{r.entity_type:<8} {r.entity_id:<10} {r.status.value:<20} {matched_str:<8} {detail:<45}")
    print("=" * 95)
    if len(resources) > max_show:
        print(f"  ... and {len(resources) - max_show} more record(s).")


def open_gui_browser(db_path: Path) -> None:
    print("\n[Opening DB Browser for SQLite...]")
    paths = [
        Path(r"C:\Program Files\DB Browser for SQLite\DB Browser for SQLite.exe"),
        Path(r"C:\Program Files (x86)\DB Browser for SQLite\DB Browser for SQLite.exe"),
    ]
    exe = None
    for p in paths:
        if p.is_file():
            exe = str(p)
            break
    if not exe:
        exe = shutil.which("sqlitebrowser")

    if exe and db_path.is_file():
        print(f"Launching: {exe} {db_path}")
        subprocess.Popen([exe, str(db_path)])
    else:
        print("[!] DB Browser for SQLite is not installed on this system.")
        print("\nTo install it (free & open source):")
        print("  1. Run in PowerShell: winget install SQLiteBrowser.SQLiteBrowser")
        print("  2. Or download installer: https://sqlitebrowser.org/dl/")
        print(f"\nOpening project folder in Explorer: {db_path.parent}")
        if sys.platform == "win32":
            os.startfile(str(db_path.parent))


def main() -> None:
    dm = DataMiner()
    db = dm.database
    db_available = db.is_available()

    while True:
        print("\n" + "=" * 70)
        print("           PRICONNE master.db BROWSER & EXPLORER")
        print("=" * 70)
        status_str = f"Available ({db.db_path.name})" if db_available else f"NOT FOUND ({db.db_path})"
        print(f"  Database Status : {status_str}")
        print("=" * 70)
        print("  1. Search Character / Unit (by English, Japanese name, or Unit ID)")
        print("  2. Search Story Episodes   (by Story ID, Chapter title, or keyword)")
        print("  3. Search Character Skills (by Skill name or ID)")
        print("  4. Search Dialogue Lines   (Homescreen & Guildhouse chirps)")
        print("  5. Cross-Reference ID      (Find all CDN asset files for an ID)")
        print("  6. List All Database Tables (View table names and row counts)")
        print("  7. Open master.db in SQLite GUI (DB Browser for SQLite)")
        print("  0. Exit")
        print("-" * 70)

        try:
            choice = input("Choose an option [1-7, 0]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not choice:
            continue

        if choice in ("0", "exit", "q"):
            print("Goodbye!")
            break

        if not db_available and choice in ("1", "2", "3", "4", "5", "6"):
            print(f"\n[!] master.db was not found at {db.db_path}!")
            print("Run '4_dataminer.bat --update-db' to download the latest database.")
            continue

        if choice == "1":
            q = input("\nEnter character name (e.g. Pecorine, ペコリーヌ) or ID (e.g. 105801): ").strip()
            if not q:
                continue
            units = db.search_units(q)
            print(f"\n[Unit Search Results] Found {len(units)} unit(s) matching '{q}':")
            for u in units:
                jp = f" ({u.get('unit_name_jp', '')})" if u.get('unit_name_jp') else ""
                guild = f" | Guild: {u.get('guild', '')}" if u.get('guild') else ""
                cv = f" | CV: {u.get('voice', '')}" if u.get('voice') else ""
                print(f"  [{u['unit_id']}] {u['unit_name']}{jp}{guild}{cv}")

        elif choice == "2":
            q = input("\nEnter story ID (e.g. 1001, 1058001) or title keyword (e.g. ヒヨリ, 美食殿): ").strip()
            if not q:
                continue
            stories = db.search_stories(q)
            print(f"\n[Story Search Results] Found {len(stories)} episode(s) matching '{q}':")
            for s in stories[:30]:
                sub = f" - {s.get('sub_title', '')}" if s.get('sub_title') else ""
                print(f"  [{s['story_id']}] {s['title']}{sub}")
            if len(stories) > 30:
                print(f"  ... and {len(stories) - 30} more episodes.")

        elif choice == "3":
            q = input("\nEnter skill name or ID: ").strip()
            if not q:
                continue
            skills = db.search_skills(q)
            print(f"\n[Skill Search Results] Found {len(skills)} skill(s) matching '{q}':")
            for sk in skills[:25]:
                print(f"  [{sk.get('skill_id')}] {sk.get('name', '')} - {sk.get('description', '')[:50]}")

        elif choice == "4":
            q = input("\nEnter dialogue keyword: ").strip()
            if not q:
                continue
            res = db.search_dialogues(q)
            homescreen = res.get("homescreen", [])
            guildhouse = res.get("guildhouse", [])
            print(f"\n[Dialogue Search Results] {len(homescreen)} homescreen, {len(guildhouse)} guildhouse:")
            for d in homescreen[:10]:
                print(f"  [Homescreen | Unit {d.get('unit_id')}] {d.get('description', '')}")
            for d in guildhouse[:10]:
                print(f"  [Guildhouse | Unit {d.get('unit_id')}] {d.get('description', '')}")

        elif choice == "5":
            q = input("\nEnter Unit or Story ID (e.g. 105801 for Pecorine, 1001 for Hiyori): ").strip()
            if not q:
                continue
            dm.manifest_manager.load_manifests()
            print(f"\n[Cross-Referencing] '{q}' against database and 113,000+ manifest assets...")
            resources = dm.discover_units(q)
            if not resources or resources[0].status == DiscoveryStatus.UNRESOLVED:
                resources.extend(dm.discover_stories(q))
            print_discovery_table(resources)

        elif choice == "6":
            tables = db.list_tables()
            print(f"\n[Total Tables in master.db: {len(tables):,}]")
            for t in tables[:40]:
                print(f"  {t['name']:<40} ({t['row_count']:,} rows)")
            if len(tables) > 40:
                print(f"  ... and {len(tables) - 40} more tables.")

        elif choice == "7":
            open_gui_browser(db.db_path)

        else:
            print("[!] Invalid option. Please choose 1-7 or 0.")


if __name__ == "__main__":
    main()
