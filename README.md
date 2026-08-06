# ARCANA Core Code

English | [中文](README_CN.md)

This directory contains the ARCANA task data, reasoning pipeline, baselines, supporting source files, and the human-study website. Runtime outputs are generated locally and excluded from Git; their formats are documented in Section 3.7.

## 1. Directory Architecture

### Top-level structure

```text
core_code/
├── README.md                         # English documentation
├── README_CN.md                      # Chinese documentation
├── data/                             # JSON data for 200 ARCANA tasks
├── test_model.py                     # Unified CLI for the pipeline and baselines
├── pipeline_runner.py                # Full pipeline implementation
├── baseline_runner.py                # Baseline implementation
├── prompts.py                        # Pipeline and baseline prompts
├── ablation_prompts.py               # Ablation-specific prompts
├── api_routing.py                    # Shared API-route and credential resolution
├── model_routing.py                  # Shared model aliases, IDs, and vision resolution
├── providers/                        # Provider-specific settings and adapters
│   ├── __init__.py
│   ├── openrouter.py                 # OpenRouter reasoning-effort settings
│   └── uni/
│       ├── __init__.py
│       ├── generation.py             # UNI max-length and thinking settings
│       ├── models.py                 # UNI model catalog, aliases, and vision IDs
│       └── streaming.py              # UNI sync/async streaming-response assembly
├── utils/                            # Shared pipeline and baseline helper package
│   ├── __init__.py
│   ├── common_utils.py               # Data, execution, evaluation, and cost helpers
│   ├── analogy_target_utils.py       # Analogy parsing and normalization
│   ├── concept_expansion_utils.py    # Concept-expansion parsing
│   ├── direct_grid_utils.py          # Direct-grid prediction and arbitration helpers
│   └── visualization.py              # Runtime images and Base64 data URLs for model calls
├── analogy_aspects.py                # Analogy dimensions and composition logic
├── analogy_aspects.json              # Analogy-dimension configuration
├── pipeline_ablations.py             # Pipeline ablation configuration
├── data_process.py                   # Data-processing helpers
├── visualization/                    # Standalone offline visualization tools
│   ├── __init__.py
│   ├── visualize_arc.py              # Configurable ARC task renderer
│   ├── visualize_dataset.py          # Batch dataset renderer
│   └── visualize_model.py            # Saved model-answer renderer
├── arc_annotations_summary_default_test.json
│                                       # Human-study annotation summary
├── pipeline_effective_cases.md       # Documented cases where pipeline modules were effective
└── website/                          # Standalone human-study website and local server
```

The tree above lists the distributable files and directories intended to be kept in Git. Python caches and runtime result directories are omitted here and described separately under [Generated output directories and formats](#37-generated-output-directories-and-formats).

### Main code flow

```text
data/*.json
    │
    ▼
test_model.py
    ├── baseline_runner.py ──► generated baseline output root
    └── pipeline_runner.py ──► generated pipeline output root

Both runners share:
prompts.py, api_routing.py, model_routing.py, utils/common_utils.py,
utils/visualization.py, and the analogy / expansion / ablation helpers.

Provider-specific behavior lives under providers/:
providers/openrouter.py handles default-baseline reasoning settings, while
providers/uni/ contains UNI generation, model-catalog, and streaming adapters.
```

### Component responsibilities

| Component | Purpose |
| --- | --- |
| `data/` | Default task data used by the Python pipeline and baselines. Every JSON file uses the top-level structure `{"train": [...], "test": [...]}`; each item contains `input` and `output` grids. |
| `test_model.py` | Unified CLI. It selects the baseline or pipeline with `--of` and changes the working directory to `core_code`. |
| `pipeline_runner.py` | Runs the full analogy, concept-expansion, code-generation, execution, validation, reflection, repair, and optional direct-grid flow. |
| `baseline_runner.py` | Runs the `base`, `cot`, `ana`, and `anacot` baselines and records tokens, cost, answers, and evaluation results. |
| `providers/` | Keeps provider-specific behavior out of the shared routers. `providers/uni/` contains UNI-only generation, model, and streaming logic; `providers/openrouter.py` contains OpenRouter-only reasoning settings. |
| `utils/` | Reusable parsing, normalization, evaluation, execution, cost, and runtime-visualization helpers shared by the pipeline and baselines. |
| `visualization/` | Standalone offline scripts for rendering the dataset and saved model answers. These scripts are not imported by the pipeline or baselines. |
| `website/` | Human-study frontend, local save/load simulation server, five assembled test groups, and tutorial videos. It runs independently from the reasoning pipeline. |

### Offline visualization tools

Run the standalone renderers from the repository root:

```bash
python3 visualization/visualize_arc.py
python3 visualization/visualize_dataset.py
python3 visualization/visualize_model.py
```

- `visualize_arc.py` reads `data/*.json` and writes configurable task figures to `data_visualization_full/`; test answers may use either the `answer` or `output` field.
- `visualize_dataset.py` renders the full dataset to `arcana_pic/`.
- `visualize_model.py` reads the locally generated `one_chance_answers.json` and writes figures to `gpt5_one_chance/`.
- These three output locations are generated artifacts and are excluded from Git. Pipeline and baseline runtime images are produced separately through `utils/visualization.py` in their configured output roots.

### Data and runtime-output boundaries

- The Python pipeline and baselines read `core_code/data/` by default.
- All 200 task files use `train` for demonstrations and `test` for evaluation cases. The readers still accept the legacy `examples` key for backward compatibility with external files.
- Pipeline and baseline output directories are created at runtime and excluded from Git. They are not part of the distributable source tree shown above.
- Use a distinct output root for each formal experiment to avoid mixing runs from different models or configurations.
- `website/test/test_group*.json` files are assembled website snapshots. They do not dynamically read `core_code/data/`. After changing `data/*.json`, regenerate or manually update the corresponding test-group JSON if the website must use the same change.

## 2. Website: Contents and Local Deployment

`website/` is a standalone copy of the ARCANA human-study participant flow. The included Python server reproduces informed consent, participant-ID lookup, test-group assignment, progress save/restore, and final result submission using local JSON files. It does not require Node.js, frontend packages, the original Cloudflare Worker, KV, or R2. Most of its disk usage comes from tutorial videos.

### Website structure

```text
website/
├── server.py                         # Local static server and API simulation
├── test_local_server.py              # Local persistence regression tests
├── index.html                        # Consent and participant-ID entry page
├── consent_end.html                  # Exit page after declining consent
├── test.html                         # Tutorial, attention check, and formal tasks
├── admin/
│   └── index.html                    # Loopback-only local Admin dashboard
├── test/
│   ├── test_group1.json
│   ├── test_group2.json
│   ├── test_group3.json
│   ├── test_group4.json
│   └── test_group5.json              # Five assembled tutorial and formal-test groups
└── tutorial_video/
    ├── drag_cn.mp4 / drag_en.mp4
    ├── draw_cn.mp4 / draw_en.mp4
    ├── edit_1_cn.mp4 ... edit_8_cn.mp4
    ├── edit_1_en.mp4 ... edit_8_en.mp4
    └── test_cn.mp4 / test_en.mp4
```

Each test group contains two tutorial tasks and twenty formal tasks. The full local flow assigns these groups round-robin by participant ID; pure static preview can select one through the `local_group` URL parameter.

### Requirements

- Python 3.10 or newer. The local server uses only the standard library.
- A modern web browser.
- No API key or external service is required.

### Start on macOS or Linux

Run the following from the directory that contains `core_code`:

```bash
cd core_code/website
python3 server.py
```

### Start on Windows

```powershell
cd core_code\website
py server.py
```

Keep the server terminal open and visit:

```text
http://127.0.0.1:8000/
```

The first page presents the bilingual informed-consent form. After agreeing, enter any non-empty local test ID. The server then finds that ID's existing assignment/progress or assigns one of the five groups. Reopen the same URL and enter the same ID to test restoration.

Open the local Admin dashboard at `http://127.0.0.1:8000/admin/`. It shows assignment and status statistics, per-group usage, active saved progress, and submitted results. It can download individual progress/results or an all-results JSON export, and can create/reuse an assignment for an explicitly entered participant ID.

To change the port or keep a separate local dataset:

```bash
python3 server.py --port 8080
python3 server.py --data-dir ./my_local_study_data
```

Press `Ctrl+C` in the server terminal when finished. If the port changes, use the same port in the browser URL.

### Local data layout and reset

The first stateful-server launch creates the Git-ignored `website/local_data/` directory:

```text
local_data/
├── state.json                 # Participant IDs, sessions, groups, and status
├── progress/                  # Latest active save for each participant ID
├── progress_archive/          # Saves archived after submit, timeout, or lock
├── results/                   # Complete final-submission JSON files
└── attention_failures/        # Attention-check failure events
```

Progress filenames use a SHA-256 digest of the participant ID; the original ID-to-session mapping remains visible in `state.json`. Writes use a temporary file plus atomic replacement and requests within one server process share a lock. Final submission moves active progress into the archive and prevents duplicate submission.

To start an independent local simulation, stop the server and move or rename `local_data/` as a backup before restarting. Alternatively, use `--data-dir` to select another directory without changing existing data.

Run the local persistence and HTTP regression tests from `website/`:

```bash
python3 -m unittest -v test_local_server.py
```

### Local-mode notes

- The default bind address is `127.0.0.1`, so responses are not exposed to the local network.
- Do not open `test.html` by double-clicking it. Browsers may block JSON or video requests when the page uses a `file://` URL.
- Runtime state is written to the Git-ignored `website/local_data/`: `state.json` records assignments, `progress/` stores active saves, `progress_archive/` stores submitted/locked saves, and `results/` stores final submissions.
- The local server accepts any non-empty participant ID and does not read or validate participants from the original deployment.
- Assignments expire after 120 hours. Completed or attention-check-failed assignments are locked.
- `load_remote_json` only accepts packaged `/test/test_group*.json` files; it does not fetch arbitrary external URLs. Test-group upload is disabled so the webpage cannot modify the distributed task data.
- This is a development simulation, not the production backend: the included Admin is loopback-only and omits destructive reset/delete/cleanup/reassignment operations, cloud backup, identity allowlists, and production access controls. Treat `local_data/` as potentially sensitive research data.
- For a page-only preview, run `python3 -m http.server 8000 --bind 127.0.0.1` and open `http://127.0.0.1:8000/test.html?local_group=test_group1.json`. This static mode cannot save or restore.

## 3. Running the Python Code

### 3.1 Python environment and dependencies

Python 3.10 or newer is recommended. Install the packages imported directly by the current code while inside `core_code`:

```bash
cd core_code
python3 -m pip install openai matplotlib numpy tqdm ipdb
```

The repository currently does not pin dependency versions. For reproducible experiments, use a dedicated virtual environment and record the installed versions.

### 3.2 API configuration

Never put API keys in source files or commit them to Git. The current routes and workloads read these environment variables:

| Workload | Base URL | API key |
| --- | --- | --- |
| Pipeline with `--api default` | `OPENAI_BASE_URL` | `OPENAI_API_KEY` |
| Baseline with `--api default` | `OPENAI_BASE_URL` | `OPENAI_API_KEY` |
| Pipeline or baseline with `--api uni` | `UNI_BASE_URL` | `UNI_API_KEY` |

Default pipeline example:

```bash
export OPENAI_BASE_URL="https://your-api-endpoint.example/v1"
export OPENAI_API_KEY="your-api-key"
```

Default baseline example:

```bash
export OPENAI_BASE_URL="https://your-api-endpoint.example/v1"
export OPENAI_API_KEY="your-api-key"
```

The default pipeline and baseline share `OPENAI_BASE_URL` and `OPENAI_API_KEY`. Configure the UNI route with:

```bash
export UNI_BASE_URL="https://your-uni-endpoint.example/v1"
export UNI_API_KEY="your-uni-api-key"
```

### 3.3 Inspect the CLI

Run all Python commands from `core_code`. The unified entry point is `test_model.py`:

```bash
cd core_code
python3 test_model.py --help
```

`--of t` runs the full single-task pipeline; `--of f` runs a baseline. String values `t` and `f` mean true and false.

### 3.4 Run the full pipeline on one task

Run one task through the default route and the current `GPT5` model mapping:

```bash
python3 test_model.py \
  --of t \
  --file basket1.json \
  --mc GPT5 \
  --upc f \
  --pipeline_output_dir ./pipeline
```

- `--file` selects a task under `data/`; the `.json` suffix is optional, so `--file basket1` and `--file basket1.json` are equivalent for pipeline, baseline, and `--html_only` runs.
- `--upc f` starts with fresh programs; `--upc t` attempts to reuse the most recently saved programs for that task.
- `--pipeline_output_dir` selects the output root that contains `results/`, `programs/`, `logs/`, and `visualizations/`.
- `GPT5` currently maps to `openai/gpt-5.5`. Use `--mc GPT5p2` for `openai/gpt-5.2`. See `model_routing.py` for the complete current mapping.
- The pipeline CLI processes one task per invocation. Omitting `--file` does not run all 200 tasks.

Run the same task through UNI with its Qwen vision model:

```bash
python3 test_model.py \
  --api uni \
  --of t \
  --file basket1.json \
  --mc Qwen \
  --upc f \
  --pipeline_output_dir ./pipeline
```

On the UNI route, `Qwen` currently maps to the vision-capable `qwen3.5` model. The pipeline requires vision support and rejects unsupported UNI models before execution.

### 3.5 Run baselines

Run all 200 tasks with all four baseline methods:

```bash
python3 test_model.py \
  --of f \
  --mc GPT5 \
  --baseline_method all \
  --code f
```

Run one task with one baseline method:

```bash
python3 test_model.py \
  --of f \
  --file basket1.json \
  --mc GPT5 \
  --baseline_method cot \
  --code f
```

`--baseline_method` accepts `base`, `cot`, `ana`, `anacot`, or `all`. When `--file` is omitted, the baseline reads every JSON file under `data/`.

### 3.6 Run code-generation baselines

Run the code baseline on all tasks:

```bash
python3 test_model.py \
  --of f \
  --mc GPT5 \
  --baseline_method all \
  --code t
```

Generated Python programs are written under `baseline_code/programs/`. To execute saved programs again without calling an API:

```bash
python3 test_model.py \
  --of f \
  --mc GPT5 \
  --baseline_method all \
  --code t \
  --rerun_code t
```

### 3.7 Generated output directories and formats

These directories are generated only after a run and are excluded from Git. Their default names are shown below because they define the runtime result format; they are not part of the repository architecture in Section 1.

| Mode | Default location | Main contents |
| --- | --- | --- |
| Pipeline | `pipeline/` | `results/`, `programs/`, `logs/`, and `visualizations/` |
| Non-code baseline | `baseline/` | Result JSON, raw-response logs, visualizations, and retry lists |
| Code baseline | `baseline_code/` | The same artifacts plus generated `execute()` programs |
| Offline visualization | `data_visualization_full/`, `arcana_pic/`, `gpt5_one_chance/` | Dataset figures and saved-answer figures generated by `visualization/` scripts |

The pipeline output root is organized by artifact type, model, optional ablation, and task-run directory:

```text
<pipeline_output_dir>/
├── results/<model>[/<ablation>]/<task>_<run>/
│   ├── result_<task>[_<n>].json
│   ├── pipeline_flow_<task>[_<n>].json
│   └── pipeline_flow_<task>[_<n>].html
├── programs/<model>[/<ablation>]/<task>_<run>/
├── logs/<model>[/<ablation>]/<task>_<run>/
└── visualizations/<model>[/<ablation>]/<task>_<run>/
```

- `result_<task>.json` stores task correctness, the best program, per-test correctness, model IDs, API-call counts, token usage, and estimated cost.
- `pipeline_flow_<task>.json` stores the ordered pipeline nodes/events and cumulative usage metadata.
- `pipeline_flow_<task>.html` is the human-readable flow report generated from the flow JSON.
- `programs/`, `logs/`, and `visualizations/` preserve generated Python programs, raw execution logs, and grid images for the same task run.

Baseline output roots use this structure:

```text
<baseline_output_dir>/
├── results/<model>/
│   ├── batch_baseline_answer_dict.json
│   └── to_be_test.json
├── logs/<model>/<run_id>/batch_full_response.jsonl
├── visualizations/<model>/<method>/
└── programs/<model>/<task>/             # code baseline only
```

- `batch_baseline_answer_dict.json` is nested as model → prompt method → task. Each task record contains answers, `corr_num`/`all_num`, correct-test indices, token counts, cost, and best-pass metadata.
- Code-baseline task records additionally retain example outputs and example-level correctness; `programs/` contains the generated `execute()` implementations.
- `to_be_test.json` records tasks that failed, were incomplete, or need another pass.
- `batch_full_response.jsonl` contains raw per-call model responses and request metadata. It can be large and may contain full prompts.

Use a separate output directory for every formal run:

```bash
python3 test_model.py \
  --of f \
  --mc GPT5 \
  --baseline_method all \
  --baseline_output_dir ./baseline_runs/gpt5_all
```

### 3.8 Concurrency, timeouts, and UNI generation settings

Set these environment variables before starting a run:

| Environment variable | Default | Purpose |
| --- | ---: | --- |
| `ARCANA_BASELINE_BATCH_SIZE` | `25` | Concurrent default-route baseline requests |
| `ARCANA_UNI_BASELINE_BATCH_SIZE` | `25` | Concurrent UNI baseline requests |
| `ARCANA_PIPELINE_MODIFY_WORKERS` | `4` | Parallel default-route program-modification jobs |
| `ARCANA_UNI_PIPELINE_LLM_WORKERS` | `2` | Concurrent UNI pipeline LLM jobs |
| `ARCANA_CODE_TIMEOUT_SECONDS` | `10` | Local execution timeout for each generated program |
| `ARCANA_UNI_BASELINE_MAX_LENGTH` | Provider default | Maximum UNI baseline generation length |
| `ARCANA_UNI_PIPELINE_MAX_LENGTH` | Provider default | Maximum UNI pipeline generation length |
| `ARCANA_UNI_ENABLE_THINKING` | Model dependent | Enables UNI Qwen thinking; accepts Boolean forms such as `true` and `false` |

For example, set default baseline concurrency to 8 and the generated-code timeout to 30 seconds:

```bash
export ARCANA_BASELINE_BATCH_SIZE=8
export ARCANA_CODE_TIMEOUT_SECONDS=30
python3 test_model.py --of f --mc GPT5 --baseline_method all --code f
```

Concurrency directly affects provider rate limits, spending rate, and local load. When connecting a new provider, validate one task first with `--file basket1.json` before starting the full dataset.

### 3.9 Other useful options

| Option | Meaning |
| --- | --- |
| `--api default|uni` | Select the default OpenAI-compatible route or the UNI route |
| `--mc MODEL` | Select a model alias or full model ID defined by `model_routing.py` |
| `--ablation none|direct_targets|task_name` | Select a pipeline ablation preset |
| `--direct_grid t` | Enable the direct-grid challenger during the pipeline break judge |
| `--html_only t` | Regenerate HTML from saved pipeline-flow JSON without rerunning the full pipeline |
| `--baseline_output_dir PATH` | Select the baseline output directory |
| `--pipeline_output_dir PATH` | Select the pipeline output root |
