# IssueLens：可验证的 Python Coding Agent / A Verifiable Python Coding Agent

[![持续集成 / CI](https://github.com/eatdrop/issuelens-agent/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/eatdrop/issuelens-agent/actions/workflows/ci.yml) [![版本 / Release](https://img.shields.io/github/v/release/eatdrop/issuelens-agent?include_prereleases&sort=semver&label=release)](https://github.com/eatdrop/issuelens-agent/releases) [![Python / Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](pyproject.toml) [![许可证 / License](https://img.shields.io/github/license/eatdrop/issuelens-agent)](LICENSE)

IssueLens 是一个本地优先、证据可追溯、默认只读的 Python Coding Agent。它把 Issue 分析、代码证据、人工审批、隔离验证和审计回执连接为一条可复现链路。

IssueLens is a local-first, evidence-grounded, read-only-by-default Coding Agent for Python repositories. It connects Issue analysis, code evidence, human approval, isolated validation, and audit receipts into a reproducible chain.

> 当前版本是作品集级 Alpha，不是生产级自动修复服务。候选补丁来自外部输入；系统不会自动写入目标仓库、Push、创建或合并 PR。
>
> The current release is a portfolio-grade alpha, not a production autonomous repair service. Candidate patches are supplied externally; the system never writes to the target repository or automatically pushes, opens, or merges a PR.

## 核心能力 / Core Capabilities

- **证据驱动分析 / Evidence-grounded analysis**：结合文本检索和 Python AST 索引，将诊断与计划绑定到文件、行号、片段和 SHA-256。
  Combines text retrieval and Python AST indexing, grounding diagnoses and plans in paths, line ranges, snippets, and SHA-256 hashes.
- **受限 Agent 循环 / Constrained Agent loop**：模型只能调用经过校验的只读工具，没有通用 Shell、网络或直接文件系统权限。
  The model may call only validated read-only tools and receives no general-purpose shell, network, or direct filesystem access.
- **可恢复执行 / Resumable execution**：完整性保护的 Checkpoint、仓库/Issue 漂移检测、工具/证据/时间预算和有界模型重试。
  Integrity-protected checkpoints, repository/Issue drift detection, tool/evidence/time budgets, and bounded model retries.
- **快照绑定审批 / Snapshot-bound approval**：Unified Diff 与基础快照形成 Proposal Hash，人工必须明确确认准确对象。
  A Unified Diff and its base snapshot form a Proposal Hash that a human must explicitly confirm.
- **Shadow Workspace 验证 / Shadow Workspace validation**：默认在固定镜像、断网、非 root、只读挂载和限资源 Docker 容器中证明“补丁前失败、补丁后通过、隐藏测试通过”。
  By default, a pinned, network-disabled, non-root, resource-bounded Docker container with a read-only mount proves “fail before, pass after, hidden tests pass.”
- **本地人工审阅 / Local human review**：仅监听回环地址、随机访问令牌、转义不可信内容，并追加记录批准或拒绝计划的决策。
  A loopback-only dashboard uses a random access token, escapes untrusted content, and append-records plan approval or rejection decisions.
- **Draft PR 文本导出 / Draft PR text export**：生成中英双语 PR 草稿正文，但不调用 GitHub 发布接口。
  Produces a bilingual PR draft body without calling GitHub publication APIs.
- **可复现评测 / Reproducible evaluation**：8 个合成案例、明确分母、失败分类和 CI Artifact；不把合成结果冒充真实 Issue 能力。
  Eight synthetic cases, explicit denominators, failure taxonomy, and CI artifacts—without presenting synthetic results as real-Issue capability.

## 工作流 / Workflow

```text
Issue / 问题描述
  → Read-only Tools + AST/Text Retrieval / 只读工具与 AST/文本检索
  → Evidence-grounded Plan + Trace / 基于证据的计划与轨迹
  → Integrity Checkpoint + Budgets / 完整性检查点与预算
  → Candidate Unified Diff / 外部候选补丁
  → Snapshot-bound Hash Approval / 快照绑定哈希审批
  → Docker Shadow Validation / Docker 隔离验证
       baseline reproduction fails / 补丁前复现失败
       patched reproduction passes / 补丁后复现通过
       regression + hidden tests pass / 回归与隐藏测试通过
  → Content-addressed Receipt / 内容寻址回执
  → Local Review UI + Draft PR Text / 本地审阅与 PR 草稿文本
```

分析、验证、审阅和发布被设计为不同权限等级。模型推理不能绕过补丁策略、人工门、容器边界或真实仓库只读不变量。

Analysis, validation, review, and publication are separate authority levels. Model reasoning cannot bypass patch policy, the human gate, the container boundary, or the real-repository read-only invariant.

## 快速开始 / Quick Start

项目运行时只依赖 Python 3.11+ 标准库；Docker 仅用于安全的目标测试执行。

The runtime uses only the Python 3.11+ standard library; Docker is used only for safe target-test execution.

```bash
git clone https://github.com/eatdrop/issuelens-agent.git
cd issuelens-agent
make test
make eval
make demo
```

运行离线 Agent 分析：

Run the offline Agent analysis:

```bash
PYTHONPATH=src python3 -m issuelens agent \
  --repo fixtures/calculator_repo \
  --issue evals/cases/division_by_zero.md \
  --policy offline \
  --run-id demo-agent \
  --run-dir runs \
  --max-steps 8 \
  --max-tool-calls 8 \
  --max-evidence 100 \
  --max-elapsed-seconds 120
```

如果进程在完成前中断，可使用同一仓库、Issue 和 Run ID 恢复；任何输入漂移都会失败关闭：

If the process is interrupted before completion, resume with the same repository, Issue, and Run ID; any input drift fails closed:

```bash
PYTHONPATH=src python3 -m issuelens agent \
  --repo fixtures/calculator_repo \
  --issue evals/cases/division_by_zero.md \
  --policy offline \
  --run-id demo-agent \
  --run-dir runs \
  --resume
```

每次运行生成结构化报告、双语报告、完整轨迹和完整性检查点：

Each run produces a structured report, bilingual report, complete trace, and integrity-protected checkpoint:

```text
runs/<run-id>/
├── report.json
├── report.md
├── trace.jsonl
└── checkpoint.json
```

## Shadow Workspace 演示 / Shadow Workspace Demo

先预拉固定 Docker 镜像；运行时使用 `--pull=never`，不会在验证过程中访问镜像仓库：

Pre-pull the pinned Docker image. Runtime validation uses `--pull=never` and never contacts a registry during execution:

```bash
docker pull python:3.12.10-slim@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db
make shadow-demo
```

演示会展示 Proposal Hash，并要求人工粘贴完整哈希与审批人名称。Docker Runner 强制 `--network=none`、非 root、只读根文件系统、只读工作区、`no-new-privileges`、能力清空及 CPU/内存/进程/超时限制。

The demo shows a Proposal Hash and requires a human to paste the complete hash and an approver name. The Docker runner enforces `--network=none`, non-root execution, a read-only root filesystem and workspace, `no-new-privileges`, dropped capabilities, and CPU/memory/process/time limits.

仅对仓库内可信固定夹具，可显式选择宿主机执行：

Host execution is available only as an explicit opt-in for trusted in-repository fixtures:

```bash
make shadow-demo-local
```

`shadow-demo-local` 会执行目标测试，不能用于未知或不可信仓库。完整威胁模型见 [Shadow Workspace 验证 / Shadow Workspace Validation](docs/shadow-validation.md)。

`shadow-demo-local` executes target tests on the host and must never be used for unknown or untrusted repositories. See [Shadow Workspace Validation / Shadow Workspace 验证](docs/shadow-validation.md) for the complete threat model.

## 本地审阅与 Draft PR 导出 / Local Review and Draft PR Export

先运行 `make demo`，再启动本地仪表盘：

Run `make demo`, then start the local dashboard:

```bash
make dashboard
```

终端会输出带随机令牌的回环地址。网页中的批准/拒绝只记录“分析计划审阅决策”，不等同于补丁 Proposal Hash 审批，也不会触发外部发布。

The terminal prints a loopback URL containing a random token. Approve/reject in the page records an “analysis-plan review decision”; it is not patch Proposal Hash approval and triggers no external publication.

将报告、候选 Diff 和可选验证回执导出为 PR 草稿正文：

Export a report, candidate Diff, and optional validation receipt as a PR draft body:

```bash
PYTHONPATH=src python3 -m issuelens draft-pr \
  --repo fixtures/calculator_repo \
  --report runs/demo-agent/report.json \
  --diff evals/patches/division_by_zero.diff \
  --validation-receipt /tmp/issuelens-shadow-audit/<receipt-hash>.json \
  --output /tmp/issuelens-draft-pr.md
```

输出必须位于目标仓库之外，已有文件不会被覆盖。详见 [本地审阅与导出 / Local Review and Export](docs/web-review.md)。

The output must remain outside the target repository, and existing files are never overwritten. See [Local Review and Export / 本地审阅与导出](docs/web-review.md).

## LLM 端点 / LLM Endpoint

IssueLens 可接入兼容 Chat Completions JSON 输出的端点。API Key 只由适配器读取，不进入 Prompt、Trace 或验证容器。

IssueLens can use an endpoint compatible with Chat Completions JSON output. The API key is read only by the adapter and never enters prompts, traces, or validation containers.

```bash
export ISSUELENS_API_KEY="..."
PYTHONPATH=src python3 -m issuelens agent \
  --repo fixtures/calculator_repo \
  --issue evals/cases/division_by_zero.md \
  --policy llm \
  --endpoint "https://your-provider.example/v1/chat/completions" \
  --model "your-model" \
  --max-retries 2 \
  --run-dir runs
```

模型只能请求 `list_files`、`find_symbol`、`search_text`、`read_file` 和 `submit_analysis`。

The model may request only `list_files`, `find_symbol`, `search_text`, `read_file`, and `submit_analysis`.

## 评测结果 / Evaluation Results

2026-08-03 的 deterministic baseline 在 8 个手工维护的合成案例上得到：

On 2026-08-03, the deterministic baseline produced these results on eight manually maintained synthetic cases:

| 指标 / Metric | 结果 / Result | 有效样本 / Eligible Cases |
|---|---:|---:|
| Hit@1 | 1.0000 | 6 / 6 |
| Gold File Recall@3 | 1.0000 | 6 / 6 |
| Mean Reciprocal Rank | 1.0000 | 6 / 6 |
| 状态准确率 / Status Accuracy | 1.0000 | 8 / 8 |
| 安全拒绝率 / Safe Abstention Rate | 1.0000 | 2 / 2 |
| 仓库保持不变率 / Repository Unchanged Rate | 1.0000 | 8 / 8 |
| 计划证据覆盖率 / Plan Evidence Coverage | 1.0000 | 6 个可审查案例 / 6 review-ready cases |

这些数字只证明固定合成夹具上的可复现行为，不代表真实 Issue 准确率或 Resolved@1。详情、逐案例结果和限制见 [固定夹具基线 / Fixed-fixture Baseline](docs/evaluation-baseline.md)。

These numbers prove reproducible behavior only on fixed synthetic fixtures; they are not real-Issue accuracy or Resolved@1. See [Fixed-fixture Baseline / 固定夹具基线](docs/evaluation-baseline.md) for per-case results and limitations.

```bash
make eval
make test
```

当前测试套件包含 130 个用例；受限本地沙箱会跳过 1 个回环套接字集成测试，该测试已在允许 `127.0.0.1` 的环境中单独通过。

The current suite contains 130 test cases. A restricted local sandbox skips one loopback-socket integration test, which passes separately in an environment allowing `127.0.0.1`.

CI 在 Python 3.11 和 3.12 上运行全部测试与评测，并单独运行默认 Docker Shadow Validation。评测及验证回执作为短期 GitHub Actions Artifact 上传。

CI runs the complete test suite and evaluation on Python 3.11 and 3.12, plus a separate default-Docker Shadow Validation job. Evaluation artifacts and validation receipts are uploaded as short-lived GitHub Actions artifacts.

## 安全边界 / Security Boundaries

- 真实目标仓库在分析、预检和验证前后必须保持同一快照。
  The real target repository must retain the same snapshot before and after analysis, preflight, and validation.
- Diff 路径、测试目录、审计目录和输出目录都经过边界检查。
  Diff paths, test directories, audit directories, and output directories are boundary-checked.
- Docker 验证不挂载凭据、SSH Agent 或 Docker Socket，且默认断网。
  Docker validation mounts no credentials, SSH agent, or Docker socket and is network-disabled by default.
- `approved_by` 与网页审阅人都是声明式元数据，不是认证身份。
  `approved_by` and web reviewers are declared metadata, not authenticated identities.
- SHA-256 提供内容完整性与对象绑定，不是数字签名或访问控制。
  SHA-256 provides content integrity and object binding, not digital signatures or access control.
- 本地 Runner 仅用于可信夹具；容器边界也不能等同于生产级恶意代码沙箱。
  The local runner is only for trusted fixtures; the container boundary is still not equivalent to a production-grade hostile-code sandbox.

完整说明见 [安全模型 / Security Model](SECURITY.md)。

See [Security Model / 安全模型](SECURITY.md) for the complete statement.

## 路线图状态 / Roadmap Status

v0.2 MVP 已完成：只读分析、受限 Agent 循环、补丁协议、Docker Shadow Workspace、failing-test → patch → hidden-test 闭环、Checkpoint/预算/重试、本地审阅界面、Draft PR 文本导出和 8 案例合成评测。

The v0.2 MVP is complete: read-only analysis, constrained Agent loop, patch protocol, Docker Shadow Workspace, failing-test → patch → hidden-test loop, checkpoints/budgets/retries, local review UI, Draft PR text export, and an eight-case synthetic evaluation.

仍在后续路线图中：可信身份、依赖构建阶段、独立 Trace Replay、30–50 个时间切分公开 Issue、真实 Resolved@1、自动发布 PR（默认关闭）和维护者反馈。

Still on the post-MVP roadmap: trusted identity, a dependency-build phase, independent trace replay, 30–50 time-split public Issues, real Resolved@1, automatic PR publication (disabled by default), and maintainer feedback.

## 文档 / Documentation

- [架构说明 / Architecture](docs/architecture.md)
- [Shadow Workspace 验证 / Shadow Workspace Validation](docs/shadow-validation.md)
- [本地审阅与导出 / Local Review and Export](docs/web-review.md)
- [评测方案 / Evaluation](docs/evaluation.md)
- [固定夹具基线 / Fixed-fixture Baseline](docs/evaluation-baseline.md)
- [作品集表述 / Portfolio](docs/portfolio.md)
- [面试演示 / Interview Demo](docs/interview-demo.md)
- [后续路线图 / Roadmap](docs/roadmap.md)
- [安全模型 / Security Model](SECURITY.md)
- [版本记录 / Changelog](CHANGELOG.md)

## 许可证 / License

[MIT](LICENSE)
