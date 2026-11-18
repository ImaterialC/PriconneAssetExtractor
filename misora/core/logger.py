#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora.core.logger - Central stdlib-only logging pipeline for Misora.
Routes structured diagnostic events to both an in-memory UI queue (for the embedded
Debug Console) and an optional append-safe UTF-8 file (misora_debug.log).
"""
from __future__ import annotations

import queue
import sys
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

LOG_LEVELS: Dict[str, int] = {
    "Debug": 10,
    "Info": 20,
    "Warning": 30,
    "Error": 40,
}

LOG_CATEGORIES: List[str] = [
    "File I/O",
    "Search",
    "XUAT Sync",
    "UI / Theme / Config",
    "Drag & Drop",
    "Errors & Exceptions",
]

ALWAYS_ON_CATEGORY = "Errors & Exceptions"


@dataclass
class LogEntry:
    timestamp: str
    level: str
    category: str
    message: str

    def format_line(self) -> str:
        return f"[{self.timestamp}] [{self.level.upper():<7}] [{self.category}] {self.message}"


class MisoraLogger:
    """
    Central thread-safe logger for Misora core and GUI modules.
    Never raises exceptions or blocks the UI thread.
    """

    def __init__(self, log_file_path: Path):
        self.log_file_path: Path = Path(log_file_path)
        self.level_name: str = "Info"
        self.log_to_file: bool = False
        self.categories: Dict[str, bool] = {cat: True for cat in LOG_CATEGORIES}
        self.categories[ALWAYS_ON_CATEGORY] = True

        self._lock = threading.Lock()
        self._ui_queue: "queue.Queue[LogEntry]" = queue.Queue(maxsize=4000)
        self._history: List[LogEntry] = []
        self._max_history: int = 2000
        self._file_error_warned: bool = False

    def configure(
        self,
        *,
        level_name: Optional[str] = None,
        log_to_file: Optional[bool] = None,
        categories: Optional[Dict[str, bool]] = None,
        log_file_path: Optional[Path] = None,
    ) -> None:
        with self._lock:
            if log_file_path is not None:
                self.log_file_path = Path(log_file_path)
                self._file_error_warned = False
            if level_name in LOG_LEVELS:
                self.level_name = level_name
            if log_to_file is not None:
                self.log_to_file = bool(log_to_file)
                if self.log_to_file:
                    self._file_error_warned = False
            if isinstance(categories, dict):
                for cat in LOG_CATEGORIES:
                    if cat == ALWAYS_ON_CATEGORY:
                        self.categories[cat] = True
                    elif cat in categories:
                        self.categories[cat] = bool(categories[cat])

    def get_config_snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "level": self.level_name,
                "log_to_file": self.log_to_file,
                "categories": dict(self.categories),
            }

    def is_category_enabled(self, category: str) -> bool:
        if category == ALWAYS_ON_CATEGORY:
            return True
        return self.categories.get(category, True)

    def log(self, level: str, category: str, message: str) -> None:
        norm_level = level if level in LOG_LEVELS else "Info"
        norm_cat = category if category in self.categories else "UI / Theme / Config"

        with self._lock:
            min_lvl = LOG_LEVELS.get(self.level_name, 20)
            cur_lvl = LOG_LEVELS[norm_level]
            cat_ok = (norm_cat == ALWAYS_ON_CATEGORY) or self.categories.get(norm_cat, True)
            if cur_lvl < min_lvl or not cat_ok:
                return

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            entry = LogEntry(timestamp=ts, level=norm_level, category=norm_cat, message=str(message))
            self._history.append(entry)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history :]

            # Real-time streaming to native Windows console
            try:
                print(entry.format_line(), file=sys.stdout, flush=True)
            except Exception:
                pass

            try:
                self._ui_queue.put_nowait(entry)
            except queue.Full:
                try:
                    self._ui_queue.get_nowait()
                    self._ui_queue.put_nowait(entry)
                except Exception:
                    pass

            if self.log_to_file:
                self._write_entry_to_file(entry)

    def _write_entry_to_file(self, entry: LogEntry) -> None:
        try:
            self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file_path, "a", encoding="utf-8") as fh:
                fh.write(entry.format_line() + "\n")
        except Exception as exc:
            if not self._file_error_warned:
                self._file_error_warned = True
                self.log_to_file = False
                warn_entry = LogEntry(
                    timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    level="Warning",
                    category=ALWAYS_ON_CATEGORY,
                    message=f"Failed writing to log file '{self.log_file_path}': {exc}. Degraded to console-only.",
                )
                self._history.append(warn_entry)
                try:
                    self._ui_queue.put_nowait(warn_entry)
                except Exception:
                    pass

    def debug(self, category: str, message: str) -> None:
        self.log("Debug", category, message)

    def info(self, category: str, message: str) -> None:
        self.log("Info", category, message)

    def warning(self, category: str, message: str) -> None:
        self.log("Warning", category, message)

    def error(self, category: str, message: str) -> None:
        self.log("Error", category, message)

    def exception(self, message: str, exc: Optional[BaseException] = None) -> None:
        if exc is not None:
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()
        else:
            tb_str = traceback.format_exc().rstrip()
        full_msg = f"{message}\n{tb_str}" if tb_str and tb_str != "NoneType: None" else message
        self.log("Error", ALWAYS_ON_CATEGORY, full_msg)

    def drain_ui_entries(self) -> List[LogEntry]:
        items: List[LogEntry] = []
        while True:
            try:
                items.append(self._ui_queue.get_nowait())
            except queue.Empty:
                break
        return items

    def get_history(self) -> List[LogEntry]:
        with self._lock:
            return list(self._history)

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()
        self.drain_ui_entries()

    def clear_log_file(self) -> bool:
        with self._lock:
            try:
                if self.log_file_path.exists():
                    self.log_file_path.write_text("", encoding="utf-8")
                return True
            except Exception as exc:
                self._file_error_warned = True
                print(f"[Misora] Failed to clear log file: {exc}", file=sys.stderr)
                return False