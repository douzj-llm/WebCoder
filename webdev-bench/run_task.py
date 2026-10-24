#!/usr/bin/env python3
"""WebDev-Bench v3.1 task runner (v4 protocol: build-only, graded checklist,
screenshot archive; visual component scoring done offline by visual_score.py).

Build-only single-round runner: copy the task materials into a sandbox
container, let the builder agent implement every requirement in one session,
archive build.tar, then run the terminal QA acceptance and write report.json.

Usage: python3 run_task.py <task_dir> <results_dir> --builder-env <env_file>
                          --accept-env <env_file> [--image <sandbox image>]

Paths are relative to the current directory (run from the directory that holds
tasks/, SUBSET40.txt and the .cc_env.* files). Env overrides: ACCEPT_ENV,
WB_IMAGE.
"""
import argparse, json, os, re, subprocess, sys, time, uuid
from pathlib import Path

DEFAULT_IMAGE = os.environ.get("WB_IMAGE", "vision2web-sandbox:latest")
DEFAULT_ACCEPT_ENV = os.environ.get("ACCEPT_ENV", "")

# Checklist dimensions appear in Chinese in the original task data and in English
# in the translated data. Chinese spellings are kept as \u escapes (functional,
# coverage, interaction, visual, data respectively) so old result directories
# still score while the source tree stays ASCII-only.
DIM_ALIASES = {
    "\u529f\u80fd": "functional", "functional": "functional",
    "\u8986\u76d6": "coverage", "coverage": "coverage",
    "\u4ea4\u4e92": "interaction", "interaction": "interaction",
    "\u89c6\u89c9": "visual", "visual": "visual",
    "\u6570\u636e": "data", "data": "data",
}


def norm_dim(d):
    """Normalize a checklist dimension (Chinese or English, any casing) to its English key."""
    if isinstance(d, str):
        s = d.strip()
        return DIM_ALIASES.get(s, DIM_ALIASES.get(s.lower(), s.lower()))
    return d

BUILD_PROMPT = """You are a frontend engineer. You have been given a development spec containing multiple requirements. Please implement all requirements in the current repository.

[Requirements]
{requests}
{seed_hint}
[Delivery requirements]
1. The app must be runnable: maintain ./start.sh (start the service in the foreground at http://localhost:3000; prefer a static or dev-server approach and avoid installing system-level dependencies).
2. Verify it yourself before delivery: start the app and use playwright-cli to take screenshots to confirm it renders correctly and has no console errors; for requirements that involve interaction, actually perform the interaction; stop the service once verification is done (fuser -k 3000/tcp).
3. When everything is complete, output one line: ALL_DONE: <one-sentence summary>

[Rules] Acceptance targets the running app; only user-observable behavior counts; do not write test files to pass acceptance; do not read or write the .qa directory."""

ACCEPT_PROMPT = """You are a strict QA acceptance engineer. The app under test is running at http://localhost:3000 .

[Part 1 - Item-by-item checklist, tiered acceptance]
Below is the acceptance checklist (JSON), grouped by high-level requirement:
{checklist}
Accept each item: use playwright-cli to actually operate and observe (open/click/fill/screenshot), with at least one screenshot or page observation per item as evidence; interaction items must be actually performed; for items involving exact values or combined states, you must actually construct that state and check the value.

Give each item a discrete score in four tiers from 0-3 (anchored rubric, strictly enforced):
- 3 = fully satisfied: observable behavior exactly matches what the item requires, with no visible flaw;
- 2 = basically satisfied: core behavior is correct, but there are small flaws (minor deviations in copy, style, or edge-state details);
- 1 = partially satisfied: only part of the item is implemented, or the behavior is unstable and intermittently wrong;
- 0 = not implemented or unusable: the required behavior is absent, has no effect, or errors.
A 3 does not require "exceeding expectations" -- satisfying the item is enough; any downgrade must be backed by concrete evidence. A button that exists but does nothing when clicked cannot receive a high score.

[Part 2 - Full-site screenshot archive]
After acceptance, return to the home page's initial state and take a full-page screenshot saved to /workspace/.qa/screens/full_rep{rep}.png (the directory already exists; use playwright-cli screenshot in full-page mode).

[Rules] Reading the source code of the repository under test is strictly forbidden; modifying any file outside .qa is strictly forbidden; everything is judged by the running app.
[Output] Output only a single JSON object, with no markdown fences:
{{"items": [{{"id": "...", "grade": 0-3, "evidence": "..."}}, ...]}}"""


ACCEPT_PROMPT_STRICT = """You are an extremely strict QA acceptance engineer (the final gate before external delivery). The app under test is running at http://localhost:3000 .

[Part 1 - Item-by-item checklist, tiered acceptance (strict mode)]
Below is the acceptance checklist (JSON), grouped by high-level requirement:
{checklist}

Acceptance method (do every one of these for each item):
1. Break the item into a list of atomic assertions (each specific piece of copy, count, color/style, state, or behavior counts as one atomic assertion);
2. Verify each one with playwright-cli: text must be compared word for word (extra, missing, or wrong characters all count as a mismatch), counts must actually be counted,
   interactions must actually be performed with before/after screenshots, and exact values or combined states must actually be constructed and checked;
3. The default position is "not satisfied": only mark it satisfied when you have clear evidence; a missing element, a state you cannot construct, or a screenshot too blurry to read all count as that atomic assertion failing.

Tiers (strictly enforced; prefer downgrading over upgrading):
- 3 = every atomic assertion of the item is verified true one by one, with no visible deviation whatsoever;
- 2 = all core-behavior assertions are true, but there is at least one minor deviation (copy not exactly identical / style detail / edge state);
- 1 = more than half of the atomic assertions are true but the core behavior is missing or unstable; or the button/entry point exists but the corresponding behavior could not be verified;
- 0 = the core element or behavior is missing, has no effect, or errors, or most atomic assertions do not hold.
Do not hesitate to downgrade; before giving a 3 you must self-check: "Did I compare every piece of copy character by character, count every count, and actually perform every interaction?" If any one of these was not done, you cannot give a 3.

[Part 2 - Full-site screenshot archive]
After acceptance, return to the home page's initial state and take a full-page screenshot saved to /workspace/.qa/screens/full_rep{rep}.png (the directory already exists; use playwright-cli screenshot in full-page mode).

[Rules] Reading the source code of the repository under test is strictly forbidden; modifying any file outside .qa is strictly forbidden; everything is judged by the running app.
[Output] Output only a single JSON object, with no markdown fences:
{{"items": [{{"id": "...", "grade": 0-3, "evidence": "each grade must be supported by concrete evidence; for downgrades, point out the atomic assertion that failed"}}, ...]}}"""



def sh(cmd, timeout=120, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed: {cmd[:120]} :: {r.stderr[:300]}")
    return r


def dexec(cid, script, env_file=None, workdir="/workspace", timeout=1800):
    ef = f"--env-file {env_file} " if env_file else ""
    return sh(f"docker exec {ef}-w {workdir} {cid} bash -c {json.dumps(script)}", timeout=timeout)


def cc(cid, env_file, prompt, workdir, timeout, log_to):
    script = (f"timeout {timeout - 60} claude --print --dangerously-skip-permissions "
              f"-p {json.dumps(prompt)} 2>>/tmp/cc_stderr.log")
    r = dexec(cid, script, env_file=env_file, workdir=workdir, timeout=timeout)
    Path(log_to).write_text(r.stdout[-200000:])
    return r.stdout


def delivery_state(cid):
    """Classify the delivery contract mechanically, before anything is started.

    Returns "ok" (./start.sh present at the repo root), "nested" (a start.sh
    exists but only in a subdirectory), or "missing". Keeping these apart matters:
    a nested start.sh is a contract violation with a working app behind it, which
    is a different failure from an app that cannot run at all.
    """
    r = dexec(cid, "test -f /workspace/start.sh && echo ok || "
                   "(find /workspace -maxdepth 3 -name start.sh -not -path '*/node_modules/*' "
                   "| head -1 | grep -q . && echo nested || echo missing)", timeout=60)
    return r.stdout.strip().splitlines()[-1].strip() if r.stdout.strip() else "missing"


START_APP_SQUATTED = set()


def start_app(cid):
    """Start ./start.sh and report whether :3000 serves.

    Port reclaim cannot use fuser/lsof/ss here: this image's /proc/net view is empty
    for the container's own sockets, so all three report nothing and `lsof -ti` even
    prints a full listing that turns `xargs kill` into a no-op. Killing by dev-server
    process pattern is the only method that actually works. Patterns are bracketed so
    the kill never matches the shell running it, and bare `node`/`python` are never
    killed -- the acceptance agent itself is a node process.

    If the port is still served after that, the service cannot be attributed to
    start.sh. Rather than emit a false zero (the costlier error), we accept it and let
    the caller record it, so the task can be re-verified in a clean container later.
    """
    pats = ["[v]ite", "[n]ext dev", "[w]ebpack", "[h]ttp.server", "[s]erve -",
            "[n]odemon", "[n]g serve", "[a]stro dev", "[n]uxt", "[r]emix",
            "[p]arcel", "[l]ive-server", "[e]sbuild --service", "[n]pm exec",
            "[n]pm run", "[n]pm start"]
    kill = "; ".join(f"pkill -9 -f '{x}' 2>/dev/null" for x in pats)
    squatted = False
    for _ in range(3):
        dexec(cid, f"{kill}; sleep 2; true", timeout=120)
        r = dexec(cid, "curl -s --noproxy '*' -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:3000", timeout=30)
        if r.stdout.strip() != "200":
            break
    else:
        squatted = True
    if squatted:
        START_APP_SQUATTED.add(cid)
        return True
    START_APP_SQUATTED.discard(cid)
    sh(f"docker exec -d -w /workspace {cid} bash -c 'bash start.sh > /tmp/app.log 2>&1'", timeout=60)
    for _ in range(45):
        r = dexec(cid, "curl -s --noproxy '*' -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:3000", timeout=30)
        if r.stdout.strip() == "200":
            return True
        time.sleep(4)
    return False


def parse_obj(text):
    for s in (i for i in range(len(text)) if text[i] == "{"):
        try:
            obj = json.loads(text[s: text.rindex("}") + 1])
            if isinstance(obj, dict) and "items" in obj:
                return obj
        except Exception:
            continue
    return None


def median(xs):
    return sorted(xs)[len(xs) // 2] if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task_dir"); ap.add_argument("results_dir")
    ap.add_argument("--builder-env", required=True)
    ap.add_argument("--accept-env", default=DEFAULT_ACCEPT_ENV,
                    help="env file for the QA accept agent (default: $ACCEPT_ENV)")
    ap.add_argument("--image", default=DEFAULT_IMAGE,
                    help="sandbox image (default: $WB_IMAGE, else vision2web-sandbox:latest)")
    ap.add_argument("--accept-prompt", default="v1", choices=["v1", "strict"])
    ap.add_argument("--accept-reps", type=int, default=1)   # v6: single pass (Vision2Web-aligned); judge retries on empty output
    a = ap.parse_args()
    if not a.accept_env:
        ap.error("--accept-env is required (or set ACCEPT_ENV)")
    task_dir, results_dir = Path(a.task_dir), Path(a.results_dir)
    task = json.loads((task_dir / "task.json").read_text())
    tid = task["task_id"]
    if (results_dir / "report.json").exists():
        print(f"[{tid}] skip(done)"); return
    results_dir.mkdir(parents=True, exist_ok=True)
    claim = results_dir / ".claim"
    if claim.exists():
        print(f"[{tid}] skip(claimed)"); return
    claim.write_text(str(time.time()))
    cid = f"wb-{tid}-{uuid.uuid4().hex[:6]}"
    sh(f"docker rm -f {cid} 2>/dev/null; true", timeout=60)
    sh(f"docker run -d --name {cid} {a.image} sleep infinity", timeout=300, check=True)
    report = {"task": tid, "protocol": "v7_1h_" + a.accept_prompt, "container": cid}
    ok = False
    try:
        # seed materials
        proto = task_dir / "prototypes"
        if proto.exists():
            sh(f"docker cp {proto} {cid}:/workspace/prototypes", timeout=300)
        repo = task_dir / "repo"
        seed_hint = "\n"
        if repo.exists():  # brownfield: seed repository (for repair tasks, the version with the bug already injected)
            sh(f"docker cp {repo}/. {cid}:/workspace/", timeout=600)
            seed_hint = "\nAn existing repository is already in the current directory; modify it in place (install the dependencies yourself first and run it to see its current state).\n"
        if (proto / "reference.jpg").exists():
            seed_hint += "The reference screenshot is at ./prototypes/reference.jpg; please look at it carefully before you start work.\n"

        requests = "\n".join(f"[Requirement {i+1}] {m['request']}" for i, m in enumerate(task["milestones"]))
        print(f"[{tid}] build ({len(task['milestones'])} reqs)", flush=True)
        out = cc(cid, a.builder_env, BUILD_PROMPT.format(requests=requests, seed_hint=seed_hint),
                 "/workspace", 3600, results_dir / "build.log")
        report["build_done"] = "ALL_DONE" in out
        sh(f"docker exec {cid} bash -c 'cd /workspace && tar --exclude=node_modules --exclude=.qa -cf /tmp/build.tar .'", timeout=300)
        sh(f"docker cp {cid}:/tmp/build.tar {results_dir}/build.tar", timeout=300)

        items = task["checklist"]
        groups = {}
        for i in items:
            groups.setdefault(i["m"], []).append({k: i[k] for k in ("id", "description", "dimension", "w")})
        checklist = json.dumps([{"requirement": m, "items": v} for m, v in sorted(groups.items())],
                               ensure_ascii=False, indent=1)
        dexec(cid, "mkdir -p /workspace/.qa/screens", timeout=30)
        report["delivery_contract"] = delivery_state(cid)
        verdicts, br = [], []
        for rep in range(a.accept_reps):
            up = start_app(cid)
            br.append(up)
            if not up:
                continue
            tpl = ACCEPT_PROMPT_STRICT if a.accept_prompt == "strict" else ACCEPT_PROMPT
            out = cc(cid, a.accept_env, tpl.format(checklist=checklist, rep=rep),
                     "/workspace/.qa", 2400, results_dir / f"accept_rep{rep}.log")
            dexec(cid, "fuser -k 3000/tcp 2>/dev/null; true", timeout=60)
            obj = parse_obj(out)
            if obj is None:
                # judge produced nothing parseable (gateway filter / truncation):
                # retry the same pass instead of losing it (v6)
                for extra in range(2):
                    print(f"[{tid}] rep{rep} unparseable, retry {extra + 1}/2", flush=True)
                    up2 = start_app(cid)
                    if not up2:
                        break
                    out = cc(cid, a.accept_env, tpl.format(checklist=checklist, rep=rep),
                             "/workspace/.qa", 2400, results_dir / f"accept_rep{rep}_retry{extra + 1}.log")
                    dexec(cid, "fuser -k 3000/tcp 2>/dev/null; true", timeout=60)
                    obj = parse_obj(out)
                    if obj:
                        break
            if obj:
                verdicts.append({v["id"]: max(0, min(3, int(v["grade"])))
                                 for v in obj.get("items", [])
                                 if "id" in v and isinstance(v.get("grade"), (int, float))})
        sh(f"docker cp {cid}:/workspace/.qa/screens {results_dir}/screens 2>/dev/null; true", timeout=300)

        report["port_squatted"] = cid in START_APP_SQUATTED
        if not verdicts and not any(br):
            # The app failed to start on all three attempts = delivery failure (aligned with
            # Vision2Web, where undelivered counts as 0); still write the report as usual.
            report["metrics"] = {"RC": 0.0, "FS": 0.0, "IS": 0.0, "VS_items": 0.0, "BR": 0.0,
                                 "per_requirement": {}, "item_grades": {},
                                 "n_accept_reps": 0, "undelivered": True,
                                 "delivery_contract": report.get("delivery_contract")}
            (results_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
            ok = True
            print(f"[{tid}] UNDELIVERED (app never started) -> zero report", flush=True)
            return
        if not verdicts:
            # The app starts but all three acceptance passes produced no valid output =
            # acceptance incident; no report may be written (an all-zero report would
            # pollute the batch statistics).
            (results_dir / "ACCEPT_FAILED").write_text("0 valid acceptance reps\n")
            claim.unlink(missing_ok=True)
            print(f"[{tid}] ACCEPT-FAILED (0 valid reps) — no report written, task requeueable", flush=True)
            return

        item_grade = {}
        for i in items:
            votes = [v[i["id"]] for v in verdicts if i["id"] in v]
            item_grade[i["id"]] = median(votes) if votes else 0
        dim = {i["id"]: norm_dim(i["dimension"]) for i in items}
        w = {i["id"]: i.get("w", 1.0) for i in items}

        def agg(ids):
            tw = sum(w[x] for x in ids)
            return round(sum(w[x] * item_grade[x] / 3 for x in ids) / tw, 4) if tw else None

        req_scores = {f"req{m}": agg([x["id"] for x in v]) for m, v in sorted(groups.items())}
        report["metrics"] = {
            "RC": round(sum(req_scores.values()) / len(req_scores), 4),
            "FS": agg([i for i in dim if dim[i] in ("functional", "coverage")]),
            "IS": agg([i for i in dim if dim[i] == "interaction"]),
            # VS_items: visual item score for PRD/brownfield tasks; for replicate tasks VS
            # comes from the visual_score.py component score.
            "VS_items": agg([i for i in dim if dim[i] == "visual"]),
            "BR": round(sum(br) / len(br), 2) if br else 0.0,
            "per_requirement": req_scores, "item_grades": item_grade,
            "n_accept_reps": len(verdicts),
        }
        (results_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
        print(f"[{tid}] DONE {json.dumps(report['metrics'], ensure_ascii=False)[:200]}", flush=True)
        ok = True
    finally:
        try:
            r = dexec(cid, "tail -c 20000 /tmp/cc_stderr.log 2>/dev/null", timeout=60)
            (results_dir / "cc_stderr.log").write_text(r.stdout)
        except Exception:
            pass
        sh(f"docker rm -f {cid} 2>/dev/null; true", timeout=120)
        if not ok:
            print(f"[{tid}] FAILED", flush=True)


if __name__ == "__main__":
    main()
