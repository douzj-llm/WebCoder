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

BUILD_PROMPT = """你是一名前端工程师，接到一份包含多个需求的开发单。请在当前仓库完成全部需求。

【需求单】
{requests}
{seed_hint}
【交付要求】
1. 应用必须可运行：维护 ./start.sh（在 http://localhost:3000 前台启动服务；优先静态/开发服务器方案，避免安装系统级依赖）。
2. 交付前自行验证：启动应用，用 playwright-cli 截图确认渲染正确、无控制台报错；涉及交互的需求实际操作一遍；验证完停掉服务（fuser -k 3000/tcp）。
3. 全部完成后输出一行：ALL_DONE: <一句话总结>

【规则】验收针对运行中的应用；只有用户可观察的行为算数；不要写测试文件应付验收；不要读写 .qa 目录。"""

ACCEPT_PROMPT = """你是一名严格的 QA 验收工程师。被测应用正运行在 http://localhost:3000 。

【第一部分 · 逐需求 checklist 分档验收】
下面是按大需求分组的验收清单（JSON）：
{checklist}
逐条验收：用 playwright-cli 实际操作与观察（open/click/fill/screenshot），每条至少一次截图或页面观察作为证据；交互类条目必须实际执行操作；涉及精确数值/组合状态的条目，必须实际构造该状态并核对数值。

每条给出 0-3 四档离散分（锚定标准，严格执行）：
- 3 = 完全满足：可观察行为与条目要求完全一致，无可见瑕疵；
- 2 = 基本满足：核心行为正确，但有小瑕疵（文案/样式/边缘状态的细节偏差）；
- 1 = 部分满足：仅实现了条目的一部分，或行为不稳定、时对时错；
- 0 = 未实现或不可用：要求的行为不存在、无效或报错。
给 3 不需要"超出预期"，满足条目即可；降档必须附具体证据。按钮存在但点击无效不能给高档。

【第二部分 · 整站截图存档】
验收完成后，回到首页初始状态，执行整页截图保存到 /workspace/.qa/screens/full_rep{rep}.png（目录已建好；用 playwright-cli screenshot 的整页模式）。

【规则】严禁阅读被测仓库源码；严禁修改 .qa 以外的任何文件；一切以运行中的应用为准。
【输出】只输出一个 JSON 对象，无 markdown 围栏：
{{"items": [{{"id": "...", "grade": 0-3, "evidence": "..."}}, ...]}}"""


ACCEPT_PROMPT_STRICT = """你是一名极其严格的 QA 验收工程师（对外交付前的最后一道门）。被测应用正运行在 http://localhost:3000 。

【第一部分 · 逐需求 checklist 分档验收（严格模式）】
下面是按大需求分组的验收清单（JSON）：
{checklist}

验收方法（每条都要做）：
1. 把该条目拆成原子断言清单（每个具体文案、数量、颜色/样式、状态、行为各算一条原子断言）；
2. 用 playwright-cli 逐个核验：文本必须逐字对照（多字/少字/错字都算不符），数量必须实际数，
   交互必须实际操作并截图前后状态，精确数值/组合状态必须实际构造出来核对；
3. 默认立场是"不满足"：只有拿到明确证据才能判满足；找不到元素、构造不出状态、截图看不清，一律按该原子断言失败计。

档位（严格执行，宁降勿升）：
- 3 = 该条目全部原子断言逐一核验为真，无任何可见偏差；
- 2 = 核心行为断言全部为真，但存在≥1处次要偏差（文案不完全一致/样式细节/边缘状态）；
- 1 = 超过一半原子断言为真但核心行为存在缺失或不稳定；或按钮/入口存在但对应行为未能验证；
- 0 = 核心元素或行为缺失、无效、报错，或大部分原子断言不成立。
降档不需要犹豫；给 3 之前必须自查："我是否逐字核对了所有文案、逐个数了所有数量、实际执行了所有交互？"有任何一项没做到就不能给 3。

【第二部分 · 整站截图存档】
验收完成后，回到首页初始状态，执行整页截图保存到 /workspace/.qa/screens/full_rep{rep}.png（目录已建好；用 playwright-cli screenshot 的整页模式）。

【规则】严禁阅读被测仓库源码；严禁修改 .qa 以外的任何文件；一切以运行中的应用为准。
【输出】只输出一个 JSON 对象，无 markdown 围栏：
{{"items": [{{"id": "...", "grade": 0-3, "evidence": "每档必须给具体证据，降档要指出失败的原子断言"}}, ...]}}"""


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
        if repo.exists():  # brownfield: 起始仓库(修复题为已注入版本)
            sh(f"docker cp {repo}/. {cid}:/workspace/", timeout=600)
            seed_hint = "\n现有仓库已在当前目录，请在其上改造（先自行安装依赖并跑起来看看现状）。\n"
        if (proto / "reference.jpg").exists():
            seed_hint += "参考截图位于 ./prototypes/reference.jpg ，请仔细查看后再动工。\n"

        requests = "\n".join(f"【需求 {i+1}】{m['request']}" for i, m in enumerate(task["milestones"]))
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
            # 应用三次都起不来 = 交付失败（对齐 Vision2Web 未交付计 0），照常落报告
            report["metrics"] = {"RC": 0.0, "FS": 0.0, "IS": 0.0, "VS_items": 0.0, "BR": 0.0,
                                 "per_requirement": {}, "item_grades": {},
                                 "n_accept_reps": 0, "undelivered": True,
                                 "delivery_contract": report.get("delivery_contract")}
            (results_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
            ok = True
            print(f"[{tid}] UNDELIVERED (app never started) -> zero report", flush=True)
            return
        if not verdicts:
            # 应用能起但三遍验收全无有效输出 = 验收事故，不得落报告（否则全 0 污染批次统计）
            (results_dir / "ACCEPT_FAILED").write_text("0 valid acceptance reps\n")
            claim.unlink(missing_ok=True)
            print(f"[{tid}] ACCEPT-FAILED (0 valid reps) — no report written, task requeueable", flush=True)
            return

        item_grade = {}
        for i in items:
            votes = [v[i["id"]] for v in verdicts if i["id"] in v]
            item_grade[i["id"]] = median(votes) if votes else 0
        dim = {i["id"]: i["dimension"] for i in items}
        w = {i["id"]: i.get("w", 1.0) for i in items}

        def agg(ids):
            tw = sum(w[x] for x in ids)
            return round(sum(w[x] * item_grade[x] / 3 for x in ids) / tw, 4) if tw else None

        req_scores = {f"req{m}": agg([x["id"] for x in v]) for m, v in sorted(groups.items())}
        report["metrics"] = {
            "RC": round(sum(req_scores.values()) / len(req_scores), 4),
            "FS": agg([i for i in dim if dim[i] in ("功能", "覆盖")]),
            "IS": agg([i for i in dim if dim[i] == "交互"]),
            "VS_items": agg([i for i in dim if dim[i] == "视觉"]),  # PRD/棕地的视觉条目分; 复刻题 VS 以 visual_score.py 组件分为准
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
