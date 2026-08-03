# 12 周交付路线图 / 12-Week Delivery Roadmap

## 第 1–2 周：V0.1 基础 / Weeks 1–2: V0.1 Foundation

- 只读仓库边界和快照哈希。
  Read-only repository boundary and snapshot hashing.
- Issue 解析、AST/文本检索和 Evidence ID。
  Issue parsing, AST/text retrieval, and Evidence IDs.
- 显式状态机、工具循环和 Trace。
  Explicit state machine, tool loop, and tracing.
- Deterministic baseline、冒烟评测和安全测试。
  Deterministic baseline, smoke evaluation, and safety tests.

退出标准 / Exit criteria:

- 所有本地测试通过 / All local tests pass
- 目标仓库写入次数为 0 / Target repository write count is zero
- 简单案例能定位预期实现文件 / Easy fixtures localize expected implementation files
- 信息不足的 Issue 触发安全拒绝 / Underspecified Issues trigger safe abstention

## 第 3–4 周：候选补丁协议 / Weeks 3–4: Patch Proposal Protocol

- 与模型供应商解耦的结构化 LLM Policy。
  Provider-independent structured LLM policy.
- Unified Diff Parser 和修改文件白名单。
  Unified Diff parser and touched-file allowlist.
- 补丁绑定 Base Snapshot Hash。
  Patch binding to the base snapshot hash.
- 审批对象绑定 Run ID、Patch Hash 和 Snapshot。
  Approval binding to run ID, patch hash, and snapshot.

退出标准 / Exit criteria:

- 拒绝格式错误或路径逃逸补丁 / Reject malformed or escaping patches
- 每个 Patch Hunk 对应证据和计划步骤 / Every patch hunk traces to evidence and a plan step
- 仓库变化后旧审批自动失效 / Repository changes invalidate prior approval

## 第 5–6 周：隔离复现 / Weeks 5–6: Isolated Reproduction

- 临时、非 root Docker Shadow Workspace。
  Ephemeral non-root Docker shadow workspace.
- 安装阶段结束后默认断网。
  Network disabled by default after dependency setup.
- 执行 Baseline Failing Test、候选补丁、目标测试和全量回归。
  Run the baseline failing test, candidate patch, targeted test, and full regression suite.
- 设置时间、CPU、内存、进程和输出限制。
  Enforce time, CPU, memory, process, and output limits.

退出标准 / Exit criteria:

- 测试不在宿主机执行 / Tests never execute on the host
- 已知 Bug 在补丁前失败、补丁后通过 / Known bug fails before and passes after the patch
- 既有通过测试继续通过 / Existing passing tests remain passing

## 第 7–8 周：Agent 评测 / Weeks 7–8: Agent Evaluation

- 从两个小型 Python 仓库收集 10–15 个近期 Issue。
  Collect 10–15 recent Issues from two small Python repositories.
- 固定 Commit，采用时间切分任务和独立 Grader。
  Pin commits and use time-split tasks with independent graders.
- 建立 Trace Replay 和失败分类。
  Build trace replay and a failure taxonomy.
- 对比纯文本检索与 AST + 文本检索。
  Compare text-only retrieval with AST + text retrieval.

退出标准 / Exit criteria:

- 公布安装、复现、定位和 Resolved@1 指标 / Publish setup, reproduction, localization, and Resolved@1 metrics
- 同时公布失败与成本 / Publish failures and cost alongside successes
- 不使用手工挑选的标题指标 / Avoid cherry-picked headline metrics

## 第 9–10 周：产品层 / Weeks 9–10: Product Layer

- 为 Issue、计划、证据、Diff 和审批提供最小 Web UI。
  Build a minimal Web UI for Issues, plans, evidence, diffs, and approval.
- 加入 Checkpoint、恢复和单次运行预算。
  Add checkpoints, resume, and per-run budgets.
- 支持人工编辑、拒绝和批准。
  Support human edit, reject, and approve workflows.
- 导出 Draft PR 文本但不自动发布。
  Export Draft PR content without publishing it automatically.

退出标准 / Exit criteria:

- 用户能理解每个修改及其证据 / Users can understand every proposed change and its evidence
- 中断后恢复不会重复副作用 / Resumed runs do not repeat side effects
- 外部发布默认关闭 / External publication remains disabled by default

## 第 11–12 周：真实开源信号 / Weeks 11–12: Real Open-Source Signal

- 扩展到 30–50 个 Held-Out Issue。
  Expand to 30–50 held-out Issues.
- 选择少量维护者认可的 `good first issue`。
  Select a small number of maintainer-approved `good first issue` tasks.
- 遵守每个仓库的贡献与 AI 披露规则。
  Follow each repository's contribution and AI-disclosure policy.
- 仅提交经过人工审核的补丁，并记录维护者反馈。
  Submit only human-reviewed patches and record maintainer feedback.

退出标准 / Exit criteria:

- 可复现实验报告 / Reproducible evaluation report
- 双语公开文档、架构图和演示视频 / Bilingual public docs, architecture diagram, and demo video
- 至少一次有实质内容的维护者互动 / At least one substantive maintainer interaction
- 简历只使用实测指标 / Resume uses measured metrics only
