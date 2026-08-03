# IssueLens 安全模型 / Security Model

Issue、目标仓库、候选 Diff、测试 Bundle、模型输出和测试输出都可能不可信。它们必须被视为有界数据，不能自动获得环境权限。

Issues, target repositories, candidate Diffs, test bundles, model output, and test output may all be untrusted. They must be treated as bounded data and receive no ambient authority.

## 当前保证 / Current Guarantees

### 分析边界 / Analysis Boundary

- 目标仓库网关拒绝绝对路径、`..` 路径逃逸和符号链接，只读取大小受限的 UTF-8 文本。
  The target-repository gateway rejects absolute paths, `..` traversal, and symlinks and reads only bounded UTF-8 text.
- Agent 动作协议不提供 Shell、网络、环境变量或写入动作。
  The Agent action schema exposes no shell, network, environment-variable, or write action.
- 每个可执行计划步骤必须引用受控工具返回的证据。
  Every actionable plan step must cite evidence returned by controlled tools.
- 分析前后计算规范化仓库快照；非预期变化使运行失败。
  A canonical repository snapshot is calculated before and after analysis; unexpected changes fail the run.
- API Key 只由模型适配器读取，不写入 Prompt、Trace、报告、Checkpoint 或容器。
  API keys are read only by the model adapter and are not written to prompts, traces, reports, checkpoints, or containers.

### Checkpoint 与预算 / Checkpoints and Budgets

- Checkpoint 绑定 Run ID、Issue 哈希、仓库快照、状态、证据、累计耗时和完整性哈希。
  Checkpoints bind the Run ID, Issue hash, repository snapshot, state, evidence, accumulated time, and integrity hash.
- 恢复拒绝 Issue 漂移、仓库漂移、回执篡改和已完成运行。
  Resume rejects Issue drift, repository drift, tampering, and completed runs.
- 工具调用、证据数量、步骤与总耗时都有上限；模型重试次数有界。
  Tool calls, evidence count, steps, and total elapsed time are bounded; model retries are limited.

### 补丁协议 / Patch Protocol

- 候选补丁必须是大小受限的 UTF-8 Unified Diff，并通过路径、重复文件、重命名和 Git 元数据策略。
  Candidate patches must be bounded UTF-8 Unified Diffs and pass path, duplicate-file, rename, and Git-metadata policy.
- Proposal Hash 绑定规范化 Diff 与当前仓库快照；任何变化都会使旧审批失效。
  A Proposal Hash binds the normalized Diff and current repository snapshot; any change invalidates prior approval.
- 审批绑定 Run ID、提案、基础快照、声明的审批人和时间。
  Approval binds the Run ID, proposal, base snapshot, declared approver, and time.
- 补丁只应用到一次性临时副本；真实仓库在预检和验证前后必须保持同一快照。
  A patch is applied only to a disposable temporary copy; the real repository must retain the same snapshot before and after preflight and validation.

### Docker Shadow Workspace / Docker Shadow Workspace

默认验证 Runner 使用固定摘要镜像和 `--pull=never`。每个阶段单独启动容器，并强制断网、只读根文件系统、只读工作区、非 root、清空 Capabilities、禁止提权、64 MB `noexec` `/tmp`、512 MB 内存、1 CPU、128 进程及每命令超时。

The default validation runner uses a digest-pinned image and `--pull=never`. Each stage starts a separate container with no network, a read-only root filesystem and workspace, non-root execution, dropped capabilities, no privilege escalation, a 64 MB `noexec` `/tmp`, 512 MB memory, one CPU, 128 processes, and a per-command timeout.

容器不挂载宿主凭据、SSH Agent、Docker Socket、Home 或真实仓库可写路径。命令以结构化参数执行，不通过 Shell。

The container mounts no host credentials, SSH agent, Docker socket, home directory, or writable real-repository path. Commands use structured arguments without a shell.

Baseline 只有在测试确实运行且出现断言失败/错误时才满足预期；导入错误、零测试、超时和基础设施失败不算成功复现。

The baseline expectation is met only when tests genuinely execute and report assertion failures/errors; import errors, zero tests, timeouts, and infrastructure failures are not successful reproduction.

### 审计、UI 与导出 / Audit, UI, and Export

- JSON 回执内容寻址、不可覆盖、大小受限，并在加载时拒绝符号链接与完整性错误。
  JSON receipts are content-addressed, non-overwriting, size-bounded, and reject symlinks and integrity failures on load.
- Dashboard 仅绑定回环地址，使用随机 Token、Host 检查、CSP、`nosniff`、Referrer Policy、`no-store` 和 HTML 转义。
  The dashboard binds only to loopback and uses a random token, Host validation, CSP, `nosniff`, Referrer Policy, `no-store`, and HTML escaping.
- 网页决策追加保存且哈希保护，但只表示计划审阅，不授予补丁或发布权限。
  Web decisions are append-only and hash-protected but represent plan review only; they grant no patch or publication authority.
- Draft PR 只导出到目标仓库外的新文件，不调用 GitHub API。
  Draft PR content is exported only to a new file outside the target repository; no GitHub API is called.

## 不安全的本地 Runner / Unsafe Local Runner

`--runner local --allow-unsafe-local` 会在宿主机执行目标测试，不具有 Docker 隔离。它只用于本仓库内已知、可信、受版本控制的固定夹具。

`--runner local --allow-unsafe-local` executes target tests on the host and provides no Docker isolation. It is only for known, trusted, version-controlled fixtures in this repository.

不要对陌生仓库、第三方 PR、网络下载的测试或用户上传内容使用本地 Runner。

Never use the local runner for unfamiliar repositories, third-party PRs, downloaded tests, or user-uploaded content.

## 已知限制 / Known Limitations

- Docker 加固降低风险，但不是经过认证的多租户恶意代码沙箱；内核漏洞、Docker Daemon 与平台实现仍属于信任基础。
  Docker hardening reduces risk but is not a certified multi-tenant hostile-code sandbox; kernel vulnerabilities, the Docker daemon, and platform implementation remain in the trusted computing base.
- MVP 没有依赖构建阶段，只支持固定 Python 镜像中的 `unittest discover`。
  The MVP has no dependency-build phase and supports only `unittest discover` inside the pinned Python image.
- 测试输出摘要可能包含敏感内容，上传 CI Artifact 或公开前必须人工检查。
  Test-output excerpts may contain sensitive content and require human review before CI upload or publication.
- `approved_by` 和网页审阅人是声明式元数据，不是 SSO、证书或数字签名认证身份。
  `approved_by` and web reviewers are declared metadata, not identities authenticated through SSO, certificates, or digital signatures.
- SHA-256 用于内容完整性和对象绑定，不等于数字签名、访问控制或不可抵赖证明。
  SHA-256 provides content integrity and object binding; it is not a digital signature, access control, or non-repudiation proof.
- 恶意仓库文本可能诱导模型；结构化动作校验缩小权限，但不能完全解决语义级 Prompt Injection。
  Malicious repository text may manipulate the model; structured action validation reduces authority but does not fully solve semantic prompt injection.
- 通用 LLM 适配器实现窄 JSON 协议，尚未验证所有服务商。
  The generic LLM adapter implements a narrow JSON protocol and has not been validated against every provider.
- 当前系统不会自动生成并提交补丁，也不会 Push、创建或合并 PR。
  The current system does not automatically generate and submit patches, push, open, or merge PRs.

## 生产化前要求 / Requirements Before Production Use

- 使用更强隔离（如独立 VM/微虚机）、只读基础镜像、出站代理与更细资源/存储配额。
  Use stronger isolation such as dedicated VMs or microVMs, read-only base images, egress proxies, and finer resource/storage quotas.
- 建立受审计的依赖获取阶段，锁定哈希、许可证与供应链来源。
  Add an audited dependency-fetch phase with pinned hashes, licenses, and provenance.
- 接入可信身份、细粒度授权、签名审批和密钥管理。
  Integrate trusted identity, fine-grained authorization, signed approvals, and key management.
- 对日志、Trace、报告和 Artifact 做秘密扫描、脱敏和保留策略。
  Apply secret scanning, redaction, and retention policy to logs, traces, reports, and artifacts.
- 独立评测 Prompt Injection、资源耗尽、容器逃逸和并发隔离。
  Independently evaluate prompt injection, resource exhaustion, container escape, and concurrent isolation.
- 外部发布保持默认关闭，并要求独立的精确对象确认。
  Keep external publication disabled by default and require a separate exact-object confirmation.

## 报告安全问题 / Reporting Security Issues

安全报告应提供最小复现，不得访问不属于本人或未经授权的仓库、账号及数据。请不要在公开 Issue 中发布凭据或可直接利用的敏感细节。

Security reports should include a minimal reproduction without accessing repositories, accounts, or data you do not own or have authorization to test. Do not publish credentials or directly exploitable sensitive details in a public Issue.
