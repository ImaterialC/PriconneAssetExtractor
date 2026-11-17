#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora.core.search_engine - Multi-file search engine across Unity3D bundles and plain text files.
Supports case-sensitive, regex, and XUnity whitespace-insensitive / playername-aware searching
with exact character-span tracking for UI keyword highlighting.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Union

from .bundle_io import load_bundle_story
from .story_ast import (
    ALL_WS_RE,
    BREAK_RE,
    DASH_MAP,
    PLAYER_PLACEHOLDER_RE,
    StoryDocument,
    norm_search,
)

_TOKEN_RE = re.compile(
    r"\{(?:player_?name|0)\}|\\n|\r\n|[\r\n\v\f\x85\u2028\u2029]|.",
    re.IGNORECASE | re.DOTALL,
)


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
    snippet_start: int = 0
    snippet_end: int = 0
    match_in_speaker: bool = False


class ProjectSearchEngine:
    """
    Search engine supporting both binary Unity3D assets and standard text files.
    """

    @staticmethod
    def _norm_search_with_spans(text: str) -> Tuple[str, List[Tuple[int, int]]]:
        """
        Normalize text identically to story_ast.norm_search() while preserving
        a 1-to-1 mapping from each normalized character back to its (start, end)
        character span in the original `text`.
        """
        if not text:
            return "", []

        raw_chars: List[str] = []
        raw_spans: List[Tuple[int, int]] = []

        for m in _TOKEN_RE.finditer(text):
            tok = m.group(0)
            s_idx, e_idx = m.start(), m.end()

            if PLAYER_PLACEHOLDER_RE.fullmatch(tok):
                expanded = "{playername}"
            elif tok == "\\n" or BREAK_RE.fullmatch(tok):
                continue
            else:
                expanded = tok

            norm_tok = unicodedata.normalize("NFKC", expanded).translate(DASH_MAP).casefold()
            norm_tok = ALL_WS_RE.sub("", norm_tok)
            for ch in norm_tok:
                raw_chars.append(ch)
                raw_spans.append((s_idx, e_idx))

        # Collapse consecutive dashes ('--' -> '-') while merging their source spans
        collapsed_chars: List[str] = []
        collapsed_spans: List[Tuple[int, int]] = []
        i = 0
        n = len(raw_chars)
        while i < n:
            if raw_chars[i] == "-":
                j = i + 1
                while j < n and raw_chars[j] == "-":
                    j += 1
                collapsed_chars.append("-")
                collapsed_spans.append((raw_spans[i][0], raw_spans[j - 1][1]))
                i = j
            else:
                collapsed_chars.append(raw_chars[i])
                collapsed_spans.append(raw_spans[i])
                i += 1

        return "".join(collapsed_chars), collapsed_spans

    @staticmethod
    def _build_highlighted_snippet(
        source_text: str,
        start: int,
        end: int,
        max_len: int = 84
    ) -> Tuple[str, int, int]:
        """
        Flatten newlines into spaces and produce a preview snippet centered around
        [start, end), returning (snippet, snippet_start, snippet_end).
        """
        flat_chars: List[str] = []
        orig_to_flat: List[int] = [0] * (len(source_text) + 1)
        idx = 0
        src_len = len(source_text)

        while idx < src_len:
            orig_to_flat[idx] = len(flat_chars)
            if source_text[idx] == "\r" and idx + 1 < src_len and source_text[idx + 1] == "\n":
                orig_to_flat[idx + 1] = len(flat_chars)
                flat_chars.append(" ")
                idx += 2
            elif source_text[idx] in ("\n", "\r"):
                flat_chars.append(" ")
                idx += 1
            else:
                flat_chars.append(source_text[idx])
                idx += 1
        orig_to_flat[src_len] = len(flat_chars)

        flat_text = "".join(flat_chars)
        s_clamped = max(0, min(src_len, start))
        e_clamped = max(s_clamped, min(src_len, end))
        flat_s = orig_to_flat[s_clamped]
        flat_e = orig_to_flat[e_clamped]

        if len(flat_text) <= max_len:
            return flat_text, flat_s, flat_e

        win_body = max_len - 6  # Reserve room for "..." on both sides
        win_start = max(0, flat_s - 24)
        win_end = min(len(flat_text), max(win_start + win_body, flat_e + 16))
        if win_end - win_start > win_body:
            win_end = win_start + win_body
        if win_end == len(flat_text):
            win_start = max(0, win_end - win_body)

        prefix = "..." if win_start > 0 else ""
        suffix = "..." if win_end < len(flat_text) else ""
        snippet = prefix + flat_text[win_start:win_end] + suffix

        hs = len(prefix) + max(0, min(win_end - win_start, flat_s - win_start))
        he = len(prefix) + max(hs - len(prefix), min(win_end - win_start, flat_e - win_start))
        return snippet, hs, he

    @classmethod
    def _compile_matcher(cls, options: SearchOptions) -> Callable[[str], List[Tuple[int, int, str]]]:
        """Compile a matching function returning exact (start, end, matched_text) tuples."""
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
                    if m.end() > m.start():
                        matches.append((m.start(), m.end(), m.group()))
                return matches

            return regex_matcher

        if options.ignore_whitespace:
            norm_q = norm_search(q)
            if not norm_q:
                return lambda _text: []

            def whitespace_matcher(text: str):
                norm_t, spans = cls._norm_search_with_spans(text)
                if not norm_t or norm_q not in norm_t:
                    return []
                matches: List[Tuple[int, int, str]] = []
                pos = 0
                q_len = len(norm_q)
                while True:
                    hit = norm_t.find(norm_q, pos)
                    if hit == -1:
                        break
                    orig_start = spans[hit][0]
                    orig_end = spans[hit + q_len - 1][1]
                    matches.append((orig_start, orig_end, text[orig_start:orig_end]))
                    pos = hit + max(1, q_len)
                return matches

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
                    in_speaker = False
                    matches = matcher(box.clean_text)

                    if not matches and box.text != box.clean_text:
                        # Fallback to raw text (e.g., literal "{0}" query with ignore_whitespace=False)
                        raw_matches = matcher(box.text)
                        if raw_matches:
                            matches = [
                                (0, len(box.clean_text), box.clean_text)
                                for _ in raw_matches
                            ]

                    if not matches and box.speaker:
                        speaker_matches = matcher(box.speaker)
                        if speaker_matches:
                            matches = speaker_matches
                            in_speaker = True

                    for start, end, _match_text in matches:
                        if in_speaker:
                            snippet, hs, he = self._build_highlighted_snippet(box.speaker, start, end)
                        else:
                            snippet, hs, he = self._build_highlighted_snippet(box.clean_text, start, end)

                        results.append(SearchResult(
                            file_path=file_path,
                            file_type="bundle",
                            line_number=box_idx + 1,
                            box_index=box_idx,
                            speaker=box.speaker or "System",
                            full_text=box.clean_text,
                            match_snippet=snippet,
                            start_pos=start,
                            end_pos=end,
                            snippet_start=hs,
                            snippet_end=he,
                            match_in_speaker=in_speaker,
                        ))
            except Exception:
                pass

        # 2. Search in plain text files
        elif ext in (".txt", ".json", ".csv", ".tsv") and options.include_text:
            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                for line_idx, line in enumerate(lines, 1):
                    matches = matcher(line)
                    for start, end, _match_text in matches:
                        snippet, hs, he = self._build_highlighted_snippet(line, start, end)
                        results.append(SearchResult(
                            file_path=file_path,
                            file_type="text",
                            line_number=line_idx,
                            box_index=None,
                            speaker="",
                            full_text=line,
                            match_snippet=snippet,
                            start_pos=start,
                            end_pos=end,
                            snippet_start=hs,
                            snippet_end=he,
                            match_in_speaker=False,
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
            if not recursive:
                break

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