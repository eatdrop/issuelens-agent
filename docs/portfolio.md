# 作品集展示 / Portfolio Presentation

## 推荐演示入口 / Recommended Demo Entry Points

先展示 Issue 分析、代码证据、状态 Trace 和只读仓库保证：

Start with Issue analysis, code evidence, the state trace, and the read-only repository guarantee:

```bash
make demo
```

再展示候选补丁、显式人工审批、临时副本预检和内容寻址审计回执：

Then demonstrate a candidate patch, explicit human approval, temporary-copy preflight, and a content-addressed audit receipt:

```bash
make patch-demo
```

`make patch-demo` 使用提前准备的固定候选 Diff，用于展示补丁审查协议；它不代表 Agent 已经从 Issue 自动生成该补丁。

`make patch-demo` uses a prepared, fixed candidate Diff to demonstrate the patch-review protocol; it does not mean that the Agent generated the patch automatically from the Issue.

完整现场话术见：

See the complete live-demo script:

- [面试演示讲稿 / Interview Demo Script](interview-demo.md)

## 三分钟演示 / Three-minute Demo

1. 运行 `make demo`，展示 Agent 如何解析 Issue，并通过 AST 与文本检索定位候选代码。
   Run `make demo` to show how the Agent parses an Issue and locates candidate code with AST and text retrieval.
2. 打开包含文件、行号、Evidence ID 和源码哈希的双语报告。
   Open the bilingual report containing file paths, line numbers, Evidence IDs, and source hashes.
3. 展示 `trace.jsonl` 中的显式状态迁移，以及分析前后的相同仓库快照。
   Show the explicit state transitions in `trace.jsonl` and the identical repository snapshots before and after analysis.
4. 运行 `make patch-demo`，指出候选 Diff、`changed_paths`、基础快照和 Proposal Hash。
   Run `make patch-demo` and point out the candidate Diff, `changed_paths`, base snapshot, and Proposal Hash.
5. 手动粘贴完整 Proposal Hash 并输入审批人名称，展示危险动作前的人工安全门。
   Manually paste the complete Proposal Hash and enter the approver name to demonstrate the human safety gate before a sensitive action.
6. 展示 `repository_unchanged: true`、预览快照、Receipt Hash 和中英双语审计报告。
   Show `repository_unchanged: true`, the preview snapshot, Receipt Hash, and bilingual audit report.
7. 如时间允许，重新运行并输入错误 Hash，展示失败关闭且不创建新回执。
   If time permits, rerun the demo with an incorrect hash to show fail-closed behavior without creating a new receipt.
8. 用一句话说明边界：当前只进行文本级临时副本预检，不执行目标仓库测试、不认证审批人身份，也不自动 Push、创建 PR 或合并。
   State the boundary in one sentence: the current version performs text-level preflight in a temporary copy; it does not execute target-repository tests, authenticate the approver, or automatically push, open a PR, or merge.

## 当前可用简历表述 / Current Resume-ready Statement

以下表述只使用当前仓库中可以复现的事实：

The following statement uses only facts reproducible in the current repository:

> 独立构建 IssueLens——面向 Python 仓库的本地优先 Coding Agent，结合 AST 符号索引与文本检索，将 Issue 诊断和修改计划绑定到文件、行号、代码片段及内容哈希；设计受限工具协议、仓库快照、显式状态 Trace，以及绑定运行/提案/快照的人工审批流程。实现 Unified Diff 路径策略、临时副本预检和内容寻址审计回执；建立 87 项自动化测试覆盖路径逃逸、符号链接、审批失效、补丁冲突与回执篡改，在当前测试中目标仓库越权写入 0 次。
>
> Independently built IssueLens, a local-first Coding Agent for Python repositories. Combined AST symbol indexing and text retrieval to ground Issue diagnoses and change plans in file, line, snippet, and content-hash evidence; designed a constrained tool protocol, repository snapshots, explicit state traces, and human approval bound to the run, proposal, and snapshot. Implemented Unified Diff path policy, temporary-copy preflight, and content-addressed audit receipts; built 87 automated tests covering path traversal, symlinks, approval invalidation, patch conflicts, and receipt tampering, with zero unauthorized target-repository writes in the current test suite.

使用时可以根据岗位压缩：

Adapt the emphasis to the role:

- **研发或 Agent 工程岗 / Engineering or Agent Engineering**：保留 AST、工具协议、状态机、Hash 绑定和自动化测试。
  Retain AST, tool protocols, the state machine, hash binding, and automated tests.
- **Agent 产品或产品岗 / Agent Product or Product**：强调证据可见性、人工审批、失败关闭和审计回执。
  Emphasize evidence visibility, human approval, fail-closed behavior, and audit receipts.

## 未来量化成果模板 / Future Quantified-results Template

只有在完成真实公开 Issue 评测或开源贡献后，才能使用以下模板。所有占位符必须替换为可验证结果；没有数据时不得保留或推测。

Use the following template only after completing real public-Issue evaluation or open-source contributions. Replace every placeholder with verifiable results; never retain or estimate a value when no data exists.

> 独立构建 IssueLens——面向 Python 开源 Issue 的本地优先 Coding Agent，结合 AST 符号索引和文本检索，将诊断与修改计划绑定到具体代码证据；设计路径隔离、仓库快照和可审计状态 Trace。在 **N** 个时间切分公开 Issue 上建立评测集，Gold File Recall@3 达 **X%**、Resolved@1 达 **Y%**，目标仓库越权写入 0 次；提交 **M** 个经人工审核的补丁，其中 **K** 个被维护者合并。
>
> Independently built IssueLens, a local-first Coding Agent for public Python Issues. Combined AST symbol indexing and text retrieval to ground diagnoses and change plans in code evidence, with path isolation, repository snapshots, and auditable state traces. Built a time-split evaluation set across **N** public Issues, reaching **X%** Gold File Recall@3 and **Y%** Resolved@1 with zero unauthorized target-repository writes; submitted **M** human-reviewed patches, of which **K** were merged by maintainers.

## 可证明与尚未证明 / Demonstrated and Not Yet Demonstrated

当前仓库可以证明：

The current repository demonstrates:

- 固定夹具上的可复现 Issue 分析和安全拒绝。
  Reproducible Issue analysis and safe abstention on fixed fixtures.
- 受限工具调用、证据引用、状态 Trace 和仓库快照验证。
  Constrained tool calls, evidence references, state traces, and repository snapshot verification.
- Unified Diff 策略、显式 Hash 审批、临时副本预检和可验证回执。
  Unified Diff policy, explicit hash approval, temporary-copy preflight, and verifiable receipts.
- 87 项自动化测试及当前测试中的目标仓库越权写入 0 次。
  87 automated tests and zero unauthorized target-repository writes in the current test suite.

当前仓库尚未证明：

The current repository does not yet demonstrate:

- 在大规模真实公开 Issue 上的解决率。
  Resolution rate on a large set of real public Issues.
- 在隔离容器中执行不可信目标代码和测试。
  Execution of untrusted target code and tests inside an isolated container.
- 经过认证的审批人身份或数字签名。
  Authenticated approver identity or digital signatures.
- 自动生成补丁后提交、Push、创建 PR 或合并。
  Submission, push, PR creation, or merge after automatic patch generation.
- 维护者接受或合并的真实开源贡献数量。
  A measured number of real open-source contributions accepted or merged by maintainers.

## 最终证据包 / Final Evidence Package

- 可运行仓库、`make demo`、`make patch-demo` 和 CI。
  Runnable repository, `make demo`, `make patch-demo`, and CI.
- 架构、安全模型和威胁边界。
  Architecture, security model, and threat boundaries.
- 可复现评测任务、测试结果和失败分类。
  Reproducible evaluation tasks, test results, and failure categories.
- 脱敏后的代表性 Trace 与内容寻址审计回执。
  Representative redacted traces and content-addressed audit receipts.
- 中英双语 README、面试演示讲稿和短演示视频。
  Bilingual README, interview-demo script, and short demo video.
- 成功案例与失败案例，而不是只展示一次成功 Demo。
  Successful and failed cases rather than a single successful demo.
- 少量高质量开源贡献链接及维护者反馈。
  Links to a small number of high-quality open-source contributions and maintainer feedback.
