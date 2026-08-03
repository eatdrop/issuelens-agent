# 作品集展示 / Portfolio Presentation

## 一句话定位 / One-line Positioning

IssueLens 是一个面向 Python 仓库的本地优先 Coding Agent，把不确定的模型推理放进“只读证据、精确审批、隔离测试、可验证回执”的确定性工程边界。

IssueLens is a local-first Coding Agent for Python repositories that places uncertain model reasoning inside deterministic boundaries of read-only evidence, exact approval, isolated tests, and verifiable receipts.

## 推荐演示顺序 / Recommended Demo Order

### 1. 分析与证据 / Analysis and Evidence

```bash
make demo
```

展示 AST + 文本检索、Evidence ID、文件/行号/片段/哈希、显式状态 Trace、Checkpoint 和分析前后相同仓库快照。

Show AST + text retrieval, Evidence IDs, path/line/snippet/hash grounding, explicit state trace, checkpoint, and identical repository snapshots before and after analysis.

### 2. 补丁绑定与人工门 / Patch Binding and Human Gate

```bash
make patch-demo
```

展示 Unified Diff 路径策略、Base Snapshot、Proposal Hash、人工粘贴完整 Hash、临时副本预检和内容寻址回执。

Show Unified Diff path policy, base snapshot, Proposal Hash, manual full-hash confirmation, temporary-copy preflight, and content-addressed receipt.

### 3. 隔离验证闭环 / Isolated Validation Loop

```bash
docker pull python:3.12.10-slim@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db
make shadow-demo
```

展示补丁前复现失败、补丁后复现通过、全量回归与外置隐藏测试通过，以及 Docker 的断网、非 root、只读挂载和资源限制。

Show fail-before/pass-after reproduction, full regression and external hidden tests, plus Docker's network-disabled, non-root, read-only, resource-bounded configuration.

### 4. 产品审阅层 / Product Review Layer

```bash
make dashboard
```

展示证据与风险的本地可视化、计划批准/拒绝记录，并说明 UI 决策不是补丁权限。最后演示 `draft-pr` 只导出双语 Markdown、不发布 GitHub PR。

Show local evidence/risk visualization and approve/reject plan records, explaining that UI decisions grant no patch authority. Finish by showing that `draft-pr` exports bilingual Markdown without publishing a GitHub PR.

## 可复现成果 / Reproducible Results

- 130 项自动化测试用例，覆盖路径逃逸、符号链接、审批失效、补丁冲突、回执/Checkpoint 篡改、预算、重试、Shadow 判定、Web 转义和外部输出边界。
  130 automated test cases cover path traversal, symlinks, approval invalidation, patch conflicts, receipt/checkpoint tampering, budgets, retries, Shadow verdicts, web escaping, and external-output boundaries.
- 8 个合成案例 deterministic baseline：6/6 定位任务 Hit@1、Recall@3 和 MRR 为 1.0；2/2 信息不足任务正确拒绝；8/8 保持目标仓库不变。
  Eight-case synthetic deterministic baseline: all 6/6 localization cases score 1.0 Hit@1, Recall@3, and MRR; both 2/2 underspecified cases abstain correctly; all 8/8 preserve the target repository.
- Python 3.11/3.12 CI、评测 Artifact 与独立 Docker Shadow Validation Job。
  Python 3.11/3.12 CI, evaluation artifacts, and an independent Docker Shadow Validation job.

所有评测数字必须带“合成案例”和“deterministic baseline”限定。Shadow Demo 使用预制补丁，不能称为 Agent-generated Resolved@1。

Every evaluation number must retain the “synthetic cases” and “deterministic baseline” qualifiers. The Shadow Demo uses a prepared patch and cannot be called Agent-generated Resolved@1.

## 简历表述 / Resume-ready Statement

### 中文 / Chinese

> 独立设计并实现 IssueLens——面向 Python 仓库的本地优先 Coding Agent：通过 AST 符号索引与文本检索，将 Issue 诊断和修改计划绑定到文件、行号、代码片段与内容哈希；构建受限只读工具协议、显式状态机、完整 Trace、完整性 Checkpoint、跨阶段预算及有界重试。设计快照绑定的 Unified Diff 审批协议，并在固定镜像、非 root、断网、只读、限资源 Docker Shadow Workspace 中实现 failing-test → patch → regression → hidden-test 验证闭环；提供内容寻址回执、本地审阅 UI 与仅导出的双语 Draft PR。建立 130 项测试和 8 案例合成 deterministic baseline，其中 6/6 定位案例 Hit@1/Recall@3/MRR 均为 1.0，2/2 信息不足案例正确拒绝，8/8 分析保持目标仓库不变。

### English / 英文

> Independently designed and implemented IssueLens, a local-first Coding Agent for Python repositories. Grounded Issue diagnoses and change plans in path, line, snippet, and content-hash evidence using AST symbol indexing and text retrieval; built a constrained read-only tool protocol, explicit state machine, complete traces, integrity-protected checkpoints, cross-stage budgets, and bounded retries. Designed a snapshot-bound Unified Diff approval protocol and implemented a failing-test → patch → regression → hidden-test loop in a digest-pinned, non-root, network-disabled, read-only, resource-bounded Docker Shadow Workspace; added content-addressed receipts, a local review UI, and export-only bilingual Draft PR content. Built 130 test cases and an eight-case synthetic deterministic baseline where all 6/6 localization cases achieved 1.0 Hit@1/Recall@3/MRR, both 2/2 underspecified cases abstained correctly, and all 8/8 analyses preserved the target repository.

## 按岗位调整重点 / Role-specific Emphasis

### Agent 或研发工程岗 / Agent or Engineering Role

- 强调 AST、受限工具协议、状态机、Checkpoint 恢复、预算、重试与确定性测试。
  Emphasize AST, constrained tool protocols, the state machine, checkpoint resume, budgets, retries, and deterministic tests.
- 强调 Diff Parser、Hash 绑定、Docker 隔离参数、失败关闭与隐藏测试独立性。
  Emphasize Diff parsing, hash binding, Docker isolation flags, fail-closed behavior, and hidden-test independence.
- 能准确说明临时副本、容器、真实仓库和发布权限之间的信任边界。
  Explain the trust boundaries between the temporary copy, container, real repository, and publication authority precisely.

### Agent 产品或产品经理岗 / Agent Product or Product Role

- 强调用户为什么需要看见证据、风险、修改范围和准确审批对象。
  Emphasize why users need visibility into evidence, risk, change scope, and the exact approval object.
- 强调“分析计划批准”“补丁执行批准”“外部发布批准”是三个不同控制点。
  Emphasize that analysis-plan approval, patch-execution approval, and external-publication approval are three distinct controls.
- 强调成功指标同时包含正确完成、正确拒绝、可恢复性和副作用为零。
  Emphasize that success includes correct completion, correct abstention, recoverability, and zero unintended side effects.

## 不应夸大 / Claims to Avoid

| 不要这样说 / Avoid | 应该这样说 / Say Instead |
|---|---|
| “能自动修复任意 Issue。” / “It automatically fixes any Issue.” | “当前实现提供证据驱动分析和外部候选补丁的受控验证。” / “The current implementation provides evidence-grounded analysis and controlled validation of externally supplied patches.” |
| “真实 Issue 准确率 100%。” / “100% accuracy on real Issues.” | “8 个合成 deterministic 案例中所有当前断言通过。” / “All current assertions pass on eight synthetic deterministic cases.” |
| “已经实现 Resolved@1。” / “Resolved@1 is implemented.” | “预制补丁通过独立复现、回归和隐藏测试；Agent-generated Resolved@1 尚未评测。” / “A prepared patch passes independent reproduction, regression, and hidden tests; Agent-generated Resolved@1 is not yet evaluated.” |
| “Docker 可以安全执行任何恶意代码。” / “Docker safely executes any malicious code.” | “Docker 加固降低风险，但仍不是生产级多租户恶意代码沙箱。” / “Docker hardening reduces risk but is not a production multi-tenant hostile-code sandbox.” |
| “审批人身份已认证。” / “The approver is authenticated.” | “审批人是声明式审计元数据，可信身份仍在路线图中。” / “The approver is declared audit metadata; trusted identity remains future work.” |
| “系统会自动创建 PR。” / “The system automatically opens PRs.” | “系统只导出双语 Draft PR Markdown，不调用发布 API。” / “The system only exports bilingual Draft PR Markdown and calls no publication API.” |

## 最终证据包 / Evidence Package

- 公共仓库、版本 Release、受保护主分支和绿色 CI。
  Public repository, versioned release, protected main branch, and green CI.
- `make demo`、`make shadow-demo`、`make dashboard` 以及可验证回执。
  `make demo`, `make shadow-demo`, `make dashboard`, and verifiable receipts.
- 双语架构、安全、评测、演示与路线图文档。
  Bilingual architecture, security, evaluation, demo, and roadmap documentation.
- 自动化测试、逐案例评测、失败分类和明确限制。
  Automated tests, per-case evaluation, failure taxonomy, and explicit limitations.
