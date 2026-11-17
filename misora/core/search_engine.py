#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora.core.search_engine - Multi-file search engine across Unity3D bundles and plain text files.
Supports case-sensitive, regex, and XUnity whitespace-insensitive / playername-aware searching.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generator, List, Optional, Union

from .bundle_io import load_bundle_story
from .story_ast import StoryDocument, norm_search


@dataclass
class SearchOptions:
    query: str
    match_case: bool = False
    use_regex: bool = False
    ignore_whitespace: bool = True
    include_bundles: bool = True
    include_text: bool = True


@dataclass
class SearchResult:
    file_path: Path
    file_type: str  # "bundle" (.unity3d) or "text" (.txt, .json)
    line_number: int
    box_index: Optional[int]
    speaker: str
    full_text: str
    match_snippet: str
    start_pos: int
    end_pos: int


class ProjectSearchEngine:
    """
    Search engine supporting both binary Unity3D assets and standard text files.
    """

    @staticmethod
    def _compile_matcher(options: SearchOptions) -> Callable[[str], List[Tuple[int, int, str]]]:
        """Compile a matching function based on search options."""
        q = options.query
        flags = 0 if options.match_case else re.IGNORECASE

        if options.use_regex:
            try:
                rx = re.compile(q, flags)
            except re.error as e:
                raise ValueError(f"Invalid regex '{q}': {e}")

            def regex_matcher(text: str):
                matches = []
                for m in rx.finditer(text):
                    matches.append((m.start(), m.end(), m.group()))
                return matches

            return regex_matcher

        if options.ignore_whitespace:
            norm_q = norm_search(q)

            def whitespace_matcher(text: str):
                norm_t = norm_search(text)
                if norm_q in norm_t:
                    # Provide approximate position in original text
                    return [(0, len(text), text[:80])]
                return []

            return whitespace_matcher

        # Standard substring matching
        if not options.match_case:
            q_lower = q.lower()

            def case_insensitive_matcher(text: str):
                t_lower = text.lower()
                matches = []
                start = 0
                while True:
                    pos = t_lower.find(q_lower, start)
                    if pos == -1:
                        break
                    matches.append((pos, pos + len(q), text[pos:pos + len(q)]))
                    start = pos + max(1, len(q))
                return matches

            return case_insensitive_matcher

        def exact_matcher(text: str):
            matches = []
            start = 0
            while True:
                pos = text.find(q, start)
                if pos == -1:
                    break
                matches.append((pos, pos + len(q), text[pos:pos + len(q)]))
                start = pos + max(1, len(q))
            return matches

        return exact_matcher

    def search_file(self, file_path: Union[str, Path], options: SearchOptions) -> List[SearchResult]:
        """Search inside a single file (.unity3d bundle or plain text)."""
        file_path = Path(file_path)
        if not file_path.is_file():
            return []

        matcher = self._compile_matcher(options)
        results: List[SearchResult] = []
        ext = file_path.suffix.lower()

        # 1. Search in Unity3D bundle
        if ext in (".unity3d", ".asset") and options.include_bundles:
            try:
                doc, _, _, _ = load_bundle_story(file_path)
                for box_idx, box in enumerate(doc.boxes):
                    matches = matcher(box.clean_text)
                    if not matches:
                        # Also check raw text and speaker name
                        matches = matcher(box.text)
                    if not matches and box.speaker:
                        matches = matcher(box.speaker)

                    for start, end, match_text in matches:
                        snippet = box.clean_text.replace("\n", " ")
                        if len(snippet) > 80:
                            snippet = snippet[:77] + "..."
                        results.append(SearchResult(
                            file_path=file_path,
                            file_type="bundle",
                            line_number=box_idx + 1,
                            box_index=box_idx,
                            speaker=box.speaker or "System",
                            full_text=box.clean_text,
                            match_snippet=snippet,
                            start_pos=start,
                            end_pos=end
                        ))
            except Exception:
                pass

        # 2. Search in plain text files
        elif ext in (".txt", ".json", ".csv", ".tsv") and options.include_text:
            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                for line_idx, line in enumerate(lines, 1):
                    matches = matcher(line)
                    for start, end, match_text in matches:
                        snippet = line.strip()
                        if len(snippet) > 80:
                            snippet = snippet[:77] + "..."
                        results.append(SearchResult(
                            file_path=file_path,
                            file_type="text",
                            line_number=line_idx,
                            box_index=None,
                            speaker="",
                            full_text=line,
                            match_snippet=snippet,
                            start_pos=start,
                            end_pos=end
                        ))
            except Exception:
                pass

        return results

    def search_directory(
        self,
        directory: Union[str, Path],
        options: SearchOptions,
        recursive: bool = True,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None
    ) -> List[SearchResult]:
        """
        Search recursively through all candidate files in a directory.
        Provides live progress callbacks and cancellation checks.
        """
        directory = Path(directory)
        if not directory.is_dir():
            return []

        all_files: List[Path] = []
        exts = []
        if options.include_bundles:
            exts.extend([".unity3d", ".asset"])
        if options.include_text:
            exts.extend([".txt", ".json"])

        for root, _, files in os.walk(directory):
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in exts:
                    all_files.append(Path(root) / f)

        total_files = len(all_files)
        all_results: List[SearchResult] = []

        for idx, fp in enumerate(all_files, 1):
            if should_cancel and should_cancel():
                break
            if on_progress:
                on_progress(idx, total_files, fp.name)
            res = self.search_file(fp, options)
            all_results.extend(res)

        return all_results
