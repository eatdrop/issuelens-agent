# IssueLens 路线图 / IssueLens Roadmap

该文档区分“v0.2 已实现的作品集 MVP”和“需要外部数据、可信身份或更强基础设施的后续能力”，避免把计划写成事实。

This document separates the implemented v0.2 portfolio MVP from future work requiring external data, trusted identity, or stronger infrastructure, so plans are not presented as facts.

## v0.2 MVP：已完成 / v0.2 MVP: Completed

### 只读分析与 Agent Loop / Read-only Analysis and Agent Loop

- [x] 仓库路径边界、符号链接防护、文本大小限制和前后快照。
  Repository path boundaries, symlink protection, text-size limits, and before/after snapshots.
- [x] Issue 解析、AST 符号索引、文本检索、Evidence ID 和内容哈希。
  Issue parsing, AST symbol indexing, text retrieval, Evidence IDs, and content hashes.
- [x] 显式状态机、结构化只读工具协议、离线 Policy 与兼容 Chat Completions JSON 的 LLM Policy。
  Explicit state machine, structured read-only tool protocol, offline policy, and a Chat-Completions-JSON-compatible LLM policy.
- [x] `insufficient_evidence` 安全拒绝、报告、完整 Trace 和仓库未变验证。
  `insufficient_evidence` safe abstention, reports, complete trace, and repository-unchanged verification.

### 补丁协议与审计 / Patch Protocol and Audit

- [x] Unified Diff Parser、路径策略、文件白名单及大小限制。
  Unified Diff parser, path policy, touched-file allowlist, and size limits.
- [x] Diff + Base Snapshot 的 Proposal Hash，以及绑定 Run/提案/快照/审批人/时间的显式审批。
  Proposal Hash binding the Diff and base snapshot, plus explicit approval binding the run, proposal, snapshot, approver, and time.
- [x] 一次性临时副本预检、文件级前后哈希与内容寻址审计回执。
  Disposable-copy preflight, per-file before/after hashes, and content-addressed audit receipts.

### Shadow Workspace / Shadow Workspace

- [x] 固定镜像、非 root、断网、只读挂载、无 Capabilities 与限资源 Docker Runner。
  Digest-pinned, non-root, network-disabled, read-only, capability-free, resource-bounded Docker runner.
- [x] Baseline failing test → patched reproduction → full regression → hidden test 闭环。
  Baseline failing test → patched reproduction → full regression → hidden test loop.
- [x] 零测试、导入错误、超时、输出限制和基础设施失败的失败关闭判定。
  Fail-closed handling of zero tests, import errors, timeouts, output limits, and infrastructure failures.
- [x] 双语验证报告与完整性保护的验证回执。
  Bilingual validation reports and integrity-protected validation receipts.

### 可靠性与产品层 / Reliability and Product Layer

- [x] 版本化 Checkpoint、输入漂移检测与不重放已完成动作的恢复。
  Versioned checkpoints, input-drift detection, and resume without replaying completed actions.
- [x] 步骤、工具、证据、时间预算和有界 LLM 重试。
  Step, tool, evidence, and time budgets plus bounded LLM retries.
- [x] 回环地址 + 随机 Token 的本地 Web 审阅界面，以及追加式批准/拒绝记录。
  Loopback-and-random-token local review UI with append-only approve/reject records.
- [x] 中英双语 Draft PR Markdown 导出；默认不发布。
  Bilingual Draft PR Markdown export with publication disabled.

### 评测与交付 / Evaluation and Delivery

- [x] 8 个合成案例：6 个定位、2 个安全拒绝，带有效分母和失败分类。
  Eight synthetic cases: six localization and two safe-abstention, with eligible denominators and failure taxonomy.
- [x] Python 3.11/3.12 CI、评测 Artifact 和默认 Docker Shadow Validation Job。
  Python 3.11/3.12 CI, evaluation artifacts, and a default-Docker Shadow Validation job.
- [x] 中英双语 README、架构、安全、评测、作品集和面试演示材料。
  Bilingual README, architecture, security, evaluation, portfolio, and interview-demo materials.

## v0.3：真实评测与通用环境 / v0.3: Real Evaluation and General Environments

- [ ] 从 3–5 个许可兼容的 Python 项目构建 30–50 个时间切分公开 Issue，固定 Base Commit。
  Build 30–50 time-split public Issues from 3–5 license-compatible Python projects with pinned base commits.
- [ ] 独立维护 Reproduction 与 Hidden Grader，不让 Agent 自己的测试成为唯一评分器。
  Independently maintain reproduction and hidden graders so Agent-generated tests are not the sole evaluator.
- [ ] 增加受审计依赖构建阶段、锁文件/哈希验证和 pytest/tox/nox 适配器。
  Add an audited dependency-build phase, lockfile/hash verification, and pytest/tox/nox adapters.
- [ ] 实现 Trace Replay 与按安装、复现、定位、生成、应用、测试和安全分层的失败分类。
  Implement trace replay and a failure taxonomy spanning setup, reproduction, localization, generation, application, tests, and safety.
- [ ] 报告 Resolved@1、Pass-to-pass、成本、Token、耗时、人工介入和失败，不只展示成功样例。
  Report Resolved@1, pass-to-pass, cost, tokens, latency, human intervention, and failures—not successes alone.

## v0.4：可信协作 / v0.4: Trusted Collaboration

- [ ] 接入可信身份、细粒度仓库授权、签名审批和密钥轮换。
  Integrate trusted identity, fine-grained repository authorization, signed approval, and key rotation.
- [ ] 支持证据/计划编辑与多审阅人策略，不把 UI 按钮等同于权限授予。
  Support evidence/plan editing and multi-reviewer policy without treating UI buttons as authority grants.
- [ ] 添加 GitHub Draft PR 发布能力，但默认关闭，并在发布前进行独立确认。
  Add GitHub Draft PR publication, disabled by default and protected by a separate pre-publication confirmation.
- [ ] 遵守目标仓库贡献规范、AI 披露和维护者意愿，记录接受/拒绝反馈。
  Follow target-repository contribution rules, AI disclosure, and maintainer preferences while recording acceptance/rejection feedback.

## v1.0 前门槛 / Gates Before v1.0

- [ ] 使用比普通 Docker 更强的多租户隔离，并完成独立安全评审。
  Use stronger multi-tenant isolation than ordinary Docker and complete an independent security review.
- [ ] 在公开、可复现、时间切分的数据集上达到预先定义的质量与安全门槛。
  Meet predeclared quality and safety thresholds on a public, reproducible, time-split dataset.
- [ ] 完成秘密扫描、脱敏、数据保留、审计访问和事故响应流程。
  Complete secret scanning, redaction, data retention, audit access, and incident-response processes.
- [ ] 证明默认关闭的外部副作用、幂等恢复和并发隔离。
  Demonstrate default-disabled external side effects, idempotent recovery, and concurrent isolation.

## 简历使用原则 / Resume-use Rule

只有带 `[x]` 且可由代码、测试、CI 或公开产物复现的能力可以作为当前成果。带 `[ ]` 的项目只能表述为下一步，不得使用预估数据。

Only `[x]` capabilities reproducible through code, tests, CI, or public artifacts may be presented as current achievements. `[ ]` items are future work and must never use estimated results.
