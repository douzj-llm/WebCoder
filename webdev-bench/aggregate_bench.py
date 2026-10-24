#!/usr/bin/env python3
"""Aggregate WebDev-Bench line results.

Columns: RS-like legacy keys RC, FS, IS, VS (replicate: component score from
visual.json; others: VS_items), and delivery rate BR.

By default the task list is SUBSET40.txt next to this file; --task-list picks
another list, --all aggregates every task directory present. Task metadata is
read from --tasks-dir (default: ./tasks).

Usage: python3 aggregate_bench.py results/<line> [more result dirs...]
                                      [--task-list SUBSET40.txt] [--tasks-dir tasks|--all]
"""
import argparse, json, statistics
from pathlib import Path

HERE = Path(__file__).parent


def mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(statistics.mean(xs), 4) if xs else None


def load_task(tasks_dir, tid):
    return json.loads((tasks_dir / tid / "task.json").read_text())


def line(rd, exam, tasks_dir):
    rows = []
    for rep in sorted(Path(rd).glob("*/report.json")):
        tid = rep.parent.name
        if exam is not None and tid not in exam:
            continue
        d = json.load(open(rep)); m = d.get("metrics", {})
        task = load_task(tasks_dir, tid)
        seed = task.get("seed_type")
        fs = m.get("FS", m.get("F")); is_ = m.get("IS", m.get("I")); vsi = m.get("VS_items", m.get("V_items"))
        vs = None
        vj = rep.parent/"visual.json"
        if vj.exists():
            try: vs = json.load(open(vj)).get("VS", json.load(open(vj)).get("V"))
            except Exception: pass
        if vs is None and seed != "replicate":
            vs = vsi
        rows.append(dict(task=tid, seed=seed, layer=task.get("layer"), RC=m.get("RC"),
                         FS=fs, IS=is_, VS=vs, VS_items=vsi, BR=m.get("BR")))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result_dirs", nargs="+")
    ap.add_argument("--task-list", default=str(HERE / "SUBSET40.txt"),
                    help="task ids to aggregate (default: SUBSET40.txt)")
    ap.add_argument("--tasks-dir", default="tasks",
                    help="directory holding <task_id>/task.json")
    ap.add_argument("--all", action="store_true",
                    help="aggregate every task directory present, ignoring the task list")
    a = ap.parse_args()
    tasks_dir = Path(a.tasks_dir)
    exam = None
    if not a.all:
        tl = Path(a.task_list)
        if not tl.exists():
            ap.error(f"task list not found: {tl} (pass --task-list or --all)")
        exam = set(tl.read_text().split())
    for rd in a.result_dirs:
        rows = line(rd, exam, tasks_dir)
        print(f"== {rd}: n={len(rows)}" + ("  [EXAM_50]" if exam is not None else "  [all tasks]"))
        for k in ("RC", "FS", "IS", "VS", "BR"):
            v = [r[k] for r in rows]
            got = sum(1 for x in v if isinstance(x, (int, float)))
            warn = ""
            if got != len(v):
                warn = f"  WARNING: {len(v) - got} task(s) have no {k} (denominator shrinks)"
            print(f"   {k}: mean={mean(v)} n={got}{warn}")
        for seed in ("replicate", "brownfield", "prd"):
            sub = [r for r in rows if r["seed"] == seed]
            if sub:
                print(f"   [{seed}] n={len(sub)} RC={mean([r['RC'] for r in sub])} "
                      f"VS={mean([r['VS'] for r in sub])} FS={mean([r['FS'] for r in sub])} "
                      f"IS={mean([r['IS'] for r in sub])}")
        low = sorted([(r['RC'], r['task']) for r in rows if isinstance(r['RC'], (int, float))])[:8]
        print("   lowest RC:", [(t, round(v, 3)) for v, t in low])
        json.dump(rows, open(Path(rd)/"aggregate_rows.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
