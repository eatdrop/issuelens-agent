# IssueLens 安全模型 / Security Model

IssueLens 会分析不可信仓库和不可信 Issue 文本。二者都必须被视为数据，不能被当作具有环境权限的指令。

IssueLens analyzes untrusted repositories and untrusted Issue text. Both must be treated as data, never as instructions with ambient authority.

## 当前安全保证 / Current Guarantees

- 目标仓库访问在设计上只读。
  Target repository access is read-only by design.
- 路径必须相对仓库根目录，并拒绝绝对路径和 `..`。
  Paths must be repository-relative; absolute paths and `..` are rejected.
- 跳过符号链接，防止逃逸仓库根目录。
  Symlinks are skipped to prevent repository-root escape.
- 只允许读取大小受限的 UTF-8 文本文件。
  Only bounded UTF-8 text files are readable.
- Agent 动作协议不提供 Shell、网络、环境变量或写入动作。
  The Agent action schema exposes no shell, network, environment, or write action.
- 每个可执行计划都必须引用受控工具返回的证据。
  Every actionable plan must cite evidence returned by approved tools.
- 运行产物存放在目标仓库之外。
  Run artifacts are stored outside the target repository.
- 运行前后计算仓库哈希，发现非预期变化即失败。
  Repository content is hashed before and after a run; unexpected changes fail the run.
- API Key 只由模型适配器读取，不进入 Prompt 或 Trace。
  API keys are read only by the model adapter and never placed in prompts or traces.
- 候选补丁必须是大小受限的 UTF-8 Unified Diff，并经过路径、重复文件、重命名和 Git 元数据策略校验。
  Candidate patches must be bounded UTF-8 Unified Diffs and pass path, duplicate-file, rename, and Git-metadata policy validation.
- 补丁提案绑定规范化 Diff 和当前仓库快照；补丁或仓库变化都会改变提案哈希。
  Patch proposals bind the normalized Diff and current repository snapshot; changing either the patch or repository changes the Proposal Hash.
- 显式审批绑定运行标识、提案、基础快照、声明的审批人和审批时间。
  Explicit approvals bind the Run ID, proposal, base snapshot, declared approver, and approval time.
- 补丁只在临时副本中进行文本级预检；真实目标仓库在预检前后必须保持不变。
  Patches receive text-level preflight only in a temporary copy; the real target repository must remain unchanged before and after preflight.
- 预检回执存储在目标仓库外的内容寻址审计目录中；已有路径不会被静默覆盖，读取时会重新验证完整性。
  Preflight receipts are stored in a content-addressed audit directory outside the target repository; existing paths are never silently overwritten, and integrity is revalidated when receipts are loaded.

## 已知限制 / Known Limitations

- 当前版本不会执行目标仓库测试，也不会把补丁应用到真实目标仓库；临时副本只提供文本级补丁预检。
  The current version neither executes target-repository tests nor applies patches to the real target repository; the temporary copy provides text-level patch preflight only.
- 临时副本不是用于执行不可信代码的安全沙箱，也不提供容器级 CPU、内存、进程或网络隔离。
  The temporary copy is not a secure sandbox for untrusted-code execution and provides no container-level CPU, memory, process, or network isolation.
- `approved_by` 是声明式审计元数据，不是经过认证的身份。
  `approved_by` is declared audit metadata, not an authenticated identity.
- SHA-256 用于内容变化检测和对象绑定，不等同于数字签名、访问控制或不可抵赖证明。
  SHA-256 is used for content-change detection and object binding; it is not a digital signature, access control, or proof of non-repudiation.
- 仓库中可能存在诱导模型的恶意文本。模型输出会经过结构化校验，但语义级 Prompt Injection 防御尚不完整。
  A repository may contain adversarial text intended to manipulate the model. Model output is schema-validated, but semantic prompt-injection defenses are not complete.
- 通用 LLM 适配器只实现窄 JSON 协议，尚未验证所有服务商。
  The generic LLM adapter implements a narrow JSON protocol and has not been validated against every provider.
- 超大文件和非 UTF-8 文件会被主动跳过。
  Oversized and non-UTF-8 files are intentionally skipped.

## 启用目标代码执行前的要求 / Requirements Before Enabling Target-code Execution

不可信目标仓库代码和测试不得直接运行在宿主机。未来的 Shadow Validator 必须具备：

Untrusted target-repository code and tests must not run directly on the host. A future Shadow Validator must use:

- 临时、非 root 容器。
  An ephemeral non-root container.
- 不挂载宿主凭据、SSH Agent 或 Docker Socket。
  No host credentials, SSH agent, or Docker socket.
- 默认断网。
  Network disabled by default.
- 只读基础源码与一次性可写层。
  Read-only base source plus a disposable writable layer.
- CPU、内存、进程、磁盘和时间限制。
  CPU, memory, process, disk, and wall-time limits.
- 从仓库元数据生成的测试命令白名单。
  An allowlisted test command derived from repository metadata.
- 完整 stdout/stderr 记录和敏感信息脱敏。
  Complete stdout/stderr capture with secret redaction.
- 保留当前补丁路径策略和绑定快照的人工审批。
  Retain the current patch path policy and snapshot-bound human approval.
- 不自动 Push、创建 PR 或合并。
  No automatic push, PR submission, or merge.

安全问题报告应提供最小复现，不得访问不属于本人或未经授权的仓库及数据。

Security reports should include a minimal reproduction without accessing repositories or data that you do not own or have authorization to test.
