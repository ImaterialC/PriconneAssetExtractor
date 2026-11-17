#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
misora.core.story_ast - AST Parser, Record & Box Representation, and Byte Serializer.
Self-contained module handling Princess Connect! Re:Dive ADV story binary & v2 text formats.
"""
from __future__ import annotations

import base64
import binascii
import re
import struct
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# -----------------------------------------------------------------------------
# Regex & Normalization Constants
# -----------------------------------------------------------------------------
PLAYER_PLACEHOLDER_RE = re.compile(r"\{(?:player_?name|0)\}", re.IGNORECASE)
ALL_WS_RE = re.compile(r"[\s\u3000\u200b\u00a0\ufeff]+")
WS_RE = re.compile(r"\s+")
DASH_MAP = {c: "-" for c in "─—―–−‐‑"}
BREAK_RE = re.compile(r"\r\n|[\r\n\v\f\x85\u2028\u2029]")
BREAK_TAIL_RE = re.compile(r"(?:\r\n|[\r\n\v\f\x85\u2028\u2029])+$")

# Default command names & categories in Priconne ADV
DEFAULT_TEXT_CMDS = ("print", "tag")
NO_SPEAKER_CMDS = ("tag",)
DEFAULT_BREAKERS = ("touch", "page")
DEFAULT_CATEGORIES = (
    "System", "Foreground", "Background", "Screen", "Sound",
    "Movie", "Motion", "Effect", "Camera", "Face", "Animation",
    "Volume", "Other",
)

_CMD_MAP = {
    0: "fade", 1: "log", 2: "bg", 3: "chara", 4: "motion", 5: "face",
    6: "print", 7: "bgm", 8: "se", 9: "voice", 10: "touch", 11: "wait",
    12: "touch", 13: "wait", 14: "movie", 15: "fade", 16: "color",
    17: "chara_motion", 18: "motion", 20: "effect", 21: "fade_in",
    22: "fade_out", 23: "eye", 24: "lip", 25: "shake", 26: "flash",
    30: "title", 31: "outline", 35: "tag", 40: "shake_screen",
    41: "bloom", 42: "blur", 43: "fade_bg", 45: "bust", 50: "scale",
    51: "depth", 52: "wipe", 53: "mask", 55: "play_se", 56: "stop_se",
    57: "play_bgm", 58: "stop_bgm", 59: "effect", 60: "chara_visible",
    61: "chara_color", 62: "chara_layer", 63: "chara_flip", 64: "chara_scale",
    65: "chara_pos", 66: "chara_fade", 67: "chara_shake", 68: "unknown_68",
    70: "camera_move", 71: "camera_zoom", 72: "camera_rotate", 73: "camera_reset",
    80: "window_visible", 81: "window_size", 82: "window_pos",
    90: "next_page", 91: "choice", 92: "choice_jump", 100: "volume",
    110: "speed", 120: "flag_set", 121: "flag_check", 122: "flag_jump",
    125: "end"
}
_INV_CMD_MAP = {v: k for k, v in _CMD_MAP.items()}


# -----------------------------------------------------------------------------
# Binary Bit-Inversion Codec for Priconne ADV
# -----------------------------------------------------------------------------
def _invert3(b: bytes) -> bytes:
    """Invert every 3rd byte (~b[i] & 0xFF) as required by Priconne ADV protocol."""
    o = bytearray(b)
    for i in range(0, len(o), 3):
        o[i] = ~o[i] & 0xFF
    return bytes(o)


def decode_arg(raw: bytes) -> str:
    """Decode raw binary argument: invert -> base64 decode -> utf-8 text."""
    inv = _invert3(raw)
    try:
        payload = base64.b64decode(inv, validate=True)
    except (binascii.Error, ValueError):
        payload = base64.b64decode(inv)
    return payload.decode("utf-8", "surrogateescape")


def encode_arg(text: str) -> bytes:
    """Encode text argument: utf-8 text -> base64 encode -> invert."""
    return _invert3(base64.b64encode(text.encode("utf-8", "surrogateescape")))


# -----------------------------------------------------------------------------
# String Utility Functions
# -----------------------------------------------------------------------------
def game_to_xuat(s: str) -> str:
    """Convert raw in-game text breaks to standard newlines and normalizes player placeholder."""
    if not s:
        return s
    s = s.replace(chr(92) + "n", "\n")
    s = BREAK_RE.sub("\n", s)
    return PLAYER_PLACEHOLDER_RE.sub("{playername}", s)


def xuat_to_game(s: str, br: str = "\n") -> str:
    """Convert XUAT translation to game engine format, replacing {playername} with {0}."""
    if not s:
        return s
    s = PLAYER_PLACEHOLDER_RE.sub("{0}", s)
    if br in (chr(92) + "n", "\\n"):
        return BREAK_RE.sub(chr(92) + "n", s)
    return BREAK_RE.sub(br, s)


def norm_search(s: str) -> str:
    """
    Produce a completely whitespace-collapsed and placeholder-normalized string
    for matching XUnity's IgnoreWhitespaceInDialogue behavior.
    """
    if not s:
        return ""
    s = game_to_xuat(s)
    s = unicodedata.normalize("NFKC", s).translate(DASH_MAP)
    return re.sub(r"-{2,}", "-", ALL_WS_RE.sub("", s)).casefold()


def escape_arg(s: str) -> str:
    """Escape an argument for v2 text representation."""
    out = s.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return out


def unescape_arg(s: str) -> str:
    """Unescape an argument from v2 text representation."""
    if s.startswith("\\b64:"):
        return base64.b64decode(s[5:]).decode("utf-8", "surrogateescape")
    out, i = [], 0
    m = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "=": "="}
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] in m:
            out.append(m[s[i + 1]])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


# -----------------------------------------------------------------------------
# Record, Segment, and Box Data Classes
# -----------------------------------------------------------------------------
@dataclass
class Record:
    cmd_id: int
    cmd_name: str
    args: List[str]
    category: str = "Other"

    def render_v2(self) -> List[str]:
        lines = [self.cmd_name]
        for a in self.args:
            lines.append(escape_arg(a))
        lines.append(self.category)
        lines.append("")
        return lines


@dataclass
class Seg:
    rec_index: int
    text: str
    raw: str


@dataclass
class Box:
    speaker: str
    voice_cue: str
    segs: List[Seg]
    kind: str  # "print" or "tag"

    @property
    def text(self) -> str:
        """Returns the continuous, concatenated dialogue text across all segments."""
        parts = [s.text for s in self.segs if s.text]
        return "".join(parts)

    @property
    def clean_text(self) -> str:
        """Game display text with {playername} placeholder formatted cleanly."""
        return game_to_xuat(self.text)

    @property
    def raw(self) -> str:
        return "".join(s.raw for s in self.segs)


# -----------------------------------------------------------------------------
# Story Document AST Representation
# -----------------------------------------------------------------------------
class StoryDocument:
    """
    Lossless representation of a Priconne ADV cutscene script.
    Maintains both low-level command records and high-level dialogue boxes.
    """

    def __init__(self, records: Optional[List[Record]] = None):
        self.records: List[Record] = records or []
        self.boxes: List[Box] = []
        self.removed_records: Set[int] = set()
        self.break_char: str = "\n"
        if self.records:
            self._rebuild_boxes()

    def _rebuild_boxes(self) -> None:
        """Group sequential print/tag command segments into user-facing dialogue boxes."""
        boxes: List[Box] = []
        cur: Optional[Box] = None
        cur_voice: str = ""

        # Detect line break style
        counter = Counter()
        for r in self.records:
            if r.cmd_name in ("touch", "voice") and r.args:
                cur_voice = r.args[0]
            for a in r.args:
                for m in BREAK_RE.finditer(a):
                    counter[m.group()] += 1

            if r.cmd_name in DEFAULT_TEXT_CMDS:
                # Text command: args[0]=speaker (for print), args[1]=text
                if r.cmd_name == "print" and len(r.args) >= 2:
                    sp, tx = r.args[0], r.args[1]
                elif r.cmd_name == "tag" and len(r.args) >= 1:
                    sp, tx = "", r.args[0]
                else:
                    sp, tx = (r.args[0] if r.args else ""), ""

                if cur is None or cur.speaker != sp or cur.kind != r.cmd_name:
                    cur = Box(speaker=sp, voice_cue=cur_voice, segs=[], kind=r.cmd_name)
                    boxes.append(cur)
                rec_idx = len(self.records) - 1
                cur.segs.append(Seg(rec_index=self.records.index(r), text=tx, raw=tx))
            elif r.cmd_name in DEFAULT_BREAKERS:
                cur = None

        self.boxes = [b for b in boxes if b.segs]
        self.break_char = counter.most_common(1)[0][0] if counter else "\n"

    def actors(self) -> List[str]:
        """Return unique speaker names in chronological appearance order."""
        seen = []
        for b in self.boxes:
            if b.speaker and b.speaker not in seen:
                seen.append(b.speaker)
        return seen

    def inject_box(self, box_index: int, new_speaker: Optional[str], new_text: str, fill: str = " ") -> None:
        """
        Update a dialogue box in-place, redistributing new text across underlying binary segments.
        Ensures any {playername} placeholder is safely converted to {0} for the game engine.
        """
        if not (0 <= box_index < len(self.boxes)):
            raise IndexError(f"Box index {box_index} out of range (0-{len(self.boxes)-1})")

        box = self.boxes[box_index]
        if new_speaker is not None:
            box.speaker = new_speaker

        # Convert XUAT player placeholder {playername} to game format {0}
        core = xuat_to_game(new_text, self.break_char).rstrip("\r\n\v\f\x85\u2028\u2029")
        m = BREAK_TAIL_RE.search(box.raw)
        tail = m.group() if m else ""

        segs = box.segs
        target_idx = next((k for k, s in enumerate(segs) if s.raw.strip()), 0)

        for k, seg in enumerate(segs):
            rec = self.records[seg.rec_index]
            seg_text = (core if k == target_idx else fill) + (tail if k == len(segs) - 1 else "")
            if box.kind == "print":
                rec.args = [box.speaker, seg_text]
            else:
                rec.args = [seg_text]
            seg.text = seg_text

    # -------------------------------------------------------------------------
    # Binary Parser & Serializer
    # -------------------------------------------------------------------------
    @classmethod
    def from_binary(cls, raw: bytes) -> StoryDocument:
        """Parse Priconne proprietary binary story script bytes into a StoryDocument."""
        records: List[Record] = []
        pos, n = 0, len(raw)

        while pos < n:
            if pos + 2 > n:
                break
            cid = struct.unpack_from(">H", raw, pos)[0]
            pos += 2
            args = []
            while True:
                if pos + 4 > n:
                    break
                ln = struct.unpack_from(">I", raw, pos)[0]
                pos += 4
                if ln == 0:
                    break
                if pos + ln > n:
                    break
                arg_bytes = raw[pos:pos + ln]
                pos += ln
                args.append(decode_arg(arg_bytes))

            cmd_name = _CMD_MAP.get(cid, f"cmd_{cid}")
            records.append(Record(cmd_id=cid, cmd_name=cmd_name, args=args))

        return cls(records)

    def to_binary(self) -> bytes:
        """Serialize StoryDocument records back into exact Priconne proprietary binary format."""
        out = bytearray()
        for idx, r in enumerate(self.records):
            if idx in self.removed_records:
                continue
            cid = r.cmd_id if r.cmd_id != 0 or r.cmd_name == "fade" else _INV_CMD_MAP.get(r.cmd_name, 0)
            out += struct.pack(">H", cid)
            for a in r.args:
                if a == "":
                    continue
                raw_arg = encode_arg(a)
                out += struct.pack(">I", len(raw_arg)) + raw_arg
            out += struct.pack(">I", 0)
        return bytes(out)

    # -------------------------------------------------------------------------
    # V2 Text Parser & Serializer
    # -------------------------------------------------------------------------
    @classmethod
    def from_v2_text(cls, text: str) -> StoryDocument:
        """Parse readable v2 script text into a StoryDocument."""
        lines = [l.rstrip("\r\n") for l in text.splitlines()]
        if lines and lines[0].startswith("#!priconne-story"):
            lines.pop(0)

        records: List[Record] = []
        i = 0
        while i < len(lines):
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines):
                break
            cmd_name = lines[i].strip()
            i += 1
            args = []
            while i < len(lines):
                l = lines[i]
                i += 1
                if not l.strip():
                    break
                if l in DEFAULT_CATEGORIES and not l.startswith("\\"):
                    category = l
                    break
                args.append(unescape_arg(l))
            cmd_id = _INV_CMD_MAP.get(cmd_name, 0)
            records.append(Record(cmd_id=cmd_id, cmd_name=cmd_name, args=args))

        return cls(records)

    def to_v2_text(self) -> str:
        """Serialize StoryDocument into human-readable v2 script format."""
        out = ["#!priconne-story v2", ""]
        for idx, r in enumerate(self.records):
            if idx not in self.removed_records:
                out.extend(r.render_v2())
        return "\n".join(out)
