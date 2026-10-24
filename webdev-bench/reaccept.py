#!/usr/bin/env python3
"""Re-run acceptance from a stored build.tar (no rebuild; preserves single-build protocol).
Usage: python3 reaccept.py <task_id> --src results/<line> --out results/<line>_reaccept
       [--prompt strict|v1] --accept-env <env_file> [--tasks-dir tasks] [--image <sandbox image>]

Env overrides: ACCEPT_ENV, WB_IMAGE.
"""
import argparse, json, os, sys, time, uuid

# Acceptance wall clock. A few tasks stall the QA agent past the default; raising it
# for those is preferable to dropping them from the plate.
ACCEPT_TIMEOUT = int(os.environ.get("ACCEPT_TIMEOUT", "2400"))
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from run_task import (sh, dexec, cc, start_app, START_APP_SQUATTED, parse_obj, median,
                      ACCEPT_PROMPT as ACCEPT_PROMPT_V1, ACCEPT_PROMPT_STRICT,
                      DEFAULT_IMAGE, DEFAULT_ACCEPT_ENV, norm_dim)  # noqa


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id"); ap.add_argument("--src", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--prompt", default="strict", choices=["strict", "v1"])
    ap.add_argument("--accept-env", default=DEFAULT_ACCEPT_ENV,
                    help="env file for the QA accept agent (default: $ACCEPT_ENV)")
    ap.add_argument("--tasks-dir", default=str(HERE / "tasks"),
                    help="directory holding <task_id>/task.json (default: ./tasks)")
    ap.add_argument("--image", default=DEFAULT_IMAGE,
                    help="sandbox image (default: $WB_IMAGE)")
    ap.add_argument("--accept-reps", type=int, default=1)
    a = ap.parse_args()
    if not a.accept_env:
        ap.error("--accept-env is required (or set ACCEPT_ENV)")
    tid = a.task_id
    src = Path(a.src) / tid; outdir = Path(a.out) / tid
    tar = src / "build.tar"
    if not tar.exists(): print(f"[{tid}] no build.tar, skip"); return
    if (outdir / "report.json").exists(): print(f"[{tid}] skip(done)"); return
    outdir.mkdir(parents=True, exist_ok=True)
    claim = outdir / ".claim"
    if claim.exists(): print(f"[{tid}] skip(claimed)"); return
    claim.write_text(str(time.time()))
    task = json.loads((Path(a.tasks_dir) / tid / "task.json").read_text())
    prompt_tpl = ACCEPT_PROMPT_STRICT if a.prompt == "strict" else ACCEPT_PROMPT_V1
    cid = f"wbr-{tid}-{uuid.uuid4().hex[:6]}"
    sh(f"docker rm -f {cid} 2>/dev/null; true", timeout=60)
    sh(f"docker run -d --name {cid} {a.image} sleep infinity", timeout=300, check=True)
    report = {"task": tid, "protocol": f"v5_aligned_reaccept_{a.prompt}", "container": cid, "build_from": str(tar)}
    ok = False
    try:
        sh(f"docker cp {tar} {cid}:/tmp/build.tar", timeout=300)
        dexec(cid, "cd /workspace && tar -xf /tmp/build.tar && mkdir -p /workspace/.qa/screens", timeout=300)
        # build.tar excludes node_modules; restore deps so "delivered" is not
        # penalised by the archive format (the builder's container had them).
        r = dexec(cid, "ls /workspace/start.sh >/dev/null 2>&1 && echo HAS_START || echo NO_START", timeout=60)
        report["start_sh_present"] = "HAS_START" in r.stdout
        # restore deps (build.tar excludes node_modules). NOTE: sh() runs the
        # docker exec through an outer shell, so the script must contain NO $vars
        # (the outer shell would expand them first) -> use find -execdir.
        inst_cmd = (
            "find /workspace -maxdepth 2 -name package.json -not -path '*/node_modules/*' "
            "-execdir sh -c 'test -d node_modules || timeout 900 npm install --no-audit --no-fund --silent "
            ">>/tmp/npm.log 2>&1' ';' ; "
            "echo INSTALL_DONE; find /workspace -maxdepth 3 -name node_modules -maxdepth 3 -prune | head -3"
        )
        inst = dexec(cid, inst_cmd, timeout=ACCEPT_TIMEOUT)
        report["deps_install_out"] = inst.stdout.strip()[-300:]
        report["deps_installed"] = "INSTALL_DONE" in inst.stdout
        items = task["checklist"]
        groups = {}
        for i in items: groups.setdefault(i["m"], []).append({k: i[k] for k in ("id", "description", "dimension", "w")})
        checklist = json.dumps([{"requirement": m, "items": v} for m, v in sorted(groups.items())], ensure_ascii=False, indent=1)
        verdicts, br = [], []
        for rep in range(a.accept_reps):
            up = start_app(cid); br.append(up)
            if not up: continue
            out = cc(cid, a.accept_env, prompt_tpl.format(checklist=checklist, rep=rep), "/workspace/.qa", ACCEPT_TIMEOUT, outdir / f"accept_rep{rep}.log")
            dexec(cid, "fuser -k 3000/tcp 2>/dev/null; true", timeout=60)
            obj = parse_obj(out)
            if obj is None:
                for extra in range(2):
                    print(f"[{tid}] rep{rep} unparseable, retry {extra + 1}/2", flush=True)
                    # The judge gateway sheds load under campaign-wide concurrency and
                    # answers "no channel ... under group default". Back off so the
                    # retries do not all land inside the same bad minute.
                    time.sleep(120 * (extra + 1))
                    if not start_app(cid):
                        break
                    out = cc(cid, a.accept_env, prompt_tpl.format(checklist=checklist, rep=rep), "/workspace/.qa", ACCEPT_TIMEOUT, outdir / f"accept_rep{rep}_retry{extra + 1}.log")
                    dexec(cid, "fuser -k 3000/tcp 2>/dev/null; true", timeout=60)
                    obj = parse_obj(out)
                    if obj:
                        break
            if obj:
                verdicts.append({v["id"]: max(0, min(3, int(v["grade"]))) for v in obj.get("items", []) if "id" in v and isinstance(v.get("grade"), (int, float))})
        sh(f"docker cp {cid}:/workspace/.qa/screens {outdir}/screens 2>/dev/null; true", timeout=300)
        report["port_squatted"] = cid in START_APP_SQUATTED
        if not verdicts and not any(br):
            report["metrics"] = {"RC": 0.0, "FS": 0.0, "IS": 0.0, "VS_items": 0.0, "BR": 0.0,
                                 "per_requirement": {}, "item_grades": {}, "n_accept_reps": 0,
                                 "undelivered": True, "port_squatted": report["port_squatted"]}
            (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1)); ok = True
            print(f"[{tid}] UNDELIVERED -> zero report", flush=True); return
        if not verdicts:
            (outdir / "ACCEPT_FAILED").write_text("0 valid acceptance reps\n"); claim.unlink(missing_ok=True)
            print(f"[{tid}] ACCEPT-FAILED", flush=True); return
        item_grade = {}
        for i in items:
            votes = [v[i["id"]] for v in verdicts if i["id"] in v]
            item_grade[i["id"]] = median(votes) if votes else 0
        dim = {i["id"]: norm_dim(i["dimension"]) for i in items}; w = {i["id"]: i.get("w", 1.0) for i in items}
        def agg(ids):
            tw = sum(w[x] for x in ids)
            return round(sum(w[x] * item_grade[x] / 3 for x in ids) / tw, 4) if tw else None
        req_scores = {f"req{m}": agg([x["id"] for x in v]) for m, v in sorted(groups.items())}
        report["metrics"] = {"RC": round(sum(req_scores.values()) / len(req_scores), 4),
                             "FS": agg([i for i in dim if dim[i] in ("functional", "coverage")]),
                             "IS": agg([i for i in dim if dim[i] == "interaction"]),
                             "VS_items": agg([i for i in dim if dim[i] == "visual"]),
                             "BR": round(sum(br) / len(br), 2) if br else 0.0,
                             "per_requirement": req_scores, "item_grades": item_grade, "n_accept_reps": len(verdicts)}
        (outdir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
        print(f"[{tid}] DONE {json.dumps(report['metrics'], ensure_ascii=False)[:160]}", flush=True); ok = True
    finally:
        sh(f"docker rm -f {cid} 2>/dev/null; true", timeout=120)
        if not ok: print(f"[{tid}] FAILED", flush=True)

if __name__ == "__main__":
    main()
