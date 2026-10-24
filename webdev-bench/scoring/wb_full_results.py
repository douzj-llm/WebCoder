#!/usr/bin/env python3
"""WebDev-Bench full results.

For every line (model), computes per-task metrics, then aggregates overall, by
task type and by empirical-difficulty tertile, plus per-dimension item grade-3
rates. Writes <out>/wb_full.json and a per-task RS matrix.

Usage: python3 wb_full_results.py --results-dir results --lines lines.json
                                  [--tasks-dir tasks] [--task-list SUBSET40.txt]
                                  [--out data]

lines.json maps display names to result subdirectories, e.g.
  {"WebCoder-27B": "qwen27b_rl29_v9", "Claude Opus 4.8": "opus48_v9_40"}

Paths are relative to the current directory; override with the flags above.
"""
import argparse, collections, json, os
from pathlib import Path

DIMS = {'功能': 'functional', '覆盖': 'coverage', '交互': 'interaction',
        '视觉': 'visual', '数据': 'data'}
FS_DIMS = {'functional', 'coverage'}; IS_DIMS = {'interaction'}; VS_DIMS = {'visual'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--lines", default="lines.json",
                    help="JSON object {display name: result subdirectory}")
    ap.add_argument("--tasks-dir", default="tasks")
    ap.add_argument("--task-list", default="SUBSET40.txt")
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    results = Path(a.results_dir); tasks_dir = Path(a.tasks_dir); out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    LINES = list(json.loads(Path(a.lines).read_text()).items())
    tasks = [l.strip() for l in open(a.task_list) if l.strip()]
    TJ = {t: json.load(open(tasks_dir / t / 'task.json')) for t in tasks}

    def grades(line, t):
        p = results / line / t / 'report.json'
        if not os.path.exists(p): return None, False
        m = json.load(open(p))['metrics']; g = m.get('item_grades') or {}
        if m.get('undelivered') or not g: return {}, False
        return {k: int(v) for k, v in g.items()}, True

    def task_metrics(line, t):
        tj = TJ[t]; cl = tj['checklist']; n = len(tj['milestones']); g, deliv = grades(line, t)
        def sat(items): return all(g.get(it['id'], 0) == 3 for it in items) if items else None
        reqs = [[it for it in cl if it['m'] == j + 1] for j in range(n)]
        RS = sum(bool(sat(r)) for r in reqs) / n
        def dimscore(dimset):
            vals = []
            for r in reqs:
                sub = [it for it in r if DIMS.get(it['dimension'], 'functional') in dimset]
                if sub: vals.append(1.0 if sat(sub) else 0.0)
            return sum(vals) / len(vals) if vals else None
        item3 = {}
        for it in cl:
            d = DIMS.get(it['dimension'], 'functional'); item3.setdefault(d, [0, 0]); item3[d][1] += 1
            item3[d][0] += (g.get(it['id'], 0) == 3)
        return dict(RS=RS, FS=dimscore(FS_DIMS), IS=dimscore(IS_DIMS), VS=dimscore(VS_DIMS),
                    deliv=deliv, item3=item3)

    data = {name: {t: task_metrics(line, t) for t in tasks} for name, line in LINES}
    # empirical difficulty: mean RS across all lines
    mean_rs = {t: sum(data[n][t]['RS'] for n, _ in LINES) / len(LINES) for t in tasks}
    order = sorted(tasks, key=lambda t: -mean_rs[t])
    third = len(order) // 3
    tiers = {'easy': order[:third], 'medium': order[third:2 * third], 'hard': order[2 * third:]}
    types = {ty: [t for t in tasks if TJ[t]['seed_type'] == ty]
             for ty in ('brownfield', 'replicate', 'prd')}

    def agg(name, ts):
        rows = [data[name][t] for t in ts]
        def m(k):
            v = [r[k] for r in rows if r[k] is not None]
            return sum(v) / len(v) if v else None
        it = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            for d, (x, y) in r['item3'].items(): it[d][0] += x; it[d][1] += y
        return dict(n=len(ts), RS=m('RS'), FS=m('FS'), IS=m('IS'), VS=m('VS'),
                    DSR=sum(r['deliv'] for r in rows) / len(rows),
                    item3={d: x / y for d, (x, y) in it.items()})

    res = {'lines': [n for n, _ in LINES], 'tasks': tasks,
           'task_type': {t: TJ[t]['seed_type'] for t in tasks},
           'task_nreq': {t: len(TJ[t]['milestones']) for t in tasks},
           'task_nitem': {t: len(TJ[t]['checklist']) for t in tasks},
           'mean_rs': mean_rs, 'tiers': tiers, 'types': types,
           'overall': {n: agg(n, tasks) for n, _ in LINES},
           'by_type': {ty: {n: agg(n, ts) for n, _ in LINES} for ty, ts in types.items()},
           'by_tier': {k: {n: agg(n, ts) for n, _ in LINES} for k, ts in tiers.items()},
           'rs_matrix': {n: {t: data[n][t]['RS'] for t in tasks} for n, _ in LINES}}
    json.dump(res, open(out / 'wb_full.json', 'w'), ensure_ascii=False, indent=1)
    for n, _ in LINES:
        o = res['overall'][n]
        print(f"{n:24s} RS {o['RS']:.3f} FS {o['FS']:.3f} IS {o['IS']:.3f} "
              f"VS {o['VS']:.3f} DSR {o['DSR']:.3f} item3 "
              + ' '.join(f"{d}:{v:.2f}" for d, v in o['item3'].items()))
    print('tier cuts', round(mean_rs[order[third - 1]], 3), round(mean_rs[order[2 * third - 1]], 3))


if __name__ == "__main__":
    main()
