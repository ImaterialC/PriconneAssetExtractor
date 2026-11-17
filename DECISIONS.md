# Technical Decisions, Assumptions & Architecture Standards

## 1. Project Separation & Boundaries

- **Separation of Concerns**: The Unity3D converter (`priconne_tool.py`, `advscript.py`, `xuat2raw.py`) and the Universal Data Miner (`OldDataMiner` and future `NewDataMiner`) are kept logically separate. The converter does not attempt to download raw assets from Cygame servers, and the Data Miner does not handle XUAT line injection or dialogue format conversions.
- **Reference Code Preservation**: The legacy Data Miner code in `OldDataMiner/` is treated as strictly read-only reference. It is never overwritten or broken during refactoring.

## 2. BepInEx Scanning Boundaries & Configuration

- **BepInEx Root Resolution**:
  - The project recognizes a configured BepInEx root path (e.g. `C:\[Gacha]\PriconneRe-TL\src\BepInEx`).
  - Derived sub-workspaces:
    - XUAT Text workspace: `<BepInEx>\Translation\en\Text`
    - Redirected Resources workspace: `<BepInEx>\Translation\en\RedirectedResources`
  - If a user configures a path pointing directly to `Translation\en\Text` or `Translation\en\RedirectedResources`, the tool automatically infers the BepInEx root while honoring explicit overrides.
- **Strict Isolation**:
  - `Translation\en\Text` is scanned strictly for translation sheets (`.txt`).
  - `Translation\en\RedirectedResources` is scanned strictly for redirected `.unity3d` / `.asset` bundles.
  - Subdirectories like `BepInEx\config`, `BepInEx\plugins`, `BepInEx\core`, `BepInEx\Translation\en\Font`, `Texture`, etc., are strictly ignored to prevent corrupting plugin configurations or unrelated translation data.

## 3. Redirected Resource Naming & Identity Matching

- **Asset Identity Representation**:
  An asset is identified using a hierarchy of identifiers:
  1. `relative_path`: Path relative to the extraction/bundle root (e.g., `storydata\0000011.unity3d`).
  2. `flattened_name`: Prefix-joined redirected filename convention used by BepInEx/XUAT RedirectedResources (e.g., `storydata_0000011.unity3d`).
  3. `basename`: Plain filename (e.g., `0000011.unity3d`).
- **Ambiguity & Collision Protection**:
  - Basename matching is only used as a fallback if and only if it is globally unique across the scanned set.
  - If identical basenames exist in different folders (e.g., `storydata\0000011.unity3d` vs `event\0000011.unity3d`), they are flagged with a collision warning and are NEVER silently merged.
- **Naming Strategies Supported**:
  1. `auto_redirect`: Automatically prepends the parent category/folder (e.g. `storydata_<basename>`).
  2. `preserve_original`: Keeps the original basename as-is.
  3. `match_existing`: If a matching asset exists in `RedirectedResources`, adopts its exact filename.
  4. `custom_pattern`: Formats according to user-defined pattern tokens.

## 4. Duplicate Detection & Reprocessing

- **Pre-Conversion Detection**:
  Before extracting or repacking, all input candidate assets are compared against the scanned `RedirectedResources` catalog.
- **Status Classification**:
  - `ALREADY_IMPLEMENTED`: Asset bundle is already in `RedirectedResources` (matches by flattened name, relative path, or verified hash). Skipped by default to prevent redundant work.
  - `NEW`: Asset bundle not found in `RedirectedResources`.
  - `COLLISION_RISK`: Ambiguous match or conflicting destination filename detected.
- **Explicit Override**:
  Users can review the scan summary and choose whether to skip already-implemented assets (default safe behavior) or explicitly reprocess designated assets.

## 5. Python Runtime Compatibility

- Python 3.12 (or 3.11–3.14 via the `py` launcher) is strictly utilized for all UnityPy operations. Python 3.15 is avoided due to the lack of precompiled `lz4` binary wheels required by UnityPy.

## 6. Universal Data Miner Design & Download Scope Safety

- **Offline Indexing First**: Manifests (113,000+ asset rows across 49 manifests) are indexed in memory. The system allows users to search by keyword, regex, or category in sub-second time without connecting to asset CDN servers or downloading files.
- **Download Scope Preview & Safety Threshold**: The Data Miner computes exact file counts and byte sizes prior to downloading (`DownloadScope`). For downloads exceeding a configurable safety threshold (50 MB), explicit user confirmation is required to prevent accidental multi-gigabyte bandwidth consumption.
- **Concurrency & Process Safety on Windows**: Concurrent downloads utilize Python's standard `concurrent.futures.ThreadPoolExecutor` instead of `multiprocessing.Pool`, eliminating Windows pickling errors, fork deadlocks, and worker crashes.
- **UnityPy Fallback Version Configuration**: Configured `UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"` across all modules to ensure unversioned Priconne story bundles parse cleanly without exceptions.
- Batch files will automatically discover and invoke the compatible Python minor version.

## 7. Game Master Database (`master.db`) Integration & Direct SQLite Access

- **Direct SQLite Querying over Raw SQL Grep**: Direct querying via Python's built-in `sqlite3` module provides sub-millisecond lookups across all 998 tables and eliminates the need to maintain enormous multi-hundred-megabyte SQL text dumps for basic lookups.
- **Read-Only Safety**: Database connections are opened using SQLite URI mode `file:<path>?mode=ro` to guarantee that queries never modify or corrupt the master database.
- **Dynamic Schema Adaptability**: Queries adapt dynamically to column presence (e.g. supporting deobfuscated tables with `unit_name_jp` or standard tables with `unit_name`).
- **Resource Cross-Referencing Classification**:
  Every entity discovery query is tagged with an explicit status:
  - `Confirmed Mapping`: Direct match in both database and manifest (e.g. story ID `1058001` -> `storydata_1058001.unity3d`).
  - `Possible Mapping`: Heuristic match on unit or voice patterns.
  - `Unresolved`: Entity present in database, but corresponding bundle absent from loaded manifests.
  - `Not Present in Current Database`: Asset exists in manifest, but entity not present in database.

## 8. Database Update Checking & Atomic Staging

- **Lightweight Update Check via HTTP HEAD**: Remote checking queries HTTP HEAD headers (`Content-Disposition`, `Content-Length`, `ETag`, `Last-Modified`) to extract the remote database version (e.g., version `10071600`) without downloading the 50 MB database.
- **Integrity Validation Before Activation**: Downloaded databases are written to a temporary staging file (`master.db.downloading`), checked with SQLite `PRAGMA quick_check`, verified to contain > 50 tables and critical game tables (`unit_data`, `story_detail`), before atomic activation.
- **Automatic Backup**: Existing `master.db` is backed up to `master.db.bak` prior to replacement.

## 9. Integrated Toolchain Architecture (P5)

- **End-to-End Orchestration**:
  Connects:
  `Database -> Resource Discovery -> Pre-Conversion Duplicate Check -> Targeted Mining -> XUAT Injection -> Repack Gating -> Redirection`.
- **Pre-Conversion Redirection Gating**: Before downloading or converting an asset, the system checks whether the bundle already exists in BepInEx `RedirectedResources`. If already implemented, it is skipped by default to eliminate redundant processing.
- **Translation Completeness Gating**: Bundles are only repacked into `.unity3d` if 100% of real dialogue lines are translated. Incomplete translations produce detailed line-by-line `.missing.txt` gap reports.
- **XUAT Cleanup**: Repacked lines are safely cleaned from active XUAT text files upon confirmation, with automatic backups preserved.
