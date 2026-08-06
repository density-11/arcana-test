# ARCANA Core Code

[English](README.md) | 中文

本目录集中保存 ARCANA 的任务数据、推理 pipeline、baseline、配套源码以及 human study 网页。运行产物会在本地生成并被 Git 忽略；具体格式见第 3.7 节。

## 1. 文件夹架构

### 总体结构

```text
core_code/
├── README.md                         # 英文说明
├── README_CN.md                      # 中文说明
├── data/                             # 200 道 ARCANA 任务的 JSON 数据
├── test_model.py                     # Pipeline 和 baseline 的统一命令行入口
├── pipeline_runner.py                # 完整 pipeline 主流程
├── baseline_runner.py                # Baseline 主流程
├── prompts.py                        # Pipeline 与 baseline 使用的提示词
├── ablation_prompts.py               # Ablation 相关提示词
├── api_routing.py                    # 共用 API 路由与凭证解析
├── model_routing.py                  # 共用模型别名、ID 与视觉能力解析
├── providers/                        # 不同 provider 的专用设置与适配器
│   ├── __init__.py
│   ├── openrouter.py                 # OpenRouter reasoning effort 设置
│   └── uni/
│       ├── __init__.py
│       ├── generation.py             # UNI max length 与 thinking 设置
│       ├── models.py                 # UNI 模型表、别名与视觉模型 ID
│       └── streaming.py              # UNI 同步/异步流式响应拼接
├── utils/                            # Pipeline 与 baseline 共用工具包
│   ├── __init__.py
│   ├── common_utils.py               # 数据读取、执行、评测与成本通用函数
│   ├── analogy_target_utils.py       # Analogy 输出解析与规范化
│   ├── concept_expansion_utils.py    # Concept expansion 输出解析
│   ├── direct_grid_utils.py          # Direct-grid prediction 与仲裁工具
│   └── visualization.py              # 模型调用所需运行图与 Base64 Data URL
├── analogy_aspects.py                # Analogy 生成维度与组合逻辑
├── analogy_aspects.json              # Analogy 维度配置数据
├── pipeline_ablations.py             # Pipeline ablation 配置与处理
├── data_process.py                   # 数据处理辅助代码
├── visualization/                    # 独立离线可视化工具
│   ├── __init__.py
│   ├── visualize_arc.py              # 可配置的 ARC 任务渲染器
│   ├── visualize_dataset.py          # 数据集批量渲染器
│   └── visualize_model.py            # 已保存模型答案渲染器
├── arc_annotations_summary_default_test.json
│                                       # Human study annotation 汇总
├── pipeline_effective_cases.md       # Pipeline 模块生效案例记录
└── website/                          # 可独立部署的 human study 网页与本地模拟服务器
```

上面的结构只列出预期由 Git 分发的文件和目录。Python 缓存和运行结果目录不在此处列出，其格式在「[3.7 生成的输出目录与格式](#37-生成的输出目录与格式)」中单独说明。

### 主要代码关系

```text
data/*.json
    │
    ▼
test_model.py
    ├── baseline_runner.py ──► 运行时生成的 baseline 输出根目录
    └── pipeline_runner.py ──► 运行时生成的 pipeline 输出根目录

两个 runner 共同使用：
prompts.py、api_routing.py、model_routing.py、utils/common_utils.py、
utils/visualization.py 以及 analogy / expansion / ablation 辅助模块。

不同 provider 的专用逻辑统一放在 providers/：providers/openrouter.py
负责默认 baseline 的 reasoning 设置，providers/uni/ 集中保存 UNI 的生成参数、
模型目录与流式响应适配器。
```

### 各部分职责

| 部分 | 作用 |
| --- | --- |
| `data/` | 当前 Python pipeline 和 baseline 默认读取的任务数据。每个 JSON 都使用顶层结构 `{"train": [...], "test": [...]}`；每个样例包含 `input` 和 `output` 矩阵。 |
| `test_model.py` | 统一 CLI 入口；根据 `--of` 选择 baseline 或 pipeline，并把当前工作目录切到 `core_code`。 |
| `pipeline_runner.py` | 执行 analogy、concept expansion、代码生成、运行验证、反思修正、direct-grid challenger 等完整流程。 |
| `baseline_runner.py` | 执行 `base`、`cot`、`ana`、`anacot` 四类 baseline，并记录 token、成本、答案和评测结果。 |
| `providers/` | 将 provider 专用逻辑与共用路由器分开；`providers/uni/` 保存 UNI 独有的生成、模型和流式处理逻辑，`providers/openrouter.py` 保存 OpenRouter 独有的 reasoning 设置。 |
| `utils/` | Pipeline 与 baseline 共用的解析、规范化、评测、执行、成本和运行时可视化工具。 |
| `visualization/` | 用于渲染数据集和已保存模型答案的独立离线脚本；pipeline 与 baseline 不会导入这些脚本。 |
| `website/` | Human study 前端、本地保存/读取模拟服务器、五组网页测试数据和教程视频；它可以脱离推理 pipeline 单独运行。 |

### 离线可视化工具

在仓库根目录运行：

```bash
python3 visualization/visualize_arc.py
python3 visualization/visualize_dataset.py
python3 visualization/visualize_model.py
```

- `visualize_arc.py` 读取 `data/*.json`，将可配置的任务图写入 `data_visualization_full/`；测试答案字段可使用 `answer` 或 `output`。
- `visualize_dataset.py` 将完整数据集渲染到 `arcana_pic/`。
- `visualize_model.py` 读取本地生成的 `one_chance_answers.json`，将图片写入 `gpt5_one_chance/`。
- 上述三个输出目录都是运行时产物，会被 Git 忽略。Pipeline 与 baseline 使用 `utils/visualization.py`，并将运行图写入各自配置的输出根目录。

### 数据与运行输出边界

- Python pipeline 和 baseline 默认读取 `core_code/data/`。
- 全部 200 个任务文件都使用 `train` 保存训练示例、使用 `test` 保存测试样例；读取代码仍兼容外部文件中的旧字段 `examples`。
- Pipeline 和 baseline 的输出目录在运行时生成，并被 Git 忽略，不属于上面展示的可分发源码结构。
- 正式实验建议每次使用独立输出根目录，避免不同模型或配置的结果混在一起。
- `website/test/test_group*.json` 是已经组装好的网页数据快照，不会动态读取 `core_code/data/`。修改 `data/*.json` 后，如果希望网页同步变化，还需要重新生成或手动更新对应的 test-group JSON。

## 2. Website：内容与本地部署

`website/` 包含 ARCANA human study 的完整参与者流程。随附的 Python 本地服务器通过本地 JSON 模拟知情同意、参与者 ID 查找、题组分配、进度保存/恢复和最终结果提交；不需要 Node.js、前端依赖或原 Cloudflare Worker、KV、R2。目录总大小主要来自教程视频。

### Website 目录结构

```text
website/
├── server.py                         # 本地静态服务与 API 模拟
├── test_local_server.py              # 本地存储回归测试
├── index.html                        # 知情同意与参与者 ID 入口
├── consent_end.html                  # 不同意参与后的结束页
├── test.html                         # 教程、注意力检查和正式测试
├── admin/
│   └── index.html                    # 仅限本机访问的本地 Admin
├── test/
│   ├── test_group1.json
│   ├── test_group2.json
│   ├── test_group3.json
│   ├── test_group4.json
│   └── test_group5.json              # 五组已组装的教程与正式题目
└── tutorial_video/
    ├── drag_cn.mp4 / drag_en.mp4
    ├── draw_cn.mp4 / draw_en.mp4
    ├── edit_1_cn.mp4 ... edit_8_cn.mp4
    ├── edit_1_en.mp4 ... edit_8_en.mp4
    └── test_cn.mp4 / test_en.mp4
```

每个 `test_group` 包含两道教程题和二十道正式题。完整本地流程按参与者 ID 轮转分配题组；纯静态预览仍可通过 `local_group` 参数指定题组。

### 环境要求

- Python 3.10 或更高版本；本地服务器只使用标准库。
- 任意现代浏览器。
- 不需要 API key 或外部服务。

### macOS / Linux 启动方法

从包含 `core_code` 的上一级目录执行：

```bash
cd core_code/website
python3 server.py
```

### Windows 启动方法

```powershell
cd core_code\website
py server.py
```

保持终端中的服务器继续运行，然后在浏览器打开：

```text
http://127.0.0.1:8000/
```

首页先显示中英文知情同意书。同意后输入任意非空的本地测试 ID；服务器会查找该 ID 的已有分配与进度，或者从五组中分配一组。重新打开首页并输入同一 ID，即可测试恢复过程。

本地 Admin 地址是 `http://127.0.0.1:8000/admin/`。它可以查看分配与状态统计、各题组累计使用次数、当前保存进度和已提交结果；支持下载单份进度、单份结果或全部结果 JSON，也可以为明确输入的 participant ID 创建或复用分配。

修改端口或使用独立数据目录：

```bash
python3 server.py --port 8080
python3 server.py --data-dir ./my_local_study_data
```

查看结束后，在运行服务器的终端按 `Ctrl+C` 停止服务。端口改变后，浏览器 URL 也要使用相同端口。

### 本地数据结构与重置方式

第一次启动完整本地服务器后，会生成被 Git 忽略的 `website/local_data/`：

```text
local_data/
├── state.json                 # Participant ID、session、题组和状态
├── progress/                  # 每个 participant ID 当前最新的保存进度
├── progress_archive/          # 提交、超时或锁定后的进度归档
├── results/                   # 完整的最终提交结果 JSON
└── attention_failures/        # Attention Check 失败事件
```

进度文件名使用 participant ID 的 SHA-256 摘要，原始 ID 与 session 的映射仍可在 `state.json` 中查看。写入采用临时文件加原子替换，同一服务器进程中的请求由锁保护。最终提交会把活动进度移入归档，并阻止重复提交。

如果要开始一套独立的本地演示，请先停止服务器，把 `local_data/` 移动或重命名为备份后再重启；也可以用 `--data-dir` 指向另一个目录，不必改动现有数据。

在 `website/` 中运行本地存储和 HTTP 回归测试：

```bash
python3 -m unittest -v test_local_server.py
```

### 本地模式注意事项

- 默认只监听 `127.0.0.1`，不会把参与者回答暴露到局域网。
- 不要直接双击 `test.html`。通过 `file://` 打开时，浏览器可能阻止页面读取 JSON 或视频资源。
- 运行数据写入已被 Git 忽略的 `website/local_data/`：`state.json` 保存分配关系，`progress/` 保存当前进度，`progress_archive/` 保存提交或锁定后的进度，`results/` 保存最终结果。
- 本地服务器接受任意非空 ID，不读取或验证原部署中的真实参与者。
- 分配在 120 小时后过期；已提交或注意力检查失败的分配会锁定。
- `load_remote_json` 只允许读取随包附带的 `/test/test_group*.json`，不会抓取任意外部 URL；题组上传接口也被禁用，网页不能修改分发包中的实验数据。
- 这是开发模拟环境，不是生产后端：本地 Admin 仅允许回环地址访问，并省略了重置、删除、清理、解锁和重新分配等破坏性操作，也不包含云备份、参与者白名单或生产级访问控制；`local_data/` 应按可能含有敏感研究回答的数据处理。
- 如果只想直接查看一组题，运行 `python3 -m http.server 8000 --bind 127.0.0.1`，再打开 `http://127.0.0.1:8000/test.html?local_group=test_group1.json`。该纯静态模式不能保存或恢复。

## 3. 运行 Python 代码

### 3.1 环境与依赖

建议使用 Python 3.10 或更高版本。在 `core_code` 目录中安装当前代码直接使用的第三方包：

```bash
cd core_code
python3 -m pip install openai matplotlib numpy tqdm ipdb
```

仓库当前没有锁定依赖版本；如需严格复现实验，建议在独立虚拟环境中安装并记录实际版本。

### 3.2 配置 API

不要把 API key 写入代码或提交到 Git。不同路由和运行模式读取的环境变量如下：

| 模式 | Base URL | API key |
| --- | --- | --- |
| Pipeline，`--api default` | `OPENAI_BASE_URL` | `OPENAI_API_KEY` |
| Baseline，`--api default` | `OPENAI_BASE_URL` | `OPENAI_API_KEY` |
| Pipeline 或 baseline，`--api uni` | `UNI_BASE_URL` | `UNI_API_KEY` |

默认 pipeline 示例：

```bash
export OPENAI_BASE_URL="https://your-api-endpoint.example/v1"
export OPENAI_API_KEY="your-api-key"
```

默认 baseline 示例：

```bash
export OPENAI_BASE_URL="https://your-api-endpoint.example/v1"
export OPENAI_API_KEY="your-api-key"
```

默认 pipeline 与 baseline 共用 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY`。UNI 路由则使用：

```bash
export UNI_BASE_URL="https://your-uni-endpoint.example/v1"
export UNI_API_KEY="your-uni-api-key"
```

### 3.3 查看命令行参数

所有 Python 命令都从 `core_code` 目录运行。统一入口是 `test_model.py`：

```bash
cd core_code
python3 test_model.py --help
```

`--of t` 运行单题完整 pipeline；`--of f` 运行 baseline。参数中的 `t` 和 `f` 分别表示 true 和 false。

### 3.4 运行单题完整 Pipeline

使用默认 API 路由和当前 `GPT5` 模型映射运行一道题：

```bash
python3 test_model.py \
  --of t \
  --file basket1.json \
  --mc GPT5 \
  --upc f \
  --pipeline_output_dir ./pipeline
```

- `--file` 选择 `data/` 中的任务；`.json` 后缀可省略，因此 pipeline、baseline 和 `--html_only` 中的 `--file basket1` 与 `--file basket1.json` 等价。
- `--upc f` 表示从新程序开始；`--upc t` 会尝试读取该题最近保存的程序。
- `--pipeline_output_dir` 指定包含 `results/`、`programs/`、`logs/` 和 `visualizations/` 的输出根目录。
- 当前 `GPT5` 映射到 `openai/gpt-5.5`；如需 `openai/gpt-5.2`，使用 `--mc GPT5p2`。完整映射见 `model_routing.py`。
- Pipeline CLI 每次处理一道题；它不会因为省略 `--file` 而自动运行全部 200 题。

使用 UNI 的 Qwen 视觉模型运行同一道题：

```bash
python3 test_model.py \
  --api uni \
  --of t \
  --file basket1.json \
  --mc Qwen \
  --upc f \
  --pipeline_output_dir ./pipeline
```

在 UNI 路由中，`Qwen` 当前映射到支持视觉输入的 `qwen3.5`。Pipeline 需要视觉模型；不支持视觉的 UNI 模型会在运行前报错。

### 3.5 运行 Baseline

运行全部 200 题、全部四种 baseline 方法：

```bash
python3 test_model.py \
  --of f \
  --mc GPT5 \
  --baseline_method all \
  --code f
```

只运行一道题和一种 baseline 方法：

```bash
python3 test_model.py \
  --of f \
  --file basket1.json \
  --mc GPT5 \
  --baseline_method cot \
  --code f
```

`--baseline_method` 可选 `base`、`cot`、`ana`、`anacot` 或 `all`。不传 `--file` 时，baseline 会读取 `data/` 中的全部 JSON。

### 3.6 运行代码生成 Baseline

运行全部题目的代码 baseline：

```bash
python3 test_model.py \
  --of f \
  --mc GPT5 \
  --baseline_method all \
  --code t
```

生成的 Python 程序保存在 `baseline_code/programs/`。如需不调用 API、只重新执行已经保存的程序：

```bash
python3 test_model.py \
  --of f \
  --mc GPT5 \
  --baseline_method all \
  --code t \
  --rerun_code t
```

### 3.7 生成的输出目录与格式

以下目录只会在运行后生成，并被 Git 忽略。这里保留它们的默认名称，是为了说明运行结果格式；它们不属于第 1 节的仓库文件架构。

| 运行模式 | 默认位置 | 主要内容 |
| --- | --- | --- |
| Pipeline | `pipeline/` | `results/`、`programs/`、`logs/`、`visualizations/` |
| 普通 baseline | `baseline/` | 结果 JSON、原始响应日志、可视化与待重试列表 |
| 代码 baseline | `baseline_code/` | 上述内容以及生成的 `execute()` 程序 |
| 离线可视化 | `data_visualization_full/`、`arcana_pic/`、`gpt5_one_chance/` | `visualization/` 脚本生成的数据集图片与已保存答案图片 |

Pipeline 输出根目录按产物类型、模型、可选 ablation 和题目运行编号组织：

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

- `result_<task>.json` 保存整题正确性、最佳程序、每个 test 的正确性、模型 ID、API 调用次数、token usage 和估算成本。
- `pipeline_flow_<task>.json` 保存按顺序排列的 pipeline 节点/事件和累积 usage 信息。
- `pipeline_flow_<task>.html` 是根据 flow JSON 生成的可读流程报告。
- `programs/`、`logs/` 和 `visualizations/` 分别保留该次题目运行的生成程序、原始日志和网格图片。

Baseline 输出根目录使用以下结构：

```text
<baseline_output_dir>/
├── results/<model>/
│   ├── batch_baseline_answer_dict.json
│   └── to_be_test.json
├── logs/<model>/<run_id>/batch_full_response.jsonl
├── visualizations/<model>/<method>/
└── programs/<model>/<task>/             # 仅代码 baseline
```

- `batch_baseline_answer_dict.json` 按“模型 → prompt 方法 → 题目”嵌套。每道题记录答案、`corr_num`/`all_num`、正确 test 索引、token 数、成本和 best-pass 信息。
- 代码 baseline 还会保留训练示例输出和示例级正确性；`programs/` 中保存生成的 `execute()` 实现。
- `to_be_test.json` 保存调用失败、结果不完整或需要再次尝试的题目。
- `batch_full_response.jsonl` 保存每次 API 调用的原始模型响应和请求元数据，可能较大，也可能包含完整 prompt。

正式实验建议每次指定一个新的输出目录：

```bash
python3 test_model.py \
  --of f \
  --mc GPT5 \
  --baseline_method all \
  --baseline_output_dir ./baseline_runs/gpt5_all
```

### 3.8 并发、超时与 UNI 生成参数

以下环境变量可以在运行命令前单独设置：

| 环境变量 | 默认值 | 作用 |
| --- | ---: | --- |
| `ARCANA_BASELINE_BATCH_SIZE` | `25` | 默认 API baseline 的并发请求数 |
| `ARCANA_UNI_BASELINE_BATCH_SIZE` | `25` | UNI baseline 的并发请求数 |
| `ARCANA_PIPELINE_MODIFY_WORKERS` | `4` | 默认 API pipeline 的并行程序修改数 |
| `ARCANA_UNI_PIPELINE_LLM_WORKERS` | `2` | UNI pipeline 的 LLM 并发数 |
| `ARCANA_CODE_TIMEOUT_SECONDS` | `10` | 生成程序单次本地执行超时 |
| `ARCANA_UNI_BASELINE_MAX_LENGTH` | provider 默认 | UNI baseline 的最大生成长度 |
| `ARCANA_UNI_PIPELINE_MAX_LENGTH` | provider 默认 | UNI pipeline 的最大生成长度 |
| `ARCANA_UNI_ENABLE_THINKING` | 按模型决定 | UNI Qwen 模型是否启用 thinking；接受 `true/false` 等布尔值 |

例如，将默认 baseline 并发设为 8，并把生成代码执行超时设为 30 秒：

```bash
export ARCANA_BASELINE_BATCH_SIZE=8
export ARCANA_CODE_TIMEOUT_SECONDS=30
python3 test_model.py --of f --mc GPT5 --baseline_method all --code f
```

并发会直接影响 API 限流、费用增长速度和本机负载。第一次接入新的 provider 时，建议先用 `--file basket1.json` 做单题验证，再运行完整数据集。

### 3.9 其他常用选项

| 参数 | 说明 |
| --- | --- |
| `--api default|uni` | 选择默认 OpenAI-compatible 路由或 UNI 路由 |
| `--mc MODEL` | 模型别名或完整模型 ID；可用值由 `model_routing.py` 定义 |
| `--ablation none|direct_targets|task_name` | 选择 pipeline ablation |
| `--direct_grid t` | 在 pipeline break judge 中启用 direct-grid challenger |
| `--html_only t` | 根据已有 pipeline flow JSON 重新生成 HTML，不重新调用完整 pipeline |
| `--baseline_output_dir PATH` | 指定 baseline 输出目录 |
| `--pipeline_output_dir PATH` | 指定 pipeline 输出根目录 |
