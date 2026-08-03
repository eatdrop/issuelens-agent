# IssueLens 架构 / Architecture

## 设计目标 / Design Goal

IssueLens 的目标不是让模型拥有更多权限，而是让非确定性推理运行在确定、可验证、可拒绝的工程边界内。

IssueLens does not aim to give a model more authority. It places nondeterministic reasoning inside deterministic, verifiable, and rejectable engineering boundaries.

系统将分析、候选补丁、隔离验证、人工审阅和外部发布分成不同权限等级。当前实现停在“生成可审阅产物”，不会写真实仓库或发布 GitHub PR。

Analysis, candidate patches, isolated validation, human review, and external publication are separate authority levels. The current implementation stops at reviewable artifacts; it neither writes the real repository nor publishes a GitHub PR.

## 组件视图 / Component View

```text
Untrusted Issue / 不可信 Issue
        │
        ▼
Issue Parser ──→ Read-only Repository Gateway ──→ AST + Text Retrieval
问题解析器          只读仓库网关                    AST 与文本检索
        │                         │
        ▼                         ▼
Constrained Policy Loop ──→ Evidence Store ──→ Analysis Report + Trace
受限策略循环             证据存储             分析报告与轨迹
        │
        ├── Integrity Checkpoint / 完整性检查点
        └── Tool, Evidence, Time Budgets / 工具、证据与时间预算

External Unified Diff / 外部候选补丁
        │
        ▼
Diff Policy + Snapshot-bound Proposal / 补丁策略与快照绑定提案
        │
        ▼
Explicit Hash Approval / 显式哈希审批
        │
        ▼
Temporary Patched Copy / 一次性补丁副本
        │
        ▼
Docker Shadow Validator / Docker 隔离验证器
  baseline fail → patched pass → regression pass → hidden pass
  补丁前失败 → 补丁后通过 → 回归通过 → 隐藏测试通过
        │
        ▼
Content-addressed Receipt / 内容寻址回执
        │
        ├── Local Review UI / 本地审阅界面
        └── Draft PR Markdown / PR 草稿 Markdown
```

## 信任边界 / Trust Boundaries

| 区域 / Zone | 信任级别 / Trust | 权限 / Authority |
|---|---|---|
| Issue、仓库文本、Diff / Issue, repository text, Diff | 不可信输入 / Untrusted input | 仅作为有界数据解析 / Parsed only as bounded data |
| LLM Policy / LLM 策略 | 不可信建议者 / Untrusted proposer | 只能请求五个结构化只读动作 / May request five structured read-only actions |
| Repository Gateway / 仓库网关 | 受信安全内核 / Trusted safety kernel | 路径、大小、编码、符号链接与快照检查 / Path, size, encoding, symlink, and snapshot checks |
| Human Approval / 人工审批 | 声明式控制 / Declarative control | 确认准确 Proposal Hash；身份未认证 / Confirms exact Proposal Hash; identity is unauthenticated |
| Shadow Container / 隔离容器 | 受限执行区 / Constrained execution zone | 执行白名单 Python unittest 命令，无网络与凭据 / Runs allowlisted Python unittest commands without network or credentials |
| Real Repository / 真实仓库 | 受保护对象 / Protected object | 分析与验证全程只读 / Read-only throughout analysis and validation |
| GitHub Publication / GitHub 发布 | 未授予 / Not granted | 当前实现不调用 / Not called by the current implementation |

## Issue 分析状态机 / Issue-analysis State Machine

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

每次状态迁移写入 `trace.jsonl`。工具调用、证据数量或总耗时超过预算时，运行失败关闭。

Every state transition is written to `trace.jsonl`. The run fails closed when tool-call, evidence, or elapsed-time budgets are exceeded.

## Checkpoint 与恢复 / Checkpoint and Resume

Agent 在开始、每个已完成步骤之后及完成时保存版本化 `checkpoint.json`。Checkpoint 绑定 Run ID、Issue 哈希、基础仓库快照、下一步、证据、观察结果、累计耗时与完整性哈希。

The Agent saves a versioned `checkpoint.json` at start, after each completed step, and at completion. A checkpoint binds the Run ID, Issue hash, base repository snapshot, next step, evidence, observations, accumulated elapsed time, and integrity hash.

恢复时必须满足：Run ID 相同、Issue 内容未变、仓库快照未变、Checkpoint 未被篡改且运行尚未完成。预算按累计值继续计算，已完成动作不会重放。

Resume requires the same Run ID, unchanged Issue content, unchanged repository snapshot, an untampered checkpoint, and an incomplete run. Budgets continue from accumulated values, and completed actions are not replayed.

LLM 适配器只对瞬时网络错误、HTTP 429/5xx 和无效结构化输出执行有上限的退避重试；确定性 4xx 不会重试。

The LLM adapter applies bounded backoff retries only to transient network failures, HTTP 429/5xx responses, and invalid structured output; deterministic 4xx failures are not retried.

## 证据契约 / Evidence Contract

每条证据包含仓库相对路径、起止行号、长度受限片段、检索原因、评分和完整源文件 SHA-256。每个可执行计划步骤必须引用 Evidence ID。

Each evidence item contains a repository-relative path, start/end lines, a bounded snippet, retrieval reason, score, and SHA-256 of the full source file. Every actionable plan step must cite an Evidence ID.

```text
Issue → Query → Code Evidence → Diagnosis → Plan → Acceptance Criteria
问题 → 查询 → 代码证据 → 诊断 → 计划 → 验收标准
```

如果受限工具没有返回足够证据，状态必须是 `insufficient_evidence`，不能生成看似确定的修改计划。

If constrained tools do not return sufficient evidence, the status must be `insufficient_evidence`; the system must not fabricate a confident change plan.

## 补丁与验证协议 / Patch and Validation Protocol

1. 解析大小受限的 UTF-8 Unified Diff，拒绝绝对路径、`..`、反斜线、Git 元数据、重命名、重复文件及白名单外路径。
   Parse a bounded UTF-8 Unified Diff and reject absolute paths, `..`, backslashes, Git metadata, renames, duplicate files, and paths outside the allowlist.
2. 规范化 Diff，并与当前仓库快照计算 Proposal Hash。
   Normalize the Diff and combine it with the current repository snapshot to calculate a Proposal Hash.
3. 要求操作者提供完全相同的 64 位哈希；审批记录绑定 Run ID、提案、快照、声明的审批人和时间。
   Require the operator to provide the exact 64-character hash; the approval record binds the Run ID, proposal, snapshot, declared approver, and time.
4. 在一次性临时副本中应用补丁，真实仓库只读。
   Apply the patch in a disposable temporary copy while the real repository remains read-only.
5. 默认 Docker Runner 依次运行 Baseline Reproduction、Patched Reproduction、Full Regression 和 Hidden Tests。
   The default Docker runner executes Baseline Reproduction, Patched Reproduction, Full Regression, and Hidden Tests in order.
6. 只有补丁前复现确实失败、补丁后所有阶段确实执行且通过，才判定成功。
   Success requires the reproduction to genuinely fail before the patch and every post-patch stage to genuinely execute and pass.
7. 保存不可覆盖、内容寻址、加载时重验完整性的 JSON 回执与双语 Markdown 报告。
   Store non-overwriting, content-addressed JSON receipts plus bilingual Markdown, revalidating integrity on load.

Baseline ImportError、零测试运行、超时、输出截断、容器失败、隐藏测试失败或真实仓库漂移都不能计为成功。

A baseline ImportError, zero executed tests, timeout, truncated output, container failure, hidden-test failure, or real-repository drift can never count as success.

## 本地审阅层 / Local Review Layer

Dashboard 只监听 `127.0.0.1`，每次启动生成随机访问令牌，检查 Host，并设置 CSP、`nosniff`、Referrer Policy 和 `no-store`。报告内容在进入 HTML 前转义。

The dashboard binds only to `127.0.0.1`, creates a random access token on every launch, validates the Host header, and sets CSP, `nosniff`, Referrer Policy, and `no-store`. Report content is escaped before entering HTML.

网页决策是追加写入、哈希保护的“计划审阅记录”，不会授予补丁执行或发布权限。Draft PR 命令仅生成 Markdown 到仓库外部的新文件。

Web decisions are append-only, hash-protected “plan review records”; they grant no patch execution or publication authority. The Draft PR command only writes Markdown to a new file outside the repository.

## 不变量 / Invariants

- 真实仓库分析前后、验证前后快照一致。
  The real-repository snapshot is identical before/after analysis and before/after validation.
- 模型没有通用 Shell 或直接文件系统权限。
  The model has no general-purpose shell or direct filesystem authority.
- Docker 验证不携带宿主凭据、网络或写入挂载。
  Docker validation receives no host credentials, network, or writable host mount.
- 审计与导出产物位于目标仓库外部且不会静默覆盖。
  Audit and export artifacts remain outside the target repository and are never silently overwritten.
- 外部发布默认且实际上关闭。
  External publication is disabled by default and in implementation.
