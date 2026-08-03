# 版本记录 / Changelog

所有重要变更记录于此。项目在 `1.0.0` 之前保持 Alpha，次版本可能调整实验性接口。

All notable changes are recorded here. The project remains alpha before `1.0.0`, and minor versions may change experimental interfaces.

## 0.2.0 — 2026-08-03

### 新增 / Added

- 固定镜像、断网、非 root、只读、限资源 Docker Shadow Workspace。
  Digest-pinned, network-disabled, non-root, read-only, resource-bounded Docker Shadow Workspace.
- Baseline failing test → patched reproduction → full regression → hidden-test 验证闭环。
  Baseline failing test → patched reproduction → full regression → hidden-test validation loop.
- 内容寻址的隔离验证 JSON 回执与中英双语 Markdown 报告。
  Content-addressed Shadow Validation JSON receipts and bilingual Markdown reports.
- 完整性保护的 Agent Checkpoint、恢复时 Issue/仓库漂移检测、跨阶段预算及有界 LLM 重试。
  Integrity-protected Agent checkpoints, Issue/repository drift detection on resume, cross-stage budgets, and bounded LLM retries.
- 回环地址、随机 Token 保护的本地审阅 Dashboard，以及追加式计划批准/拒绝记录。
  Loopback-and-random-token local review dashboard with append-only plan approval/rejection records.
- 仅导出的中英双语 Draft PR Markdown，不调用 GitHub 发布接口。
  Export-only bilingual Draft PR Markdown with no GitHub publication API call.
- 评测从 3 个扩展到 8 个合成案例，并加入失败分类。
  Evaluation expanded from three to eight synthetic cases with a failure taxonomy.
- CI 新增独立默认 Docker Shadow Validation Job 和验证 Artifact。
  CI adds an independent default-Docker Shadow Validation job and validation artifact.

### 安全改进 / Security Improvements

- 测试必须确实运行；零测试、Baseline 导入错误、超时和基础设施失败不计为成功复现。
  Tests must genuinely execute; zero tests, baseline import errors, timeouts, and infrastructure failures do not count as successful reproduction.
- 验证回执、Checkpoint 与 Web 决策均进行结构、大小和内容完整性检查。
  Validation receipts, checkpoints, and web decisions receive structural, size, and content-integrity checks.
- Dashboard 增加回环绑定、Token、Host 校验、安全响应头与 HTML 转义。
  The dashboard adds loopback binding, token and Host validation, security headers, and HTML escaping.

### 已知边界 / Known Boundaries

- 候选补丁仍由外部提供；当前版本不实现 Agent 自动生成补丁的 Resolved@1。
  Candidate patches remain externally supplied; this release does not implement Agent-generated Resolved@1.
- Docker Runner 只支持固定 Python `unittest` 环境，没有通用依赖构建阶段。
  The Docker runner supports only a fixed Python `unittest` environment and has no general dependency-build phase.
- 审批人未经过认证，外部 PR 发布保持关闭。
  Approver identity is unauthenticated, and external PR publication remains disabled.

## 0.1.0 — 2026-07-29

### 新增 / Added

- 本地优先、默认只读的 Issue 分析工作流。
  Local-first, read-only-by-default Issue-analysis workflow.
- AST + 文本检索、证据引用、显式状态机、报告与 Trace。
  AST + text retrieval, evidence citations, explicit state machine, reports, and traces.
- Unified Diff 策略、快照绑定 Proposal Hash、显式审批和临时副本预检。
  Unified Diff policy, snapshot-bound Proposal Hash, explicit approval, and temporary-copy preflight.
- 内容寻址审计回执和初始 3 案例 deterministic baseline。
  Content-addressed audit receipts and an initial three-case deterministic baseline.
