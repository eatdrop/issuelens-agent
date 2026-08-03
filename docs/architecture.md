# IssueLens 架构 / Architecture

## 产品边界 / Product Boundary

IssueLens 当前包含两条相互隔离的工作流：

IssueLens currently contains two isolated workflows:

1. **Issue 分析 / Issue analysis**：只读解析 Issue、检索代码证据，并输出修改计划和完整 Trace。
   Read-only parsing of Issues, retrieval of code evidence, and generation of change plans and complete traces.
2. **补丁审查 / Patch review**：将外部提供的候选 Unified Diff 绑定到仓库快照，经显式人工审批后只在临时副本中预检，并把回执写入目标仓库外部。
   Bind an externally supplied candidate Unified Diff to a repository snapshot, require explicit human approval, preflight it only in a temporary copy, and write the receipt outside the target repository.

两条工作流都不会执行目标仓库代码，也不会修改真实目标仓库。补丁审查不会从 Issue 自动生成补丁。

Neither workflow executes target-repository code or modifies the real target repository. Patch review does not generate a patch automatically from an Issue.

系统将五类职责明确分离：

The system separates five concerns:

1. **仓库访问 / Repository access**：负责路径校验、文件大小限制和快照。
   Owns path validation, file-size limits, and snapshots.
2. **检索 / Retrieval**：负责文本搜索和 AST 符号索引。
   Owns text search and AST symbol indexing.
3. **推理策略 / Reasoning policy**：把 Issue 信号与证据转换为计划。
   Converts Issue signals and evidence into a plan.
4. **工作流与评测 / Workflow and evaluation**：负责状态、Trace、安全不变量和指标。
   Owns state, traces, safety invariants, and metrics.
5. **补丁协议与审计 / Patch protocol and audit**：负责 Unified Diff 策略、提案与审批绑定、临时副本预检和内容寻址回执。
   Owns Unified Diff policy, proposal and approval binding, temporary-copy preflight, and content-addressed receipts.

离线 deterministic policy 和兼容 Chat Completions JSON 的 LLM policy 可以共享相同的仓库访问、安全、Trace 和评测边界；模型不需要直接文件系统或 Shell 权限。

The offline deterministic policy and an LLM policy compatible with Chat Completions JSON share the same repository-access, safety, tracing, and evaluation boundaries; the model needs neither direct filesystem nor shell access.

## 状态机 / State Machine

```text
CREATED / 已创建
  → ISSUE_PARSED / Issue 已解析
  → REPO_SNAPSHOTTED / 仓库已生成快照
  → INDEX_BUILT / 索引已构建
  → EVIDENCE_RETRIEVED / 证据已检索
  → PLAN_CREATED / 计划已生成
  → REPO_VERIFIED / 仓库已验证
  → FINISHED / 已完成
```

每次状态迁移都会写入 `trace.jsonl`，非法迁移会失败并停止。

Every transition is written to `trace.jsonl`; illegal transitions fail closed.

该状态机描述 Issue 分析工作流。补丁审查使用独立的显式链路：

This state machine describes the Issue-analysis workflow. Patch review uses a separate explicit chain:

```text
Repository Snapshot + Unified Diff / 仓库快照与候选补丁
  → Patch Proposal / 补丁提案
  → Explicit Human Approval / 显式人工审批
  → Temporary-copy Preflight / 临时副本预检
  → Content-addressed Receipt / 内容寻址回执
  → Verified Audit Report / 已验证审计报告
```

## 证据契约 / Evidence Contract

每条证据包含：

Every evidence item contains:

- 仓库相对路径 / Repository-relative path
- 起止行号 / Start and end lines
- 长度受限的源码片段 / Bounded source snippet
- 检索原因和分数 / Retrieval reason and score
- 完整源文件 SHA-256 / SHA-256 of the full source file

每个计划步骤必须引用 Evidence ID，形成以下可追溯链路：

Every plan step must cite Evidence IDs, preserving this traceable chain:

```text
Issue / 问题
→ Query / 查询
→ Code Evidence / 代码证据
→ Diagnosis / 诊断
→ Plan / 计划
→ Validation Criteria / 验证标准
```

## 目标仓库只读不变量 / Target-repository Read-only Invariant

工作流在分析前后计算规范化仓库快照。如果哈希不一致，运行立即失败；运行产物必须写在目标仓库之外。

The workflow computes a canonical repository snapshot before and after analysis. If the hashes differ, the run fails; artifacts must be written outside the target repository.

当前补丁审查工作流遵守以下原则：

The current patch-review workflow follows these rules:

- 补丁是数据，不是命令。
  A patch is data, not a command.
- Unified Diff 必须经过路径校验。
  Unified Diffs must pass path validation.
- 提案绑定基础仓库快照和规范化补丁内容。
  A proposal binds the base repository snapshot and normalized patch content.
- 审批绑定运行标识、提案、基础快照、声明的审批人和审批时间。
  An approval binds the Run ID, proposal, base snapshot, declared approver, and approval time.
- 补丁只在标准库临时副本中进行文本级预检，不执行目标代码。
  The patch receives text-level preflight only in a standard-library temporary copy; target code is not executed.
- 真实目标仓库在提案和预检前后必须保持同一快照。
  The real target repository must retain the same snapshot before and after proposal inspection and preflight.
- 回执写入目标仓库外的内容寻址审计存储，并在读取报告前重新验证。
  Receipts are written to a content-addressed audit store outside the target repository and revalidated before report rendering.

## LLM 工具循环 / LLM Tool Loop

模型只能返回以下受限动作结构：

The model may return only this constrained action structure:

```json
{
  "action": "list_files | search_text | find_symbol | read_file | submit_analysis",
  "arguments": {},
  "rationale": "简短、可审计的原因 / short auditable reason"
}
```

模型不会获得通用 Shell 工具。当前版本不执行目标仓库测试；未来如启用测试执行，必须将其作为独立高权限能力放入无凭据、限资源的 Shadow Container。

The model never receives a general-purpose shell tool. The current version does not execute target-repository tests; if test execution is enabled later, it must be a separate privileged capability inside a credential-free, resource-bounded Shadow Container.
