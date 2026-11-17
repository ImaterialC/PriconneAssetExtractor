"""
misora.core - Self-contained engine for Misora: Unity3D Revision Tool & Story Editor.
"""
from .story_ast import StoryDocument, Box, Seg, Record, game_to_xuat, xuat_to_game, norm_search
from .bundle_io import load_bundle_story, save_bundle_story, BundleIOError
from .search_engine import ProjectSearchEngine, SearchOptions, SearchResult
from .xunity_sync import XUnitySyncManager, SyncMatch

__all__ = [
    "StoryDocument", "Box", "Seg", "Record", "game_to_xuat", "xuat_to_game", "norm_search",
    "load_bundle_story", "save_bundle_story", "BundleIOError",
    "ProjectSearchEngine", "SearchOptions", "SearchResult",
    "XUnitySyncManager", "SyncMatch"
]
