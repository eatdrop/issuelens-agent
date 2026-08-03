# IssueLens 面试演示讲稿 / IssueLens Interview Demo Script

## 使用目标 / Purpose

这份讲稿用于在约三分钟内展示 IssueLens 的 Agent 工程、安全设计和产品思考。演示重点不是“AI 自动写出正确代码”，而是“如何让 Coding Agent 的判断、审批和验证过程可追溯、可拒绝、可复现”。

This script presents IssueLens's Agent engineering, safety design, and product thinking in about three minutes. The focus is not “AI automatically writes correct code,” but “making a Coding Agent's reasoning, approval, and validation process traceable, rejectable, and reproducible.”

演示中的候选 Diff 是提前准备的固定夹具。`make patch-demo` 负责审查、审批绑定、临时副本预检和审计，不负责从 Issue 自动生成该补丁。

The candidate Diff in this demo is a prepared fixture. `make patch-demo` performs review, approval binding, temporary-copy preflight, and auditing; it does not generate the patch automatically from the Issue.

## 演示前准备 / Pre-demo Checklist

- 在项目根目录打开终端。
  Open a terminal at the project root.
- 确认可以运行 `python3` 和 `make`。
  Confirm that `python3` and `make` are available.
- 预先运行 `make test`，确认当前版本的 87 项测试全部通过。
  Run `make test` beforehand and confirm that all 87 tests pass on the current version.
- 放大终端字号，确保 Diff、Hash 和审计报告清晰可见。
  Increase the terminal font size so the Diff, hashes, and audit report are easy to read.
- 不要提前修改 `fixtures/calculator_repo`，否则演示中的 Proposal Hash 会变化。
  Do not modify `fixtures/calculator_repo` before the demo, because that changes the Proposal Hash.

## 三分钟现场演示 / Three-minute Live Demo

### 0:00–0:25：项目定位 / Project Positioning

中文讲稿：

Chinese script:

> IssueLens 是我从零构建的本地优先 Python Coding Agent。它关注的不只是生成答案，而是把 Issue、代码证据、修改提案、人工审批和验证回执连接成可审计链路。模型没有通用 Shell 或直接文件系统权限，仓库访问由受限工具控制。

英文讲稿：

English script:

> IssueLens is a local-first Python Coding Agent that I built from scratch. Instead of focusing only on answer generation, it connects Issues, code evidence, patch proposals, human approval, and validation receipts into an auditable chain. The model receives neither a general-purpose shell nor direct filesystem access; repository access is mediated by constrained tools.

此时运行：

Run:

```bash
make patch-demo
```

### 0:25–0:55：候选补丁与提案绑定 / Candidate Patch and Proposal Binding

终端首先显示候选 Unified Diff，然后输出提案 JSON。

The terminal first displays the candidate Unified Diff and then prints the proposal JSON.

指给面试官看的字段：

Point out these fields:

- `changed_paths`：补丁将影响哪些仓库相对路径。
  Which repository-relative paths the patch will affect.
- `base_snapshot_hash`：审批所针对的准确仓库状态。
  The exact repository state covered by the approval.
- `proposal_hash`：把补丁内容和基础快照绑定为一个可比较标识。
  A comparable identifier binding the patch content to the base snapshot.
- `repository_unchanged: true`：提案检查阶段没有修改目标仓库。
  Proposal inspection did not modify the target repository.

中文讲稿：

Chinese script:

> 这里的补丁被当作不可信数据，而不是命令。系统先解析 Unified Diff、限制路径，再把补丁绑定到仓库快照。只要补丁内容或仓库状态发生变化，Proposal Hash 就会改变，旧审批不能继续使用。

英文讲稿：

English script:

> The patch is treated as untrusted data, not as a command. The system parses the Unified Diff, enforces path policy, and binds the patch to a repository snapshot. If either the patch content or repository state changes, the Proposal Hash changes and the old approval can no longer be used.

### 0:55–1:25：人工安全门 / Human Safety Gate

终端会要求粘贴刚刚显示的完整 Proposal Hash。复制该值并粘贴，然后输入自己的姓名。

The terminal asks for the complete Proposal Hash that was just displayed. Copy and paste it, then enter your name.

中文讲稿：

Chinese script:

> 我没有让程序自动批准自己生成的 Hash。流程会在危险动作前暂停，要求操作者明确确认准确提案。输入错误或过期 Hash 时会失败关闭，不会创建审计回执。

英文讲稿：

English script:

> I deliberately avoid letting the program automatically approve its own hash. The workflow pauses before the sensitive action and requires the operator to confirm the exact proposal. A wrong or stale hash fails closed and creates no audit receipt.

如果时间允许，可以先故意输入错误 Hash，展示拒绝后重新运行命令。

If time permits, first enter an incorrect hash to demonstrate rejection, then rerun the command.

需要主动说明：审批人名称目前是声明式审计元数据，不是经过 SSO、证书或数字签名认证的身份。

State explicitly that the approver name is currently declared audit metadata, not an identity authenticated through SSO, certificates, or digital signatures.

### 1:25–2:10：临时副本预检 / Temporary-copy Preflight

Hash 匹配后，系统在临时副本中应用补丁，并输出审批和预检结果。

After the hash matches, the system applies the patch in a temporary copy and prints the approval and preflight result.

指给面试官看的字段：

Point out these fields:

- `approval_hash`：绑定运行标识、提案、基础快照、审批人和审批时间。
  Binds the Run ID, proposal, base snapshot, approver, and approval time.
- `preview_snapshot_hash`：临时副本应用补丁后的预览状态。
  The preview state after applying the patch in the temporary copy.
- `receipt_hash`：用于定位和验证内容寻址审计回执。
  Locates and verifies the content-addressed audit receipt.
- `repository_unchanged: true`：真实目标仓库仍然没有被写入。
  The real target repository still has not been modified.

中文讲稿：

Chinese script:

> 预检不是直接修改真实仓库。系统复制安全文本视图，在临时目录中检查 hunk 上下文并生成修改后快照，同时记录每个文件修改前后的 Hash 和行数统计。任何提案、审批、快照或上下文不一致都会中止流程。

英文讲稿：

English script:

> Preflight does not modify the real repository. The system copies the safe text view, checks hunk context in a temporary directory, produces a preview snapshot, and records per-file before/after hashes and line statistics. Any mismatch in the proposal, approval, snapshot, or hunk context aborts the workflow.

### 2:10–2:40：内容寻址审计报告 / Content-addressed Audit Report

命令最后会读取刚保存的回执、重新验证完整性，并输出中英双语 Markdown 报告。

Finally, the command loads the stored receipt, verifies its integrity again, and renders a bilingual Markdown report.

中文讲稿：

Chinese script:

> 审计回执存放在目标仓库之外，并以 Receipt Hash 命名。报告只包含绑定关系、文件统计和内容 Hash，不复制源码正文。SHA-256 可以检测内容变化，但它不是数字签名，所以我没有把它包装成身份认证。

英文讲稿：

English script:

> The audit receipt is stored outside the target repository and named by its Receipt Hash. The report contains bindings, file statistics, and content hashes without copying source text. SHA-256 detects content changes, but it is not a digital signature, so I do not present it as identity authentication.

重点展示：

Highlight:

```text
状态 / Status: 通过 / Passed
真实仓库写入 / Real repository write: 否 / No
回执完整性 / Receipt integrity: 已验证 / Verified
```

### 2:40–3:00：能力边界与下一步 / Boundaries and Next Step

中文讲稿：

Chinese script:

> 当前版本验证的是安全协议和可审计工作流：补丁解析、快照绑定、人工审批、临时副本预检和回执验证。它还没有在无凭据容器中执行目标仓库测试，也不会自动 Push、创建 PR 或合并。下一阶段会把测试执行放进限时、限资源、默认断网的 Shadow Workspace。

英文讲稿：

English script:

> The current version validates the safety protocol and auditable workflow: patch parsing, snapshot binding, human approval, temporary-copy preflight, and receipt verification. It does not yet execute target-repository tests inside a credential-free container, and it never automatically pushes, opens a PR, or merges. The next stage is to run tests in a time- and resource-bounded, network-disabled-by-default Shadow Workspace.

## 三十秒压缩版 / Thirty-second Version

中文讲稿：

Chinese script:

> IssueLens 是一个证据驱动、默认只读的 Python Coding Agent。它通过受限工具定位代码，并将候选补丁绑定到仓库快照；操作者必须手动确认 Proposal Hash，补丁才会进入临时副本预检。结果以内容寻址回执保存，真实仓库保持不变。当前实现重点验证安全与审计协议，容器化测试执行仍是下一阶段。

英文讲稿：

English script:

> IssueLens is an evidence-grounded, read-only-by-default Python Coding Agent. It locates code through constrained tools and binds candidate patches to repository snapshots; an operator must manually confirm the Proposal Hash before temporary-copy preflight. Results are stored as content-addressed receipts while the real repository remains unchanged. The current implementation validates the safety and audit protocol; containerized test execution is the next stage.

## 面试官常见追问 / Common Interview Questions

### 为什么这不是普通脚本？ / Why is this more than a regular script?

中文回答：

Chinese answer:

> 补丁演示本身是确定性的安全 Harness，但完整项目还包含 Issue 解析、AST 与文本检索、受限工具循环、可替换 Policy、证据引用、显式状态机和评测。我的设计重点是让非确定性的模型推理运行在确定性的权限与验证边界内。

英文回答：

English answer:

> The patch demo itself is a deterministic safety harness, while the complete project also includes Issue parsing, AST and text retrieval, a constrained tool loop, replaceable policies, evidence references, an explicit state machine, and evaluation. The design goal is to run nondeterministic model reasoning inside deterministic permission and validation boundaries.

### 为什么不直接应用补丁？ / Why not apply the patch directly?

中文回答：

Chinese answer:

> 因为“模型建议修改”和“真实环境发生写入”是两个不同权限等级。当前阶段只证明指定补丁能针对指定快照完成安全预检，把真实写入保留给后续明确授权的独立能力。

英文回答：

English answer:

> “A model proposes a change” and “the real environment is modified” are different authority levels. The current stage only proves that an exact patch can pass safe preflight against an exact snapshot, reserving real writes for a separately and explicitly authorized capability.

### 为什么同时需要 Snapshot Hash 和 Proposal Hash？ / Why use both a Snapshot Hash and a Proposal Hash?

中文回答：

Chinese answer:

> Snapshot Hash 标识审批所针对的代码基础，Proposal Hash 标识“这个基础上的这份补丁”。二者共同避免仓库变化后继续使用旧审批，也避免操作者审核 A 补丁却实际预检 B 补丁。

英文回答：

English answer:

> The Snapshot Hash identifies the codebase covered by the approval, while the Proposal Hash identifies “this patch against this base.” Together they prevent reuse of stale approvals after repository changes and prevent reviewing patch A while preflighting patch B.

### Hash 是否等于安全签名？ / Is a hash equivalent to a security signature?

中文回答：

Chinese answer:

> 不是。Hash 用于内容完整性和准确对象绑定，但不能证明是谁批准的。生产环境仍需要可信身份系统、不可抵赖签名、权限策略和密钥管理。

英文回答：

English answer:

> No. A hash provides content integrity and exact-object binding, but it does not prove who approved it. A production system still needs trusted identity, non-repudiable signatures, authorization policy, and key management.

### 为什么现在不用 Docker？ / Why not use Docker yet?

中文回答：

Chinese answer:

> 当前 Task 先验证不依赖第三方服务的补丁协议、失败关闭行为和审计结构。临时副本可以证明不写真实仓库，但不能安全执行不可信代码。真正执行目标测试前，必须加入无凭据、非 root、限资源和默认断网的容器边界。

英文回答：

English answer:

> The current task validates the patch protocol, fail-closed behavior, and audit structure without external services. A temporary copy proves that the real repository is not written, but it is not sufficient for safely executing untrusted code. Before running target tests, the system needs a credential-free, non-root, resource-bounded, network-disabled-by-default container boundary.

### 如何评估这个 Agent？ / How do you evaluate the Agent?

中文回答：

Chinese answer:

> 当前仓库有固定评测夹具和 87 项测试，覆盖检索信号、路径逃逸、符号链接、审批失效、补丁冲突和回执篡改等行为。对于真实能力，我只会使用时间切分的公开 Issue、固定 Commit、定位指标、解决率和失败分类，不用单个成功 Demo 代替评测。

英文回答：

English answer:

> The repository currently has fixed evaluation fixtures and 87 tests covering retrieval signals, path traversal, symlinks, approval invalidation, patch conflicts, and receipt tampering. For real-world capability, I would use time-split public Issues, pinned commits, localization metrics, resolution rate, and failure categories rather than treating one successful demo as evaluation.

### 如果做成产品，下一步是什么？ / What is the next product step?

中文回答：

Chinese answer:

> 第一是把目标测试执行迁移到隔离 Shadow Workspace；第二是接入可信身份和审批策略；第三是增加 Checkpoint、预算、失败恢复和可视化证据审查；最后才考虑默认关闭的 Draft PR 导出。

英文回答：

English answer:

> First, move target-test execution into an isolated Shadow Workspace. Second, integrate trusted identity and approval policy. Third, add checkpoints, budgets, failure recovery, and visual evidence review. Only then consider Draft PR export, disabled by default.

## 不同岗位的讲述重点 / Role-specific Emphasis

### 研发或 Agent 工程岗 / Engineering or Agent Engineering Role

- 强调 AST 索引、受限工具协议、显式状态机和确定性测试。
  Emphasize AST indexing, constrained tool protocols, the explicit state machine, and deterministic tests.
- 强调补丁解析、路径策略、Hash 绑定和失败关闭。
  Emphasize patch parsing, path policy, hash binding, and fail-closed behavior.
- 说明如何把模型 Policy 与仓库访问、安全 Harness 和评测解耦。
  Explain how the model policy is decoupled from repository access, the safety harness, and evaluation.

### Agent 产品或产品经理岗位 / Agent Product or Product Management Role

- 强调用户为什么需要看见证据、影响范围和审批对象。
  Emphasize why users need visibility into evidence, affected scope, and the exact approval object.
- 强调危险动作前的暂停、拒绝路径和可恢复工作流。
  Emphasize pauses before sensitive actions, rejection paths, and recoverable workflows.
- 强调信任指标：拒绝是否正确、仓库是否保持不变、回执是否可验证。
  Emphasize trust metrics: correct rejection, repository immutability, and receipt verifiability.

## 不应夸大的表述 / Claims to Avoid

| 不要这样说 / Avoid | 应该这样说 / Say Instead |
| --- | --- |
| “Agent 已经可以自动修复任意 Issue。” / “The Agent can automatically fix any Issue.” | “当前版本提供证据驱动分析和受控补丁审查基线。” / “The current version provides an evidence-grounded analysis and controlled patch-review baseline.” |
| “补丁已经在沙箱中运行测试。” / “The patch has run tests in a sandbox.” | “补丁只在标准库临时副本中完成文本级预检，未执行目标代码。” / “The patch only passes text-level preflight in a standard-library temporary copy; target code is not executed.” |
| “审批人身份已经认证。” / “The approver identity is authenticated.” | “审批人是声明式审计元数据，身份认证尚未接入。” / “The approver is declared audit metadata; identity authentication is not yet integrated.” |
| “SHA-256 能防止所有篡改。” / “SHA-256 prevents all tampering.” | “Hash 用于检测内容变化和绑定准确对象，不等于数字签名或访问控制。” / “Hashes detect content changes and bind exact objects; they are not digital signatures or access control.” |
| “项目已经达到生产级。” / “The project is production-ready.” | “项目验证了核心安全协议，容器执行、可信身份和真实 Issue 评测仍在路线图中。” / “The project validates the core safety protocol; container execution, trusted identity, and real-Issue evaluation remain on the roadmap.” |

## 收尾句 / Closing Statement

中文讲稿：

Chinese script:

> 这个项目最想证明的不是我能调用一个模型，而是我能把 Agent 的不确定性放进可验证的工程边界：证据可追溯、权限最小化、危险动作需要明确审批、失败时默认停止、结果可以独立复核。

英文讲稿：

English script:

> The main point of this project is not that I can call a model. It is that I can place Agent uncertainty inside verifiable engineering boundaries: traceable evidence, least privilege, explicit approval for sensitive actions, fail-closed behavior, and independently reviewable results.
