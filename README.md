# SWE-Skills-Bench

**Does giving a coding agent a curated skill document actually make it better at real
software-engineering tasks?**

SWE-Skills-Bench ([arXiv:2603.15401](https://arxiv.org/abs/2603.15401)) pairs **98 skills**
(curated `SKILL.md` documents) with real GitHub repositories, requirement documents and hidden
test suites. Every task is run with and without the skill, and the paired difference is
measured. This repository holds the code and data needed to reproduce the reported results.

Repository: <https://github.com/ControllableModel/SWE-Skills-Bench>

---

## Benchmark design

```
cell = (agent, model, skill, requirement, skill_mode)
         |      |      |       |            '- none | one
         |      |      |       '- batch1..batch10 (10 requirement docs per skill)
         |      |      '- 98 skills, each pinned to a GitHub repo at a fixed commit
         |      '- any Anthropic- or OpenAI-compatible model endpoint
         '- claude (Claude Code CLI) | codex (OpenAI Codex CLI)
```

98 skills x 10 requirements x 2 modes = **1960 cells per agent x model configuration**.

| mode | what the agent gets |
|---|---|
| `none` | the requirement document only |
| `one`  | the requirement document, plus the skill's `SKILL.md` installed in the container and invoked explicitly with the `/<skill-id>` slash command |

Each cell runs in a fresh, isolated container:

```
start container -> clone repo @ pinned commit -> run setup commands
  -> (one mode) install SKILL.md -> give the requirement to the agent CLI -> agent edits code
  -> export trajectory -> run hidden tests -> score = pass rate -> tear down
```

---

## Results

Mean test pass rate (%) over the 980 (skill, requirement) pairs of each configuration.
All 7840 cells pass the infra-clean gate (see [Validity](#validity-the-infra-clean-gate)).

| agent x model           | none | one  | paired delta (pp) |
|-------------------------|-----:|-----:|------------------:|
| Claude Code x Haiku 4.5 | 74.2 | 74.5 | +0.26 |
| Claude Code x Kimi-K2.6 | 78.5 | 79.2 | +0.64 |
| Codex x GPT-5.4-mini    | 76.0 | 76.7 | +0.76 |
| Codex x Kimi-K2.6       | 77.6 | 77.3 | -0.29 |

All four configurations fall within +/-1pp. **Injecting the skill gives no systematic gain.**

Raw tables are in [`results/final_results/`](results/final_results/):

| file | content |
|---|---|
| `<agent>__<model>_cells.csv` | one row per (skill, requirement): none / one / delta |
| `ALL_combined_cells.csv` | the four configurations concatenated |
| `summary_by_skill.html` | per-skill mean +/- std over the 10 requirements |
| `infra_refused_reports.csv` | superseded reports rejected by the gate, kept for audit |

---

## Repository layout

```
main.py                         single-cell CLI: run / list-skills / validate / show-report
run_all_skills.py               run all 98 skills of one batch (interaction + immediate eval)
eval.py, run_all_skills_eval.py scoring
config/benchmark_config.yaml    the 98 skills: repo, commit, image, setup commands, eval params
src/
  orchestrator/                 lifecycle + container backends (enroot, docker)
  initializer/                  repo checkout and environment setup inside the container
  proxy/                        agent drivers (Claude Code, Codex) + Responses->Chat bridge
  evaluator/                    test runner and scoring
  utils/                        helpers, infra-error classifier
skills/<id>/                    skill documents (SKILL.md + references)
tasks/batchN/<id>.md            requirement documents given to the agent
tests/batchN/test_<id>.py       hidden test suites used for scoring
docker/
  <lang>/Dockerfile             per-language benchmark images
  base/, skills/                base layers and per-skill Dockerfiles
scripts/                        SLURM runner, sweep launchers, image baking, health check, table builders
proxy/ccr_config.reference.json claude-code-router template (for non-Anthropic models)
docs/                           requirement-doc template and data-generation prompts
results/final_results/          final result tables
```

---

## Containers: enroot (used) and Docker (provided)

**All reported results were produced with [enroot](https://github.com/NVIDIA/enroot)** on a
SLURM cluster without a Docker daemon (`global.container_backend: enroot` in the config).
Images are pulled from Docker Hub (`zhangyiiiiii/swe-skills-bench-*`) and stored as squashfs
files in `$SWE_ENROOT_IMAGE_CACHE` (default `data/enroot-images/`). An image ref maps to a file
by replacing `/` and `:` with `+`, e.g. `zhangyiiiiii+swe-skills-bench-python.sqsh`.

At run time `scripts/run_batch.sbatch` picks the most specific cached variant of each image:
`<image>-cli2168` (Claude Code CLI 2.1.168 baked in, required for `/skill-id` loading in `one`
mode; build with `scripts/bake_image.sbatch`), or `<image>-cli2168-codex` / `<image>-codex` for
the Codex arm (`scripts/bake_agents_image.sbatch`).

**The Dockerfiles for every image are in [`docker/`](docker/)**, so the environments can be
inspected or rebuilt with Docker. A Docker backend is included
(`container_backend: docker`), but the reported numbers were not produced with it.

Note: some images used by newer skills (`*-ext` tags, e.g. `node-ext`, `cpp-ext`, `bun-ext`)
may not be on Docker Hub. Build them from `docker/` or with the `scripts/build_*_image.sbatch`
/ `scripts/bake_*_image.sbatch` scripts.

---

## Quick start

```bash
git clone https://github.com/ControllableModel/SWE-Skills-Bench.git
cd SWE-Skills-Bench

conda create -n swe-skills-bench python=3.11 -y
conda activate swe-skills-bench
pip install -r requirements.txt

cp .env.example .env            # model credentials (see "Model backends" below)
bash scripts/precache_images.sh # enroot: import images into data/enroot-images/

python main.py validate
python main.py list-skills
python main.py run -s fastapi-patterns --skill-mode none --clean-container
python main.py run -s fastapi-patterns --skill-mode one  --clean-container
```

The agent CLIs (Claude Code, Codex) are baked into the images, so nothing has to be installed on
the host. The jobs only orchestrate containers, and inference happens at the model endpoint, so
**no GPU is required**.

### Full sweep on SLURM

```bash
# one batch, one mode (98 cells)
sbatch --export=ALL,BATCH=batch1,SKILL_MODE=none,AGENT=claude,MODEL_NAME=claude-haiku-4-5 \
       scripts/run_batch.sbatch

# all 10 batches x {none, one} (20 chained jobs)
PARTITION=<partition> bash scripts/launch_model_none_one.sh   # Claude Code arm
PARTITION=<partition> bash scripts/launch_codex_none_one.sh   # Codex arm
```

Useful environment knobs: `SWE_ISOLATE_ENROOT=1` (per-job enroot state, so several jobs can
share a node), `SWE_TOTAL_TIMEOUT_SEC`, `ONLY_SKILLS_FILE`, `FORCE_RERUN=true`.

Outputs:

- `outputs/reports/<agent>/<model>/<batch>/eval/eval_report_*.json`: per-cell scores
- `outputs/{claude,codex}_process/<agent>/<model>/...`: trajectories (`.jsonl`) and raw logs

Rebuild the result tables from your own runs (edit `CONFIGS` in the script to point at them):

```bash
python scripts/build_final_results.py
python scripts/build_final_summary_by_skill.py
```

### Model backends

All credentials come from environment variables (or `.env`):

| arm | settings |
|---|---|
| Claude Code + Anthropic API | `ANTHROPIC_AUTH_TOKEN`, `MODEL_NAME` |
| Claude Code + OpenAI-compatible model | run [claude-code-router](https://github.com/musistudio/claude-code-router) with `proxy/ccr_config.reference.json` as `~/.claude-code-router/config.json`. `scripts/lib_local_ccr.sh` starts one per job. Set `ANTHROPIC_BASE_URL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, `MODEL_NAME`. |
| Codex + OpenAI | `AGENT=codex`, `CODEX_MODEL`, `CODEX_API_KEY` (or `~/.codex/auth.json`) |
| Codex + chat-only server (vLLM / SGLang) | additionally `SWE_CODEX_BRIDGE_UPSTREAM=<endpoint>/v1`, which starts `src/proxy/responses_bridge.py` (Responses API -> Chat Completions) |

---

## Validity: the infra-clean gate

A score does not by itself mean the run was valid. A run that dies at turn 0 (gateway down,
slash command not registered, missing tool, OOM, ...) still gets a syntactically valid score of
0, which looks exactly like a model failure. `src/utils/infra_errors.py` classifies every
report, `scripts/traj_healthcheck.py` scans trajectories, and `scripts/build_final_results.py`
counts only gated, latest-valid reports. Cells that hit an infra error must be re-run,
not counted.

---

## Data notes

- These benchmark inputs are kept **byte-identical** to what the agents saw, so they contain
  some non-English text: `tasks/batch1/{analyze-ci,gitops-workflow,slo-implementation}.md`,
  `skills/security-review/*`, `skills/tdd-workflow/SKILL.md`.
- Claude Code reserves `/security-review` as a built-in command, so inside Claude Code
  containers that skill is installed as `skill-security-review` (`RESERVED_SKILL_NAMES` in
  `src/utils/helpers.py`).
- Requirement documents and tests are static artifacts. The prompts used to generate them are in
  [`docs/prompts/`](docs/prompts/).

## Citation

```bibtex
@article{sweskillsbench2026,
  title   = {SWE-Skills-Bench},
  journal = {arXiv preprint arXiv:2603.15401},
  year    = {2026}
}
```

## License

MIT, see [LICENSE](LICENSE). Each skill's target repository keeps its own license.
