#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewDataMiner.cli - Interactive CLI & Targeted Resource Discovery Interface
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from .config import MinerConfig
from .dataminer import DataMiner
from .models import AssetCategory, ManifestEntry
from .resource_cross_ref import DiscoveredResource, DiscoveryStatus


def print_results_table(entries: List[ManifestEntry], max_show: int = 25) -> None:
    print("\n" + "=" * 90)
    print(f"{'Filename':<36} {'Category':<10} {'Size':<12} {'Manifest':<28}")
    print("-" * 90)
    for e in entries[:max_show]:
        fn = e.name if len(e.name) <= 34 else e.name[:31] + "..."
        print(f"{fn:<36} {e.category.value:<10} {e.human_size:<12} {e.manifest_name:<28}")
    if len(entries) > max_show:
        print(f"... and {len(entries) - max_show} more matching entries.")
    print("=" * 90)


def print_discovery_table(resources: List[DiscoveredResource], max_show: int = 20) -> None:
    print("\n" + "=" * 95)
    print(f"{'Type':<8} {'ID':<10} {'Status':<18} {'Assets':<8} {'Title / Details':<48}")
    print("-" * 95)
    for r in resources[:max_show]:
        title = r.title if len(r.title) <= 46 else r.title[:43] + "..."
        print(f"{r.entity_type:<8} {r.entity_id:<10} {r.status.value:<18} {len(r.matched_entries):<8} {title:<48}")
    if len(resources) > max_show:
        print(f"... and {len(resources) - max_show} more discovered records.")
    print("=" * 95)


def interactive_menu(dm: DataMiner) -> None:
    print("\nInitializing manifest catalog...")
    count = dm.manifest_manager.load_manifests()
    print(f"Indexed {count:,} assets across {len(dm.manifest_manager._by_manifest)} manifests.")

    db_status = "Available (master.db)" if dm.database.is_available() else "Not Found (master.db)"
    print(f"Game Database Status: {db_status}")

    while True:
        print("\n========================================================")
        print("         PRICONNE UNIVERSAL DATA MINER (NEW)")
        print("========================================================")
        print("  --- Manifest Asset Mining ---")
        print("  1. Search Assets in Manifests (Offline & Fast)")
        print("  2. Story Scripts (Search & Targeted Download)")
        print("  3. Unit & Character Assets (Search & Targeted Download)")
        print("  4. Textures, Icons & Backgrounds")
        print("  5. Sound & Music (Targeted Search with Size Preview)")
        print("  6. Movies / Videos (Targeted Search with Size Preview)")
        print("  7. Extract Local Files (input/ or downloads/)")
        print("  --- Database & Cross-Referenced Discovery (P3 & P4) ---")
        print("  8. Search Game Database (Units, Stories, Skills, Dialogues)")
        print("  9. Cross-Referenced Discovery (DB Entity -> Manifest Assets)")
        print("  10. Export Database Table to .sql")
        print("  11. Check for Database Updates (Lightweight Remote Check)")
        print("  0. Exit")

        choice = input("\nChoose: ").strip()
        if choice == "0":
            return

        if choice == "1":
            q = input("Search query (e.g. 0000011, Pecorine, bgm, boss): ").strip()
            if not q:
                continue
            results = dm.search(q)
            scope = dm.preview_scope(results)
            print(f"\nFound {scope.summary()}")
            print_results_table(results)

            if results:
                ans = input(f"\nDownload these {len(results)} file(s) ({scope.human_size})? [y/N]: ").strip().lower()
                if ans == "y":
                    downloaded = dm.download_targets(results, confirm=False)
                    ext_ans = input("Extract downloaded files now? [Y/n]: ").strip().lower()
                    if ext_ans != "n":
                        dm.extract_targets(downloaded)

        elif choice == "2":
            q = input("Story search (Quest / Episode ID e.g. 9080155, 80-9, tutorial): ").strip()
            results = dm.search(q, category=AssetCategory.STORY)
            scope = dm.preview_scope(results)
            print(f"\nFound {scope.summary()}")
            print_results_table(results)
            if results:
                ans = input(f"Download & extract these {len(results)} story file(s)? [y/N]: ").strip().lower()
                if ans == "y":
                    dl = dm.download_targets(results, confirm=False)
                    dm.extract_targets(dl)

        elif choice == "3":
            uid = input("Unit ID or name prefix (e.g. 1001, 100111): ").strip()
            results = dm.search(uid, category=AssetCategory.UNIT)
            results.extend(dm.search(uid, category=AssetCategory.SPINE))
            scope = dm.preview_scope(results)
            print(f"\nFound {scope.summary()}")
            print_results_table(results)
            if results:
                ans = input(f"Download & extract {len(results)} unit file(s) ({scope.human_size})? [y/N]: ").strip().lower()
                if ans == "y":
                    dl = dm.download_targets(results, confirm=False)
                    dm.extract_targets(dl)

        elif choice == "4":
            q = input("Texture/Icon keyword (e.g. icon_unit_100111, bg_common): ").strip()
            results = dm.search(q, category=AssetCategory.ICON)
            results.extend(dm.search(q, category=AssetCategory.BG))
            results.extend(dm.search(q, category=AssetCategory.BANNER))
            scope = dm.preview_scope(results)
            print(f"\nFound {scope.summary()}")
            print_results_table(results)
            if results:
                ans = input(f"Download & extract {len(results)} texture(s) ({scope.human_size})? [y/N]: ").strip().lower()
                if ans == "y":
                    dl = dm.download_targets(results, confirm=False)
                    dm.extract_targets(dl)

        elif choice == "5":
            q = input("Sound/BGM keyword (e.g. bgm_AM01, vo_): ").strip()
            results = dm.search(q, category=AssetCategory.SOUND)
            scope = dm.preview_scope(results)
            print(f"\n[Sound Preview] Found {scope.summary()}")
            print_results_table(results)
            if results:
                ans = input(f"Proceed with downloading {scope.human_size}? [y/N]: ").strip().lower()
                if ans == "y":
                    dl = dm.download_targets(results, confirm=False)
                    dm.extract_targets(dl)

        elif choice == "6":
            q = input("Movie keyword (e.g. arcade_1001, op): ").strip()
            results = dm.search(q, category=AssetCategory.MOVIE)
            scope = dm.preview_scope(results)
            print(f"\n[Movie Preview] Found {scope.summary()}")
            print_results_table(results)
            if results:
                ans = input(f"Proceed with downloading {scope.human_size}? [y/N]: ").strip().lower()
                if ans == "y":
                    dl = dm.download_targets(results, confirm=False)
                    dm.extract_targets(dl)

        elif choice == "7":
            local_dir = input("Local folder to extract [default: downloads]: ").strip() or "downloads"
            p = Path(local_dir)
            if not p.exists():
                print(f"Folder '{local_dir}' not found.")
                continue
            files = [x for x in p.rglob("*") if x.is_file() and x.suffix.lower() in (".unity3d", ".asset", ".usm", ".awb", ".acb")]
            print(f"Found {len(files)} extractable local files in {p}.")
            if files:
                dm.extract_targets(files)
                print(f"Extraction complete -> {dm.config.extract_dir}")

        elif choice == "8":
            if not dm.database.is_available():
                print(f"[!] master.db not found at: {dm.database.db_path}")
                continue
            print("\nDatabase Search Categories:")
            print("  a. Units (by ID, EN/JP name, CV, Guild)")
            print("  b. Stories (by ID, Title, Subtitle)")
            print("  c. Skills (by ID, Name, Description)")
            print("  d. Dialogues (Homescreen & Guildhouse chirps)")
            cat_choice = input("Select category [a/b/c/d]: ").strip().lower()

            q = input("Search query: ").strip()
            if not q:
                continue

            if cat_choice == "a":
                units = dm.database.search_units(q)
                print(f"\nFound {len(units)} unit(s):")
                for u in units[:20]:
                    print(f"  [{u['unit_id']}] {u['unit_name']} ({u.get('unit_name_jp', '')}) | Guild: {u.get('guild', '')} | CV: {u.get('voice', '')}")
            elif cat_choice == "b":
                stories = dm.database.search_stories(q)
                print(f"\nFound {len(stories)} story episode(s):")
                for s in stories[:20]:
                    print(f"  [{s['story_id']}] {s['title']} - {s.get('sub_title', '')}")
            elif cat_choice == "c":
                skills = dm.database.search_skills(q)
                print(f"\nFound {len(skills)} skill(s):")
                for sk in skills[:20]:
                    desc = sk.get('description', '').replace('\n', ' ')[:60]
                    print(f"  [{sk['skill_id']}] {sk['name']} ({sk.get('name_jp', '')}) : {desc}...")
            elif cat_choice == "d":
                res = dm.database.search_dialogues(q)
                hs = res.get("homescreen", [])
                gh = res.get("guildhouse", [])
                print(f"\nFound {len(hs)} Homescreen dialogue(s), {len(gh)} Guildhouse chirp(s):")
                for d in hs[:10]:
                    desc = d.get('description', '').replace('\n', ' ')
                    print(f"  [Homescreen | Unit {d['unit_id']}] {desc}")
                for d in gh[:10]:
                    desc = d.get('description', '').replace('\n', ' ')
                    print(f"  [Guildhouse | Unit {d['unit_id']}] {desc}")

        elif choice == "9":
            if not dm.database.is_available():
                print(f"[!] master.db not found at: {dm.database.db_path}")
                continue
            print("\nCross-Referenced Discovery:")
            print("  a. Character / Unit Discovery (Resolves Battle, Spine, Voice, Icons)")
            print("  b. Story Discovery (Resolves Scripts, Icons, Voices)")
            print("  c. Skill Discovery (Resolves Skill Icons)")
            print("  d. Dialogue Discovery (Resolves Character Voice Audio)")
            c_type = input("Select mode [a/b/c/d]: ").strip().lower()
            q = input("Search query (Character name, ID, or Title): ").strip()
            if not q:
                continue

            resources: List[DiscoveredResource] = []
            if c_type == "a":
                resources = dm.discover_units(q)
            elif c_type == "b":
                resources = dm.discover_stories(q)
            elif c_type == "c":
                resources = dm.discover_skills(q)
            elif c_type == "d":
                resources = dm.discover_dialogues(q)

            print_discovery_table(resources)

            if resources:
                sel = input("\nEnter index # to inspect and download assets (or Enter to skip): ").strip()
                if sel.isdigit() and 1 <= int(sel) <= len(resources):
                    target_res = resources[int(sel) - 1]
                    scope = target_res.download_scope
                    print(f"\nSelected '{target_res.title}' [{target_res.status.value}]")
                    print(f"Target Assets: {scope.summary()}")
                    for e in target_res.matched_entries:
                        print(f"  - {e.name} ({e.category.value}, {e.human_size})")

                    ans = input(f"\nDownload these {scope.total_count} file(s) ({scope.human_size})? [y/N]: ").strip().lower()
                    if ans == "y":
                        dl = dm.download_targets(target_res.matched_entries, confirm=False)
                        ext_ans = input("Extract downloaded files now? [Y/n]: ").strip().lower()
                        if ext_ans != "n":
                            dm.extract_targets(dl)

        elif choice == "10":
            if not dm.database.is_available():
                print(f"[!] master.db not found at: {dm.database.db_path}")
                continue
            tbl = input("Table name to export (e.g. unit_data, story_detail, skill_data): ").strip()
            if not tbl:
                continue
            out_file = Path("exports") / f"{tbl}.sql"
            try:
                rows = dm.export_table_sql(tbl, out_file)
                print(f"\n[OK] Exported {rows:,} rows of '{tbl}' to {out_file}")
            except Exception as e:
                print(f"[!] Failed to export: {e}")

        elif choice == "11":
            print("\nChecking for master.db updates from remote source...")
            res = dm.check_database_updates()
            print(f"Remote Source: {res.remote_info.source_name} ({res.remote_info.url})")
            print(f"Local Database: {'Found' if res.local_info.exists else 'Missing'} ({res.local_info.human_size})")
            if res.remote_info.version:
                print(f"Remote Version: {res.remote_info.version} (Filename: {res.remote_info.filename})")
            print(f"Status: {res.reason}")

            if res.update_available:
                ans = input(f"\nDownload and install update ({res.remote_info.human_size})? [y/N]: ").strip().lower()
                if ans == "y":
                    def show_prog(dl, tot):
                        mb_dl = dl / (1024 * 1024)
                        mb_tot = tot / (1024 * 1024) if tot > 0 else 0
                        print(f"\rDownloading database: {mb_dl:.1f}/{mb_tot:.1f} MB...", end="", flush=True)

                    dm.apply_database_update(on_progress=show_prog)
                    print("\n[OK] Database updated successfully.")


def main():
    ap = argparse.ArgumentParser(description="Priconne Universal Japanese Game Data Miner & Database Explorer")
    ap.add_argument("-s", "--search", help="search query across manifests")
    ap.add_argument("-c", "--category", choices=[c.value for c in AssetCategory], help="filter by asset category")
    ap.add_argument("-m", "--manifest", help="filter by manifest name")
    ap.add_argument("--download", action="store_true", help="download search matches")
    ap.add_argument("--extract", action="store_true", help="extract downloaded files")
    ap.add_argument("-o", "--out", help="destination directory for extracted assets")

    # P3 & P4 CLI Flags
    ap.add_argument("--db-unit", help="search units in master.db")
    ap.add_argument("--db-story", help="search stories in master.db")
    ap.add_argument("--db-skill", help="search skills in master.db")
    ap.add_argument("--db-dialogue", help="search dialogues in master.db")
    ap.add_argument("--cross-ref", help="cross-reference entity to manifest assets")
    ap.add_argument("--export-sql", help="export specified database table to SQL")
    ap.add_argument("--list-tables", action="store_true", help="list all database tables")
    ap.add_argument("--check-db-update", action="store_true", help="check for newer database version")
    ap.add_argument("--update-db", action="store_true", help="download and install database update if available")

    a = ap.parse_args()
    dm = DataMiner()

    if a.check_db_update or a.update_db:
        print("\nChecking for database updates...")
        res = dm.check_database_updates()
        print(f"Source: {res.remote_info.source_name}")
        print(f"Local: {res.local_info.human_size} | Remote: {res.remote_info.human_size}")
        if res.remote_info.version:
            print(f"Remote Version: {res.remote_info.version}")
        print(f"Result: {res.reason}")

        if a.update_db and res.update_available:
            print("Applying update...")
            dm.apply_database_update()
            print("[OK] Database updated.")
        return

    if a.list_tables:
        if not dm.database.is_available():
            print(f"[!] Database not available at {dm.database.db_path}")
            sys.exit(1)
        tables = dm.list_database_tables()
        print(f"\nTotal Tables: {len(tables):,}")
        for t in tables[:40]:
            print(f"  {t['name']:<40} ({t['row_count']:,} rows)")
        if len(tables) > 40:
            print(f"  ... and {len(tables) - 40} more tables.")
        return

    if a.export_sql:
        out_p = Path("exports") / f"{a.export_sql}.sql"
        rows = dm.export_table_sql(a.export_sql, out_p)
        print(f"Exported {rows:,} rows of '{a.export_sql}' to {out_p}")
        return

    if a.db_unit:
        dm.manifest_manager.load_manifests()
        units = dm.database.search_units(a.db_unit)
        print(f"\n[Unit Search Results] Found {len(units)} unit(s) matching '{a.db_unit}':")
        for u in units:
            print(f"  [{u['unit_id']}] {u['unit_name']} ({u.get('unit_name_jp', '')}) | Guild: {u.get('guild', '')} | CV: {u.get('voice', '')}")
        return

    if a.db_story:
        dm.manifest_manager.load_manifests()
        stories = dm.database.search_stories(a.db_story)
        print(f"\n[Story Search Results] Found {len(stories)} episode(s) matching '{a.db_story}':")
        for s in stories:
            print(f"  [{s['story_id']}] {s['title']} - {s.get('sub_title', '')}")
        return

    if a.cross_ref:
        dm.manifest_manager.load_manifests()
        print(f"\n[Cross-Referencing] '{a.cross_ref}'...")
        res = dm.discover_units(a.cross_ref)
        if not res or res[0].status == DiscoveryStatus.UNRESOLVED:
            res.extend(dm.discover_stories(a.cross_ref))
        print_discovery_table(res)
        return

    if a.search or a.category or a.manifest:
        results = dm.search(query=a.search or "", category=a.category, manifest=a.manifest)
        scope = dm.preview_scope(results)
        print(f"\n[Search Results] Found {scope.summary()}")
        print_results_table(results)

        if a.download and results:
            downloaded = dm.download_targets(results, confirm=not a.extract)
            if a.extract and downloaded:
                extracted = dm.extract_targets(downloaded, dest_dir=Path(a.out) if a.out else None)
                print(f"\nExtracted {len(extracted)} files to {a.out or dm.config.extract_dir}")
    else:
        interactive_menu(dm)


if __name__ == "__main__":
    main()
