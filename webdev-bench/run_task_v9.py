#!/usr/bin/env python3
"""WebDev-Bench v9: sequential requirement injection WITH per-round judge gate.
Per requirement: builder round -> mechanical health check -> lightweight judge gate
(glm-5.3-flash, one VLM call on screenshot+text vs this req's checklist; pass = all
visible items look >=2). Fail/timeout/won't-load -> retry SAME requirement with a
one-sentence user-voice feedback; retries draw from a fixed per-task time POOL
(n_req x 1200s). Pool exhausted -> task over. Official metrics still come from the
terminal full acceptance (identical to v7). Protocol tag v9_gated_v1.
Usage: python3 run_task_v9.py <task_dir> <results_dir> --builder-env <env_file>
                              --judge-url <OpenAI-compatible /v1 URL> [--judge-model ...]
                              [--accept-env <env_file>] [--image <sandbox image>]

Run from the directory that holds tasks/, SUBSET40.txt and the .cc_env.* files.
Env overrides: JUDGE_URL, JUDGE_MODEL, ACCEPT_ENV, WB_IMAGE.
"""
import argparse, base64, json, os, re, subprocess, sys, time, uuid
from pathlib import Path
import urllib.request
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from run_task import (sh, dexec, start_app, delivery_state, parse_obj, median,
                      ACCEPT_PROMPT, DEFAULT_IMAGE, DEFAULT_ACCEPT_ENV, norm_dim)  # noqa
from run_task import START_APP_SQUATTED  # noqa

POOL_PER_REQ = 1200; ROUND_CAP = 1500; MIN_ROUND = 180; MAX_ATTEMPTS = 3
FIRST_PROMPT = """You are a frontend engineer. The product manager will give you requirements one at a time; complete the current one first, and more requirements will follow (contents unknown), so keep the code evolvable.

[Current requirement]
{req}
{seed_hint}
[Delivery requirements]
1. The app must be runnable: maintain ./start.sh (start the service in the foreground at http://localhost:3000; prefer a static or dev-server approach).
2. Verify this requirement yourself, then stop the service (fuser -k 3000/tcp).
3. After completing this requirement, output one line: REQ_DONE: <one-sentence summary>

[Rules] Acceptance targets the running app; only user-observable behavior counts; do not write test files to pass acceptance; do not read or write the .qa directory."""
NEXT_PROMPT = """The product manager confirmed that the previous requirement passed and has raised the next requirement. Note: all previously completed requirements will be fully re-checked at final acceptance, so do not break them.

[Current requirement]
{req}

When done, likewise start the app to verify, stop the service, and output one line: REQ_DONE: <one-sentence summary>"""
RETRY_PROMPT = """The product manager has reviewed it; this requirement has not passed yet. Feedback:

[Feedback] {feedback}

[Still the current requirement]
{req}

Please fix it, then start the app to verify, stop the service, and output one line: REQ_DONE: <one-sentence summary>"""
GATE_SYS = "You are an acceptance reviewer. Based on the full-page screenshot and the page text, decide whether the implementation shown in the screenshot satisfies each acceptance point of this requirement. Rely only on observable evidence; when an interaction acceptance point cannot be confirmed from a static screenshot, pass it as long as the relevant UI element exists and shows no obvious flaw. Output strict JSON."
GATE_USER = """[This requirement]
{req}

[Acceptance points]
{items}

[Page text and console errors]
{pagetext}

Output JSON: {{"pass": true/false, "feedback": "if it fails, say in one sentence, in the product manager's voice, what is wrong (do not quote the acceptance points verbatim); if it passes, use an empty string"}}"""


def judge_gate(url, model, req, items, png, pagetext):
    b64 = base64.b64encode(Path(png).read_bytes()).decode() if png and Path(png).exists() else None
    content = [{"type": "text", "text": GATE_USER.format(req=req, items=items, pagetext=pagetext[:4000])}]
    if b64: content.insert(0, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}})
    body = json.dumps({"model": model, "max_tokens": 8000, "temperature": 0,
                       "messages": [{"role": "system", "content": GATE_SYS}, {"role": "user", "content": content}]}).encode()
    errs = []
    for attempt in range(3):
        try:
            rq = urllib.request.Request(url.rstrip("/") + "/chat/completions", data=body,
                                        headers={"Content-Type": "application/json", "Authorization": "Bearer dummy"})
            with urllib.request.urlopen(rq, timeout=180) as r:
                msg = json.loads(r.read())["choices"][0]["message"]
            # A thinking model sometimes leaves content empty and puts everything in
            # reasoning_content; read both rather than crashing into fail-open, which
            # would silently wave the requirement through.
            txt = (msg.get("content") or "") + "\n" + (msg.get("reasoning_content") or "")
            m = re.search(r'\{[^{}]*"pass"[^{}]*\}', txt, re.S)
            if m:
                o = json.loads(m.group(0))
                return bool(o.get("pass")), str(o.get("feedback", ""))[:300]
        except Exception as e:
            errs.append(str(e)[:150])
        time.sleep(5)
    # judge unreachable/unparseable -> fail-open (never punish the builder for infra),
    # but mark it so the report can tell a real pass from a degraded one.
    return None, "; ".join(errs[-2:])

def cc_round(cid, env_file, prompt, log_to, cont, cap):
    flag = "--continue " if cont else ""
    script = (f"timeout {max(int(cap) - 30, 60)} claude --print {flag}--dangerously-skip-permissions "
              f"-p {json.dumps(prompt)} 2>>/tmp/cc_stderr.log")
    r = dexec(cid, script, env_file=env_file, workdir="/workspace", timeout=int(cap))
    Path(log_to).write_text(r.stdout[-200000:])
    return r.stdout

def health_snap(cid, results_dir, tag):
    """start app, screenshot+text, kill. Returns (up, png_path, pagetext)."""
    up = start_app(cid)
    png = txt = None; pagetext = ""
    if up:
        r = dexec(cid, f"cd /workspace/.qa9 && NODE_PATH=/usr/lib/node_modules timeout 60 node snap.cjs "
                       f"/workspace/.qa9/{tag} && echo SNAP_OK", timeout=90)
        if "SNAP_OK" in r.stdout:
            sh(f"docker cp {cid}:/workspace/.qa9/{tag}.png {results_dir}/rounds/{tag}.png 2>/dev/null; true", timeout=60)
            sh(f"docker cp {cid}:/workspace/.qa9/{tag}.txt {results_dir}/rounds/{tag}.txt 2>/dev/null; true", timeout=60)
            png = results_dir / "rounds" / f"{tag}.png"
            tf = results_dir / "rounds" / f"{tag}.txt"
            if tf.exists():
                try:
                    d = json.loads(tf.read_text()); pagetext = d.get("text", "") + " | console_errors: " + json.dumps(d.get("console_errors", []), ensure_ascii=False)
                except Exception: pass
    dexec(cid, "fuser -k 3000/tcp 2>/dev/null; sleep 1; true", timeout=60)
    return up, (str(png) if png and Path(png).exists() else None), pagetext

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task_dir"); ap.add_argument("results_dir")
    ap.add_argument("--builder-env", required=True)
    ap.add_argument("--judge-url", default=os.environ.get("JUDGE_URL", ""),
                    help="OpenAI-compatible judge endpoint (default: $JUDGE_URL)")
    ap.add_argument("--judge-model", default=os.environ.get("JUDGE_MODEL", "glm-5.3-flash"),
                    help="model name sent to the gate judge (default: $JUDGE_MODEL)")
    ap.add_argument("--accept-env", default=DEFAULT_ACCEPT_ENV,
                    help="env file for the terminal QA accept agent (default: $ACCEPT_ENV)")
    ap.add_argument("--image", default=os.environ.get("WB_IMAGE", "vision2web-sandbox:wbench7"),
                    help="sandbox image (default: $WB_IMAGE)")
    a = ap.parse_args()
    if not a.judge_url:
        ap.error("--judge-url is required (or set JUDGE_URL)")
    if not a.accept_env:
        ap.error("--accept-env is required (or set ACCEPT_ENV)")
    task_dir, results_dir = Path(a.task_dir), Path(a.results_dir)
    task = json.loads((task_dir / "task.json").read_text()); tid = task["task_id"]
    if (results_dir / "report.json").exists(): print(f"[{tid}] skip(done)"); return
    # A banked build (build.tar, no report) is waiting for re-acceptance; never rebuild it.
    if (results_dir / "build.tar").exists(): print(f"[{tid}] skip(banked)"); return
    results_dir.mkdir(parents=True, exist_ok=True); (results_dir / "rounds").mkdir(exist_ok=True)
    claim = results_dir / ".claim"
    if claim.exists(): print(f"[{tid}] skip(claimed)"); return
    claim.write_text(str(time.time()))
    milestones = task["milestones"]; items = task["checklist"]
    by_m = {}
    for i in items: by_m.setdefault(i["m"], []).append(i)
    # checklist[].m is a 1-based foreign key into milestones; fail loudly if that ever drifts.
    if set(by_m) != set(range(1, len(milestones) + 1)):
        raise SystemExit(f"[{tid}] checklist m keys {sorted(by_m)} != 1..{len(milestones)}")
    pool = POOL_PER_REQ * len(milestones)
    cid = f"wb9-{tid}-{uuid.uuid4().hex[:6]}"
    sh(f"docker rm -f {cid} 2>/dev/null; true", timeout=60)
    sh(f"docker run -d --name {cid} {a.image} sleep infinity", timeout=300, check=True)
    report = {"task": tid, "protocol": "v9_gated_v1", "container": cid, "pool_seconds": pool, "rounds": []}
    ok = False
    try:
        dexec(cid, "mkdir -p /workspace/.qa9 /workspace/.qa/screens", timeout=30)
        sh(f"docker cp {HERE}/snap.cjs {cid}:/workspace/.qa9/snap.cjs", timeout=60)
        proto = task_dir / "prototypes"
        if proto.exists(): sh(f"docker cp {proto} {cid}:/workspace/prototypes", timeout=300)
        repo = task_dir / "repo"; seed_hint = "\n"
        if repo.exists():
            sh(f"docker cp {repo}/. {cid}:/workspace/", timeout=600)
            seed_hint = "\nAn existing repository is already in the current directory; modify it in place (install the dependencies yourself first and run it to see its current state).\n"
        if (proto / "reference.jpg").exists():
            seed_hint += "The reference screenshot is at ./prototypes/reference.jpg; please look at it carefully before you start work.\n"
        t_all0 = time.time(); first_round = True; pool_left = pool
        for j, m in enumerate(milestones, 1):
            gate_items = "\n".join(f"- {i['description']}" for i in by_m[j])
            passed = False; attempt = 0; feedback = ""
            while pool_left > MIN_ROUND and not passed and attempt < MAX_ATTEMPTS:
                attempt += 1
                if attempt == 1:
                    prompt = (FIRST_PROMPT.format(req=m["request"], seed_hint=seed_hint) if first_round
                              else NEXT_PROMPT.format(req=m["request"]))
                else:
                    prompt = RETRY_PROMPT.format(feedback=feedback, req=m["request"])
                cap = min(ROUND_CAP, pool_left)
                t0 = time.time()
                print(f"[{tid}] req{j} attempt{attempt} cap={int(cap)} pool={int(pool_left)}", flush=True)
                out = cc_round(cid, a.builder_env, prompt, results_dir / "rounds" / f"build_r{j}_a{attempt}.log",
                               cont=not first_round, cap=cap)
                first_round = False
                spent = time.time() - t0; pool_left -= spent
                rec = {"req": j, "attempt": attempt, "seconds": round(spent), "req_done": "REQ_DONE" in out}
                t_gate = time.time()
                up, png, pagetext = health_snap(cid, results_dir, f"req{j}_a{attempt}")
                rec["health"] = up
                if not up:
                    feedback = "The app does not start anymore (localhost:3000 will not come up); fix it first so that ./start.sh starts normally."
                    rec["gate"] = "health_fail"
                else:
                    g, fb = judge_gate(a.judge_url, a.judge_model, m["request"], gate_items, png, pagetext)
                    if g is None:
                        rec["gate"] = "fail_open"; rec["judge_error"] = fb; passed = True
                    elif g:
                        rec["gate"] = "pass"; passed = True
                    else:
                        rec["gate"] = "fail"; rec["feedback"] = fb
                        feedback = fb or "This requirement is not fully implemented yet; please check it again against the original requirement text."
                rec["gate_seconds"] = round(time.time() - t_gate)
                pool_left -= (time.time() - t_gate)
                report["rounds"].append(rec)
            report.setdefault("req_outcome", {})[f"req{j}"] = {
                "passed": passed, "attempts": attempt,
                "stopped_by": ("pass" if passed else
                               "attempt_cap" if attempt >= MAX_ATTEMPTS else "pool")}
            if pool_left <= MIN_ROUND:
                report["pool_exhausted_at_req"] = j
                break
        report["build_seconds_total"] = round(time.time() - t_all0)
        report["pool_left"] = round(max(pool_left, 0))
        sh(f"docker exec {cid} bash -c 'cd /workspace && tar --exclude=node_modules --exclude=.qa --exclude=.qa9 -cf /tmp/build.tar .'", timeout=300)
        sh(f"docker cp {cid}:/tmp/build.tar {results_dir}/build.tar", timeout=300)
        # ---- terminal acceptance: identical to v7 ----
        groups = {}
        for i in items: groups.setdefault(i["m"], []).append({k: i[k] for k in ("id", "description", "dimension", "w")})
        checklist = json.dumps([{"requirement": mm, "items": v} for mm, v in sorted(groups.items())], ensure_ascii=False, indent=1)
        report["delivery_contract"] = delivery_state(cid)
        verdicts, br = [], []
        for rep in range(1):
            up = start_app(cid); br.append(up)
            if not up: continue
            sp = ACCEPT_PROMPT.format(checklist=checklist, rep=rep)
            obj = None
            for extra in range(4):
                if extra:
                    # The judge gateway sheds load under campaign-wide concurrency
                    # ("no channel ... under group default"). Back off instead of
                    # burning all retries inside the same bad minute.
                    time.sleep(120 * extra)
                r = dexec(cid, f"timeout 2340 claude --print --dangerously-skip-permissions -p {json.dumps(sp)} 2>>/tmp/cc_stderr.log",
                          env_file=a.accept_env, workdir="/workspace/.qa", timeout=2400)
                (results_dir / f"accept_rep{rep}{'_retry'+str(extra) if extra else ''}.log").write_text(r.stdout[-200000:])
                obj = parse_obj(r.stdout)
                if obj: break
                dexec(cid, "fuser -k 3000/tcp 2>/dev/null; true", timeout=60)
                if extra < 3 and not start_app(cid): break
            dexec(cid, "fuser -k 3000/tcp 2>/dev/null; true", timeout=60)
            if obj:
                verdicts.append({v["id"]: max(0, min(3, int(v["grade"]))) for v in obj.get("items", [])
                                 if "id" in v and isinstance(v.get("grade"), (int, float))})
        sh(f"docker cp {cid}:/workspace/.qa/screens {results_dir}/screens 2>/dev/null; true", timeout=300)
        report["port_squatted"] = cid in START_APP_SQUATTED
        if not verdicts and not any(br):
            report["metrics"] = {"RC": 0.0, "FS": 0.0, "IS": 0.0, "VS_items": 0.0, "BR": 0.0,
                                 "per_requirement": {}, "item_grades": {}, "n_accept_reps": 0, "undelivered": True,
                                 "delivery_contract": report.get("delivery_contract")}
            (results_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1)); ok = True
            print(f"[{tid}] UNDELIVERED", flush=True); return
        if not verdicts:
            (results_dir / "ACCEPT_FAILED").write_text("0 valid reps\n"); claim.unlink(missing_ok=True); return
        item_grade = {}
        for i in items:
            votes = [v[i["id"]] for v in verdicts if i["id"] in v]
            item_grade[i["id"]] = median(votes) if votes else 0
        dim = {i["id"]: norm_dim(i["dimension"]) for i in items}; w = {i["id"]: i.get("w", 1.0) for i in items}
        def agg(ids):
            tw = sum(w[x] for x in ids)
            return round(sum(w[x] * item_grade[x] / 3 for x in ids) / tw, 4) if tw else None
        req_scores = {f"req{mm}": agg([x["id"] for x in v]) for mm, v in sorted(groups.items())}
        report["metrics"] = {"RC": round(sum(req_scores.values()) / len(req_scores), 4),
                             "FS": agg([i for i in dim if dim[i] in ("functional", "coverage")]),
                             "IS": agg([i for i in dim if dim[i] == "interaction"]),
                             "VS_items": agg([i for i in dim if dim[i] == "visual"]),
                             "BR": round(sum(br) / len(br), 2) if br else 0.0,
                             "per_requirement": req_scores, "item_grades": item_grade, "n_accept_reps": len(verdicts)}
        (results_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
        print(f"[{tid}] DONE {json.dumps(report['metrics'], ensure_ascii=False)[:150]}", flush=True); ok = True
    finally:
        try:
            r = dexec(cid, "tail -c 20000 /tmp/cc_stderr.log 2>/dev/null", timeout=60)
            (results_dir / "cc_stderr.log").write_text(r.stdout)
        except Exception: pass
        sh(f"docker rm -f {cid} 2>/dev/null; true", timeout=120)
        if not ok: print(f"[{tid}] FAILED", flush=True)

if __name__ == "__main__":
    main()
