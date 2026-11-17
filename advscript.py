#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Core library: Priconne ADV raw script <-> clean translation sheets."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

DEFAULT_CATEGORIES = ("System", "Motion", "Effect")
DEFAULT_TEXT_CMDS = ("focus",)
NO_SPEAKER_CMDS = ("title", "outline", "title_telop")
DEFAULT_BREAKERS = ("goto", "type", "touch", "title", "outline", "situation")

CMD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
KANA_RE = re.compile(r"[\u3040-\u30ff]")
WORD_RE = re.compile(r"[0-9A-Za-z\u3040-\u30ff\u4e00-\u9fff]")
WS_RE = re.compile(r"\s+")
JP_PUNCT = "。、！？「」『』（）・〜～…─゛゜"
DASH_MAP = {c: "-" for c in "─—―–−‐‑"}
BREAK_RE = re.compile(r"\r\n|[\r\n\v\f\x85\u2028\u2029]")
BREAK_TAIL_RE = re.compile(r"(?:\r\n|[\r\n\v\f\x85\u2028\u2029])+$")

H_ACTORS, H_SCRIPTS, H_PUNCT = "## Actors", "## Scripts", "## Punctuation"
HEADER = "#!priconne-story v2"


def game_to_xuat(s):
    if not s:
        return s
    s = s.replace(chr(92) + "n", "\n")
    return BREAK_RE.sub("\n", s)


def xuat_to_game(s, br):
    if not s:
        return s
    if br in (chr(92) + "n", "\\n"):
        return BREAK_RE.sub(chr(92) + "n", s)
    return BREAK_RE.sub(br, s)


@dataclass
class Config:
    categories: tuple = DEFAULT_CATEGORIES
    text_cmds: tuple = DEFAULT_TEXT_CMDS
    breakers: tuple = DEFAULT_BREAKERS
    trailing_nl: str = "always"
    break_char: str = "auto"
    filler: str = " "

    @staticmethod
    def load(path=None):
        c = Config()
        if path and Path(path).exists():
            d = {k.strip(): v for k, v in json.loads(Path(path).read_text("utf-8")).items()}
            for k in ("categories", "text_cmds", "breakers"):
                if k in d:
                    setattr(c, k, tuple(str(x).strip() for x in d[k]))
            for k in ("trailing_nl", "break_char", "filler"):
                if k in d:
                    setattr(c, k, d[k])
        return c


# ---------------------------------------------------------------- escaping
def esc(s):
    return (s.replace("\\", "\\\\").replace("\n", "\\n")
            .replace("\r", "\\r").replace("\t", "\\t"))


def unesc(s):
    out, i, m = [], 0, {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "=": "="}
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] in m:
            out.append(m[s[i + 1]]); i += 2
        else:
            out.append(s[i]); i += 1
    return "".join(out)


_ESC = {"\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\v": "\\v",
        "\f": "\\f", "\x85": "\\N", "\u2028": "\\L", "\u2029": "\\P"}
_UNESC = {v[1]: k for k, v in _ESC.items()}
_UNESC.update({"s": " ", "S": "\u3000"})
_ESC_RE = re.compile("[" + re.escape("".join(_ESC)) + "]")


def escape_arg(s):
    out = _ESC_RE.sub(lambda m: _ESC[m.group()], s)
    m = re.search(r"[ \u3000]+$", out)
    if m:
        out = out[:m.start()] + "".join("\\s" if c == " " else "\\S" for c in m.group())
    return "\\" + out if out in DEFAULT_CATEGORIES else out


def unescape_arg(line):
    if line.startswith("\\b64:"):
        import base64
        return base64.b64decode(line[5:]).decode("utf-8", "surrogateescape")
    if line.startswith("\\") and line[1:] in DEFAULT_CATEGORIES:
        return line[1:]
    out, i = [], 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line) and line[i + 1] in _UNESC:
            out.append(_UNESC[line[i + 1]]); i += 2
        else:
            out.append(line[i]); i += 1
    return "".join(out)


# ---------------------------------------------------------------- text utils
def norm1(s):
    return game_to_xuat(s).strip()


def norm2(s):
    s = unicodedata.normalize("NFKC", norm1(s)).translate(DASH_MAP)
    return re.sub(r"-{2,}", "-", WS_RE.sub("", s)).casefold()


def looks_japanese(s):
    if KANA_RE.search(s):
        return True
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    latin = bool(re.search(r"[A-Za-z]", s))
    if cjk and not latin:
        return True
    if cjk >= 2:
        return True
    return any(ch in JP_PUNCT for ch in s) and not latin


def is_punct_only(s):
    return not WORD_RE.search(s)


def load_lines(path, encoding=None):
    raw = Path(path).read_bytes()
    bom, enc = b"", encoding
    if enc is None:
        if raw.startswith(b"\xef\xbb\xbf"):
            enc, bom = "utf-8", b"\xef\xbb\xbf"
        elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            enc = "utf-16"
        else:
            enc = "utf-8"
    try:
        text = raw.decode(enc)
    except UnicodeDecodeError:
        enc, text = "cp932", raw.decode("cp932", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
        if enc == "utf-8":
            bom = b"\xef\xbb\xbf"
    eol = "\r\n" if "\r\n" in text else "\n"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    final = text.endswith("\n")
    lines = text.split("\n")
    if final:
        lines.pop()
    return lines, {"enc": enc, "bom": bom, "eol": eol, "final_nl": final}


def save_lines(path, lines, meta):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = meta["eol"].join(lines) + (meta["eol"] if meta["final_nl"] else "")
    p.write_bytes(meta["bom"] + text.encode(meta["enc"], "surrogateescape"))


def write_text(path, text, eol="\n"):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.replace("\n", eol).encode("utf-8"))


def iter_inputs(inp, recursive=True, pattern="*.txt"):
    p = Path(inp)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(x for x in (p.rglob(pattern) if recursive else p.glob(pattern))
                      if x.is_file() and "_probe" not in x.parts)
    return sorted(Path().glob(inp))


# ---------------------------------------------------------------- clean sheets
def is_clean(lines):
    for l in lines:
        if l.strip():
            return l.lstrip().startswith("##")
    return False


def read_clean(path, encoding=None):
    lines, _ = load_lines(path, encoding)
    sec, cur = {}, None
    for l in lines:
        if l.lstrip().startswith("##"):
            cur = l.strip()[2:].strip().lower()
            sec.setdefault(cur, [])
            continue
        if cur is None or not l.strip():
            continue
        sec[cur].append(unesc(l))
    return sec


def write_clean(path, actors, scripts, punct=None):
    L = [H_ACTORS] + [esc(a) for a in actors] + ["", H_SCRIPTS] + [esc(s) for s in scripts]
    if punct:
        L += ["", H_PUNCT] + [esc(p) for p in punct]
    write_text(path, "\n".join(L) + "\n")


# ---------------------------------------------------------------- raw parsing
@dataclass
class Record:
    cmd: str
    args: list
    cat: object

    def render(self):
        out = [self.cmd] + [escape_arg(a) for a in self.args]
        if self.cat is not None:
            out.append(self.cat)
        out.append("")
        return out


def parse_records(lines, cfg, warnings, where=""):
    cats = set(cfg.categories)
    v2 = bool(lines) and lines[0].startswith("#!")
    i, n, recs = (1 if v2 else 0), len(lines), []
    while i < n:
        if lines[i] == "":
            i += 1
            continue
        cmd = lines[i]; i += 1
        args = []
        while i < n and lines[i] not in cats:
            ln = lines[i]
            if v2:
                args.append(unescape_arg(ln))
            elif ln == "":
                if args and not (cmd in ("focus", "print") and len(args) == 1):
                    args[-1] += "\n"
                else:
                    args.append("\n")
            else:
                args.append(ln)
            i += 1
        cat = None
        if i < n:
            cat = lines[i]; i += 1
        else:
            warnings.append(f"{where}: record {cmd!r} has no category terminator")
        if not CMD_RE.match(cmd):
            warnings.append(f"{where}: suspicious command token {cmd!r}")
        recs.append(Record(cmd, args, cat))
    return recs


@dataclass
class Seg:
    rec: int
    raw: str

    @property
    def text(self):
        return game_to_xuat(self.raw)


@dataclass
class Box:
    speaker: str
    voice: str
    segs: list = field(default_factory=list)
    kind: str = "focus"

    @property
    def raw(self):
        return "".join(s.raw for s in self.segs)

    @property
    def text(self):
        return game_to_xuat(self.raw)


def split_focus(r):
    if r.cmd in NO_SPEAKER_CMDS:
        return "", (r.args[0] if r.args else "")
    return (r.args[0] if r.args else ""), (r.args[1] if len(r.args) > 1 else "")


def set_seg_text(r, speaker, text, no_speaker=False):
    body = [text] if text else []
    r.args = body if no_speaker else [speaker] + body


def build_boxes(recs, cfg):
    boxes, cur, voice = [], None, ""
    tc, br = set(cfg.text_cmds), set(cfg.breakers)
    for i, r in enumerate(recs):
        if r.cmd == "touch" and r.args:
            voice = r.args[0]
        if r.cmd in tc:
            sp, tx = split_focus(r)
            if cur is None or cur.speaker != sp or cur.kind != r.cmd:
                cur = Box(sp, voice, [], r.cmd)
                boxes.append(cur)
            cur.segs.append(Seg(i, tx))
        elif r.cmd in br:
            cur = None
    return [b for b in boxes if b.segs]


def detect_break_char(recs, default="\n"):
    c = Counter(m.group() for r in recs for a in r.args for m in BREAK_RE.finditer(a))
    return c.most_common(1)[0][0] if c else default


def box_key(box, policy="always"):
    t = box.text
    if not t.strip():
        return t
    if policy == "always":
        return t.rstrip("\n") + "\n"
    if policy == "never":
        return t.rstrip("\n")
    return t


class Document:
    def __init__(self, path, encoding=None, cfg=None):
        self.path = Path(path)
        self.cfg = cfg or Config()
        self.lines, self.meta = load_lines(path, encoding)
        self.warnings = []
        self.removed = set()
        self.records = parse_records(self.lines, self.cfg, self.warnings, self.path.name)
        self.boxes = build_boxes(self.records, self.cfg)
        self.break_char = (detect_break_char(self.records)
                           if self.cfg.break_char == "auto" else self.cfg.break_char)
        self.items = [(i, b) for i, b in enumerate(self.boxes)
                      if box_key(b, "auto").strip()]
        if not self.records:
            self.warnings.append(f"{self.path.name}: no records parsed")

    def actors(self):
        seen = []
        for b in self.boxes:
            if b.speaker and b.speaker not in seen:
                seen.append(b.speaker)
        return seen

    def rename_speaker(self, old, new):
        for r in self.records:
            if (r.cmd in self.cfg.text_cmds and r.cmd not in NO_SPEAKER_CMDS
                    and r.args and r.args[0] == old):
                r.args[0] = new

    def save(self, path):
        out = [HEADER]
        for i, r in enumerate(self.records):
            if i not in self.removed:
                out.extend(r.render())
        save_lines(path, out, dict(self.meta, final_nl=True))


# ---------------------------------------------------------------- injection
def inject(doc, box, en, mode="first", fill=None):
    br = doc.break_char
    fill = doc.cfg.filler if fill is None else fill
    core = xuat_to_game(en, br).rstrip("\r\n\v\f\x85\u2028\u2029")
    m = BREAK_TAIL_RE.search(box.raw)
    tail = m.group() if m else ""
    no_sp = box.kind in NO_SPEAKER_CMDS
    segs = box.segs
    ti = next((k for k, s in enumerate(segs) if s.raw.strip()), 0)

    if fill == "drop":
        for k, seg in enumerate(segs):
            if k == ti:
                set_seg_text(doc.records[seg.rec], box.speaker, core + tail, no_sp)
            else:
                doc.removed.add(seg.rec)
        return

    if mode == "spread" and len(segs) > 1:
        w = [max(1, len(WS_RE.sub("", s.text))) for s in segs]
        parts = _spread(core, w)
        for k, seg in enumerate(segs):
            t = (parts[k] or fill) + (tail if k == len(segs) - 1 else "")
            set_seg_text(doc.records[seg.rec], box.speaker, t, no_sp)
        return

    for k, seg in enumerate(segs):
        t = (core if k == ti else fill) + (tail if k == len(segs) - 1 else "")
        set_seg_text(doc.records[seg.rec], box.speaker, t, no_sp)


def _spread(en, w):
    total, cuts, acc = sum(w) or 1, [0], 0
    for x in w[:-1]:
        acc += x
        pos = round(len(en) * acc / total)
        snap = None
        for d in range(9):
            for p in (pos - d, pos + d):
                if 0 < p < len(en) and en[p - 1] in " \n\u3000":
                    snap = p; break
            if snap is not None:
                break
        cuts.append(max(snap if snap is not None else pos, cuts[-1]))
    cuts.append(len(en))
    return [en[cuts[i]:cuts[i + 1]] for i in range(len(w))]


# ---------------------------------------------------------------- dictionary
@dataclass
class Entry:
    key: str
    val: str
    src: str
    line: int


class Store:
    def __init__(self, fuzzy=0.92, session_file="conflict_resolutions.json"):
        self.exact, self.empty, self.used = {}, set(), set()
        self.conflicts, self.skipped = [], []
        self.fuzzy = fuzzy
        self.candidates = {}     # norm_key -> list[Entry]
        self.resolutions = {}    # norm_key -> chosen_val
        self.session_file = session_file
        self._load_resolutions()
        self._loose = self._tight = self._head = self._tail = None

    def _load_resolutions(self):
        p = Path(self.session_file)
        if not p.is_absolute():
            for cand in [Path(self.session_file), Path(__file__).parent / self.session_file]:
                if cand.exists():
                    p = cand
                    break
        if p.exists():
            try:
                self.resolutions = json.loads(p.read_text("utf-8"))
            except Exception:
                self.resolutions = {}

    def _save_resolutions(self):
        try:
            p = Path(self.session_file)
            p.write_text(json.dumps(self.resolutions, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def load(self, paths, encoding=None):
        for p in paths or []:
            for f in iter_inputs(p):
                self.load_file(f, encoding)
        return self

    def load_file(self, path, encoding=None):
        lines, _ = load_lines(path, encoding)
        if lines and lines[0].startswith("#!priconne-story"):
            self.skipped.append((str(path), "raw script")); return
        if is_clean(lines):
            self.skipped.append((str(path), "clean sheet")); return
        if not any("=" in l for l in lines) and any(l.strip() == "System" for l in lines[:200]):
            self.skipped.append((str(path), "legacy raw")); return
        block = any(l.startswith("=") for l in lines)
        section, jp, en, in_en, start = None, [], [], False, 0

        def flush():
            nonlocal jp, en, in_en
            if jp:
                self.add("\n".join(jp), "\n".join(en), str(path), start)
            jp, en, in_en = [], [], False

        for no, raw in enumerate(lines, 1):
            line = raw.rstrip("\r")
            s = line.strip()
            if s.startswith("##"):
                flush()
                section = "actors" if "actor" in s.lower() else "scripts"
                continue
            if s.startswith("//") or (s.startswith("#") and not s.startswith("#!")):
                continue
            if s.startswith(("r:", "sr:")):
                self.skipped.append((f"{path}:{no}", "regex")); continue
            if not s:
                flush(); continue
            if line.startswith("="):
                in_en, en = True, [line[1:]]; continue
            if not block or section == "actors":
                if "=" in line:
                    flush()
                    k, v = line.split("=", 1)
                    self.add(unesc(k), unesc(v), str(path), no)
                    continue
            if in_en:
                if looks_japanese(line):
                    flush(); jp, start = [line], no
                else:
                    en.append(line)
            else:
                if not jp:
                    start = no
                jp.append(line)
        flush()

    def add(self, key, val, src, line):
        key = game_to_xuat(key)
        if not key.strip():
            return
        e = Entry(key, val, src, line)
        norm_k = key.rstrip("\n")
        self.candidates.setdefault(norm_k, []).append(e)

        old = self.exact.get(key)
        if old is not None:
            if old.val.strip() and val.strip() and old.val != val:
                self.conflicts.append((key, old.val, val,
                                       f"{old.src}:{old.line}", f"{src}:{line}"))
            if not old.val.strip() and val.strip():
                self.exact[key] = e
        else:
            self.exact[key] = e
        if not val.strip():
            self.empty.add(key)
        else:
            self.empty.discard(key)

    def _build(self, tight=False):
        if self._loose is None:
            self._loose = {}
            for k, e in self.exact.items():
                self._loose.setdefault(norm1(k), e)
        if tight and self._tight is None:
            self._tight, self._head, self._tail = {}, {}, {}
            for k, e in self.exact.items():
                t = norm2(k)
                self._tight.setdefault(t, []).append(e)
                self._head.setdefault(t[:3], []).append(t)
                self._tail.setdefault(t[-3:], []).append(t)

    def lookup(self, text, allow_fuzzy=True, actors=None):
        text = game_to_xuat(text)
        for c in (text, text.rstrip("\n"), text.rstrip("\n") + "\n", text.strip()):
            e = self.exact.get(c)
            if e and e.val.strip():
                self.used.add(e.key); return e, "exact"
        self._build()
        e = self._loose.get(norm1(text))
        if e and e.val.strip():
            self.used.add(e.key); return e, "strip"
        variants = [text]
        if actors and "\n" in text:
            h, rest = text.split("\n", 1)
            if h.strip() in actors:
                variants.append(rest)
        self._build(tight=True)
        for v in variants:
            good = [h for h in self._tight.get(norm2(v), []) if h.val.strip()]
            if good:
                best = min(good, key=lambda h: abs(len(h.key) - len(v)))
                self.used.add(best.key); return best, "norm"
        if allow_fuzzy and self.fuzzy > 0:
            e = self._fuzzy(norm2(text))
            if e:
                self.used.add(e.key); return e, "fuzzy"
        return None, "none"

    def lookup_resolved(self, text, allow_fuzzy=True, actors=None, interactive=True, context=""):
        norm_k = game_to_xuat(text).rstrip("\n")
        cands = self.candidates.get(norm_k, [])
        seen_vals = {}
        unique_cands = []
        for c in cands:
            v = c.val.strip()
            if v and v not in seen_vals:
                seen_vals[v] = True
                unique_cands.append(c)

        if len(unique_cands) > 1:
            chosen = self.resolve_conflict(text, unique_cands, interactive, context)
            if chosen:
                self.used.add(chosen.key)
                return chosen, "conflict_resolved"

        return self.lookup(text, allow_fuzzy, actors)

    def resolve_conflict(self, text, unique_cands, interactive=True, context=""):
        norm_k = game_to_xuat(text).rstrip("\n")
        if norm_k in self.resolutions:
            chosen_val = self.resolutions[norm_k]
            for c in unique_cands:
                if c.val.strip() == chosen_val.strip():
                    return c
            return Entry(text, chosen_val, "resolved_session", 0)

        if not interactive:
            return unique_cands[0]

        print("\n" + "=" * 70)
        print(f"[!] TRANSLATION CONFLICT DETECTED {f'in {context}' if context else ''}")
        print("Japanese Line:")
        for line in text.strip().split("\n"):
            print(f"  {line}")
        print("\nCompeting Translations Found Across Project:")
        for idx, c in enumerate(unique_cands, 1):
            src_name = Path(c.src).name
            print(f"  [{idx}] {c.val}")
            print(f"      Source: {src_name}:{c.line} ({c.src})")
        print("=" * 70)

        while True:
            try:
                choice = input(f"Choose option [1-{len(unique_cands)}] (Enter = [1], '1a' = remember choice): ").strip()
            except (EOFError, KeyboardInterrupt):
                choice = "1"
            num_part = choice.rstrip("aA").strip()
            if not num_part:
                sel = 1
                break
            if num_part.isdigit() and 1 <= int(num_part) <= len(unique_cands):
                sel = int(num_part)
                break
            print(f"Please enter a number between 1 and {len(unique_cands)}.")

        chosen = unique_cands[sel - 1]
        self.resolutions[norm_k] = chosen.val
        self._save_resolutions()
        print(f"-> Selected [{sel}]: {chosen.val[:50]}...\n")
        return chosen

    def resolve_actor(self, name):
        if not name or not name.strip():
            return None
        e, _ = self.lookup(name.strip(), allow_fuzzy=False)
        if e and e.val.strip() and not looks_japanese(e.val.strip()):
            return e.val.strip()
        return None

    def _fuzzy(self, t):
        if len(t) < 6:
            return None
        pool = set(self._head.get(t[:3], ())) | set(self._tail.get(t[-3:], ()))
        lo, hi, best, score = len(t) * .75, len(t) * 1.3, None, self.fuzzy
        for c in list(pool)[:4000]:
            if not (lo <= len(c) <= hi):
                continue
            sm = SequenceMatcher(None, t, c)
            if sm.quick_ratio() < score:
                continue
            r = sm.ratio()
            if r > score:
                good = [h for h in self._tight[c] if h.val.strip()]
                if good:
                    best, score = good[0], r
        return best


# ---------------------------------------------------------------- status & cleanup
def generate_status_report(reports, out_dir):
    import datetime
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fully_translated = [r for r in reports if r['real_boxes'] > 0 and r['missing_real'] == 0]
    near_complete = [r for r in reports if r['missing_real'] in (1, 2) and r['hit_real'] > 0]
    missing_entirely = [r for r in reports if r['real_boxes'] > 0 and r['hit_real'] == 0 and r['missing_real'] > 0]
    partially_translated = [r for r in reports if r['missing_real'] > 2 and r['hit_real'] > 0]
    symbol_only = [r for r in reports if r['real_boxes'] == 0]

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    L = [
        "=" * 80,
        "                    PRICONNE STORY TRANSLATION STATUS REPORT",
        "=" * 80,
        f"Generated: {now_str}",
        f"Total Story Files: {len(reports)}",
        f"  - [1] FULLY TRANSLATED (100% complete - Repacked) : {len(fully_translated)}",
        f"  - [2] NEAR COMPLETE (Missing 1 or 2 lines)       : {len(near_complete)}",
        f"  - [3] IN PROGRESS (Partially translated)          : {len(partially_translated)}",
        f"  - [4] MISSING ENTIRELY (0% translated)            : {len(missing_entirely)}",
        f"  - [5] SYMBOLS / NO DIALOGUE                       : {len(symbol_only)}",
        "=" * 80,
        "",
        f"[1] FULLY TRANSLATED (100% Complete - Ready for Repack): {len(fully_translated)} file(s)",
        "-" * 80,
    ]
    for r in fully_translated:
        status_repack = "[REPACKED]" if r.get('repacked') else "[READY]"
        L.append(f"  {status_repack} {r['stem']:<20} ({r['hit_real']}/{r['real_boxes']} lines translated)")

    L.extend([
        "",
        f"[2] NEAR COMPLETE (Missing 1 or 2 lines): {len(near_complete)} file(s)",
        "-" * 80,
    ])
    for r in near_complete:
        L.append(f"  {r['stem']:<20} ({r['hit_real']}/{r['real_boxes']} lines - missing {r['missing_real']}) -> {r['stem']}.missing.txt")
        for m in r['missing_lines'][:2]:
            clean_m = m.replace('\n', ' ')
            L.append(f"      Missing: {clean_m[:60]}")

    L.extend([
        "",
        f"[3] MISSING ENTIRELY (Untranslated): {len(missing_entirely)} file(s)",
        "-" * 80,
    ])
    for r in missing_entirely:
        L.append(f"  {r['stem']:<20} (0/{r['real_boxes']} lines translated) -> {r['stem']}.missing.txt")

    if partially_translated:
        L.extend([
            "",
            f"[4] IN PROGRESS (Partially translated): {len(partially_translated)} file(s)",
            "-" * 80,
        ])
        for r in partially_translated:
            L.append(f"  {r['stem']:<20} ({r['hit_real']}/{r['real_boxes']} lines - missing {r['missing_real']})")

    report_text = "\n".join(L) + "\n"
    (out_dir / "_TRANSLATION_STATUS.txt").write_text(report_text, encoding="utf-8")

    summary_data = {
        "generated": now_str,
        "counts": {
            "total": len(reports),
            "fully_translated": len(fully_translated),
            "near_complete": len(near_complete),
            "partially_translated": len(partially_translated),
            "missing_entirely": len(missing_entirely),
            "symbol_only": len(symbol_only),
        },
        "files": {
            "fully_translated": [r['stem'] for r in fully_translated],
            "near_complete": [r['stem'] for r in near_complete],
            "missing_entirely": [r['stem'] for r in missing_entirely],
            "partially_translated": [r['stem'] for r in partially_translated],
        }
    }
    (out_dir / "_TRANSLATION_STATUS.json").write_text(json.dumps(summary_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_text


def prompt_xuat_cleanup(repacked_entries, log_dir=None, interactive=True):
    if not repacked_entries:
        return

    import datetime
    by_file = {}
    for e in repacked_entries:
        if e.src and Path(e.src).is_file():
            by_file.setdefault(e.src, []).append(e)

    if not by_file:
        return

    print("\n" + "=" * 70)
    print("                      XUAT CLEANUP / PRUNING")
    print("=" * 70)
    print(f"Repacking succeeded! {len(repacked_entries)} lines are now safely embedded directly")
    print(f"into your redirected .unity3d bundles.")
    print(f"These {len(repacked_entries)} lines can now be pruned from your XUAT files to avoid")
    print(f"redundancy, prevent cross-scene collisions, and reduce memory lag.")
    print(f"\nAffected XUAT translation files ({len(by_file)}):")
    for fpath, elist in list(by_file.items())[:10]:
        print(f"  - {Path(fpath).name}: {len(elist)} lines")
    if len(by_file) > 10:
        print(f"  ... and {len(by_file) - 10} more files")
    print("-" * 70)

    if interactive:
        try:
            ans = input("Prune these lines from XUAT files now? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = "n"
    else:
        ans = "n"

    if ans != "y":
        print("[cleanup] Skipped. XUAT translation files remain untouched.\n")
        return

    log_dir = Path(log_dir) if log_dir else Path(".")
    log_file = log_dir / "xuat_cleanup.log"
    backup_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = log_dir / "xuat_backups" / backup_timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    log_lines = [
        "=" * 80,
        f"XUAT PRUNING LOG - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Backup directory: {backup_dir.resolve()}",
        "=" * 80,
    ]

    pruned_count = 0
    try:
        import conflict_manager
    except ImportError:
        for sdir in [Path(__file__).parent, Path(__file__).parent / "priconne-adv-tools"]:
            if (sdir / "conflict_manager.py").exists() and str(sdir) not in sys.path:
                sys.path.insert(0, str(sdir))
        import conflict_manager

    for fpath, elist in by_file.items():
        src_path = Path(fpath)
        rel_backup = backup_dir / src_path.name
        bk_counter = 1
        while rel_backup.exists():
            rel_backup = backup_dir / f"{src_path.stem}_{bk_counter}{src_path.suffix}"
            bk_counter += 1
        rel_backup.write_bytes(src_path.read_bytes())

        fm = conflict_manager.FileModel(src_path)
        keys_to_prune = {conflict_manager.norm_key(e.key): e.val.strip() for e in elist}
        file_pruned = 0
        for entry in fm.entries:
            k = conflict_manager.norm_key(entry.key)
            if k in keys_to_prune:
                fm.delete_entry(entry)
                file_pruned += 1
                pruned_count += 1
                log_lines.append(f"PRUNED [{src_path.name}:{entry.start + 1}] {entry.key[:40]!r} = {entry.val[:40]!r}")

        if file_pruned > 0:
            fm.save()
            print(f"  [pruned] {src_path.name}: removed {file_pruned} lines (backup: {rel_backup.name})")

    with open(log_file, "a", encoding="utf-8") as lf:
        lf.write("\n".join(log_lines) + "\n\n")

    print(f"\n[cleanup complete] Pruned {pruned_count} lines across {len(by_file)} files.")
    print(f"  Backups: {backup_dir.resolve()}")
    print(f"  Log    : {log_file.resolve()}\n")