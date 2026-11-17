#!/usr/bin/env python3
"""PROGRAM 1: Raw script -> clean, ordered translation sheet (one .txt per file)."""
from __future__ import annotations

import argparse
from pathlib import Path

from advscript import Config, Document, box_key, esc, iter_inputs, write_clean, write_text


def main():
    ap = argparse.ArgumentParser(description="Raw -> clean sheet")
    ap.add_argument("input")
    ap.add_argument("-o", "--out", default="Work")
    ap.add_argument("-r", "--recursive", action="store_true", default=True)
    ap.add_argument("--encoding")
    ap.add_argument("--config")
    ap.add_argument("--trailing-nl", choices=["auto", "always", "never"])
    ap.add_argument("--also-xuat", action="store_true", help="extra flat dictionary (opt-in)")
    a = ap.parse_args()

    cfg = Config.load(a.config)
    if a.trailing_nl:
        cfg.trailing_nl = a.trailing_nl
    root = Path(a.input) if Path(a.input).is_dir() else None
    out = Path(a.out)
    total = files = 0

    for f in iter_inputs(a.input, a.recursive):
        doc = Document(f, a.encoding, cfg)
        rel = f.relative_to(root) if root else Path(f.name)
        actors = doc.actors()
        keys = [box_key(b, cfg.trailing_nl) for _, b in doc.items]
        write_clean(out / rel, actors, keys)
        if a.also_xuat:
            body = [f"{esc(k)}=" for k in dict.fromkeys(keys)] + [f"{esc(n)}=" for n in actors]
            write_text(out / rel.with_suffix(".xuat.txt"), "\n".join(body) + "\n")
        total += len(keys)
        files += 1
        print(f"[ok] {rel}: {len(keys)} lines, {len(actors)} actors"
              + (f"  WARNINGS:{len(doc.warnings)}" if doc.warnings else ""))

    print(f"\n{files} file(s), {total} lines -> {out}")
    print("Translate these sheets, keep the line order and count, save into TRANS.")


if __name__ == "__main__":
    main()