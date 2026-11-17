#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Priconne story / movie-subtitle bundle tool  (text format v2.1 - lossless)

  1 Extract  input/*.unity3d -> text/*.txt (story) / *.json (subtitle)
  2 Repack   input + text    -> output/*.unity3d   (verifies the WRITTEN bundle)
  3 Probe    shows the real control characters inside the script (diagnostic)
  4 Verify   checks a .txt round-trips byte-exactly, writes nothing

Story stream: record = u16be cmd_id, then (u32be len, bytes)*, terminated by len 0.
Arg bytes: invert every 3rd byte -> base64 -> UTF-8.
Because len 0 is the terminator, an EMPTY ARGUMENT CANNOT EXIST - the game omits it.

v2.1 text format: one argument = one physical line, always.
  \\ -> \\\\   LF -> \\n   CR -> \\r   TAB -> \\t   VT -> \\v   FF -> \\f
  NEL -> \\N   U+2028 -> \\L   U+2029 -> \\P
  trailing ASCII space -> \\s   trailing U+3000 -> \\S
  non-UTF-8 payload -> \\b64:....
  an argument equal to System/Motion/Effect -> \\System etc.
Blank lines between records are decoration and may be stripped safely.
Old (legacy) .txt files are still read on repack - auto-detected.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import struct
import sys
import warnings
from collections import Counter
from pathlib import Path

import asset_registry

try:
    import UnityPy
    import UnityPy.config
    warnings.filterwarnings("ignore")
except ImportError:
    import subprocess
    print("Installing UnityPy ...")
    if subprocess.call([sys.executable, "-m", "pip", "install",
                        "--only-binary=:all:", "UnityPy"]) != 0:
        v = f"{sys.version_info.major}.{sys.version_info.minor}"
        raise SystemExit(
            f"Could not install UnityPy on Python {v}.\n"
            "UnityPy needs Python 3.11 - 3.14 (newer versions have no prebuilt lz4 wheel).\n"
            "-> Install Python 3.13 from python.org (side by side) and run again.")
    import UnityPy
    import UnityPy.config

UnityPy.config.FALLBACK_UNITY_VERSION = "2021.3.20f1"
warnings.filterwarnings("ignore", category=DeprecationWarning)

COMMANDS = [
    "title", "outline", "chara", "visible", "type", "face", "focus", "background",
    "print", "tag", "goto", "bgm", "touch", "choice", "vo", "wait",
    "in_L", "in_R", "out_L", "out_R", "fadein", "fadeout", "in_float", "out_float",
    "jump", "shake", "pop", "nod", "question_right", "question_left", "se", "black_out",
    "black_in", "white_out", "white_in", "transition", "situation", "color_fadein", "flash", "shake_text",
    "text_size", "shake_screen", "double", "flower_y", "flower_r", "concent", "find_l", "find_r",
    "laugh_l", "laugh_r", "chord_l", "chord_r", "sweat_l", "sweat_r", "question_l", "question_r",
    "angry", "drop_l", "drop_r", "live", "scale", "title_telop", "window_visible", "log",
    "novoice", "attract", "change", "fadeout_all",
]
NAME2ID = {n: i for i, n in enumerate(COMMANDS)}
CATS = {"System", "Motion", "Effect"}
MOTION = set(range(16, 30)) | {60, 66}
EFFECT = set(range(43, 59))
HEADER = "#!priconne-story v2"
BREAK_RE = re.compile(r"\r\n|[\r\n\v\f\x85\u2028\u2029]")
BRK_CMDS = {"title", "outline", "type", "goto", "touch", "situation"}


class ToolError(Exception):
    """A problem with one file (reported as ERR, run continues)."""


class NotSupported(ToolError):
    """Nothing to do for this file (reported as skip)."""


def cname(cid):
    return COMMANDS[cid] if cid < len(COMMANDS) else f"unknown_{cid}"


def name2id(name):
    if name in NAME2ID:
        return NAME2ID[name]
    m = re.fullmatch(r"unknown_(\d+)", name) or re.fullmatch(r"(\d+)", name)
    if m:
        return int(m.group(1))
    raise ToolError(f"unknown command name {name!r}")


def _category(cid):
    return "Motion" if cid in MOTION else "Effect" if cid in EFFECT else "System"


# ------------------------------------------------------------ codec
def _invert3(b: bytes) -> bytes:
    o = bytearray(b)
    for i in range(0, len(o), 3):
        o[i] = ~o[i] & 0xFF
    return bytes(o)


def decode_arg(raw: bytes) -> str:
    inv = _invert3(raw)
    try:
        payload = base64.b64decode(inv, validate=True)
    except (binascii.Error, ValueError):
        payload = base64.b64decode(inv)
    return payload.decode("utf-8", "surrogateescape")


def encode_arg(text: str) -> bytes:
    return _invert3(base64.b64encode(text.encode("utf-8", "surrogateescape")))


def parse_story(data: bytes):
    recs, pos, n = [], 0, len(data)
    while pos < n:
        if pos + 2 > n:
            raise ToolError(f"story data: trailing bytes at {pos}")
        cid = struct.unpack_from(">H", data, pos)[0]
        pos += 2
        args = []
        while True:
            if pos + 4 > n:
                raise ToolError(f"story data: truncated at {pos}")
            ln = struct.unpack_from(">I", data, pos)[0]
            pos += 4
            if ln == 0:
                break
            if pos + ln > n:
                raise ToolError(f"story data: truncated arg at {pos}")
            args.append(data[pos:pos + ln])
            pos += ln
        recs.append([cid, args])
    return recs


# ------------------------------------------------------------ escaping (v2.1)
_ESC = {"\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\v": "\\v",
        "\f": "\\f", "\x85": "\\N", "\u2028": "\\L", "\u2029": "\\P"}
_UNESC = {v[1]: k for k, v in _ESC.items()}
_UNESC.update({"s": " ", "S": "\u3000"})
_ESC_RE = re.compile("[" + re.escape("".join(_ESC)) + "]")


def escape_arg(s: str) -> str:
    if any(0xDC80 <= ord(c) <= 0xDCFF for c in s):
        return "\\b64:" + base64.b64encode(s.encode("utf-8", "surrogateescape")).decode("ascii")
    out = _ESC_RE.sub(lambda m: _ESC[m.group()], s)
    m = re.search(r"[ \u3000]+$", out)
    if m:
        out = out[:m.start()] + "".join("\\s" if c == " " else "\\S" for c in m.group())
    return "\\" + out if out in CATS else out


def unescape_arg(line: str) -> str:
    if line.startswith("\\b64:"):
        return base64.b64decode(line[5:]).decode("utf-8", "surrogateescape")
    if line.startswith("\\") and line[1:] in CATS:
        return line[1:]
    out, i = [], 0
    while i < len(line):
        if line[i] == "\\" and i + 1 < len(line) and line[i + 1] in _UNESC:
            out.append(_UNESC[line[i + 1]])
            i += 2
        else:
            out.append(line[i])
            i += 1
    return "".join(out)


# ------------------------------------------------------------ text <-> records
def story_to_text(recs) -> str:
    """recs = [[cid, [str, ...]], ...]"""
    out = [HEADER]
    for cid, args in recs:
        out.append(cname(cid))
        out.extend(escape_arg(a) for a in args)
        out.append(_category(cid))
        out.append("")
    return "\r\n".join(out) + "\r\n"


def _norm_lines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def looks_v2(text: str) -> bool:
    if text.lstrip().startswith("#!priconne-story"):
        return True
    return bool(re.search(r"\\[nrtsvfnNLPS\\]|\\b64:", text))


def text_to_recs(text: str):
    lines = _norm_lines(text)
    i = 1 if lines and lines[0].startswith("#!") else 0
    recs = []
    while i < len(lines):
        if lines[i] == "":
            i += 1
            continue
        name = lines[i]
        i += 1
        cid = name2id(name)
        args = []
        while i < len(lines) and lines[i] not in CATS:
            args.append(unescape_arg(lines[i]))
            i += 1
        if i >= len(lines):
            raise ToolError(f"record #{len(recs)} '{name}' has no category line")
        i += 1
        recs.append([cid, args])
    if not recs:
        raise ToolError("no records parsed")
    return recs


def legacy_to_recs(text: str, orig):
    """Old layout. Blank lines inside a record = a break character that was eaten."""
    lines = _norm_lines(text)
    i, recs, warns = 0, [], []
    while i < len(lines):
        if lines[i] == "":
            i += 1
            continue
        name = lines[i]
        i += 1
        cid = name2id(name)
        args = []
        while i < len(lines) and lines[i] not in CATS:
            if lines[i] == "":
                if args and not (cname(cid) in ("focus", "print") and len(args) == 1):
                    args[-1] += "\n"
                else:
                    args.append("\n")
            else:
                args.append(lines[i])
            i += 1
        if i >= len(lines):
            raise ToolError(f"legacy record #{len(recs)} '{name}' has no category line")
        i += 1
        idx = len(recs)
        old = orig[idx] if idx < len(orig) and orig[idx][0] == cid else None
        k = len(old[1]) if old else len(args)
        if old and len(args) > k:
            head, pos = [], 0
            olddec = [decode_arg(b) for b in old[1]]
            for j in range(k - 1):
                want = max(1, min(olddec[j].count("\n") + 1, len(args) - pos - (k - 1 - j)))
                head.append("\n".join(args[pos:pos + want]))
                pos += want
            args = head + ["\n".join(args[pos:])]
            warns.append(f"rec {idx} '{name}': re-joined {len(args)} lines into {k} args")
        recs.append([cid, args])
    return recs, warns


def build_bytes(recs, orig, warns):
    """Unchanged args keep their ORIGINAL bytes -> byte-exact round-trip."""
    if len(recs) != len(orig):
        warns.append(f"record count changed: {len(orig)} -> {len(recs)}")
    out = bytearray()
    for idx, (cid, args) in enumerate(recs):
        old = orig[idx] if idx < len(orig) and orig[idx][0] == cid else None
        olddec = [decode_arg(b) for b in old[1]] if old else []
        out += struct.pack(">H", cid)
        for j, a in enumerate(args):
            if a == "":
                warns.append(f"rec {idx} '{cname(cid)}': empty arg {j} omitted")
                continue
            raw = old[1][j] if j < len(olddec) and olddec[j] == a else encode_arg(a)
            out += struct.pack(">I", len(raw)) + raw
        out += struct.pack(">I", 0)
    return bytes(out)


# ------------------------------------------------------------ bundle I/O
def _script_of(d):
    for attr in ("m_Script", "script", "text"):
        v = getattr(d, attr, None)
        if v is not None:
            return attr, v
    raise ToolError("TextAsset has no script field")


def load_bundle(path):
    try:
        env = UnityPy.load(str(path))
    except Exception as e:
        raise ToolError(f"cannot open as Unity bundle ({e.__class__.__name__}: {e})")
    story = sub = None
    for o in env.objects:
        try:
            if o.type.name == "TextAsset":
                d = o.read()
                nm = getattr(d, "m_Name", "") or ""
                if nm.startswith("storydata") or "story" in nm.lower():
                    story = o
            elif o.type.name == "MonoBehaviour":
                t = o.read_typetree()
                rl = t.get("recordList")
                if rl and isinstance(rl, list) and "text" in rl[0]:
                    sub = o
        except Exception:
            continue
    if story is not None:
        return env, "story", story
    if sub is not None:
        return env, "subtitle", sub
    raise NotSupported("no storydata TextAsset or subtitle recordList in this bundle")


def story_bytes(obj) -> bytes:
    _, s = _script_of(obj.read())
    return s.encode("utf-8", "surrogateescape") if isinstance(s, str) else bytes(s)


def save_bundle(env, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(env.file.save(packer="original"))


def write_story_verified(env, obj, data: bytes, out_path: Path):
    attr, cur = _script_of(obj.read())
    modes = ["str", "bytes"] if isinstance(cur, str) else ["bytes", "str"]
    last = None
    for mode in modes:
        d = obj.read()
        setattr(d, attr, data.decode("utf-8", "surrogateescape") if mode == "str" else data)
        d.save()
        save_bundle(env, out_path)
        try:
            _, kind2, obj2 = load_bundle(out_path)
            back = story_bytes(obj2) if kind2 == "story" else b""
        except Exception as e:
            last = f"cannot re-read output ({e!r})"
            continue
        if back == data:
            return mode
        last = f"written asset differs ({len(back)} bytes vs {len(data)})"
    try:
        out_path.unlink()
    except OSError:
        pass
    raise ToolError(f"write verification FAILED [{last}] - output discarded")


# ------------------------------------------------------------ subtitles
def sub_to_json(rl):
    return json.dumps([{"id": i + 1, "startTime": r["startTime"],
                        "endTime": r["endTime"], "text": r["text"]}
                       for i, r in enumerate(rl)], ensure_ascii=False, indent=2) + "\n"


def json_to_sub(text, rl):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ToolError(f"invalid JSON: {e}")
    if isinstance(data, dict):
        data = data.get("subtitles") or data.get("recordList") or data.get("records")
    if not isinstance(data, list):
        raise ToolError("subtitle json must be a list")
    if len(data) != len(rl):
        raise ToolError(f"subtitle count changed: {len(data)} vs {len(rl)}")
    for r, d in zip(rl, data):
        r["startTime"] = float(d.get("startTime", r["startTime"]))
        r["endTime"] = float(d.get("endTime", r["endTime"]))
        r["text"] = str(d["text"])
    return rl


def sub_to_text(rl):
    return "".join(f"{r['startTime']!r}\t{r['endTime']!r}\t{r['text']}\r\n" for r in rl)


def text_to_sub(text, rl):
    rows = [l for l in _norm_lines(text) if l != ""]
    if len(rows) != len(rl):
        raise ToolError(f"subtitle count changed: {len(rows)} vs {len(rl)}")
    for r, row in zip(rl, rows):
        st, en, tx = row.split("\t", 2)
        r["startTime"], r["endTime"], r["text"] = float(st), float(en), tx
    return rl


# ------------------------------------------------------------ naming / scan
LEGEND = """\
{name} full stem | {hash} before '-' | {id} after '-' | {default} storydata_{id}
{folder} {path} {kind} {index} {ext}      e.g. {index:04d}_{default}
Repack locates the translation with the EXTRACT pattern - keep it unchanged."""
SAMPLE = dict(name="a-b", ext="unity3d", folder="f", path="p", hash="a", id="b",
              kind="story", index=1, default="storydata_b")


def check_pattern(p):
    try:
        p.format(**SAMPLE)
        return True
    except (KeyError, IndexError, ValueError) as e:
        print(f"  Invalid pattern ({e!r}). See legend (option 8).")
        return False


def make_name(pattern, src: Path, root: Path, index: int, kind: str) -> str:
    stem = src.stem
    h, sep, rest = stem.partition("-")
    id_ = rest if sep else stem
    default = id_ if id_.startswith("storydata_") else "storydata_" + id_
    try:
        path = "_".join(src.parent.relative_to(root).parts)
    except ValueError:
        path = ""
    name = pattern.format(name=stem, ext=src.suffix.lstrip("."), folder=src.parent.name,
                          path=path, hash=h if sep else "", id=id_, kind=kind,
                          index=index, default=default)
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or stem


def scan(src: Path, recursive: bool, exclude):
    src = src.resolve()
    if not src.exists():
        src.mkdir(parents=True)
        print(f"Created folder '{src}'. Put .unity3d files in it and run again.")
        return src, []
    if src.is_file():
        print(f"Scanning: single file {src}")
        return src.parent, [src]
    excl = [e.resolve() for e in exclude]
    it = src.rglob("*") if recursive else src.iterdir()
    files = sorted(p for p in it if p.is_file() and p.suffix.lower() == ".unity3d"
                   and not any(e in p.parents for e in excl))
    print(f"Scanning: {src}")
    print(f"  Subfolders: {'ON' if recursive else 'OFF'}  |  found {len(files)} file(s)")
    return src, files


def rel_sub(f, root, mirror):
    return f.parent.relative_to(root) if mirror else Path()


def unique_path(p: Path, used: set) -> Path:
    q, n = p, 2
    while q in used:
        q = p.with_name(f"{p.stem}_{n}{p.suffix}")
        n += 1
    used.add(q)
    return q


class Stats:
    def __init__(self):
        self.ok, self.skipped, self.failed, self.warned = 0, [], [], []

    def run(self, tag, fn):
        try:
            msg, warns = fn()
            self.ok += 1
            print(f"  [ok]   {tag}  {msg or ''}")
            for w in warns or []:
                self.warned.append(f"{tag}: {w}")
        except NotSupported as e:
            self.skipped.append((tag, str(e)))
            print(f"  [skip] {tag}: {e}")
        except ToolError as e:
            self.failed.append((tag, str(e)))
            print(f"  [ERR]  {tag}: {e}")
        except Exception as e:
            self.failed.append((tag, repr(e)))
            print(f"  [ERR]  {tag}: {e!r}")

    def report(self, log: Path):
        print(f"\nSummary: {self.ok} ok, {len(self.skipped)} skipped, "
              f"{len(self.failed)} failed, {len(self.warned)} warning(s).")
        lines = ([f"WARN {w}" for w in self.warned]
                 + [f"SKIP {t}: {m}" for t, m in self.skipped]
                 + [f"ERR  {t}: {m}" for t, m in self.failed])
        if lines:
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"Details -> {log}")


LOG_PATH = Path(__file__).with_name("priconne_tool.log")


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig", newline="")


def find_translation(tl_root, f, root, kind, cfg, index):
    sub = rel_sub(f, root, cfg["mirror"])
    stems = [make_name(cfg["extract_name"], f, root, index, kind), f.stem]
    exts = [".txt"] if kind == "story" else [".json", ".txt"]
    for d in [tl_root / sub] + ([tl_root] if sub != Path() else []):
        for s in stems:
            for e in exts:
                if (d / (s + e)).exists():
                    return d / (s + e)
    return None


def _read_recs(text, orig, cfg, warns):
    if cfg["format"] == "legacy" or (cfg["format"] == "auto" and not looks_v2(text)):
        recs, w = legacy_to_recs(text, orig)
        warns += w + ["LEGACY format read - re-extract to get a lossless v2 file"]
        return recs
    return text_to_recs(text)


# ------------------------------------------------------------ commands
def run_extract(cfg):
    out = Path(cfg["text"]).resolve()
    root, files = scan(Path(cfg["input"]), cfg["recursive"], [out, Path(cfg["output"])])
    print(f"Extracting to: {out}\n")
    st, used = Stats(), set()
    for i, f in enumerate(files, 1):
        def job():
            _, kind, obj = load_bundle(f)
            warns = []
            if kind == "story":
                raw = story_bytes(obj)
                orig = parse_story(raw)
                recs = [[cid, [decode_arg(a) for a in args]] for cid, args in orig]
                text = story_to_text(recs)
                if build_bytes(text_to_recs(text), orig, warns) != raw:
                    raise ToolError("v2 round-trip is not byte-exact - NOT written")
                nlf = sum(1 for _, a in recs for s in a if BREAK_RE.search(s))
                msg, ext = f"story {len(recs)} recs, {nlf} arg(s) with a line break", ".txt"
            else:
                text, msg, ext = sub_to_json(obj.read_typetree()["recordList"]), "subtitle", ".json"
            stem = make_name(cfg["extract_name"], f, root, i, kind)
            p = unique_path(out / rel_sub(f, root, cfg["mirror"]) / (stem + ext), used)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="")
            return f"{msg} -> {p.relative_to(out)}", warns
        st.run(str(f.relative_to(root)), job)
    st.report(LOG_PATH)


def run_repack(cfg):
    tl_root, out = Path(cfg["text"]).resolve(), Path(cfg["output"]).resolve()
    root, files = scan(Path(cfg["input"]), cfg["recursive"], [tl_root, out])

    # P1: Check against RedirectedResources before repacking
    ws = _get_workspace(cfg)
    strategy_name = cfg.get("naming_strategy", "auto_redirect")
    try:
        strat = asset_registry.NamingStrategy(strategy_name)
    except ValueError:
        strat = asset_registry.NamingStrategy.AUTO_REDIRECT

    reproc_raw = cfg.get("reprocess", "")
    reprocess_keys = set(x.strip().lower() for x in (reproc_raw.split(",") if isinstance(reproc_raw, str) else reproc_raw) if x.strip())
    scanner = asset_registry.PreConversionScanner(
        workspace=ws,
        strategy=strat,
        custom_pattern=cfg.get("repack_name", "{default}"),
        reprocess_keys=reprocess_keys
    )
    candidates = scanner.scan_candidates(files, input_root=root)
    print("\n" + scanner.render_summary(candidates) + "\n")

    if cfg.get("preview_only"):
        print("[preview-only] Scan complete. Halting before repack as requested.")
        return

    print(f"Translations from: {tl_root}\nWriting to: {out}\n")
    st, used = Stats(), set()
    skip_existing = cfg.get("skip_existing", True)
    cand_map = {c.identity.file_path: c for c in candidates}

    for i, f in enumerate(files, 1):
        cand = cand_map.get(f.resolve())
        if skip_existing and cand and cand.action == "SKIP":
            def skip_job():
                return f"[SKIP] {cand.reason}", []
            st.run(str(f.relative_to(root)), skip_job)
            continue

        def job():
            env, kind, obj = load_bundle(f)
            tl = find_translation(tl_root, f, root, kind, cfg, i)
            if tl is None:
                raise NotSupported("no translation file found")
            text, warns = read_text(tl), []
            out_target_name = cand.proposed_filename if cand else (make_name(cfg["repack_name"], f, root, i, kind) + f.suffix)
            p = unique_path(out / rel_sub(f, root, cfg["mirror"]) / out_target_name, used)
            if kind == "story":
                if tl.suffix.lower() == ".json":
                    raise ToolError("story bundles use .txt")
                raw = story_bytes(obj)
                orig = parse_story(raw)
                recs = _read_recs(text, orig, cfg, warns)
                if not cfg["allow_struct"] and len(recs) != len(orig):
                    raise ToolError(f"record count {len(orig)} -> {len(recs)} "
                                    f"(use --allow-struct to override)")
                data = build_bytes(recs, orig, warns)
                if data == raw:
                    save_bundle(env, p)
                    return f"<- {tl.name} (unchanged) -> {p.name}", warns
                mode = write_story_verified(env, obj, data, p)
                return f"<- {tl.name} [{mode}, verified] -> {p.name}", warns
            t = obj.read_typetree()
            conv = json_to_sub if tl.suffix.lower() == ".json" else text_to_sub
            t["recordList"] = conv(text, t["recordList"])
            obj.save_typetree(t)
            save_bundle(env, p)
            return f"<- {tl.name} -> {p.name}", warns
        st.run(str(f.relative_to(root)), job)
    st.report(LOG_PATH)


def run_verify(cfg):
    tl_root = Path(cfg["text"]).resolve()
    root, files = scan(Path(cfg["input"]), cfg["recursive"], [tl_root])
    st = Stats()
    for i, f in enumerate(files, 1):
        def job():
            _, kind, obj = load_bundle(f)
            if kind != "story":
                raise NotSupported("subtitle: nothing to verify")
            tl = find_translation(tl_root, f, root, kind, cfg, i)
            if tl is None:
                raise NotSupported("no .txt found")
            raw = story_bytes(obj)
            orig = parse_story(raw)
            warns = []
            recs = _read_recs(read_text(tl), orig, cfg, warns)
            data = build_bytes(recs, orig, warns)
            if data != raw:
                o, n = parse_story(raw), parse_story(data)
                w = next((k for k in range(min(len(o), len(n))) if o[k] != n[k]), None)
                raise ToolError(f"NOT byte-exact (first diff at record {w})")
            return f"byte-exact, {len(recs)} records", warns
        st.run(str(f.relative_to(root)), job)
    st.report(LOG_PATH)


def run_probe(cfg):
    out = Path(cfg["text"]).resolve() / "_probe"
    root, files = scan(Path(cfg["input"]), cfg["recursive"], [])
    st, total = Stats(), Counter()
    for i, f in enumerate(files, 1):
        def job():
            _, kind, obj = load_bundle(f)
            if kind != "story":
                raise NotSupported("subtitle bundle")
            orig = parse_story(story_bytes(obj))
            dec = [[cid, [decode_arg(a) for a in args]] for cid, args in orig]
            c, body = Counter(), []
            for idx, (cid, args) in enumerate(dec):
                for s in args:
                    for ch in s:
                        if ord(ch) < 32 or ord(ch) in (0x85, 0x2028, 0x2029):
                            c[f"U+{ord(ch):04X}"] += 1
                    if s in CATS:
                        c["arg_equals_category"] += 1
                    if s.endswith(" "):
                        c["arg_trailing_space"] += 1
                    if any(0xDC80 <= ord(x) <= 0xDCFF for x in s):
                        c["arg_non_utf8"] += 1
                body.append(f"[{idx:04d}] {cname(cid)} argc={len(args)}")
                body += [f"    {j}: {s!r}" for j, s in enumerate(args)]
            boxes, cur, voice = [], None, ""
            for cid, args in dec:
                nm = cname(cid)
                if nm == "touch" and args:
                    voice = args[0]
                if nm == "focus":
                    sp = args[0] if args else ""
                    tx = args[1] if len(args) > 1 else ""
                    if cur is None or cur[0] != sp:
                        cur = [sp, "", voice]
                        boxes.append(cur)
                    cur[1] += BREAK_RE.sub("\n", tx)
                elif nm in BRK_CMDS:
                    cur = None
            keys = [f"{sp}\t{tx if tx.endswith(chr(10)) else tx + chr(10)}"
                    for sp, tx, vc in boxes if tx.strip()]
            total.update(c)
            p = out / rel_sub(f, root, cfg["mirror"])
            p.mkdir(parents=True, exist_ok=True)
            (p / (f.stem + ".probe.txt")).write_text("\n".join(body) + "\n", encoding="utf-8")
            (p / (f.stem + ".keys.txt")).write_text("\n".join(keys) + "\n", encoding="utf-8")
            info = ", ".join(f"{k}={v}" for k, v in sorted(c.items())) or "NONE"
            print(f"         control chars: {info}   |   {len(boxes)} dialogue boxes")
            return f"{len(orig)} recs -> _probe/{f.stem}.probe.txt / .keys.txt", []
        st.run(str(f.relative_to(root)), job)
    st.report(LOG_PATH)
    print("\nTOTAL control chars:", dict(total) or "NONE")
    print("(U+000D = CR, U+000A = LF.  NONE means the breaks are added by the game engine.)")


# ------------------------------------------------------------ auto-translate
def _get_workspace(cfg) -> asset_registry.BepInExWorkspace:
    target = cfg.get("bepinex_root") or cfg.get("project") or ""
    if not target or not Path(target).exists():
        for bat in [Path(__file__).parent / "adv_paths.bat",
                    Path(__file__).parent / "priconne-adv-tools" / "adv_paths.bat",
                    Path(r"c:\[Gacha]\priconne-adv-tools\adv_paths.bat")]:
            if bat.exists():
                for line in bat.read_text("utf-8", errors="replace").splitlines():
                    if line.startswith('set "PROJECT=') and line.endswith('"'):
                        pval = line[len('set "PROJECT='):-1].strip()
                        if pval and Path(pval).exists():
                            target = pval
                            break
                if target:
                    break
    ws = asset_registry.BepInExWorkspace.resolve(target)
    if not ws.xuat_text_dir or not ws.xuat_text_dir.exists():
        target = ask("BepInEx or XUAT Translation folder", target or r"C:\[Gacha]\PriconneRe-TL\src\BepInEx")
        ws = asset_registry.BepInExWorkspace.resolve(target)
        if ws.bepinex_root:
            cfg["bepinex_root"] = str(ws.bepinex_root)
        if ws.xuat_text_dir:
            cfg["project"] = str(ws.xuat_text_dir)
        save_settings(cfg)
    return ws


def _get_store(cfg):
    ws = _get_workspace(cfg)
    proj = str(ws.xuat_text_dir) if ws.xuat_text_dir and ws.xuat_text_dir.exists() else cfg.get("project")
    if not proj or not Path(proj).exists():
        raise ToolError(f"Project XUAT folder not found: {proj}")

    for d in [Path(__file__).parent / "priconne-adv-tools", Path(__file__).parent, Path(r"c:\[Gacha]\priconne-adv-tools")]:
        if (d / "advscript.py").exists() and str(d) not in sys.path:
            sys.path.insert(0, str(d))
    import advscript
    print(f"\nLoading XUAT translations strictly from Text workspace: {proj}")
    store = advscript.Store().load([proj])
    print(f"Loaded {len(store.exact):,} entries into memory.")
    return store, advscript, ws


def run_autotranslate(cfg):
    """1-Click Pipeline: input/*.unity3d -> Inject XUAT translations -> output/*.unity3d + text/*.txt"""
    store, advscript, ws = _get_store(cfg)
    tl_root, out = Path(cfg["text"]).resolve(), Path(cfg["output"]).resolve()
    root, files = scan(Path(cfg["input"]), cfg["recursive"], [tl_root, out])

    # P1: Pre-conversion scanning and duplicate detection against RedirectedResources
    strategy_name = cfg.get("naming_strategy", "auto_redirect")
    try:
        strat = asset_registry.NamingStrategy(strategy_name)
    except ValueError:
        strat = asset_registry.NamingStrategy.AUTO_REDIRECT

    reproc_raw = cfg.get("reprocess", "")
    reprocess_keys = set(x.strip().lower() for x in (reproc_raw.split(",") if isinstance(reproc_raw, str) else reproc_raw) if x.strip())
    scanner = asset_registry.PreConversionScanner(
        workspace=ws,
        strategy=strat,
        custom_pattern=cfg.get("repack_name", "{default}"),
        reprocess_keys=reprocess_keys
    )
    candidates = scanner.scan_candidates(files, input_root=root)
    print("\n" + scanner.render_summary(candidates) + "\n")

    if cfg.get("preview_only"):
        print("[preview-only] Scan complete. Halting before conversion as requested.")
        return

    print(f"Injecting XUAT & Repacking eligible bundle(s) from: {Path(cfg['input']).resolve()}")
    print(f"Repacked bundles -> {out}\nTranslated scripts -> {tl_root}\n")

    st, used = Stats(), set()
    file_reports = []
    repacked_entries = []
    skip_existing = cfg.get("skip_existing", True)
    cand_map = {c.identity.file_path: c for c in candidates}

    for i, f in enumerate(files, 1):
        cand = cand_map.get(f.resolve())
        if skip_existing and cand and cand.action == "SKIP":
            def skip_job():
                return f"[SKIP] {cand.reason}", []
            st.run(str(f.relative_to(root)), skip_job)
            continue

        def job():
            env, kind, obj = load_bundle(f)
            if kind != "story":
                raise NotSupported("subtitle bundle (auto-translate supports story scripts)")
            orig_raw = story_bytes(obj)
            orig_recs = parse_story(orig_raw)
            recs_extracted = [[cid, [decode_arg(a) for a in args]] for cid, args in orig_recs]
            raw_text = story_to_text(recs_extracted)

            stem = cand.identity.stem if cand else make_name(cfg["extract_name"], f, root, i, kind)
            txt_path = unique_path(tl_root / rel_sub(f, root, cfg["mirror"]) / (stem + ".txt"), set())
            txt_path.parent.mkdir(parents=True, exist_ok=True)
            txt_path.write_text(raw_text, encoding="utf-8", newline="")

            doc = advscript.Document(txt_path)
            aset = set(doc.actors())
            hit, hit_real, miss, punct, missing, miss_names = 0, 0, 0, 0, [], []
            file_used_entries = []
            for k, (b_idx, b) in enumerate(doc.items):
                jp = advscript.box_key(b, "auto")
                po = advscript.is_punct_only(jp)
                e, lvl = store.lookup_resolved(jp, allow_fuzzy=False, actors=aset, interactive=True, context=f"{f.name}#{b_idx:03d}")
                if e:
                    hit += 1
                    if not po:
                        hit_real += 1
                    file_used_entries.append(e)
                    advscript.inject(doc, b, e.val, "first", " ")
                elif po:
                    punct += 1
                else:
                    miss += 1
                    missing.append((b_idx, b.voice, b.speaker, jp))

            for actor in doc.actors():
                resolved = store.resolve_actor(actor)
                if resolved:
                    doc.rename_speaker(actor, resolved)
                else:
                    miss_names.append(actor)

            doc.save(txt_path)
            if missing or miss_names:
                miss_path = txt_path.with_name(stem + ".missing.txt")
                advscript.write_clean(miss_path, miss_names, [m[3] for m in missing])

            missing_real = [m for m in missing if not advscript.is_punct_only(m[3])]
            real_boxes_count = len([b for _, b in doc.items if not advscript.is_punct_only(advscript.box_key(b, "auto"))])
            is_complete = (len(missing_real) == 0 and real_boxes_count > 0)
            was_repacked = False
            warns = []

            if not is_complete:
                file_reports.append({
                    "stem": stem,
                    "file": str(f),
                    "total_boxes": len(doc.items),
                    "real_boxes": real_boxes_count,
                    "hit_real": hit_real,
                    "missing_real": len(missing_real),
                    "missing_lines": [m[3] for m in missing_real],
                    "missing_names": miss_names,
                    "repacked": False,
                })
                return f"[SKIP REPACK: incomplete ({len(missing_real)} line(s) missing)] {hit}/{len(doc.items)} translated -> {txt_path.name}", warns

            trans_recs = _read_recs(txt_path.read_text(encoding="utf-8"), orig_recs, cfg, [])
            new_data = build_bytes(trans_recs, orig_recs, warns)
            out_target_name = cand.proposed_filename if cand else (make_name(cfg["repack_name"], f, root, i, kind) + f.suffix)
            out_bundle_path = unique_path(out / rel_sub(f, root, cfg["mirror"]) / out_target_name, used)
            mode = write_story_verified(env, obj, new_data, out_bundle_path)
            was_repacked = True
            repacked_entries.extend(file_used_entries)

            file_reports.append({
                "stem": stem,
                "file": str(f),
                "total_boxes": len(doc.items),
                "real_boxes": real_boxes_count,
                "hit_real": hit_real,
                "missing_real": len(missing_real),
                "missing_lines": [m[3] for m in missing_real],
                "missing_names": miss_names,
                "repacked": was_repacked,
            })
            status_msg = f"{hit}/{len(doc.items)} lines [{mode}] -> {out_bundle_path.name}"
            return status_msg, warns

        st.run(str(f.relative_to(root)), job)
    st.report(LOG_PATH)

    if file_reports:
        rep_text = advscript.generate_status_report(file_reports, out)
        print("\n" + rep_text)

    if repacked_entries:
        advscript.prompt_xuat_cleanup(repacked_entries, out, interactive=True)


def run_translate_raw(cfg):
    """Inject XUAT translations into raw scripts in text/*.txt -> save in place / report gaps"""
    store, advscript = _get_store(cfg)
    txt_root = Path(cfg["text"]).resolve()
    files = sorted(txt_root.rglob("*.txt") if cfg["recursive"] else txt_root.glob("*.txt"))
    files = [f for f in files if not f.name.endswith((".missing.txt", ".report.txt", ".xuat.txt", ".probe.txt", ".keys.txt"))]
    print(f"\nInjecting XUAT into {len(files)} raw script(s) in: {txt_root}\n")
    st = Stats()
    file_reports = []

    for i, f in enumerate(files, 1):
        def job():
            doc = advscript.Document(f)
            aset = set(doc.actors())
            hit, hit_real, miss, punct, missing, miss_names = 0, 0, 0, 0, [], []
            for k, (b_idx, b) in enumerate(doc.items):
                jp = advscript.box_key(b, "auto")
                po = advscript.is_punct_only(jp)
                e, lvl = store.lookup_resolved(jp, allow_fuzzy=False, actors=aset, interactive=True, context=f"{f.name}#{b_idx:03d}")
                if e:
                    hit += 1
                    if not po:
                        hit_real += 1
                    advscript.inject(doc, b, e.val, "first", " ")
                elif po:
                    punct += 1
                else:
                    miss += 1
                    missing.append((b_idx, b.voice, b.speaker, jp))

            for actor in doc.actors():
                resolved = store.resolve_actor(actor)
                if resolved:
                    doc.rename_speaker(actor, resolved)
                else:
                    miss_names.append(actor)

            doc.save(f)
            if missing or miss_names:
                advscript.write_clean(f.with_name(f.stem + ".missing.txt"), miss_names, [m[3] for m in missing])

            missing_real = [m for m in missing if not advscript.is_punct_only(m[3])]
            real_boxes_count = len([b for _, b in doc.items if not advscript.is_punct_only(advscript.box_key(b, "auto"))])
            file_reports.append({
                "stem": f.stem,
                "file": str(f),
                "total_boxes": len(doc.items),
                "real_boxes": real_boxes_count,
                "hit_real": hit_real,
                "missing_real": len(missing_real),
                "missing_lines": [m[3] for m in missing_real],
                "missing_names": miss_names,
                "repacked": False,
            })

            msg = f"{hit}/{len(doc.items)} translated" + (f" ({miss} missing)" if miss else "")
            return msg, doc.warnings

        st.run(str(f.relative_to(txt_root)), job)
    st.report(LOG_PATH)

    if file_reports:
        rep_text = advscript.generate_status_report(file_reports, txt_root)
        print("\n" + rep_text)


def run_dataminer(cfg):
    """Launch Universal Data Miner & Database Explorer interface"""
    from NewDataMiner.cli import interactive_menu
    from NewDataMiner.dataminer import DataMiner
    dm = DataMiner()
    interactive_menu(dm)


def run_integrated_workflow(cfg, initial_query=None):
    """
    P5: Complete Integrated Workflow
    Database -> Resource Discovery -> Targeted Data Mining -> Unity3D Asset Identification -> Unity3D-to-XUAT Conversion -> Redirected Resource Validation
    """
    from NewDataMiner.dataminer import DataMiner
    from NewDataMiner.models import AssetCategory
    from NewDataMiner.resource_cross_ref import DiscoveryStatus

    dm = DataMiner()
    dm.manifest_manager.load_manifests()

    ws = _get_workspace(cfg)
    redir_index = asset_registry.RedirectIndex(ws.redirected_resources_dir) if ws.redirected_resources_dir else None

    print("\n" + "=" * 80)
    print("        PRICONNE INTEGRATED WORKFLOW (DB -> MINE -> XUAT -> REDIRECT)")
    print("================================================================================")
    print("Pipeline: Database -> Manifest Discovery -> Safe Mining -> XUAT Repack -> Redirection")
    print("=" * 80)

    query = initial_query or input("\nEnter Story or Unit search query (ID, title, character name): ").strip()
    if not query:
        return

    # 1. Database & Cross-Referenced Discovery
    print(f"\n[Step 1: Database Discovery] Searching for '{query}'...")
    stories = dm.discover_stories(query)
    units = dm.discover_units(query) if not stories else []
    candidates = stories or units

    if not candidates:
        print("[!] No records found in database or manifests.")
        return

    print("\nDiscovered Candidates:")
    for idx, cand in enumerate(candidates[:15], 1):
        print(f"  {idx}. [{cand.entity_type.upper()}] {cand.entity_id} - {cand.title} ({len(cand.matched_entries)} assets) [{cand.status.value}]")

    if len(candidates) == 1:
        selected_res = candidates[0]
        print(f"\nAuto-selected sole match: {selected_res.title}")
    else:
        sel = input(f"\nSelect entry # (1-{min(len(candidates), 15)}) to process [default: 1]: ").strip()
        selected_idx = int(sel) - 1 if sel.isdigit() and 1 <= int(sel) <= min(len(candidates), 15) else 0
        selected_res = candidates[selected_idx]

    # Filter target story bundles
    story_entries = [e for e in selected_res.matched_entries if e.name.endswith(".unity3d") and "storydata" in e.name]
    if not story_entries:
        story_entries = [e for e in selected_res.matched_entries if e.name.endswith(".unity3d")]
        if not story_entries:
            print(f"[!] No Unity3D bundles found for '{selected_res.title}'.")
            return

    target_entry = story_entries[0]
    print(f"\n[Step 2: Redirection & Duplicate Check] Target: {target_entry.name}")

    # Check against BepInEx RedirectedResources
    already_done = False
    if redir_index:
        ident = asset_registry.AssetIdentity.from_path(target_entry.name)
        if redir_index.contains(ident):
            already_done = True
            existing = redir_index.find_match(ident)
            existing_fn = existing.path.name if existing else target_entry.name
            print(f"  [!] Asset '{existing_fn}' is ALREADY IMPLEMENTED in RedirectedResources!")
            force = input("  Force reprocess and download fresh copy? [y/N]: ").strip().lower()
            if force != "y":
                print("  Skipping conversion as asset is already implemented in project patch.")
                return

    # 3. Targeted Mining (Download to input/)
    input_dir = Path(cfg["input"]).resolve()
    input_dir.mkdir(parents=True, exist_ok=True)
    target_file = input_dir / target_entry.name

    if not target_file.exists() or already_done:
        print(f"\n[Step 3: Targeted Mining] Downloading {target_entry.name} ({target_entry.human_size})...")
        downloaded = dm.download_targets([target_entry], dest_dir=input_dir, confirm=False)
        if not downloaded:
            print("[!] Download failed or aborted.")
            return
    else:
        print(f"\n[Step 3: Targeted Mining] Using existing local copy in: {target_file}")

    # 4. Unity3D-to-XUAT Conversion, Injection & Gated Repack
    print(f"\n[Step 4: XUAT Translation & Gated Repack] Processing {target_entry.name}...")
    temp_cfg = dict(cfg)
    temp_cfg["input"] = str(input_dir)
    temp_cfg["reprocess"] = [target_entry.name, target_entry.name.replace(".unity3d", "")]
    run_autotranslate(temp_cfg)


# ------------------------------------------------------------ settings / menu
SETTINGS_PATH = Path(__file__).with_name("priconne_tool_settings.json")
DEFAULTS = dict(input="input", text="text", output="output", project="",
                bepinex_root="", naming_strategy="auto_redirect", skip_existing=True,
                reprocess="", preview_only=False,
                recursive=False, mirror=True,
                extract_name="{name}", repack_name="{default}", format="auto",
                allow_struct=False)
RUNNERS = {"extract": run_extract, "repack": run_repack,
           "xuat-repack": run_autotranslate, "xuat": run_autotranslate,
           "autotranslate": run_autotranslate, "translate": run_autotranslate,
           "xuat-raw": run_translate_raw, "translate-raw": run_translate_raw,
           "probe": run_probe, "verify": run_verify,
           "mine": run_dataminer, "dataminer": run_dataminer,
           "workflow": run_integrated_workflow}


def load_settings():
    cfg = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            cfg.update({k: v for k, v in json.loads(SETTINGS_PATH.read_text("utf-8")).items()
                        if k in DEFAULTS})
        except Exception:
            pass
    return cfg


def save_settings(cfg):
    try:
        SETTINGS_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except OSError:
        pass


def ask(label, cur):
    return input(f"  {label} [{cur}] (Enter = keep): ").strip().strip('"') or cur


def menu(cfg):
    while True:
        onoff = lambda b: "ON" if b else "OFF"
        ws = asset_registry.BepInExWorkspace.resolve(cfg.get("bepinex_root") or cfg.get("project"))
        redir_str = str(ws.redirected_resources_dir) if ws.redirected_resources_dir and ws.redirected_resources_dir.exists() else "(not found)"
        print("\n==========================================")
        print("     PRICONNE STORY TOOL  v2.5 (INTEGRATED)")
        print("==========================================")
        print(f" Input  bundle : {Path(cfg['input']).resolve()}")
        print(f" Text   folder : {Path(cfg['text']).resolve()}")
        print(f" Output bundle : {Path(cfg['output']).resolve()}")
        print(f" BepInEx Root  : {ws.bepinex_root or '(not set)'}")
        print(f" RedirectedRes : {redir_str}")
        print(f" XUAT Text     : {ws.xuat_text_dir or '(not set)'}")
        print(f" Naming Style  : {cfg.get('naming_strategy', 'auto_redirect')}   Skip Duplicates: {onoff(cfg.get('skip_existing', True))}")
        print(f" Subfolders: {onoff(cfg['recursive'])}   Mirror: {onoff(cfg['mirror'])}"
              f"   Format: {cfg['format']}")
        print(f" Extract name: {cfg['extract_name']}   Repack name: {cfg['repack_name']}")
        print("\n 1. Extract            (input .unity3d -> text/*.txt)")
        print(" 2. Repack             (input .unity3d + text/*.txt -> output/*.unity3d)")
        print(" 3. XUAT -> Repack     (input .unity3d + XUAT -> output/*.unity3d) [1-STEP]")
        print(" 4. XUAT -> Raw text   (text/*.txt + XUAT -> translated text/*.txt)")
        print(" 5. Probe              (show real line-break characters)")
        print(" 6. Verify             (byte-exact check, writes nothing)")
        print(" 7. Toggle scan subfolders")
        print(" 8. Toggle mirror subfolders")
        print(" 9. Toggle skip duplicates in RedirectedResources")
        print(" 10. Set naming strategy")
        print(" 11. Set folders & BepInEx root")
        print(" 12. Set rename patterns / show legend")
        print(" 13. Universal Data Miner (Search, Audio, Movies & DB)")
        print(" 14. Integrated Workflow  (DB -> Mine -> XUAT -> Repack)")
        print(" 0. Exit")
        c = input("\nChoose: ").strip()
        if c == "0":
            return
        if c in ("1", "2", "3", "4", "5", "6"):
            runner_keys = ["extract", "repack", "xuat-repack", "xuat-raw", "probe", "verify"]
            RUNNERS[runner_keys[int(c) - 1]](cfg)
        elif c == "13":
            RUNNERS["mine"](cfg)
        elif c == "14":
            RUNNERS["workflow"](cfg)
        elif c == "7":
            cfg["recursive"] = not cfg["recursive"]
        elif c == "8":
            cfg["mirror"] = not cfg["mirror"]
        elif c == "9":
            cfg["skip_existing"] = not cfg.get("skip_existing", True)
            print(f"Skip Duplicates is now: {'ON' if cfg['skip_existing'] else 'OFF'}")
        elif c == "10":
            print("\nNaming Strategies:")
            print("  1. auto_redirect    (default: <folder>_<basename> or storydata_<basename>)")
            print("  2. preserve_original (keeps raw input basename)")
            print("  3. match_existing   (adopts matching filename in RedirectedResources)")
            print("  4. custom_pattern   (uses repack_name pattern tokens)")
            sc = input("Select [1-4] (Enter=keep): ").strip()
            strats = {"1": "auto_redirect", "2": "preserve_original", "3": "match_existing", "4": "custom_pattern"}
            if sc in strats:
                cfg["naming_strategy"] = strats[sc]
                print(f"Naming strategy set to: {cfg['naming_strategy']}")
        elif c == "11":
            for k, lbl in (("input", "Input folder"), ("text", "Text folder"),
                           ("output", "Output folder"), ("bepinex_root", "BepInEx Root folder"),
                           ("project", "XUAT Project / Text folder")):
                cfg[k] = ask(lbl, cfg.get(k, ""))
        elif c == "12":
            print("\n" + LEGEND + "\n")
            for k in ("extract_name", "repack_name"):
                v = ask(k, cfg[k])
                if check_pattern(v):
                    cfg[k] = v
        else:
            print("Invalid choice.")
            continue
        save_settings(cfg)


def main():
    ap = argparse.ArgumentParser(description="Run with no arguments for the menu.")
    ap.add_argument("mode", nargs="?", choices=list(RUNNERS))
    ap.add_argument("-i", "--input")
    ap.add_argument("-t", "--text")
    ap.add_argument("-o", "--output")
    ap.add_argument("-p", "--project")
    ap.add_argument("--bepinex", help="BepInEx root directory")
    ap.add_argument("--naming-strategy", choices=["auto_redirect", "preserve_original", "match_existing", "custom_pattern"])
    ap.add_argument("--reprocess", nargs="*", default=[], help="specific asset names/stems to force reprocess")
    ap.add_argument("--skip-existing", dest="skip_existing", action="store_true", default=None)
    ap.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    ap.add_argument("--preview", dest="preview_only", action="store_true", help="scan and show preview without converting")
    ap.add_argument("-r", "--recursive", action="store_true")
    ap.add_argument("--flat", action="store_true")
    ap.add_argument("--extract-name")
    ap.add_argument("--repack-name")
    ap.add_argument("--format", choices=["auto", "v2", "legacy"])
    ap.add_argument("--allow-struct", action="store_true")
    ap.add_argument("-q", "--query", help="initial search query for workflow or dataminer")
    a = ap.parse_args()
    cfg = load_settings()
    if a.mode is None:
        menu(cfg)
        return
    for k in ("input", "text", "output", "project", "extract_name", "repack_name", "format"):
        if getattr(a, k) is not None:
            cfg[k] = getattr(a, k)
    if a.bepinex is not None:
        cfg["bepinex_root"] = a.bepinex
    if a.naming_strategy is not None:
        cfg["naming_strategy"] = a.naming_strategy
    if a.reprocess:
        cfg["reprocess"] = a.reprocess
    if a.skip_existing is not None:
        cfg["skip_existing"] = a.skip_existing
    if a.preview_only:
        cfg["preview_only"] = True
    if a.recursive:
        cfg["recursive"] = True
    if a.flat:
        cfg["mirror"] = False
    if a.allow_struct:
        cfg["allow_struct"] = True
    if not (check_pattern(cfg["extract_name"]) and check_pattern(cfg["repack_name"])):
        raise SystemExit(1)
    if a.mode == "workflow" and a.query:
        run_integrated_workflow(cfg, initial_query=a.query)
    else:
        RUNNERS[a.mode](cfg)


if __name__ == "__main__":
    main()