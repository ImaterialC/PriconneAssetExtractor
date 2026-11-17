#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora.core.undo_journal - Bounded coalescing undo/redo journal for Misora.
Tracks box edits, plain-text edits, and bulk find-replace operations.
No external dependencies beyond stdlib.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

MAX_HISTORY = 50
COALESCE_WINDOW_SECS = 2.0


@dataclass
class BoxEditDelta:
    """Single dialogue box text/speaker change."""
    box_index: int
    old_speaker: str
    new_speaker: str
    old_text: str
    new_text: str
    file_path: str = ""  # str repr of Path for display


@dataclass
class PlainTextDelta:
    """Plain-text (.txt) file edit — full snapshot before/after."""
    file_path: str
    old_content: str
    new_content: str


@dataclass
class BulkFileDelta:
    """Replace-All across multiple files: list of (file_path, old_text, new_text) tuples."""
    description: str  # human-readable label e.g. "Replace 'foo' -> 'bar' in 3 files"
    per_file: List[Tuple[str, str, str]] = field(default_factory=list)  # (path, old, new)


@dataclass
class UndoOperation:
    """One undoable unit that may contain multiple deltas."""
    label: str                    # shown in Edit > Undo <label>
    timestamp: float              # time.monotonic() at creation
    deltas: List[Any] = field(default_factory=list)  # BoxEditDelta | PlainTextDelta | BulkFileDelta
    # True when this op was created by coalescing with the previous one
    coalesced: bool = False


class MasterUndoJournal:
    """
    Thread-safe bounded coalescing undo/redo journal.
    - Max MAX_HISTORY operations; oldest dropped on overflow.
    - Consecutive BoxEditDelta ops for the same box within COALESCE_WINDOW_SECS are merged.
    - begin_batch()/end_batch() groups multiple record() calls into one UndoOperation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._undo_stack: List[UndoOperation] = []
        self._redo_stack: List[UndoOperation] = []
        self._batch: Optional[UndoOperation] = None
        self._batch_depth: int = 0

    # ------------------------------------------------------------------
    # Batch API
    # ------------------------------------------------------------------
    def begin_batch(self, label: str) -> None:
        with self._lock:
            if self._batch_depth == 0:
                self._batch = UndoOperation(label=label, timestamp=time.monotonic())
            self._batch_depth += 1

    def end_batch(self) -> None:
        with self._lock:
            if self._batch_depth <= 0:
                return
            self._batch_depth -= 1
            if self._batch_depth == 0 and self._batch is not None:
                if self._batch.deltas:
                    self._push(self._batch)
                self._batch = None

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def record(self, delta: Any, label: str = "") -> None:
        """Record one delta. If inside a batch, appends to batch; otherwise creates/coalesces."""
        with self._lock:
            if self._batch is not None:
                self._batch.deltas.append(delta)
                if label and not self._batch.label:
                    self._batch.label = label
                return

            now = time.monotonic()
            # Coalescing: merge consecutive BoxEditDelta for same box within window
            if (
                isinstance(delta, BoxEditDelta)
                and self._undo_stack
                and not self._undo_stack[-1].coalesced is None  # always True, just checking stack non-empty
                and len(self._undo_stack[-1].deltas) == 1
                and isinstance(self._undo_stack[-1].deltas[0], BoxEditDelta)
                and self._undo_stack[-1].deltas[0].box_index == delta.box_index
                and self._undo_stack[-1].deltas[0].file_path == delta.file_path
                and (now - self._undo_stack[-1].timestamp) <= COALESCE_WINDOW_SECS
            ):
                prev_delta = self._undo_stack[-1].deltas[0]
                prev_delta.new_text = delta.new_text
                prev_delta.new_speaker = delta.new_speaker
                self._undo_stack[-1].timestamp = now
                self._undo_stack[-1].coalesced = True
                return

            op = UndoOperation(
                label=label or _auto_label(delta),
                timestamp=now,
                deltas=[delta],
            )
            self._push(op)

    def _push(self, op: UndoOperation) -> None:
        """Push op to undo stack, clear redo stack, enforce MAX_HISTORY."""
        self._redo_stack.clear()
        self._undo_stack.append(op)
        if len(self._undo_stack) > MAX_HISTORY:
            self._undo_stack = self._undo_stack[-MAX_HISTORY:]

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------
    def can_undo(self) -> bool:
        with self._lock:
            return bool(self._undo_stack)

    def can_redo(self) -> bool:
        with self._lock:
            return bool(self._redo_stack)

    def undo_label(self) -> str:
        with self._lock:
            return self._undo_stack[-1].label if self._undo_stack else ""

    def redo_label(self) -> str:
        with self._lock:
            return self._redo_stack[-1].label if self._redo_stack else ""

    def pop_undo(self) -> Optional[UndoOperation]:
        with self._lock:
            if not self._undo_stack:
                return None
            op = self._undo_stack.pop()
            self._redo_stack.append(op)
            return op

    def pop_redo(self) -> Optional[UndoOperation]:
        with self._lock:
            if not self._redo_stack:
                return None
            op = self._redo_stack.pop()
            self._undo_stack.append(op)
            return op

    def clear(self) -> None:
        with self._lock:
            self._undo_stack.clear()
            self._redo_stack.clear()
            self._batch = None
            self._batch_depth = 0

    @property
    def undo_depth(self) -> int:
        with self._lock:
            return len(self._undo_stack)

    @property
    def redo_depth(self) -> int:
        with self._lock:
            return len(self._redo_stack)


def _auto_label(delta: Any) -> str:
    if isinstance(delta, BoxEditDelta):
        return f"Edit box #{delta.box_index}"
    if isinstance(delta, PlainTextDelta):
        import os
        return f"Edit {os.path.basename(delta.file_path)}"
    if isinstance(delta, BulkFileDelta):
        return delta.description
    return "Edit"
