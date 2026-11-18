"""
misora.core - Self-contained engine for Misora: Unity3D Revision Tool & Story Editor.
"""
from .story_ast import StoryDocument, Box, Seg, Record, game_to_xuat, xuat_to_game, norm_search
from .bundle_io import load_bundle_story, save_bundle_story, BundleIOError
from .search_engine import ProjectSearchEngine, SearchOptions, SearchResult
from .xunity_sync import XUnitySyncManager, SyncMatch
from .logger import MisoraLogger, LogEntry, LOG_CATEGORIES, LOG_LEVELS, ALWAYS_ON_CATEGORY
from .undo_journal import MasterUndoJournal, UndoOperation, BoxEditDelta, PlainTextDelta, BulkFileDelta
from .mtl_engine import MTLConfig, MTLEngine, TagMasker, translate_async, MTL_ENGINES, DEFAULT_LLM_PROMPT

__all__ = [
    "StoryDocument", "Box", "Seg", "Record", "game_to_xuat", "xuat_to_game", "norm_search",
    "load_bundle_story", "save_bundle_story", "BundleIOError",
    "ProjectSearchEngine", "SearchOptions", "SearchResult",
    "XUnitySyncManager", "SyncMatch",
    "MisoraLogger", "LogEntry", "LOG_CATEGORIES", "LOG_LEVELS", "ALWAYS_ON_CATEGORY",
    "MasterUndoJournal", "UndoOperation", "BoxEditDelta", "PlainTextDelta", "BulkFileDelta",
    "MTLConfig", "MTLEngine", "TagMasker", "translate_async", "MTL_ENGINES", "DEFAULT_LLM_PROMPT",
]
