#!/usr/bin/env python3
"""PROGRAM 3: fill missing lines from the whole project, or verify alignment."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from advscript import (Config, Document, Store, box_key, esc, is_clean, is_punct_only,
                       iter_inputs, load_lines, looks_japanese, read_clean,
                       write_clean, write_text)
from xuat2raw import find_pair


def main():
    ap = argparse.ArgumentParser(description="Fill missing / verify")
    ap.add_argument("input", nargs="?")
    ap.add_argument("-t", "--trans", nargs="*")
    ap.add_argument("-p", "--project", nargs="*")
    ap.add_argument("-o", "--out", default="Found")
    ap.add_argument("--fill", action="store_true", help="fill gaps into TRANS sheets")
    ap.add_argument("--inplace", action="store_true", help="write into TRANS directly")
    ap.add_argument("--find")
    ap.add_argument("--actors", action="store_true")
    ap.add_argument("--conflicts", action="store_true")
    ap.add_argument("--encoding")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = Config.load(a.config)
    out = Path(a.out)

    if a.find:
        st = Store(0.90).load((a.project or []) + (a.trans or []), a.encoding)
        e, lvl = st.lookup(a.find, True)
        print(f"[{lvl}] {esc(a.find)}" + (f"\n  -> {esc(e.val)}  ({e.src}:{e.line})" if e else ""))
        return

    troots = [Path(x) for x in (a.trans or [])]
    store = Store(0.92).load((a.project or []) + (a.trans or []), a.encoding)
    if a.fill:
        print(f"[dict] {len(store.exact)} keys loaded")

    root = Path(a.input) if a.input and Path(a.input).is_dir() else None
    actors, levels, rows, warns = Counter(), Counter(), [], []
    found_n = miss_n = 0
    dest = troots[0] if (a.inplace and troots) else out

    for f in iter_inputs(a.input) if a.input else []:
        doc = Document(f, a.encoding, cfg)
        rel = f.relative_to(root) if root else Path(f.name)
        warns += doc.warnings
        for b in doc.boxes:
            if b.speaker:
                actors[b.speaker] += 1

        pair = find_pair(troots, rel)
        sec = read_clean(pair, a.encoding) if pair else {}
        pa, ps = sec.get("actors", []), sec.get("scripts", [])
        if ps and len(ps) != len(doc.items):
            warns.append(f"{rel}: TRANS line count {len(ps)} != {len(doc.items)} boxes")
            ps = []
        if pa and len(pa) != len(doc.actors()):
            pa = []

        out_a, out_s, punct, log = [], [], [], []
        aset = set(doc.actors())
        for idx, n in enumerate(doc.actors()):
            cur = pa[idx].strip() if pa else ""
            if cur and cur != n and not looks_japanese(cur):
                out_a.append(cur); continue
            e, lvl = store.lookup(n, allow_fuzzy=False)
            if e and e.val.strip() and not looks_japanese(e.val):
                out_a.append(e.val.strip()); found_n += 1
                log.append(f"[NAME {lvl}] {n} -> {e.val.strip()}  ({e.src}:{e.line})")
            else:
                out_a.append(n); miss_n += 1
                log.append(f"[NAME MISS] {n}")

        for k, (i, b) in enumerate(doc.items):
            jp = box_key(b, "auto")
            po = is_punct_only(jp)
            cur = ps[k] if ps else ""
            if cur.strip() and cur.rstrip("\n") != jp.rstrip("\n") and (po or not looks_japanese(cur)):
                out_s.append(cur); levels["kept"] += 1; continue
            e, lvl = store.lookup(jp, not po, aset)
            if e:
                out_s.append(e.val); levels[lvl] += 1; found_n += 1
                log.append(f"[{lvl.upper()}] {f.stem}#{i:03d} {b.voice}\n"
                           f"  JP: {esc(jp)}\n  EN: {esc(e.val)}  ({e.src}:{e.line})")
            else:
                out_s.append(jp); levels["none"] += 1
                if po:
                    punct.append(jp)
                else:
                    miss_n += 1
                    log.append(f"[MISS] {f.stem}#{i:03d} {b.voice}  {esc(jp)}")

        if a.fill:
            write_clean(dest / rel, out_a, out_s)
            write_text(out / (str(rel) + ".fill.txt"), "\n".join(log) + "\n")
            print(f"[fill] {rel}: kept {levels['kept']}, filled/missing see {out}")
        else:
            rows += log

    if actors and a.actors:
        write_text(out / "actors.txt",
                   "\n".join(f"{k}\t{v}" for k, v in actors.most_common()) + "\n")
    if a.fill:
        write_text(out / "_fill_report.txt",
                   f"filled={found_n}  still missing={miss_n}\n"
                   f"destination={dest}\n")
        print(f"\nfilled={found_n}, still missing={miss_n} -> {dest}")
    else:
        write_text(out / "alignment.txt",
                   "\n".join([f"levels: {dict(levels)}", ""] + rows) + "\n")
        if a.conflicts and store.conflicts:
            write_text(out / "conflicts.txt", "\n".join(
                f"{esc(k)}\n  {esc(v1)} ({s1})\n  {esc(v2)} ({s2})"
                for k, v1, v2, s1, s2 in store.conflicts) + "\n")
        print(f"files actors={len(actors)} levels={dict(levels)} -> {out}")
    if warns:
        write_text(out / "warnings.txt", "\n".join(warns) + "\n")


if __name__ == "__main__":
    main()