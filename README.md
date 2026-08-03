# IssueLens：可追溯的 Python Coding Agent / An Evidence-Grounded Python Coding Agent

IssueLens 是一个本地优先、证据可追溯、默认只读的 Python Coding Agent。

IssueLens is a local-first, evidence-grounded, read-only-by-default Coding Agent for Python repositories.

输入一个本地 Python 仓库和一份公开 Issue 后，IssueLens 可以：

Given a local Python repository and a public Issue, IssueLens can:

1. 解析 Issue 中的文件、符号、异常和行为线索。
   Parse file, symbol, exception, and behavioral clues from the Issue.
2. 结合文本检索与 Python AST 索引定位候选代码。
   Locate candidate code with text retrieval and a Python AST symbol index.
3. 为每个判断保存文件、行号、代码片段和内容哈希。
   Preserve file paths, line numbers, snippets, and content hashes for every conclusion.
4. 生成影响分析、最小修改计划、风险与验收标准。
   Produce impact analysis, a minimal change plan, risks, and acceptance criteria.
5. 验证分析前后目标仓库快照一致，证明 Agent 没有越权写入。
   Verify identical repository snapshots before and after analysis to prove there were no unauthorized writes.
6. 在固定评测集上输出代码定位、证据覆盖率和安全拒绝指标。
   Report localization, evidence coverage, and safe-abstention metrics on a fixed evaluation set.

首个版本重点解决 Coding Agent 最容易被忽略的三个问题：

The first version focuses on three frequently overlooked Coding Agent problems:

- **证据 Grounding**：所有结论必须能回到具体代码证据。
  Every conclusion must trace back to concrete code evidence.
- **安全 Safety**：默认不执行仓库代码，也不写目标仓库。
  Repository code is not executed and the target repository is not modified by default.
- **评测 Evaluation**：不能用一次漂亮 Demo 代替可重复实验。
  A polished one-off demo cannot replace reproducible evaluation.

## 项目动机 / Motivation

真实软件工程任务不是“根据一句话生成一段代码”。Agent 必须理解已有仓库、定位影响范围、提出可验证修改，并在危险动作前等待人工审核。

Real software engineering is not “generate code from one sentence.” An Agent must understand an existing repository, identify the affected scope, propose verifiable changes, and pause for human review before risky actions.

```text
Issue / 问题描述
  ↓
Issue Parser / 问题解析
  ↓
Repository Snapshot / 仓库快照 ──→ Path & Symlink Guard / 路径与符号链接保护
  ↓
Text Search + AST Index / 文本检索与 AST 索引
  ↓
Evidence-Grounded Diagnosis / 基于证据的诊断
  ↓
Change Plan + Tests + Risks / 修改计划、测试与风险
  ↓
Patch Proposal / 候选补丁
  ↓
Explicit Hash Approval / 显式哈希审批
  ↓
Temporary-copy Preflight / 临时副本预检
  ↓
Content-addressed Audit Receipt / 内容寻址审计回执
```

## 快速开始 / Quick start

首版只使用 Python 标准库，不需要 API Key。默认 Demo 会运行一个具有步数预算、显式工具契约和完整 Trace 的离线 Agent Policy。

The first version uses only the Python standard library and needs no API key. The default demo runs an offline Agent policy with a step budget, explicit tool contracts, and a complete trace.

```bash
cd issuelens-agent
make demo
```

一条命令启动交互式补丁审查演示。命令会暂停并要求你手动粘贴刚刚展示的完整 Proposal Hash，再输入审批人名称：

Start the interactive patch review demo with one command. It pauses and asks you to manually paste the complete Proposal Hash that was just displayed, followed by the approver name:

```bash
make patch-demo
```

直接运行离线 Agent Loop：

Run the offline Agent loop directly:

```bash
PYTHONPATH=src python3 -m issuelens agent \
  --repo fixtures/calculator_repo \
  --issue evals/cases/division_by_zero.md \
  --policy offline \
  --run-dir runs
```

接入兼容 Chat Completions JSON 输出的模型端点：

Connect an endpoint compatible with Chat Completions JSON output:

```bash
export ISSUELENS_API_KEY="..."
PYTHONPATH=src python3 -m issuelens agent \
  --repo fixtures/calculator_repo \
  --issue evals/cases/division_by_zero.md \
  --policy llm \
  --endpoint "https://your-provider.example/v1/chat/completions" \
  --model "your-model" \
  --run-dir runs
```

模型没有 Shell 或直接文件系统权限，只能请求经过校验的 `list_files`、`find_symbol`、`search_text`、`read_file` 和 `submit_analysis` 动作。

The model receives neither shell access nor direct filesystem access. It may only request the validated `list_files`, `find_symbol`, `search_text`, `read_file`, and `submit_analysis` actions.

运行产物包括：

Each run produces:

```text
runs/<run-id>/
├── report.json       # 结构化结果 / Structured result
├── report.md         # 中英双语报告 / Bilingual report
└── trace.jsonl       # 完整动作轨迹 / Complete action trace
```

执行评测与测试：

Run evaluations and tests:

```bash
make eval
make test
```

## 人工审批补丁审查演示 / Human-approved patch review demo

下面的流程展示如何审查一个候选 Unified Diff。所有哈希均由当前仓库快照和补丁内容计算，因此实际输出会与示例占位符不同。

The following flow demonstrates how to review a candidate Unified Diff. All hashes are calculated from the current repository snapshot and patch content, so real output will differ from the example placeholders.

首先准备一个只修改演示仓库的补丁文件：

First, prepare a patch file that only changes the fixture repository:

```bash
cat > /tmp/issuelens-candidate.diff <<'DIFF'
--- a/src/calculator.py
+++ b/src/calculator.py
@@ -13,1 +13,3 @@
-    return left / right
+    if right == 0:
+        raise ValueError("right must not be zero")
+    return left / right
DIFF
```

### 第一步：检查并生成提案哈希 / Step 1: Inspect and generate a Proposal Hash

`patch-proposal` 解析补丁、校验路径策略，并将提案绑定到目标仓库的当前快照。它不会修改仓库。

`patch-proposal` parses the patch, validates its path policy, and binds the proposal to the target repository's current snapshot. It does not modify the repository.

```bash
PYTHONPATH=src python3 -m issuelens patch-proposal \
  --repo fixtures/calculator_repo \
  --diff /tmp/issuelens-candidate.diff
```

示例输出：

Example output:

```json
{
  "added_lines": 3,
  "base_snapshot_hash": "<base-snapshot-hash>",
  "changed_file_count": 1,
  "changed_paths": [
    "src/calculator.py"
  ],
  "proposal_hash": "<proposal-hash>",
  "removed_lines": 1,
  "repository_unchanged": true
}
```

人工审查补丁和 `changed_paths` 后，复制完整的 64 位小写 `proposal_hash`。如果补丁或仓库快照发生变化，下一步的哈希审批会失败。

After reviewing the patch and `changed_paths`, copy the complete 64-character lowercase `proposal_hash`. If either the patch or repository snapshot changes, the hash approval in the next step will fail.

### 第二步：显式审批并在临时副本中预检 / Step 2: Explicitly approve and preflight in a temporary copy

将 `<proposal-hash>` 替换为上一步的真实值。`--audit-dir` 必须位于目标仓库之外；示例将内容寻址回执写入 `/tmp/issuelens-audit`。

Replace `<proposal-hash>` with the real value from Step 1. `--audit-dir` must be outside the target repository; this example writes the content-addressed receipt to `/tmp/issuelens-audit`.

```bash
PYTHONPATH=src python3 -m issuelens patch-review \
  --repo fixtures/calculator_repo \
  --diff /tmp/issuelens-candidate.diff \
  --run-id demo-review-001 \
  --approved-by "your-name" \
  --approve-proposal-hash "<proposal-hash>" \
  --audit-dir /tmp/issuelens-audit
```

示例输出：

Example output:

```json
{
  "approval_hash": "<approval-hash>",
  "audit_path": "/tmp/issuelens-audit/<receipt-hash>.json",
  "base_snapshot_hash": "<base-snapshot-hash>",
  "preview_snapshot_hash": "<preview-snapshot-hash>",
  "proposal_hash": "<proposal-hash>",
  "receipt_hash": "<receipt-hash>",
  "repository_unchanged": true,
  "run_id": "demo-review-001"
}
```

该命令只在标准库创建的临时副本中尝试应用补丁，然后保存不可覆盖的内容寻址回执；它不会把补丁写入真实仓库。`--approved-by` 是声明式审计元数据，不是经过认证的数字身份。

This command only attempts to apply the patch in a standard-library temporary copy and then stores a non-overwriting, content-addressed receipt; it never writes the patch to the real repository. `--approved-by` is declared audit metadata, not an authenticated digital identity.

### 第三步：验证回执并生成人类可读报告 / Step 3: Verify the receipt and render a human-readable report

将 `<receipt-hash>` 替换为第二步返回的真实值：

Replace `<receipt-hash>` with the real value returned by Step 2:

```bash
PYTHONPATH=src python3 -m issuelens audit-report \
  --audit-dir /tmp/issuelens-audit \
  --receipt-hash "<receipt-hash>"
```

报告会先验证回执完整性，再输出中英双语 Markdown 摘要，其中包括运行标识、提案/审批/快照哈希、文件级变更统计和以下关键结论：

The command verifies receipt integrity before rendering a bilingual Markdown summary with the Run ID, proposal/approval/snapshot hashes, file-level change statistics, and these key conclusions:

```text
状态 / Status: 通过 / Passed
真实仓库写入 / Real repository write: 否 / No
回执完整性 / Receipt integrity: 已验证 / Verified
```

当前流程证明“指定补丁已针对指定仓库快照，在临时副本中通过预检并留下可验证回执”，但不执行目标仓库测试、不认证审批人身份，也不代表补丁已经合并或写入真实仓库。

The current flow proves that “an exact patch passed preflight against an exact repository snapshot in a temporary copy and produced a verifiable receipt.” It does not run target-repository tests, authenticate the approver, or imply that the patch was merged or written to the real repository.

## 当前能力边界 / Current scope

V0.1 提供可复现的 deterministic baseline，用于验证仓库读取、检索、状态机、工具循环、证据链和评测体系。它不会声称能够自动修复任意 Issue。

V0.1 provides a reproducible deterministic baseline for validating repository access, retrieval, the state machine, the tool loop, evidence chains, and evaluation. It does not claim to repair arbitrary Issues automatically.

当证据不足时，系统返回 `insufficient_evidence`，而不是编造补丁。真实 LLM 只替换 Reasoner/Policy，仓库访问、安全、Trace 和 Eval 不随模型变化。

When evidence is insufficient, the system returns `insufficient_evidence` instead of fabricating a patch. A real LLM replaces only the Reasoner/Policy; repository access, safety, tracing, and evaluation remain unchanged.

## 安全原则 / Safety principles

- 所有路径必须位于仓库根目录。
  Every path must remain inside the repository root.
- 拒绝绝对路径、`..` 路径逃逸和指向仓库外的符号链接。
  Absolute paths, `..` traversal, and escaping symlinks are rejected.
- 默认不执行或写入目标仓库。
  The target repository is neither executed nor modified by default.
- 运行产物写入外部 `run-dir`。
  Run artifacts are written to an external `run-dir`.
- 分析前后计算仓库快照，任何非预期变化都会使运行失败。
  Repository snapshots are calculated before and after analysis; unexpected changes fail the run.
- 候选补丁绑定仓库快照哈希；人工审批绑定运行标识、提案、基础快照、声明的审批人和审批时间。
  Candidate patches are bound to repository snapshot hashes; human approvals bind the Run ID, proposal, base snapshot, declared approver, and approval time.
- 补丁预检只在临时副本中进行，不会写入真实仓库。
  Patch preflight runs only in a temporary copy and never writes to the real repository.
- 审计回执存储在目标仓库之外，并通过内容哈希命名和验证。
  Audit receipts are stored outside the target repository, named and verified by their content hashes.

## 路线图 / Roadmap

- [x] Issue 解析、代码检索、AST 符号索引
  Issue parsing, code retrieval, and AST symbol indexing
- [x] 证据哈希、仓库快照、状态机与 Trace
  Evidence hashes, repository snapshots, state machine, and tracing
- [x] 离线评测与安全测试
  Offline evaluation and safety tests
- [x] 有步数预算的结构化 LLM Tool Calling
  Structured LLM tool calling with a step budget
- [x] Unified Diff 解析与策略校验
  Unified Diff parsing and policy validation
- [x] 快照绑定的提案、显式人工审批、临时副本预检与内容寻址审计回执
  Snapshot-bound proposals, explicit human approval, temporary-copy preflight, and content-addressed audit receipts
- [ ] 临时 Docker Shadow Workspace
  Ephemeral Docker shadow workspace
- [ ] failing-test → patch → hidden-test 验证闭环
  failing-test → patch → hidden-test validation loop
- [ ] Checkpoint、跨阶段预算与重试
  Checkpoints, cross-stage budgets, and retries
- [ ] GitHub Draft PR，默认关闭并仅在明确批准后启用
  GitHub Draft PR, disabled by default and enabled only after explicit approval
- [ ] 30–50 个近期公开 Issue 的时间切分评测
  Time-split evaluation on 30–50 recent public Issues

详细信息请阅读：

Learn more:

- [架构说明 / Architecture](docs/architecture.md)
- [评测方案 / Evaluation](docs/evaluation.md)
- [12 周路线图 / 12-week roadmap](docs/roadmap.md)
- [安全说明 / Security](SECURITY.md)
- [作品集展示 / Portfolio](docs/portfolio.md)
