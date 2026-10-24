#!/usr/bin/env python3
"""Offline visual component scoring for replicate-seed tasks (Vision2Web VS instrument).

For each replicate task, compares results/<line>/<tid>/screens/full_rep*.png
against tasks/<tid>/prototypes/reference.jpg. Per rep the judge auto-segments
components and grades each on {0,.25,.5,.75,1}; rep V = component mean;
task V = median over reps. Writes visual.json next to report.json.

The judge is called through an OpenAI-compatible endpoint. Required env:
  VS_API_KEY   API key for the judge endpoint
Optional env:
  VS_BASE_URL  endpoint base URL (default: https://your-gateway.example/v1)
  VS_MODEL     judge model name (default: glm-5.3-flash)
  NO_PROXY=localhost,127.0.0.1 must be set so screenshots can reach :3000.

Usage: python3 visual_score.py --results results/<line>
                               [--tasks-dir tasks] [--concurrency 4]
"""
import argparse, asyncio, base64, json, re, statistics, sys
from pathlib import Path

from openai import AsyncOpenAI

import os

HERE = Path(__file__).parent
BASE = os.environ.get("VS_BASE_URL", "https://your-gateway.example/v1")
JUDGE_KEY = os.environ.get("VS_API_KEY", "")
MODEL = os.environ.get("VS_MODEL", "glm-5.3-flash")

# Official Vision2Web VISUAL_PROMPT, inlined verbatim (two image placeholders).
VISUAL_PROMPT = """You are a **senior QA automation engineer**. Your task is to **compare a prototype image with an actual page screenshot** and score the appearance of the page.

> **Important:** Carefully observe **all differences** between the prototype and the actual page. Do not overlook any discrepancies, however small. Score strictly according to the rules below.

---

## Input
1. **Prototype Image** : {prototype_page}
2. **Actual Page Image** : {actual_page}

> Note: You need to automatically segment the page into meaningful UI components based on visual and functional layout.

---

## Component Segmentation Rules
- Divide the page into **logical functional blocks**, not too granular or too coarse.
- Example functional blocks:
  - Navigation bar / header
  - Hero section / main banner
  - Product listing / catalog area
  - Checkout / payment section
  - Footer
  - Any other visually distinct functional sections
- For each block, treat it as a **single component** for scoring purposes.

---

## Scoring Rules

Each component/block gets an independent score:

| Score | Description |
|-------|-------------|
| 1.0   | **Perfect Match:** Component position exactly matches the prototype. Layout, spacing, alignment, and sizing are identical. Text matches perfectly with no typos. Fonts, colors, icons, images, and other multimedia are fully accurate. No visually discernible differences. Flawless replication. |
| 0.75  | **Minor Imperfections:** Component position mostly accurate, with very slight misalignment (<2px). Layout and spacing largely consistent with the prototype. Text has only very minor typos or formatting differences. Multimedia matches but may have slight scaling or color variations. Differences are only noticeable upon close inspection. |
| 0.5   | **Partial Match:** Component position roughly correct, but noticeable misalignment or spacing issues. Layout design partially consistent; some elements may be offset or resized. Text has several discrepancies (typos, truncation, formatting). Multimedia partially incorrect or inconsistent (wrong size, minor color differences, missing elements). Differences are noticeable at normal viewing. |
| 0.25  | **Poor Match:** Component position recognizable but significantly misaligned. Layout mostly inconsistent; spacing, sizing, or alignment clearly wrong. Text differs significantly from prototype. Multimedia missing, incorrect, or visually inconsistent. Overall appearance deviates strongly from the prototype. |
| 0.0   | **No Match:** Component missing or completely misplaced. Layout unrelated to prototype. Text entirely incorrect or missing. Multimedia absent or completely incorrect. Appearance largely unrecognizable compared to the prototype. |

---

## Output Requirements
- Output **only** a JSON object in the following structure:

```json
[
    {{
      "name": "<component name>",
      "score": <0 | 0.25 | 0.5 | 0.75 | 1>,
      "reason": "<brief explanation of why this score was given>"
    }}
]
```"""


def load_official_prompt():
    return VISUAL_PROMPT


def b64(p):
    return base64.b64encode(Path(p).read_bytes()).decode()


async def score_pair(client, prompt, ref, act):
    content = [
        {"type": "text", "text": prompt.split("{prototype_page}")[0]},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64(ref)}},
        {"type": "text", "text": "2. **Actual Page Image** :"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64(act)}},
        {"type": "text", "text": prompt.split("{actual_page}")[1]},
    ]
    for att in range(4):
        try:
            r = await client.chat.completions.create(model=MODEL, max_tokens=8000,
                messages=[{"role": "user", "content": content}])
            txt = r.choices[0].message.content or ""
            s = txt.find("[")
            comps = json.loads(txt[s:txt.rfind("]") + 1])
            if comps:
                return comps
        except Exception:
            await asyncio.sleep(6 * (att + 1))
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--tasks-dir", default=str(HERE / "tasks"),
                    help="directory holding <task_id>/prototypes/reference.jpg")
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args()
    if not JUDGE_KEY:
        ap.error("set VS_API_KEY to the judge endpoint key")
    tasks_dir = Path(a.tasks_dir)
    client = AsyncOpenAI(api_key=JUDGE_KEY, base_url=BASE, timeout=600, max_retries=0)
    prompt = load_official_prompt()
    sem = asyncio.Semaphore(a.concurrency)

    async def do_task(rdir):
        tid = rdir.name
        ref = tasks_dir / tid / "prototypes" / "reference.jpg"
        out = rdir / "visual.json"
        if out.exists() or not ref.exists():
            return
        shots = sorted((rdir / "screens").glob("full_rep*.png"))
        if not shots:
            out.write_text(json.dumps({"VS": None, "V": None, "judge": MODEL, "reason": "no screenshots"}))
            print(f"{tid} no-screens"); return
        reps = []
        for s in shots:
            async with sem:
                comps = await score_pair(client, prompt, ref, s)
            if comps:
                reps.append({"shot": s.name,
                             "components": comps,
                             "mean": sum(c.get("score", 0) for c in comps) / len(comps)})
        V = round(statistics.median([r["mean"] for r in reps]), 4) if reps else None
        out.write_text(json.dumps({"VS": V, "V": V, "judge": MODEL, "reps": reps}, ensure_ascii=False, indent=1))
        print(f"{tid} V={V} ({len(reps)} reps)", flush=True)

    dirs = [d for d in sorted(Path(a.results).iterdir()) if (d / "report.json").exists()]
    await asyncio.gather(*[do_task(d) for d in dirs])


if __name__ == "__main__":
    asyncio.run(main())
