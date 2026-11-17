#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""conflict_manager.py - Priconne XUAT conflict resolver (GUI). Stdlib only.

v3 fixes: restored missing Rescan command (v2 crashed at startup), folder
rescan mode, binary-search line lookup, full traceback reporting, keeps
_*.txt project files, migrates v1 ignore list.
"""
from __future__ import annotations
import bisect, json, os, re, subprocess, sys, threading, queue, time, traceback
import urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = APP_DIR / "conflict_ui_settings.json"
SESSION_PATH = APP_DIR / "conflict_ui_session.json"
OLD_STATE_PATH = APP_DIR / "conflict_ui_state.json"
DEFAULT_SETTINGS = {"notepadpp": "", "target_lang": "en", "deepl_key": "",
                    "libre_url": "https://libretranslate.com", "libre_key": "",
                    "lingva_url": "https://lingva.ml"}
NORMAL_BG, KEEP_BG, DEAD_BG = "#f2f2f2", "#d9ead3", "#e6e6e6"
KEEP_TXT, DEAD_TXT = "#eef7ea", "#ececec"

_ESC_MAP = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "=": "="}
def unesc(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] in _ESC_MAP:
            out.append(_ESC_MAP[s[i + 1]]); i += 2
        else:
            out.append(s[i]); i += 1
    return "".join(out)
def esc(s):
    return s.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

PLAYER_PLACEHOLDER_RE = re.compile(r"\{(?:player_?name|0)\}", re.IGNORECASE)
ALL_WS_RE = re.compile(r"[\s\u3000\u200b\u00a0\ufeff]+")

def norm_key(s):
    s = unesc(s).replace("\r\n", "\n")
    s = PLAYER_PLACEHOLDER_RE.sub("{playername}", s)
    return ALL_WS_RE.sub("", s)

def letters(i): return "ABCDEFGH"[i] if i < 8 else str(i)

def load_lines(path):
    raw = Path(path).read_bytes(); bom, enc = b"", "utf-8"
    if raw.startswith(b"\xef\xbb\xbf"): bom = b"\xef\xbb\xbf"
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff")): enc = "utf-16"
    try: text = raw.decode(enc)
    except UnicodeDecodeError: enc, text = "cp932", raw.decode("cp932", errors="replace")
    if text.startswith("\ufeff") and enc != "utf-16": text = text[1:]
    eol = "\r\n" if "\r\n" in text else "\n"
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    final_nl = text.endswith("\n"); lines = text.split("\n")
    if final_nl: lines.pop()
    return raw, lines, {"enc": enc, "bom": bom, "eol": eol, "final_nl": final_nl}
def render_lines(lines, meta):
    text = meta["eol"].join(lines) + (meta["eol"] if meta["final_nl"] else "")
    return meta["bom"] + text.encode(meta["enc"], errors="surrogateescape")

MARKER = re.compile(r"^([AB])\((.+?):(\d+)\):\s?(.*)$")
def parse_dump(text):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n"); marks = []
    for i, ln in enumerate(lines):
        m = MARKER.match(ln)
        if m: marks.append((i, m.group(1), os.path.normpath(m.group(2)), int(m.group(3)), m.group(4)))
    hints, prev_end, i = [], 0, 0
    while i < len(marks) - 1:
        ia, ta, fa, la, _ = marks[i]; ib, tb, fb, lb, _ = marks[i + 1]
        if ta == "A" and tb == "B":
            seg = "\n".join(lines[prev_end:ia]).strip("\n")
            hints.append((fa, la, fb, lb, seg)); prev_end = ib + 1; i += 2
        else: i += 1
    return hints

@dataclass
class Entry:
    file: str; start: int; end: int; key_raw: str; val_raw: str; kind: str
    @property
    def key(self): return norm_key(self.key_raw)
    @property
    def val(self): return unesc(self.val_raw)

def parse_entries(path, lines):
    n = len(lines); block_mode = any(l.startswith("=") for l in lines); entries = []
    def skip(l):
        s = l.strip()
        return (not s) or s.startswith("#") or s.startswith("//") or s.startswith("r:") or s.startswith("sr:")
    i = 0
    while i < n:
        l = lines[i]
        if skip(l): i += 1; continue
        if l.startswith("="):
            start = i
            while start > 0 and not skip(lines[start - 1]) and not lines[start - 1].startswith("="): start -= 1
            end = i
            while end + 1 < n and not skip(lines[end + 1]): end += 1
            key = "\n".join(lines[start:i]); val = "\n".join([lines[i][1:]] + lines[i + 1:end + 1])
            entries.append(Entry(str(path), start, end, key, val, "block")); i = end + 1; continue
        if "=" in l and not block_mode:
            k, v = l.split("=", 1); entries.append(Entry(str(path), i, i, k, v, "flat")); i += 1; continue
        if block_mode:
            j = i
            while j < n and not skip(lines[j]) and not lines[j].startswith("="): j += 1
            if j < n and lines[j].startswith("="):
                k = j
                while k + 1 < n and not skip(lines[k + 1]): k += 1
                key = "\n".join(lines[i:j]); val = "\n".join([lines[j][1:]] + lines[j + 1:k + 1])
                entries.append(Entry(str(path), i, k, key, val, "block")); i = k + 1
            else:
                for t in range(i, j):
                    if "=" in lines[t] and not lines[t].startswith("="):
                        kk, vv = lines[t].split("=", 1); entries.append(Entry(str(path), t, t, kk, vv, "flat"))
                i = max(j, i + 1)
            continue
        i += 1
    return entries

class FileModel:
    def __init__(self, path):
        self.path = str(path); self.raw, self.lines, self.meta = load_lines(path)
        self.entries = parse_entries(path, self.lines)
        self.starts = [e.start for e in self.entries]
        self.by_key = {}
        for e in self.entries: self.by_key.setdefault(e.key, []).append(e)
        self.pending = {}; self.backup_path = None; self.write_count = 0
    def locate(self, line0):
        i = bisect.bisect_right(self.starts, line0) - 1
        if i >= 0:
            e = self.entries[i]
            if e.start <= line0 <= e.end: return e
        return None
    def entry_deleted(self, e):
        return all(self.pending.get(i, "x") is None for i in range(e.start, e.end + 1))
    def current_line(self, orig_idx):
        delta = sum((0 if v is None else len(v)) - 1 for i, v in self.pending.items() if i < orig_idx)
        return orig_idx + 1 + delta
    def effective_value(self, e):
        if e.kind == "flat":
            if e.start in self.pending:
                rep = self.pending[e.start]
                if rep is None: return e.val
                line = rep[0]; return unesc(line.split("=", 1)[1]) if "=" in line else e.val
            return e.val
        en_start = next((i for i in range(e.start, e.end + 1) if self.lines[i].startswith("=")), None)
        if en_start is None: return e.val
        out = []
        for i in range(en_start, e.end + 1):
            if i in self.pending:
                rep = self.pending[i]
                if rep is None: continue
                out.extend(rep)
            else: out.append(self.lines[i])
        if not out: return e.val
        return "\n".join([out[0][1:]] + out[1:])
    def _set(self, changes):
        diff = {}
        for idx, val in changes.items():
            diff[idx] = self.pending.get(idx, "ORIG")
            if val == "ORIG": self.pending.pop(idx, None)
            else: self.pending[idx] = val
        return diff
    def delete_entry(self, e): return self._set({i: None for i in range(e.start, e.end + 1)})
    def edit_changes(self, e, new_value):
        new_value = new_value.replace("\r\n", "\n").rstrip("\n")
        if e.kind == "flat":
            kp = self.lines[e.start].split("=", 1)[0]
            return {e.start: [kp + "=" + esc(new_value)]}
        en_start = next((i for i in range(e.start, e.end + 1) if self.lines[i].startswith("=")), None)
        if en_start is None: return {}
        parts = new_value.split("\n"); ch = {en_start: ["=" + parts[0]] + parts[1:]}
        for i in range(en_start + 1, e.end + 1): ch[i] = None
        return ch
    def restore(self, diff): self._set(diff)
    def save(self):
        if not self.pending and self.write_count == 0: return
        if self.backup_path is None:
            base = Path(self.path + ".bak")
            if base.exists():
                k = 2
                while Path(str(base) + str(k)).exists(): k += 1
                base = Path(str(base) + str(k))
            base.write_bytes(self.raw); self.backup_path = str(base)
        out = []
        for i, ln in enumerate(self.lines):
            if i in self.pending:
                rep = self.pending[i]
                if rep is None: continue
                out.extend(rep)
            else: out.append(ln)
        Path(self.path).write_bytes(render_lines(out, self.meta)); self.write_count += 1
    def revert_all(self):
        diff = {i: "ORIG" for i in list(self.pending)}; self._set(diff)
        Path(self.path).write_bytes(self.raw)

@dataclass
class Conflict:
    key: str; entries: list = field(default_factory=list); ignored: bool = False
    @property
    def norm(self): return norm_key(self.key)

def build_conflicts(dump_path, progress=None):
    hints = parse_dump(Path(dump_path).read_text(encoding="utf-8-sig", errors="replace"))
    files, seen = [], set()
    for fa, la, fb, lb, seg in hints:
        for f in (fa, fb):
            if f not in seen: seen.add(f); files.append(f)
    models, missing = {}, []
    for k, f in enumerate(files):
        if progress: progress(k, len(files), f)
        if not Path(f).is_file(): missing.append(f); continue
        try: models[f] = FileModel(f)
        except Exception: missing.append(f)
    wanted, order = set(), {}
    for fa, la, fb, lb, seg in hints:
        for f, ln in ((fa, la), (fb, lb)):
            fm = models.get(f)
            if not fm: continue
            hit = fm.locate(ln - 1)
            if hit:
                wanted.add(hit.key)
                if hit.key not in order: order[hit.key] = len(order)
        if seg: wanted.add(norm_key(seg))
    groups = {}
    for fm in models.values():
        for key, ents in fm.by_key.items():
            if key in wanted: groups.setdefault(key, []).extend(ents)
    conflicts = []
    for key, ents in groups.items():
        uniq = {}
        for e in ents: uniq[(e.file, e.start)] = e
        ents = sorted(uniq.values(), key=lambda e: (e.file, e.start))
        if len(ents) < 2: continue
        conflicts.append(Conflict(key=key, entries=ents))
    conflicts.sort(key=lambda c: order.get(c.norm, 10 ** 9))
    return conflicts, models, missing, len(hints)

def conflict_status(c, models):
    alive = [e for e in c.entries if not models[e.file].entry_deleted(e)]
    if c.ignored: return "ignored"
    if len(alive) == 1: return "resolved"
    if len(alive) == 0: return "empty!"
    vals = {models[e.file].effective_value(e).strip() for e in alive}
    return "duplicate" if len(vals) == 1 else "conflict"
def alive_pairs(c, models):
    return [(i, e) for i, e in enumerate(c.entries) if not models[e.file].entry_deleted(e)]
def is_ui_entry(c, models):
    if c.key.lstrip().startswith("/"): return True
    return all(re.fullmatch(r"ChangeFontSize\(\d+\)", models[e.file].effective_value(e).strip()) for e in c.entries)

def priority_score(path, patterns):
    import fnmatch
    p = str(path).replace("\\", "/").lower()
    for i, pat in enumerate(patterns):
        q = pat.replace("\\", "/").lower()
        if "*" in q or "?" in q:
            if fnmatch.fnmatch(p, q) or fnmatch.fnmatch(p, "*" + q + "*"): return i
        elif q and q in p: return i
    return len(patterns)
def pick_by_priority(pairs, patterns):
    if not pairs or not patterns: return None
    best = min(pairs, key=lambda ie: (priority_score(ie[1].file, patterns), ie[0]))
    return best[0] if priority_score(best[1].file, patterns) < len(patterns) else None
def pick_by_order(pairs, last=False):
    if not pairs: return None
    return (pairs[-1] if last else pairs[0])[0]
def pick_identical_first(pairs, models):
    if len(pairs) < 2: return None
    vals = {models[e.file].effective_value(e).strip() for _, e in pairs}
    return pairs[0][0] if len(vals) == 1 else None

def export_remaining(conflicts, models):
    out = []
    for c in conflicts:
        if c.ignored: continue
        pairs = alive_pairs(c, models)
        if len(pairs) < 2: continue
        out.append(c.key)
        for n, (i, e) in enumerate(pairs[:2]):
            fm = models[e.file]
            out.append(f"{'AB'[n]}({e.file}:{fm.current_line(e.start)}): {fm.effective_value(e)}")
    return "\n".join(out) + ("\n" if out else "")
def session_pack(dump, folder, conflicts, selections, ignored, priority, flags, cursor, flt):
    sel = {}
    for c in conflicts:
        v = selections.get(c.norm)
        if v is not None and 0 <= v < len(c.entries):
            e = c.entries[v]; sel[c.norm] = [e.file, e.start]
    return {"dump": str(dump) if dump else "", "folder": str(folder) if folder else "",
            "selections": sel, "ignored": sorted(ignored), "priority": list(priority),
            "flags": dict(flags), "cursor": cursor or "", "filter": flt}
def session_restore(data, conflicts, models):
    sel = {}; ign = set(data.get("ignored", []))
    for c in conflicts:
        c.ignored = c.norm in ign
        ref = data.get("selections", {}).get(c.norm)
        if ref:
            for i, e in enumerate(c.entries):
                if e.file == ref[0] and e.start == ref[1] and not models[e.file].entry_deleted(e):
                    sel[c.norm] = i; break
    return sel, ign

# ---------------- MT engines ----------------
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
def _http(url, data=None, headers=None, timeout=12):
    hdr = dict(UA)
    if headers: hdr.update(headers)
    if isinstance(data, dict): data = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=data, headers=hdr)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")
def mt_google(text, tl):
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=ja&tl="
           + urllib.parse.quote(tl) + "&dt=t&q=" + urllib.parse.quote(text))
    data = json.loads(_http(url)); return "".join(s[0] for s in data[0] if s and s[0])
def mt_mymemory(text, tl):
    url = ("https://api.mymemory.translated.net/get?q=" + urllib.parse.quote(text) + "&langpair=ja|" + urllib.parse.quote(tl))
    data = json.loads(_http(url))
    if str(data.get("responseStatus")) != "200": raise RuntimeError(str(data.get("responseDetails", "quota / error")))
    return data["responseData"]["translatedText"]
_bing_cache = {"t": 0}
def mt_bing(text, tl):
    now = time.time()
    if now - _bing_cache["t"] > 600 or "ig" not in _bing_cache:
        page = _http("https://www.bing.com/translator")
        ig = re.search(r'IG:"([0-9A-Fa-f]+)"', page); iid = re.search(r'data-iid="([^"]+)"', page)
        prm = re.search(r'params_AbusePreventionHelper\s*=\s*\[(\d+),"([^"]+)"', page)
        if not (ig and prm): raise RuntimeError("Bing token page changed")
        _bing_cache.update(t=now, ig=ig.group(1), iid=iid.group(1) if iid else "translator.5023",
                           key=prm.group(1), token=prm.group(2))
    c = _bing_cache
    url = f"https://www.bing.com/ttranslatev3?isVertical=1&IG={c['ig']}&IID={c['iid']}"
    data = json.loads(_http(url, data={"fromLang": "ja", "to": tl, "text": text, "token": c["token"], "key": c["key"]},
                            headers={"Content-Type": "application/x-www-form-urlencoded"}))
    return data[0]["translations"][0]["text"]
def mt_deepl(text, tl, key):
    if not key: raise RuntimeError("no DeepL API key (Settings)")
    host = "https://api-free.deepl.com" if key.endswith(":fx") else "https://api.deepl.com"
    target = {"en": "EN-US", "en-us": "EN-US", "en-gb": "EN-GB"}.get(tl.lower(), tl.upper())
    data = json.loads(_http(host + "/v2/translate", data={"text": text, "source_lang": "JA", "target_lang": target},
                            headers={"Authorization": "DeepL-Auth-Key " + key, "Content-Type": "application/x-www-form-urlencoded"}))
    return data["translations"][0]["text"]
def mt_libre(text, tl, url, key):
    body = {"q": text, "source": "ja", "target": tl.split("-")[0], "format": "text"}
    if key: body["api_key"] = key
    data = json.loads(_http(url.rstrip("/") + "/translate", data=json.dumps(body).encode(),
                            headers={"Content-Type": "application/json"}))
    if "translatedText" not in data: raise RuntimeError(str(data.get("error", data))[:120])
    return data["translatedText"]
def mt_lingva(text, tl, base):
    url = base.rstrip("/") + "/api/v1/ja/" + urllib.parse.quote(tl) + "/" + urllib.parse.quote(text)
    return json.loads(_http(url))["translation"]
def run_engine(name, text, settings):
    tl = settings.get("target_lang", "en")
    if name == "Google": return mt_google(text, tl)
    if name == "MyMemory": return mt_mymemory(text, tl)
    if name == "Bing": return mt_bing(text, tl)
    if name == "DeepL": return mt_deepl(text, tl, settings.get("deepl_key", ""))
    if name == "LibreTranslate": return mt_libre(text, tl, settings.get("libre_url", ""), settings.get("libre_key", ""))
    if name == "Lingva": return mt_lingva(text, tl, settings.get("lingva_url", ""))
    raise RuntimeError("unknown engine " + name)
ENGINE_NAMES = ["Google", "MyMemory", "Bing", "DeepL", "LibreTranslate", "Lingva"]
def web_url(engine, text):
    q = urllib.parse.quote(text)
    return {"Google": f"https://translate.google.com/?sl=ja&tl=en&text={q}&op=translate",
            "DeepL": f"https://www.deepl.com/translator#ja/en/{q}",
            "Bing": f"https://www.bing.com/translator?from=ja&to=en&text={q}",
            "Papago": f"https://papago.naver.com/?sk=ja&tk=en&st={q}",
            "Yandex": f"https://translate.yandex.com/?source_lang=ja&target_lang=en&text={q}"}[engine]

def load_json(path, default):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception: return default
def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
def find_notepadpp(setting=""):
    cands = [setting] if setting else []
    cands += [r"C:\Program Files\Notepad++\notepad++.exe", r"C:\Program Files (x86)\Notepad++\notepad++.exe",
              str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Notepad++/notepad++.exe")]
    for c in cands:
        if c and Path(c).is_file(): return c
    return ""
def open_folder(path): subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
def open_npp(path, line, settings):
    npp = find_notepadpp(settings.get("notepadpp", ""))
    if npp: subprocess.Popen([npp, f"-n{int(line)}", str(path)])
    else: subprocess.Popen(["notepad.exe", str(path)])

# ---------------- GUI ----------------
def run_gui(initial_dump=None):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    settings = load_json(SETTINGS_PATH, dict(DEFAULT_SETTINGS))
    for k, v in DEFAULT_SETTINGS.items(): settings.setdefault(k, v)
    sess = load_json(SESSION_PATH, None)
    if sess is None:
        sess = {"ignored": load_json(OLD_STATE_PATH, {}).get("ignored", [])}

    class App:
        def __init__(self, root):
            self.root = root; root.title("Priconne Conflict Manager"); root.geometry("1320x860")
            self.conflicts, self.models, self.missing = [], {}, []
            self.selections = {}; self.ignored = set(sess.get("ignored", []))
            self.priority = list(sess.get("priority", []))
            self.flags = {"confirm": True, "auto_advance": True, "auto_priority": True}
            self.flags.update(sess.get("flags", {}))
            self.dump_path = None; self.folder = None
            self.view = []; self.cur = None; self.cards = []
            self.choice_var = tk.IntVar(value=-1); self.undo_stack = []; self.mt_cache = {}
            self.q = queue.Queue(); self.pool = ThreadPoolExecutor(max_workers=6); self.busy = False
            self._build(); root.after(100, self._poll); root.protocol("WM_DELETE_WINDOW", self._on_close)
            start = initial_dump or sess.get("dump")
            startfolder = sess.get("folder")
            if start and Path(start).is_file():
                self.load_async(start)
            elif startfolder and Path(startfolder).is_dir():
                self.load_async(None, startfolder)
            elif (APP_DIR / "_conflicts.txt").is_file():
                self.load_async(str(APP_DIR / "_conflicts.txt"))

        def _build(self):
            r = self.root; men = tk.Menu(r); fm = tk.Menu(men, tearoff=0)
            fm.add_command(label="Open _conflicts.txt...  (Ctrl+O)", command=self.open_dump)
            fm.add_command(label="Rescan project folder...", command=self.rescan)
            fm.add_command(label="Save session  (Ctrl+S)", command=self.save_session_explicit)
            fm.add_command(label="Export remaining _conflicts.txt...", command=self.export_remaining_dialog)
            fm.add_separator()
            fm.add_command(label="Revert ALL changes (this session)", command=self.revert_all)
            fm.add_command(label="Exit", command=self._on_close)
            men.add_cascade(label="File", menu=fm)
            sm = tk.Menu(men, tearoff=0)
            sm.add_command(label="Mass select: first line (A)", command=lambda: self.mass_select("first"))
            sm.add_command(label="Mass select: last line", command=lambda: self.mass_select("last"))
            sm.add_command(label="Mass select: by file priority", command=lambda: self.mass_select("priority"))
            sm.add_command(label="Mass select: identical values -> first", command=lambda: self.mass_select("identical"))
            sm.add_separator()
            sm.add_command(label="Clear ALL selections", command=self.clear_selections)
            sm.add_command(label="File priority...", command=self.priority_dialog)
            sm.add_separator()
            sm.add_command(label="Mass delete selected", command=self.mass_delete)
            men.add_cascade(label="Select", menu=sm)
            tm = tk.Menu(men, tearoff=0)
            tm.add_command(label="Bulk ignore UI / resizer conflicts", command=self.bulk_ignore_ui)
            tm.add_command(label="Settings...", command=self.settings_dialog)
            tm.add_command(label="Keyboard shortcuts", command=self.show_keys)
            men.add_cascade(label="Tools", menu=tm); r.config(menu=men)

            top = ttk.Frame(r, padding=6); top.pack(fill="x")
            ttk.Button(top, text="Open", command=self.open_dump).pack(side="left")
            ttk.Button(top, text="Rescan", command=self.rescan).pack(side="left", padx=3)
            ttk.Button(top, text="Save session", command=self.save_session_explicit).pack(side="left", padx=3)
            ttk.Button(top, text="Export remaining", command=self.export_remaining_dialog).pack(side="left", padx=3)
            ttk.Button(top, text="Mass delete", command=self.mass_delete).pack(side="left", padx=3)
            self.filter_var = tk.StringVar(value=sess.get("filter", "pending"))
            ttk.Combobox(top, textvariable=self.filter_var, width=10, state="readonly",
                         values=["pending", "conflict", "duplicate", "resolved", "ignored", "all"]).pack(side="left", padx=6)
            self.filter_var.trace_add("write", lambda *a: self.refresh_list())
            ttk.Label(top, text="Search:").pack(side="left")
            self.search_var = tk.StringVar()
            se = ttk.Entry(top, textvariable=self.search_var, width=24)
            se.pack(side="left", padx=4); se.bind("<Return>", lambda *a: self.refresh_list())
            self.confirm_var = tk.BooleanVar(value=self.flags["confirm"])
            ttk.Checkbutton(top, text="Confirm deletes", variable=self.confirm_var,
                            command=lambda: self._flag("confirm", self.confirm_var.get())).pack(side="left", padx=6)
            self.adv_var = tk.BooleanVar(value=self.flags["auto_advance"])
            ttk.Checkbutton(top, text="Auto-advance", variable=self.adv_var,
                            command=lambda: self._flag("auto_advance", self.adv_var.get())).pack(side="left")
            self.count_lbl = ttk.Label(top, text="no file loaded"); self.count_lbl.pack(side="right")

            pan = ttk.PanedWindow(r, orient="horizontal"); pan.pack(fill="both", expand=True, padx=6, pady=4)
            left = ttk.Frame(pan); pan.add(left, weight=1)
            self.tree = ttk.Treeview(left, columns=("n", "status", "key", "cand", "sel"), show="headings", selectmode="browse")
            for c, w, t in (("n", 44, "#"), ("status", 72, "Status"), ("key", 300, "Key"), ("cand", 40, "N"), ("sel", 40, "Keep")):
                self.tree.heading(c, text=t); self.tree.column(c, width=w, stretch=(c == "key"))
            sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=sb.set); self.tree.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y"); self.tree.bind("<<TreeviewSelect>>", self.on_select)
            for tag, col in (("conflict", "#b00020"), ("duplicate", "#8a6d00"), ("resolved", "#1b7f3b"),
                             ("ignored", "#888888"), ("empty!", "#b00020")):
                self.tree.tag_configure(tag, foreground=col)

            right = ttk.Frame(pan); pan.add(right, weight=2)
            ttk.Label(right, text="Japanese key").pack(anchor="w")
            self.key_txt = tk.Text(right, height=4, wrap="word", bg="#f6f6f6", font=("Yu Gothic UI", 10))
            self.key_txt.pack(fill="x"); self.key_txt.config(state="disabled")
            mid = ttk.Frame(right); mid.pack(fill="both", expand=True, pady=4)
            self.canvas = tk.Canvas(mid, highlightthickness=0)
            csb = ttk.Scrollbar(mid, orient="vertical", command=self.canvas.yview)
            self.card_frame = tk.Frame(self.canvas)
            self.card_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
            self.canvas.create_window((0, 0), window=self.card_frame, anchor="nw")
            self.canvas.configure(yscrollcommand=csb.set); self.canvas.pack(side="left", fill="both", expand=True)
            csb.pack(side="right", fill="y")
            self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))
            bar = ttk.Frame(right); bar.pack(fill="x", pady=2)
            ttk.Button(bar, text="KEEP selected, delete others (Del)", command=self.keep_selected).pack(side="left")
            ttk.Button(bar, text="Ignore", command=self.ignore_cur).pack(side="left", padx=4)
            ttk.Button(bar, text="Unignore", command=self.unignore_cur).pack(side="left")
            ttk.Button(bar, text="Next pending", command=self.next_pending).pack(side="left", padx=4)
            ttk.Button(bar, text="Undo (Ctrl+Z)", command=self.undo).pack(side="left")

            mt = ttk.LabelFrame(right, text="Machine translation (JP -> target)", padding=4); mt.pack(fill="x", pady=4)
            row = ttk.Frame(mt); row.pack(fill="x"); self.eng_vars = {}
            for name in ENGINE_NAMES:
                v = tk.BooleanVar(value=name in settings.get("engines", ["Google", "MyMemory", "Bing"]))
                self.eng_vars[name] = v; ttk.Checkbutton(row, text=name, variable=v).pack(side="left")
            ttk.Button(row, text="Translate", command=self.translate).pack(side="left", padx=6)
            row2 = ttk.Frame(mt); row2.pack(fill="x", pady=2); ttk.Label(row2, text="Open web:").pack(side="left")
            for w in ("Google", "DeepL", "Bing", "Papago", "Yandex"):
                ttk.Button(row2, text=w, width=7, command=lambda x=w: self.open_web(x)).pack(side="left", padx=2)
            self.mt_tree = ttk.Treeview(mt, columns=("eng", "txt"), show="headings", height=4)
            self.mt_tree.heading("eng", text="Engine"); self.mt_tree.heading("txt", text="Result")
            self.mt_tree.column("eng", width=110, stretch=False); self.mt_tree.column("txt", width=700)
            self.mt_tree.pack(fill="x", pady=2); self.mt_tree.bind("<Double-1>", lambda e: self.copy_mt())
            row3 = ttk.Frame(mt); row3.pack(fill="x")
            ttk.Button(row3, text="Copy result", command=self.copy_mt).pack(side="left")
            ttk.Button(row3, text="Use result -> selected entry", command=self.use_mt).pack(side="left", padx=4)
            self.status = ttk.Label(r, text="Ready. Open a _conflicts.txt or Rescan a folder.",
                                    relief="sunken", anchor="w", padding=3)
            self.status.pack(fill="x", side="bottom")

            for seq, fn in (("<Up>", self._kb_up), ("<Down>", self._kb_down),
                            ("<Left>", self._kb_left), ("<Right>", self._kb_right),
                            ("<Delete>", self._kb_del)):
                r.bind(seq, fn); self.tree.bind(seq, fn)
            r.bind("<Control-z>", lambda e: self.undo()); r.bind("<Control-s>", lambda e: self.save_session_explicit())
            r.bind("<Control-o>", lambda e: self.open_dump()); r.bind("<Control-n>", lambda e: self.next_pending())

        # ---- helpers
        def _flag(self, k, v): self.flags[k] = v; self.save_session()
        def _editing(self):
            w = self.root.focus_get()
            if w is None: return False
            return isinstance(w, (tk.Text, tk.Entry)) or w.winfo_class() in ("Entry", "TEntry")
        def save_session(self):
            data = session_pack(self.dump_path, self.folder, self.conflicts, self.selections,
                                self.ignored, self.priority, self.flags,
                                self.cur.norm if self.cur else "", self.filter_var.get())
            save_json(SESSION_PATH, data)
        def save_session_explicit(self):
            self.save_session(); self.status.config(text="Session saved to " + SESSION_PATH.name); return "break"
        def export_remaining_dialog(self):
            if not self.conflicts: return
            p = filedialog.asksaveasfilename(title="Export remaining conflicts", initialdir=str(APP_DIR),
                                             initialfile="_conflicts.remaining.txt", defaultextension=".txt",
                                             filetypes=[("Text", "*.txt"), ("All", "*.*")])
            if p:
                Path(p).write_text(export_remaining(self.conflicts, self.models), encoding="utf-8")
                self.status.config(text="Exported remaining conflicts -> " + p)
        def show_keys(self):
            messagebox.showinfo("Shortcuts", "Up/Down: move conflict\nLeft/Right: choose candidate to keep\n"
                                "Del: keep selected, delete others\nCtrl+S: save session\nCtrl+O: open\n"
                                "Ctrl+Z: undo\nCtrl+N: next pending")

        # ---- loading
        def open_dump(self):
            p = filedialog.askopenfilename(title="Open _conflicts.txt", initialdir=str(APP_DIR),
                                           filetypes=[("Text", "*.txt"), ("All", "*.*")])
            if p: self.load_async(p)
            return "break"
        def rescan(self):
            d = filedialog.askdirectory(title="Project Text folder (scans ALL .txt)")
            if d: self.load_async(None, d)
            return "break"
        def load_async(self, dump, folder=None):
            if self.busy: return
            self.busy = True; self.status.config(text="Loading / parsing source files ...")
            def prog(i, n, f): self.q.put(("prog", f"Parsing {i + 1}/{n}: {Path(f).name}"))
            def work():
                try:
                    res = build_conflicts(dump, prog) if dump else self._rescan(folder, prog)
                    self.q.put(("loaded", (dump, folder, res)))
                except Exception:
                    self.q.put(("error", traceback.format_exc()))
            threading.Thread(target=work, daemon=True).start()
        def _rescan(self, folder, prog):
            files = sorted(Path(folder).rglob("*.txt")); models, missing = {}, []
            skip_names = {"_conflicts.txt", "_conflicts.remaining.txt", "_SUMMARY.txt",
                          "_missing.txt", "_warnings.txt", "_unused.txt"}
            for i, f in enumerate(files):
                prog(i, len(files), str(f))
                if f.name in skip_names or f.name.endswith((".bak", ".report.txt", ".missing.txt", ".fill.txt")):
                    continue
                try: fm = FileModel(f)
                except Exception: missing.append(str(f)); continue
                if fm.entries: models[str(f)] = fm
            groups = {}
            for fm in models.values():
                for k, ents in fm.by_key.items():
                    if k.strip(): groups.setdefault(k, []).extend(ents)
            conflicts = [Conflict(key=k, entries=sorted(v, key=lambda e: (e.file, e.start)))
                         for k, v in groups.items() if len(v) >= 2]
            return conflicts, models, missing, 0
        def _poll(self):
            try:
                while True:
                    kind, payload = self.q.get_nowait()
                    if kind == "prog":
                        self.status.config(text=payload)
                    elif kind == "loaded":
                        dump, folder, (cs, ms, missing, nh) = payload
                        self.dump_path = dump; self.folder = folder
                        self.conflicts, self.models, self.missing = cs, ms, missing
                        cur_sess = load_json(SESSION_PATH, sess)
                        self.selections, self.ignored = session_restore(cur_sess, cs, ms)
                        self.auto_priority_fill(); self.busy = False; self.refresh_list()
                        cur = cur_sess.get("cursor", "")
                        target = next((iid for iid, c in self.view if c.norm == cur), None)
                        if not target and self.view: target = self.view[0][0]
                        if target: self.tree.selection_set(target); self.tree.see(target)
                        msg = f"{len(cs)} groups from {len(ms)} files"
                        if missing: msg += f" | {len(missing)} missing/unreadable"
                        self.status.config(text=msg); self.save_session()
                    elif kind == "error":
                        self.busy = False
                        print(payload)
                        messagebox.showerror("Load failed", payload[-1800:])
                        self.status.config(text="Load failed - see console / popup for the traceback.")
                    elif kind == "mt":
                        eng, ok, txt = payload
                        self.mt_tree.insert("", "end", values=(eng, txt if ok else "ERROR: " + txt))
                    elif kind == "mtdone":
                        self.status.config(text="MT finished.")
            except queue.Empty:
                pass
            self.root.after(100, self._poll)

        # ---- list / cards
        def refresh_list(self):
            self.tree.delete(*self.tree.get_children()); self.view = []
            flt = self.filter_var.get(); needle = self.search_var.get().strip().lower()
            for idx, c in enumerate(self.conflicts):
                st = conflict_status(c, self.models)
                if flt == "pending" and st not in ("conflict", "duplicate"): continue
                if flt in ("conflict", "duplicate", "resolved", "ignored") and st != flt: continue
                if needle:
                    hay = c.key.lower() + " " + " ".join(
                        e.file.lower() + " " + self.models[e.file].effective_value(e).lower() for e in c.entries)
                    if needle not in hay: continue
                sel = self.selections.get(c.norm)
                mark = letters(sel) if sel is not None else ""
                iid = self.tree.insert("", "end",
                                       values=(idx + 1, st, c.key.replace("\n", " ")[:90], len(c.entries), mark),
                                       tags=(st,))
                self.view.append((iid, c))
            self.count_lbl.config(text=f"{len(self.view)} shown / {len(self.conflicts)} total")
        def on_select(self, _=None):
            sel = self.tree.selection()
            if not sel: return
            iid = sel[0]
            hit = next((c for i, c in self.view if i == iid), None)
            if hit is None: return
            self.cur = hit; self.show_conflict()
        def show_conflict(self):
            c = self.cur
            self.key_txt.config(state="normal"); self.key_txt.delete("1.0", "end")
            self.key_txt.insert("1.0", c.key); self.key_txt.config(state="disabled")
            for w in self.card_frame.winfo_children(): w.destroy()
            self.cards = []; self.choice_var.set(self.selections.get(c.norm, -1))
            for i, e in enumerate(c.entries):
                fm = self.models[e.file]; dead = fm.entry_deleted(e)
                card = tk.LabelFrame(self.card_frame, text="", padx=4, pady=4, bg=NORMAL_BG)
                card.pack(fill="x", padx=2, pady=3)
                head = tk.Frame(card, bg=NORMAL_BG); head.pack(fill="x")
                rb = tk.Radiobutton(head, text="keep this", variable=self.choice_var, value=i,
                                    bg=NORMAL_BG, activebackground=NORMAL_BG, command=lambda x=i: self._set_choice(x))
                rb.pack(side="left")
                for seq, fn in (("<Up>", self._kb_up), ("<Down>", self._kb_down), ("<Left>", self._kb_left),
                                ("<Right>", self._kb_right), ("<Delete>", self._kb_del)):
                    rb.bind(seq, fn)
                lbl = tk.Label(head, text=e.file, fg="#555", bg=NORMAL_BG); lbl.pack(side="left", padx=6)
                txt = tk.Text(card, height=max(2, min(6, e.val.count("\n") + 2)), wrap="word", font=("Yu Gothic UI", 10))
                txt.insert("1.0", fm.effective_value(e))
                if dead: txt.config(state="disabled", bg=DEAD_TXT)
                txt.pack(fill="x", pady=2)
                btns = tk.Frame(card, bg=NORMAL_BG); btns.pack(fill="x")
                ttk.Button(btns, text="Save edit", command=lambda x=i: self.save_edit(x)).pack(side="left")
                ttk.Button(btns, text="Delete line", command=lambda x=i: self.delete_one(x)).pack(side="left", padx=3)
                ttk.Button(btns, text="Folder", command=lambda x=e: open_folder(x.file)).pack(side="left", padx=3)
                ttk.Button(btns, text="N++", command=lambda x=e: open_npp(x.file,
                           self.models[x.file].current_line(x.start), settings)).pack(side="left", padx=3)
                ttk.Button(btns, text="Copy", command=lambda x=i: self.copy_val(x)).pack(side="left", padx=3)
                if dead: ttk.Button(btns, text="Undelete", command=lambda x=i: self.undelete(x)).pack(side="left", padx=3)
                self.cards.append({"card": card, "head": head, "lbl": lbl, "btns": btns,
                                   "txt": txt, "rb": rb, "e": e, "dead": dead})
            self._recolor(); self.mt_tree.delete(*self.mt_tree.get_children())
        def _recolor(self):
            chosen = self.choice_var.get()
            for i, cd in enumerate(self.cards):
                dead = cd["dead"]; bg = DEAD_BG if dead else (KEEP_BG if i == chosen else NORMAL_BG)
                tbg = DEAD_TXT if dead else (KEEP_TXT if i == chosen else "white")
                cd["card"].config(bg=bg, text=f"{letters(i)}  {Path(cd['e'].file).name}:"
                                  f"{self.models[cd['e'].file].current_line(cd['e'].start)}  ({cd['e'].kind})"
                                  + ("  [DELETED]" if dead else ("  [KEEP]" if i == chosen else "")))
                for w in (cd["head"], cd["btns"], cd["lbl"], cd["rb"]):
                    w.config(bg=bg)
                cd["rb"].config(activebackground=bg)
                if not dead: cd["txt"].config(bg=tbg)
        def _set_choice(self, i):
            if not self.cur or self.cards[i]["dead"]: return
            self.choice_var.set(i); self.selections[self.cur.norm] = i
            self._recolor(); self.save_session(); self._update_sel_cell()
        def _update_sel_cell(self):
            if not self.cur: return
            for iid, c in self.view:
                if c is self.cur:
                    sel = self.selections.get(c.norm)
                    self.tree.set(iid, "sel", letters(sel) if sel is not None else ""); break

        # ---- keyboard
        def _kb_up(self, e):
            if self._editing(): return
            self._move(-1); return "break"
        def _kb_down(self, e):
            if self._editing(): return
            self._move(1); return "break"
        def _move(self, d):
            if not self.view: return
            s = self.tree.selection(); idx = 0
            if s: idx = next((k for k, (i, c) in enumerate(self.view) if i == s[0]), 0)
            idx = max(0, min(len(self.view) - 1, idx + d))
            iid = self.view[idx][0]; self.tree.selection_set(iid); self.tree.see(iid)
        def _kb_left(self, e):
            if self._editing(): return
            self._cycle(-1); return "break"
        def _kb_right(self, e):
            if self._editing(): return
            self._cycle(1); return "break"
        def _cycle(self, d):
            if not self.cur: return
            alive = [i for i, cd in enumerate(self.cards) if not cd["dead"]]
            if not alive: return
            cur = self.choice_var.get()
            if cur not in alive: nxt = alive[0] if d > 0 else alive[-1]
            else: nxt = alive[(alive.index(cur) + d) % len(alive)]
            self._set_choice(nxt)
        def _kb_del(self, e):
            if self._editing(): return
            self.keep_selected(); return "break"

        # ---- commit
        def _commit(self, items, desc):
            per_file = {}; nconf = 0; nlines = 0; done = []
            for c, ki, new in items:
                pairs = alive_pairs(c, self.models)
                if not any(i == ki for i, _ in pairs): continue
                others = [e for i, e in pairs if i != ki]
                if not others: continue
                nconf += 1; done.append(c.norm)
                kept = c.entries[ki]; kfm = self.models[kept.file]
                if new is not None and new != kfm.effective_value(kept):
                    d = per_file.setdefault(kfm, {}); d.update(kfm.edit_changes(kept, new))
                for e in others:
                    fm = self.models[e.file]; d = per_file.setdefault(fm, {})
                    for j in range(e.start, e.end + 1): d[j] = None; nlines += 1
            if not per_file: return 0, 0
            undo = []
            for fm, ch in per_file.items():
                diff = fm._set(ch); fm.save(); undo.append((fm, diff))
            self.undo_stack.append((desc, undo))
            for k in done: self.selections.pop(k, None)
            self.auto_priority_fill(); self.save_session(); self.refresh_list()
            if self.cur: self.show_conflict()
            self.status.config(text=f"{desc}: {nconf} conflicts, {nlines} lines deleted (Ctrl+Z undo)")
            if self.flags["auto_advance"] and self.cur and conflict_status(self.cur, self.models) in ("resolved", "ignored"):
                self.next_pending()
            return nconf, nlines
        def keep_selected(self):
            if not self.cur: return
            ki = self.choice_var.get()
            if ki < 0 or ki >= len(self.cards) or self.cards[ki]["dead"]:
                self.status.config(text="Choose a candidate first (Left/Right)."); return
            pairs = alive_pairs(self.cur, self.models)
            others = [e for i, e in pairs if i != ki]
            if not others: self.status.config(text="Already resolved."); return
            if self.flags["confirm"]:
                if not messagebox.askyesno("Confirm", f"Delete {len(others)} line(s) and keep {letters(ki)}?"): return
            new = self.cards[ki]["txt"].get("1.0", "end").rstrip("\n")
            self._commit([(self.cur, ki, new)], "Keep selected")
        def mass_delete(self):
            items = []
            for c in self.conflicts:
                if c.ignored: continue
                ki = self.selections.get(c.norm)
                if ki is None: continue
                pairs = alive_pairs(c, self.models)
                if any(i == ki for i, _ in pairs) and len(pairs) > 1: items.append((c, ki, None))
            if not items:
                messagebox.showinfo("Mass delete", "No conflicts have a selected candidate."); return
            nl = sum(len(alive_pairs(c, self.models)) - 1 for c, _, _ in items)
            if self.flags["confirm"]:
                if not messagebox.askyesno("Mass delete", f"Commit {len(items)} conflicts, delete {nl} lines?"): return
            self._commit(items, "Mass delete")
        def delete_one(self, i):
            e = self.cards[i]["e"]; fm = self.models[e.file]
            if fm.entry_deleted(e): return
            if self.flags["confirm"]:
                if not messagebox.askyesno("Confirm", f"Delete this entry ({Path(e.file).name}:{fm.current_line(e.start)})?"): return
            diff = fm.delete_entry(e); fm.save(); self.undo_stack.append(("Delete line", [(fm, diff)]))
            self.save_session(); self.refresh_list(); self.show_conflict()
        def undelete(self, i):
            e = self.cards[i]["e"]; fm = self.models[e.file]
            diff = fm._set({j: "ORIG" for j in range(e.start, e.end + 1)}); fm.save()
            self.undo_stack.append(("Undelete", [(fm, diff)])); self.save_session(); self.refresh_list(); self.show_conflict()
        def save_edit(self, i):
            cd = self.cards[i]; e = cd["e"]; fm = self.models[e.file]
            if fm.entry_deleted(e): return
            new = cd["txt"].get("1.0", "end").rstrip("\n")
            if new == fm.effective_value(e): self.status.config(text="No change to save."); return
            diff = fm._set(fm.edit_changes(e, new)); fm.save(); self.undo_stack.append(("Save edit", [(fm, diff)]))
            self.save_session(); self.refresh_list(); self.show_conflict()
        def undo(self):
            if not self.undo_stack: self.status.config(text="Nothing to undo."); return "break"
            desc, undo = self.undo_stack.pop()
            for fm, diff in reversed(undo): fm.restore(diff); fm.save()
            self.save_session(); self.refresh_list()
            if self.cur: self.show_conflict()
            self.status.config(text="Undone: " + desc); return "break"
        def revert_all(self):
            if not self.models: return
            if not messagebox.askyesno("Revert", "Rewrite ALL touched files with their original content?"): return
            for fm in self.models.values():
                if fm.pending or fm.write_count: fm.revert_all()
            self.undo_stack.clear(); self.save_session(); self.refresh_list()
            if self.cur: self.show_conflict()
            self.status.config(text="All files reverted.")

        # ---- mass select / priority
        def _pending_view(self):
            return [c for _, c in self.view
                    if conflict_status(c, self.models) in ("conflict", "duplicate") and not c.ignored]
        def mass_select(self, mode):
            n = 0; skip = 0
            for c in self._pending_view():
                pairs = alive_pairs(c, self.models)
                if mode == "first": ki = pick_by_order(pairs)
                elif mode == "last": ki = pick_by_order(pairs, last=True)
                elif mode == "priority": ki = pick_by_priority(pairs, self.priority)
                else: ki = pick_identical_first(pairs, self.models)
                if ki is None: skip += 1; continue
                self.selections[c.norm] = ki; n += 1
            self.save_session(); self.refresh_list()
            if self.cur: self.show_conflict()
            self.status.config(text=f"Mass select ({mode}): {n} marked" + (f", {skip} skipped" if skip else ""))
        def clear_selections(self):
            self.selections.clear(); self.save_session(); self.refresh_list()
            if self.cur: self.show_conflict()
            self.status.config(text="All selections cleared.")
        def auto_priority_fill(self):
            if not (self.flags["auto_priority"] and self.priority): return
            for c in self.conflicts:
                if c.ignored or c.norm in self.selections: continue
                if conflict_status(c, self.models) not in ("conflict", "duplicate"): continue
                ki = pick_by_priority(alive_pairs(c, self.models), self.priority)
                if ki is not None: self.selections[c.norm] = ki
        def priority_dialog(self):
            d = tk.Toplevel(self.root); d.title("File priority (top = preferred)"); d.geometry("560x420"); d.transient(self.root)
            lb = tk.Listbox(d); lb.pack(fill="both", expand=True, padx=8, pady=8)
            for p in self.priority: lb.insert("end", p)
            row = ttk.Frame(d); row.pack(fill="x", padx=8)
            ent = ttk.Entry(row); ent.pack(side="left", fill="x", expand=True)
            def add():
                v = ent.get().strip()
                if v: lb.insert("end", v); ent.delete(0, "end")
            ttk.Button(row, text="Add", command=add).pack(side="left", padx=4)
            row2 = ttk.Frame(d); row2.pack(fill="x", padx=8, pady=4)
            def mv(delta):
                s = lb.curselection()
                if not s: return
                i = s[0]; j = i + delta
                if 0 <= j < lb.size():
                    v = lb.get(i); lb.delete(i); lb.insert(j, v); lb.selection_set(j)
            def rm():
                s = lb.curselection()
                if s: lb.delete(s[0])
            ttk.Button(row2, text="Up", command=lambda: mv(-1)).pack(side="left")
            ttk.Button(row2, text="Down", command=lambda: mv(1)).pack(side="left", padx=4)
            ttk.Button(row2, text="Remove", command=rm).pack(side="left")
            ap = tk.BooleanVar(value=self.flags["auto_priority"])
            ttk.Checkbutton(d, text="Auto-mark preferred files on load / after commit", variable=ap).pack(anchor="w", padx=8)
            ttk.Label(d, text="Patterns: substring (e.g. \\Story\\) or glob (e.g. *BossDesc*). Case-insensitive.",
                      foreground="#555").pack(anchor="w", padx=8)
            def ok():
                self.priority = [lb.get(i) for i in range(lb.size())]
                self.flags["auto_priority"] = ap.get(); self.auto_priority_fill()
                self.save_session(); self.refresh_list()
                if self.cur: self.show_conflict()
                d.destroy()
            ttk.Button(d, text="OK", command=ok).pack(pady=8)
        def bulk_ignore_ui(self):
            n = 0
            for c in self.conflicts:
                if not c.ignored and is_ui_entry(c, self.models):
                    c.ignored = True; self.ignored.add(c.norm); n += 1
            self.save_session(); self.refresh_list()
            messagebox.showinfo("Ignore UI", f"{n} UI/resizer conflicts ignored.")
        def ignore_cur(self):
            if self.cur:
                self.cur.ignored = True; self.ignored.add(self.cur.norm)
                self.save_session(); self.refresh_list()
                if self.flags["auto_advance"]: self.next_pending()
        def unignore_cur(self):
            if self.cur:
                self.cur.ignored = False; self.ignored.discard(self.cur.norm)
                self.save_session(); self.refresh_list(); self.show_conflict()
        def next_pending(self):
            for iid, c in self.view:
                if conflict_status(c, self.models) in ("conflict", "duplicate") and not c.ignored:
                    self.tree.selection_set(iid); self.tree.see(iid); return "break"
            self.status.config(text="No pending conflicts left in this view."); return "break"

        # ---- MT / misc
        def translate(self):
            if not self.cur: return
            text = self.cur.key; engines = [n for n, v in self.eng_vars.items() if v.get()]
            if not engines: messagebox.showinfo("MT", "Tick at least one engine."); return
            settings["engines"] = engines; save_json(SETTINGS_PATH, settings)
            self.mt_tree.delete(*self.mt_tree.get_children()); self.status.config(text="MT running: " + ", ".join(engines))
            def job(eng):
                ck = (eng, text, settings.get("target_lang"))
                if ck in self.mt_cache: self.q.put(("mt", (eng, True, self.mt_cache[ck]))); return
                try:
                    res = run_engine(eng, text, settings); self.mt_cache[ck] = res
                    self.q.put(("mt", (eng, True, res)))
                except Exception as ex:
                    self.q.put(("mt", (eng, False, f"{type(ex).__name__}: {ex}")))
            for eng in engines: self.pool.submit(job, eng)
            self.pool.submit(lambda: self.q.put(("mtdone", None)))
        def _mt_sel(self):
            s = self.mt_tree.selection()
            return self.mt_tree.item(s[0], "values")[1] if s else None
        def copy_mt(self):
            v = self._mt_sel()
            if v: self.root.clipboard_clear(); self.root.clipboard_append(v); self.status.config(text="MT result copied.")
        def use_mt(self):
            v = self._mt_sel()
            if v and self.cards:
                i = self.choice_var.get()
                if i < 0 or i >= len(self.cards): i = 0
                t = self.cards[i]["txt"]; t.delete("1.0", "end"); t.insert("1.0", v)
                self.status.config(text="Result placed in selected entry - press Save edit or Del.")
        def open_web(self, engine):
            if self.cur:
                import webbrowser; webbrowser.open(web_url(engine, self.cur.key))
        def copy_val(self, i):
            v = self.cards[i]["txt"].get("1.0", "end").rstrip("\n")
            self.root.clipboard_clear(); self.root.clipboard_append(v)
        def settings_dialog(self):
            d = tk.Toplevel(self.root); d.title("Settings"); d.geometry("560x300"); vars_ = {}
            rows = [("notepadpp", "Notepad++ exe path"), ("target_lang", "MT target language"),
                    ("deepl_key", "DeepL API key (free ends :fx)"), ("libre_url", "LibreTranslate URL"),
                    ("libre_key", "LibreTranslate API key"), ("lingva_url", "Lingva mirror URL")]
            for i, (k, lbl) in enumerate(rows):
                ttk.Label(d, text=lbl).grid(row=i, column=0, sticky="w", padx=6, pady=4)
                v = tk.StringVar(value=str(settings.get(k, ""))); vars_[k] = v
                ttk.Entry(d, textvariable=v, width=52).grid(row=i, column=1, padx=6, pady=4)
            def ok():
                for k, v in vars_.items(): settings[k] = v.get().strip()
                save_json(SETTINGS_PATH, settings); d.destroy()
            ttk.Button(d, text="Save", command=ok).grid(row=len(rows), column=1, sticky="e", padx=6, pady=8)
        def _on_close(self):
            self.save_session(); save_json(SETTINGS_PATH, settings); self.root.destroy()

    root = tk.Tk()
    try: ttk.Style().theme_use("vista")
    except Exception: pass

    def tk_exc(exc, val, tb):
        traceback.print_exception(exc, val, tb)
        try: messagebox.showerror("Error", f"{exc.__name__}: {val}")
        except Exception: pass
    root.report_callback_exception = tk_exc

    try:
        App(root)
    except Exception:
        traceback.print_exc()
        input("Startup failed - press Enter to close (send the traceback above).")
        raise
    root.mainloop()

if __name__ == "__main__":
    run_gui(sys.argv[1] if len(sys.argv) > 1 else None)