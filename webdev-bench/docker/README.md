# Sandbox image

The evaluation runs every task inside a disposable Docker container. The
published runs used:

```
vision2web-sandbox:wbench7
```

## Where this image actually comes from

`wbench7` has **no single Dockerfile**. It is a chain of `docker commit`s on top
of the base sandbox:

```
Dockerfile.sandbox  ->  vision2web-sandbox:latest
                               |
                               +-- docker commit  ->  :wbench2
                               +-- docker commit  ->  :wbench4
                               +-- docker commit  ->  :wbench6
                               +-- docker commit  ->  :wbench7
```

The commit steps were ad-hoc maintenance, and their commands were not kept. The
only surviving description is in `setup_infra.sh`, which documents one of the
increments: model routes appended to `/opt/litellm_cfg.yaml` (an OpenAI-style
`hosted_vllm/<model>` entry per tested model, `api_key: os.environ/EVAL_API_KEY`,
`additional_drop_params: ["user"]`), followed by `docker commit`. A rollback tag
`vision2web-sandbox:pre_wbench_<date>` was kept before that step.

`Dockerfile.wbench` is a **best-effort reconstruction** of the recoverable part:
it starts from `:latest` and applies the documented litellm route step. Every
step that could not be recovered from the repository is listed as a comment
block at the bottom of that file and marked `NOT RECOVERABLE`; authors need to
fill those in or publish the image digest.

## Build

Base image only (this is enough for the Python runners and for QA agents that
bring their own gateway credentials):

```bash
./build.sh                      # tags vision2web-sandbox:wbench7
# or an explicit tag:
./build.sh vision2web-sandbox:latest
```

Reconstructed wbench layer on top of the base:

```bash
./build.sh vision2web-sandbox:latest
docker build -f Dockerfile.wbench \
    --build-arg LITELLM_API_BASE=https://your-gateway.example/v1 \
    -t vision2web-sandbox:wbench7 .
```

## What the base image provides

Ubuntu 22.04, Python 3.12, Node.js 20, PostgreSQL/Redis/nginx, Google Chrome,
Playwright (CLI and Python), and the Claude Code / Codex agent CLIs. Tasks run
under `/workspace`; the runner copies the task materials there and starts the
application on port 3000.

## Notes

* The image is large; builds take a while and need network access.
* `snap.cjs` looks for Chromium via `CHROMIUM_EXECUTABLE` first and otherwise
  lets Playwright resolve its own browser. If you pin a browser build inside
  your image, set that variable accordingly.
* The litellm route block in `Dockerfile.wbench` is for exposing **your** models
  through an in-container router. If your builder and judge reach a gateway
  directly, you do not need it: the base image plus `.cc_env` is sufficient.
