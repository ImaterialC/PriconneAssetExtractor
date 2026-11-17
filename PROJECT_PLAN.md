# Princess Connect! Re:Dive Toolchain Refactoring & Integration Plan

## 1. Executive Summary & Architecture Overview

The Princess Connect! Re:Dive asset modification and localization ecosystem consists of two historically separate, specialized toolchains:

1. **Unity3D-to-XUAT Converter** (`priconne_tool.py`, `priconne-adv-tools`):
   - Responsible for extracting lossless script/subtitle text from Unity3D asset bundles.
   - Converts and aligns text with XUnity Auto Translator (XUAT) formats and clean translation sheets.
   - Injects translations, resolves translation conflicts, and repacks modified bytecode into `.unity3d` asset bundles for asset redirection via BepInEx.
   
2. **Universal Japanese Game Data Miner / Asset Extractor** (`OldDataMiner` / new implementation):
   - Responsible for communicating with game asset servers, parsing asset manifests (`manifest/*_assetmanifest`), downloading asset bundles, and extracting diverse asset types (graphics, textures, audio/sound, video/movie, story scripts, etc.).
   
These systems have distinct concerns and lifecycles. They must remain logically modular, testable, and maintainable, while integrating seamlessly in later phases.

---

## 2. Project Scope & Phased Priorities

Development strictly adheres to the following sequential phases:

```
[Phase 0: P0] Architecture Inspection & Baseline Documentation
      │
      ▼
[Phase 1: P1] Fix Unity3D Duplicate Detection, Workspace Boundaries & Naming Redesign
      │
      ▼
[Phase 2: P2] Universal Japanese Game Data Miner (Clean Architecture Rebuild)
      │
      ▼
[Phase 3: P3] Game Master Database Integration (SQLite, Schema, Asset Discovery)
      │
      ▼
[Phase 4: P4] Database Update Checking & Retrieval System (Version Diff, Safe Download)
      │
      ▼
[Phase 5: P5] End-to-End Toolchain Integration & Unified Workflow
```

---

## 3. Phase Details & Deliverables

### Phase 0: P0 — Inspection and Baseline (Current Scope)
- Inspect converter scanning logic, rename mechanism, and asset repacking.
- Inspect BepInEx layout (`Translation/en/Text`, `Translation/en/RedirectedResources`).
- Confirm separation and structure of `OldDataMiner`.
- Author `PROJECT_PLAN.md`, `DECISIONS.md`, and `PROGRESS.md`.

### Phase 1: P1 — Unity3D Duplicate Detection & Naming Redesign (Current Scope)
- **BepInEx Project Root Resolution**:
  - Accept BepInEx root path (e.g., `C:\[Gacha]\PriconneRe-TL\src\BepInEx`).
  - Isolate XUAT text scanning strictly to `Translation/en/Text`.
  - Isolate redirected asset scanning strictly to `Translation/en/RedirectedResources`.
  - Prevent recursive scanning of unrelated plugins or configs.
- **Pre-Conversion Duplicate & Redirect Detection**:
  - Scan `RedirectedResources` before any conversion/repacking begins.
  - Classify input assets into:
    - *Already Implemented*: identical or matching redirected asset already present.
    - *New / Unimplemented*: candidate for conversion and repacking.
    - *Collision Warning*: basename collision across different folders or conflicting target names.
  - Provide an interactive / CLI preview of detected duplicates with skip-by-default behavior and optional force-reprocess.
- **Multi-Representation Filename & Folder-Prefix Mapping**:
  - Support original relative paths (`storydata\0000011.unity3d`), flattened redirected names (`storydata_0000011.unity3d`), and basenames (`0000011.unity3d`).
  - Disambiguate identical basenames across disparate directories; never merge blindly.
- **Redesigned Naming Strategies**:
  1. *Automatic Redirected Resource Naming* (`<folder>_<basename>`)
  2. *Preserve Original Filename* (`<basename>`)
  3. *Match Existing Redirected Resource* (adopt existing matched redirected filename)
  4. *Custom Pattern Rule* (user-defined template)
  - Full preview of proposed output names prior to conversion, preventing silent overwrites.

### Phase 2: P2 — Universal Data Miner Rebuild
- Rebuild extraction engine based on `OldDataMiner` reference.
- Support multi-asset extraction (Text, Textures, Spine, Audio, Video).
- Prevent blind massive downloads through targeted manifest filtering.

### Phase 3: P3 — Game Master Database Integration (Completed)
- Direct read-only SQLite reading of `master.db` via `NewDataMiner/database.py`.
- Schema exploration and mapping tables (998 tables; units, character profiles, story titles, voice IDs, skill descriptions).
- Resource discovery queries and cross-referencing via `NewDataMiner/resource_cross_ref.py` connecting database rows to asset manifest filenames.
- Status classification: `Confirmed Mapping`, `Possible Mapping`, `Unresolved`, `Not Present in Current Database`.

### Phase 4: P4 — Database Update Checking (Completed)
- Lightweight remote check via HTTP HEAD requests in `NewDataMiner/db_updater.py` (reads `Content-Disposition`, `Content-Length`, `ETag`, `Last-Modified`).
- Version extraction from headers (e.g. `10071600`) without downloading 50MB file.
- SQLite integrity validation (`PRAGMA quick_check`, table count > 50, critical tables present).
- Safe download, validation in temporary staging, automatic backup of existing (`master.db.bak`), and atomic activation.

### Phase 5: P5 — Complete Integrated Workflow (Completed)
- Unified pipeline in `priconne_tool.py`:
  `Database query -> Manifest discovery -> Pre-check RedirectedResources -> Targeted extraction -> Text translation / XUAT injection -> Gated Repack -> Redirection validation`.
- Standalone launcher `5_integrated_workflow.bat` and CLI flags (`workflow`, `mine`).
