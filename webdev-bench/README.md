# Webdev-Bench evaluation harness

This directory contains the evaluation code for **Webdev-Bench**, the benchmark
introduced in *WebCoder: Scaling General Frontend Development with
Artifact-Grounded Agentic Reinforcement Learning*
([arXiv:2610.23104](https://arxiv.org/abs/2610.23104)).

Webdev-Bench measures whether an agent can carry a frontend project through
**several rounds of requirements on the same evolving codebase**: it builds an
app from a natural-language requirement, then keeps modifying that app as new
requirements arrive. Each checklist item is graded 0–3 against the running
application only; scores are computed **conjunctively per requirement**.

## Relation to the dataset

Tasks are **not** stored in this repository. They live in the Hugging Face
dataset [`Roy-DOU/Webdev-Bench`](https://huggingface.co/datasets/Roy-DOU/Webdev-Bench):

```
SUBSET40.txt                  the 40 task ids used by the reported results
tasks/<id>/task.json          milestones (requirements), hidden checklist, metadata
tasks/<id>/repo/**            seed Vite + React project (brownfield tasks)
tasks/<id>/prototypes/        reference.jpg or repo_state.jpg
```

Download it and put (or symlink) it next to this README, so that `tasks/` and
`SUBSET40.txt` sit in the evaluation working directory:

```bash
huggingface-cli download Roy-DOU/Webdev-Bench --repo-type dataset --local-dir .
```

The copy of `SUBSET40.txt` in this repository is the frozen task list; the
dataset ships the same list.

## Repository layout

```
run_task.py            single-round (build-only) runner + terminal acceptance
run_task_v9.py         reference protocol: sequential requirements with judge gates
reaccept.py            re-run acceptance from a stored build.tar (no rebuild)
visual_score.py        offline visual (VS) component scoring for replicate tasks
aggregate_bench.py     per-line aggregation of reports
snap.cjs               screenshot + page text collector (gate evidence)
run_v9.sh              paired base/RL run with run_task_v9.py
run_v9_multi.sh        multi-model campaign with run_task_v9.py
run_composite.sh       reaccept-then-build run on the composite subset
run_line.sh            full line: build, visual scoring, aggregation
SUBSET40.txt           task ids used for the reported results
.cc_env.example        template for Claude Code environment files
docker/                sandbox image: base Dockerfile, reconstruction notes
scoring/               full-results tables, per-dimension item stats, heat-map
```

## Prerequisites

* Docker (the runner starts one container per task and copies materials in).
* Python 3.10+ with `openai` installed (only for `visual_score.py`).
* An OpenAI-compatible endpoint for the **judge** (QA acceptance and, in the v9
  protocol, the per-round gate).
* Agent credentials: the builder and judge agents are driven as CLI agents
  inside the container via Claude Code (`claude --print`). Put their endpoint
  and key in `.cc_env.<line>` files (see below).

`playwright`, Chromium, Chromium headless-shell and `playwright-cli` are inside
the sandbox image; you do not install them on the host.

## Credentials

Copy the template once per line:

```bash
cp .cc_env.example .cc_env.judge     # QA acceptance agent (the judge)
cp .cc_env.example .cc_env.myline    # builder agent for one tested model
chmod 600 .cc_env.*
```

`.cc_env.*`, `*api_key*`, `*.key` and `*.pem` are gitignored. Never commit them.

Two roles are configured separately:

* **builder** — `--builder-env .cc_env.<line>`; the tested model.
* **accept** — `--accept-env .cc_env.judge` (or `$ACCEPT_ENV`); the QA agent that
  operates the running app with `playwright-cli`. It must not be the same model
  as the builder if you care about judge independence.

For the v9 gate, pass `--judge-url https://your-gateway.example/v1` (or set
`JUDGE_URL`). The gate model defaults to `glm-5.3-flash`; change it with
`--judge-model` / `JUDGE_MODEL`. The endpoint must follow the OpenAI chat
completions schema and accept image inputs for the gate.

## Run one task

```bash
# 1. build the sandbox (see docker/README.md)
cd docker && ./build.sh vision2web-sandbox:wbench7 && cd ..

# 2. run one task (paths are relative to this directory)
python3 run_task.py tasks/c03 results/mymodel/c03 \
    --builder-env .cc_env.myline \
    --accept-env  .cc_env.judge \
    --image vision2web-sandbox:wbench7
```

Output under `results/mymodel/c03/`:

```
build.log              builder transcript
build.tar              the delivered workspace (node_modules excluded)
accept_rep0.log        terminal QA transcript
screens/full_rep0.png  full-page screenshot archived by the judge
report.json            protocol metadata, per-requirement scores, item grades
```

`report.json` is the unit of record. A task whose app never starts gets an
`undelivered: True` report with all-zero metrics; a task where the app starts
but the judge produced no parseable verdict gets `ACCEPT_FAILED` and no report,
so it is not silently counted as zero.

## Run the full set

Reference protocol (multi-round, gated), as used for the reported numbers:

```bash
JUDGE_URL=https://your-gateway.example/v1 \
ACCEPT_ENV=$PWD/.cc_env.judge \
BASE_TAG=mybase RL_TAG=myrl \
bash run_v9.sh
```

This runs the two lines listed in `run_v9.sh` over `SUBSET40.txt`. For an
arbitrary set of lines:

```bash
JUDGE_URL=... bash run_v9_multi.sh myline:myline_v9 other:other_v9
```

Single-round runner over one line, followed by visual scoring and aggregation:

```bash
TAG=myline OUT=myline_v9 P=5 bash run_line.sh
```

`run_composite.sh` is the repair path for a campaign that was interrupted after
building: it first replays acceptance from each `build.tar` (`reaccept.py`),
then builds the remaining tasks.

All paths are relative to this directory. The shell scripts accept `TASKS`,
`TASKS_DIR`, `ACCEPT_ENV`, `IMG`/`WB_IMAGE`; the Python entry points take the
equivalent command-line flags. There are no absolute paths or private hosts in
this release.

## Protocol (v9, reference)

For each requirement, in order, on the same evolving project:

1. one builder round (`claude --print`), with a fixed per-task time pool of
   `1200 s x number of requirements`;
2. a mechanical health check: start `./start.sh` and wait for `:3000`;
3. a gate: one VLM call on the full-page screenshot plus page text against this
   requirement's checklist. Pass means the visible items plausibly reach grade 2;
4. on failure, one short user-voice feedback line and retry the same requirement,
   up to three attempts, while the pool lasts;
5. at the end, one terminal acceptance pass over **every** checklist item of
   **every** requirement. Metrics come from this pass only.

If the gate endpoint is unreachable, the gate fails open and the round is marked
`fail_open` in the report, so infrastructure failures are not charged to the
builder.

`run_task.py` implements the simpler single-round variant (all requirements in
one build session, then terminal acceptance).

## Metrics

Each checklist item is graded 0–3. Let a requirement's items be `I_r`.

**Conjunctive per requirement.** Requirement `r` is satisfied iff every item in
`I_r` has terminal grade 3. Then

```
RS = |{r : r satisfied}| / |requirements|
```

Dimension slices use the same rule over the items of one dimension:

* **FS** — functional + coverage items
* **IS** — interaction items
* **VS** — visual items

**DSR** is the delivery success rate: tasks whose app started on `:3000` during
the terminal acceptance. Undelivered tasks score 0 and stay in the denominator.
`aggregate_bench.py` reports the legacy keys (`RC`, `VS_items`, `BR`) emitted by
the runners; `scoring/wb_full_results.py` computes the conjunctive RS/FS/IS/VS
used in the paper.

For `replicate` tasks, `visual_score.py` scores screenshots against the reference
image with the official Vision2Web `VISUAL_PROMPT` (component segmentation,
five anchors {0, .25, .5, .75, 1}, per-rep component mean, median over reps).
Visual item scores and component scores are **different instruments**; report
them separately rather than pooling them.

## The judge

Grading is done by a model-based QA agent operating the running application via
`playwright-cli`. The prompts are frozen in the runners (`BUILD_PROMPT`,
`ACCEPT_PROMPT`, `ACCEPT_PROMPT_STRICT`, `GATE_SYS`, `GATE_USER`) and are part of
the benchmark definition. The acceptance agent never reads the candidate's
source code and may only write inside `.qa/`.

Prompt differences matter. The reported numbers use the v9 protocol with
`ACCEPT_PROMPT`; `ACCEPT_PROMPT_STRICT` is provided for re-audits.

## Scoring tables

```bash
python3 scoring/wb_full_results.py \
    --results-dir results --lines scoring/lines.example.json \
    --tasks-dir tasks --task-list SUBSET40.txt --out data
python3 scoring/gen_full_results_en.py --input data/wb_full.json --out full_results_en.tex
python3 scoring/plot_wb_heatmap.py --input data/wb_full.json --out figs/fig_wb_heatmap.pdf
```

`lines.example.json` maps display names to result subdirectories; edit it for
your own runs. Per-task difficulty tertiles are computed empirically (mean RS
across the lines present), so they depend on the line set.

## Known limitations

* **The sandbox image is not fully reproducible.** `wbench7` was produced by
  repeated `docker commit`, not a Dockerfile. `docker/Dockerfile.wbench` rebuilds
  only the documented litellm route increment and marks the rest as unrecoverable.
  If exact reproduction matters, use the published image digest or supply the
  missing steps.
* **Reference images are third-party material.** The `replicate` tasks depend on
  long screenshots of real websites. They are distributed with the dataset for
  research only, not under MIT; rights remain with the site owners.
* **Task text is Chinese.** Requirements and checklist descriptions were authored
  and run in Chinese; the harness does not translate them.
* **Judge dependence.** Absolute scores are tied to the judge model and prompt.
  Do not compare numbers obtained with different judges or prompt variants.
* **Denominators can shrink silently.** If a `visual.json` is missing for a
  replicate task, its VS value is undefined; `aggregate_bench.py` prints a
  warning, but downstream tables should be checked for `n`.
* **No external snapshot of the judge model.** The reported gate/acceptance runs
  used a self-hosted model. No hosted endpoint is guaranteed to reproduce the
  same grades.

## License

Evaluation code: MIT (see the repository `LICENSE`). Task definitions and seed
projects: MIT, via the dataset. Reference design images: excluded from MIT, see
the dataset card.

## Citation

```bibtex
@article{dou2026webcoder,
  title   = {WebCoder: Scaling General Frontend Development with Artifact-Grounded Agentic Reinforcement Learning},
  author  = {Dou, Zijun and Yang, Zhen and Liu, Xijun and Zhou, Dongzhuoran and Zeng, Aohan and Tang, Jie},
  journal = {arXiv preprint arXiv:2610.23104},
  year    = {2026}
}
```
