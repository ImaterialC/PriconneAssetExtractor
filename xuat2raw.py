#!/usr/bin/env python3
"""PROGRAM 2: Trans sheets + Raw skeleton -> translated Raw + missing report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for sdir in [Path(__file__).parent, Path(__file__).parent.parent, Path("d:/priconne-asset-extractor-main")]:
    if (sdir / "asset_registry.py").exists() and str(sdir) not in sys.path:
        sys.path.insert(0, str(sdir))
import asset_registry

from advscript import (Config, Document, Store, box_key, esc, inject, is_clean,
                       is_punct_only, iter_inputs, load_lines, looks_japanese,
                       read_clean, write_clean, write_text,
                       generate_status_report, prompt_xuat_cleanup)


def find_pair(roots, rel):
    for r in roots:
        for p in (r / rel, r / Path(rel).name):
            if p.is_file():
                return p
    return None


def main():
    ap = argparse.ArgumentParser(description="Trans -> Raw")
    ap.add_argument("input", help="Raw file or folder")
    ap.add_argument("-t", "--trans", nargs="*", default=[], help="translation sheet folder(s)")
    ap.add_argument("-p", "--project", nargs="*", default=[], help="XUAT dictionary folder(s)")
    ap.add_argument("-o", "--out", default="Out")
    ap.add_argument("--bundles", help="folder containing original .unity3d bundles to repack into")
    ap.add_argument("--repack-out", default="output", help="folder to save repacked .unity3d bundles")
    ap.add_argument("--repack", action="store_true", help="repack into .unity3d bundle after translation")
    ap.add_argument("-r", "--recursive", action="store_true", default=True)
    ap.add_argument("--encoding")
    ap.add_argument("--config")
    ap.add_argument("--mode", choices=["first", "spread"], default="first")
    ap.add_argument("--fill", choices=["space", "zwsp", "drop"], default="space")
    ap.add_argument("--pair", choices=["auto", "off"], default="auto")
    ap.add_argument("--fuzzy", type=float, default=0.92)
    ap.add_argument("--no-fuzzy", action="store_true")
    ap.add_argument("--no-actors", action="store_true")
    ap.add_argument("--include-punct", action="store_true")
    ap.add_argument("--break-char", choices=["auto", "cr", "lf"])
    ap.add_argument("--no-interactive", action="store_true", help="disable interactive conflict prompts")
    ap.add_argument("--reprocess", nargs="*", default=[], help="specific asset stems to force reprocess")
    ap.add_argument("--no-skip-existing", dest="skip_existing", action="store_false", default=True)
    ap.add_argument("--report-unused", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cfg = Config.load(a.config)
    if a.break_char:
        cfg.break_char = {"auto": "auto", "cr": "\r", "lf": "\n"}[a.break_char]
    cfg.filler = {"space": " ", "zwsp": "\u200b", "drop": "drop"}[a.fill]

    troots = [Path(x) for x in a.trans]
    sources = list(a.trans or []) + list(a.project or [])
    if not sources:
        for bat in [Path("adv_paths.bat"), Path(__file__).parent / "adv_paths.bat"]:
            if bat.exists():
                for line in bat.read_text("utf-8", errors="replace").splitlines():
                    if line.startswith('set "PROJECT=') and line.endswith('"'):
                        pval = line[len('set "PROJECT='):-1].strip()
                        if pval and Path(pval).exists():
                            sources = [pval]
                            print(f"[auto-detect] Using PROJECT from adv_paths.bat: {pval}")
                            break
                if sources:
                    break
    if not sources:
        print("[warn] No translation source (-t or -p) provided, and PROJECT not found in adv_paths.bat.")
    store = Store(0.0 if a.no_fuzzy else a.fuzzy).load(sources, a.encoding)
    print(f"[dict] {len(store.exact)} keys, {len(store.conflicts)} conflicts")

    ws = asset_registry.BepInExWorkspace.resolve(sources[0] if sources else None)
    redirect_index = asset_registry.RedirectIndex(ws.redirected_resources_dir) if ws.redirected_exists() else None
    if redirect_index:
        print(f"[redirect-index] Indexed {redirect_index.total_count:,} bundles from RedirectedResources")

    root = Path(a.input) if Path(a.input).is_dir() else None
    out = Path(a.out)
    fillers = {"space": "a single ASCII space", "zwsp": "U+200B zero-width space",
               "drop": "extra focus records deleted"}
    agg_a, agg_s, agg_p, warns, rep = {}, {}, {}, [], []
    tot = dict(files=0, boxes=0, hit=0, miss=0, paired=0, fuzzy=0, norm=0, names=0)
    file_reports = []
    repacked_entries = []

    for f in iter_inputs(a.input, a.recursive):
        doc = Document(f, a.encoding, cfg)
        rel = f.relative_to(root) if root else Path(f.name)
        aset = set(doc.actors())

        pair_a = pair_s = None
        pair = find_pair(troots, rel) if a.pair == "auto" else None
        if pair:
            plines, _ = load_lines(pair, a.encoding)
            if is_clean(plines):
                sec = read_clean(pair, a.encoding)
                pa, ps = sec.get("actors", []), sec.get("scripts", [])
                if len(ps) == len(doc.items):
                    pair_s = ps
                else:
                    doc.warnings.append(
                        f"PAIR MISMATCH {pair.name}: {len(ps)} lines vs "
                        f"{len(doc.items)} boxes - positional pairing disabled")
                if len(pa) == len(doc.actors()):
                    pair_a = pa
                elif pa:
                    doc.warnings.append(
                        f"ACTOR MISMATCH {pair.name}: {len(pa)} vs {len(doc.actors())}")
            else:
                pair = None

        rows, missing, punct, miss_names = [], [], [], []
        file_used_entries = []
        hit = 0
        hit_real = 0
        for k, (i, b) in enumerate(doc.items):
            jp = box_key(b, "auto")
            po = is_punct_only(jp)
            en = lvl = src = None
            matched_entry = None
            if pair_s is not None:
                v = pair_s[k]
                if v.strip() and v.rstrip("\n") != jp.rstrip("\n") and (po or not looks_japanese(v)):
                    en, lvl, src = v, "pair", str(pair)
            if en is None:
                e, lvl2 = store.lookup_resolved(jp, not a.no_fuzzy, aset, interactive=not a.no_interactive, context=f"{f.name}#{i:03d}")
                if e:
                    en, lvl, src = e.val, lvl2, f"{e.src}:{e.line}"
                    matched_entry = e
            bid = f"{f.stem}#{i:03d}"
            if en is not None:
                hit += 1
                if not po:
                    hit_real += 1
                inject(doc, b, en, a.mode, cfg.filler)
                rows.append({"id": bid, "voice": b.voice, "speaker": b.speaker,
                             "level": lvl, "jp": jp, "en": en, "src": src})
                if matched_entry:
                    file_used_entries.append(matched_entry)
                if lvl in ("norm", "fuzzy"):
                    warns.append(f"[{lvl.upper()}] {bid} {b.voice}\n"
                                 f"  raw : {esc(jp)}\n  dict: {esc(en)}  ({src})")
            else:
                rec = {"id": bid, "voice": b.voice, "speaker": b.speaker, "jp": jp}
                if po and not a.include_punct:
                    punct.append(rec)
                    agg_p.setdefault(jp, None)
                else:
                    missing.append(rec)
                    agg_s.setdefault(jp, None)

        names_out = []
        if not a.no_actors:
            for idx, n in enumerate(doc.actors()):
                val = None
                if pair_a is not None:
                    v = pair_a[idx].strip()
                    if v and v != n and not looks_japanese(v):
                        val = v
                if val is None:
                    val = store.resolve_actor(n)
                if val:
                    doc.rename_speaker(n, val)
                    names_out.append(f"{n} -> {val}")
                else:
                    miss_names.append(n)
                    agg_a.setdefault(n, None)

        missing_real = [m for m in missing if not is_punct_only(m["jp"])]
        real_boxes_count = len([b for _, b in doc.items if not is_punct_only(box_key(b, "auto"))])
        is_complete = (len(missing_real) == 0 and real_boxes_count > 0)
        was_repacked = False

        if not a.dry_run:
            doc.save(out / rel)
            if a.repack or a.bundles:
                ident = asset_registry.AssetIdentity.create(f, root)
                matched_redir = None
                if redirect_index and a.skip_existing:
                    lvl, matched_redir, _ = redirect_index.find_match(ident)
                    reproc_stems = [x.lower() for x in a.reprocess]
                    if matched_redir and f.stem.lower() not in reproc_stems and ident.asset_id.lower() not in reproc_stems:
                        print(f"  [SKIP REPACK] {f.stem}: Already implemented in RedirectedResources as '{matched_redir.name}'.")
                        is_complete = False

                if not is_complete:
                    if not (redirect_index and matched_redir and a.skip_existing):
                        print(f"  [SKIP REPACK] {f.stem}: Incomplete ({len(missing_real)} line(s) missing). Only 100% complete files can be repacked.")
                else:
                    bundle_src = None
                    bundle_dirs = [Path(a.bundles)] if a.bundles else []
                    bundle_dirs += [Path("input"), Path("../input"), Path("d:/priconne-asset-extractor-main/input"), f.parent]
                    for bdir in bundle_dirs:
                        if bdir and bdir.exists():
                            for cand in [bdir / (f.stem + ".unity3d"), bdir / (f.stem + ".asset"), bdir / f.name]:
                                if cand.is_file() and cand.suffix.lower() in (".unity3d", ".asset"):
                                    bundle_src = cand
                                    break
                        if bundle_src:
                            break
                    if bundle_src:
                        try:
                            import sys
                            for sdir in [Path(__file__).parent, Path(__file__).parent.parent, Path("d:/priconne-asset-extractor-main")]:
                                if str(sdir) not in sys.path and (sdir / "priconne_tool.py").exists():
                                    sys.path.insert(0, str(sdir))
                            import priconne_tool
                            env, kind, obj = priconne_tool.load_bundle(bundle_src)
                            if kind == "story":
                                orig_raw = priconne_tool.story_bytes(obj)
                                orig_recs = priconne_tool.parse_story(orig_raw)
                                out_text = (out / rel).read_text(encoding="utf-8")
                                recs = priconne_tool.text_to_recs(out_text)
                                warns_rep = []
                                new_data = priconne_tool.build_bytes(recs, orig_recs, warns_rep)
                                repack_out_dir = Path(a.repack_out)
                                target_fn = matched_redir.name if matched_redir else ident.flattened_name
                                repack_out_file = repack_out_dir / target_fn
                                repack_out_file.parent.mkdir(parents=True, exist_ok=True)
                                mode = priconne_tool.write_story_verified(env, obj, new_data, repack_out_file)
                                was_repacked = True
                                print(f"  [repack ok] {target_fn} ({mode}) -> {repack_out_file}")
                                repacked_entries.extend(file_used_entries)
                        except Exception as ex:
                            print(f"  [repack err] {f.stem}: {ex}")

        file_reports.append({
            "stem": f.stem,
            "file": str(f),
            "total_boxes": len(doc.items),
            "real_boxes": real_boxes_count,
            "hit_real": hit_real,
            "missing_real": len(missing_real),
            "missing_lines": [m["jp"] for m in missing_real],
            "missing_names": miss_names,
            "repacked": was_repacked,
        })

        tot["files"] += 1
        tot["boxes"] += len(doc.items)
        tot["hit"] += hit
        tot["miss"] += len(missing)
        tot["names"] += len(miss_names)
        tot["paired"] += sum(1 for r in rows if r["level"] == "pair")
        tot["norm"] += sum(1 for r in rows if r["level"] == "norm")
        tot["fuzzy"] += sum(1 for r in rows if r["level"] == "fuzzy")
        warns += doc.warnings

        L = [f"FILE   : {f}",
             f"PAIR   : {pair if pair_s is not None else '(none - dictionary matching)'}",
             f"BREAK  : {doc.break_char!r}   FILL: {fillers[a.fill]}",
             f"BOXES  : {len(doc.items)}   translated={hit}   missing={len(missing)}   "
             f"punct-only={len(punct)}", ""]
        if miss_names:
            L += ["== MISSING SPEAKER NAMES =="] + miss_names + [""]
        if names_out:
            L += ["== SPEAKER NAMES =="] + names_out + [""]
        if missing:
            L += ["== MISSING DIALOGUE =="]
            for m in missing:
                L += [f"{m['id']}  {m['voice']}  {m['speaker']}", f"  JP: {esc(m['jp'])}"]
            L += [""]
        if punct:
            L += ["== PUNCTUATION-ONLY (kept as-is, no translation needed) =="]
            L += [f"{m['id']}  {esc(m['jp'])}" for m in punct] + [""]
        L += ["== TRANSLATED (proofread order) =="]
        for r in rows:
            L += [f"{r['id']}  {r['voice']}  {r['speaker']}  [{r['level']}]",
                  f"  JP: {esc(r['jp'])}", f"  EN: {esc(r['en'])}"]
        if doc.warnings:
            L += ["", "== WARNINGS =="] + doc.warnings
        if not a.dry_run:
            write_text(out / (str(rel) + ".report.txt"), "\n".join(L) + "\n")
            if missing or miss_names:
                write_clean(out / (str(rel) + ".missing.txt"), miss_names,
                            [m["jp"] for m in missing], [m["jp"] for m in punct])
        rep.append({"file": str(f), "translated": hit, "missing": missing,
                    "missing_names": miss_names, "matched": rows})
        print(f"[{'dry' if a.dry_run else 'ok'}] {rel}: {hit}/{len(doc.items)} translated, "
              f"{len(missing)} lines + {len(miss_names)} names missing"
              + ("  [paired]" if pair_s is not None else ""))

    write_text(out / "_SUMMARY.txt", "\n".join([
        f"files={tot['files']}  boxes={tot['boxes']}  translated={tot['hit']}  "
        f"missing={tot['miss']}",
        f"paired={tot['paired']}  norm={tot['norm']}  fuzzy={tot['fuzzy']}  "
        f"missing names={tot['names']}",
        f"fill between segments: {fillers[a.fill]}", "",
        "MISSING SPEAKER NAMES:"] + [f"{k}" for k in agg_a]) + "\n")
    if agg_a or agg_s:
        write_clean(out / "_missing.txt", list(agg_a), list(agg_s), list(agg_p))
    if warns:
        write_text(out / "_warnings.txt", "\n".join(warns) + "\n")
    if store.conflicts:
        write_text(out / "_conflicts.txt", "\n".join(
            f"{esc(k)}\n  A({s1}): {esc(v1)}\n  B({s2}): {esc(v2)}"
            for k, v1, v2, s1, s2 in store.conflicts) + "\n")
    if a.report_unused:
        un = [e for k, e in store.exact.items() if k not in store.used and e.val.strip()]
        write_text(out / "_unused.txt",
                   "\n".join(f"{esc(e.key)}={esc(e.val)}" for e in un) + "\n")
    if a.json:
        write_text(out / "_report.json", json.dumps(rep, ensure_ascii=False, indent=1))

    status_summary = generate_status_report(file_reports, out)
    print("\n" + status_summary)

    if repacked_entries and not a.dry_run:
        prompt_xuat_cleanup(repacked_entries, out, interactive=not a.no_interactive)

    print(f"\n{tot}\n-> {out}")


if __name__ == "__main__":
    main()