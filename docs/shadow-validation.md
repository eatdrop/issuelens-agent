# Shadow Workspace 验证 / Shadow Workspace Validation

## 目的 / Purpose

Shadow Workspace 验证一个精确、已审批的候选补丁是否满足“补丁前复现失败、补丁后复现通过、既有测试通过、隐藏测试通过”，同时保持真实目标仓库不变。

The Shadow Workspace validates whether an exact, approved candidate patch satisfies “reproduction fails before the patch, reproduction passes after it, existing tests pass, and hidden tests pass,” while preserving the real target repository.

该能力验证候选补丁，不负责从 Issue 生成补丁，也不会把补丁写回真实仓库。

This capability validates a candidate patch. It does not generate a patch from an Issue or write the patch back to the real repository.

## 四阶段判定 / Four-stage Verdict

| 阶段 / Stage | 工作区 / Workspace | 预期 / Expected |
|---|---|---|
| `baseline_reproduction` | 未打补丁临时副本 / Unpatched temporary copy | 测试确实运行且失败 / Tests genuinely run and fail |
| `patched_reproduction` | 已打补丁临时副本 / Patched temporary copy | 同一复现测试确实运行且通过 / The same reproduction tests genuinely run and pass |
| `patched_full_suite` | 已打补丁临时副本 / Patched temporary copy | 全量回归确实运行且通过 / The full regression suite genuinely runs and passes |
| `patched_hidden_suite` | 已打补丁临时副本 / Patched temporary copy | 外置隐藏测试确实运行且通过 / External hidden tests genuinely run and pass |

判定不是简单检查退出码。`unittest` 必须报告实际运行测试；Baseline 的导入错误、`ModuleNotFoundError` 或 `_FailedTest` 被视为基础设施失败，而不是“成功复现 Bug”。

The verdict does more than inspect exit codes. `unittest` must report actual test execution; baseline import errors, `ModuleNotFoundError`, or `_FailedTest` are infrastructure failures, not a “successful bug reproduction.”

任一阶段超时、未执行测试、期望不匹配、隐藏测试失败或真实仓库快照变化，最终 verdict 都是 `failed`。

Any timeout, zero-test run, expectation mismatch, hidden-test failure, or real-repository snapshot change produces a final `failed` verdict.

## Docker 安全配置 / Docker Security Configuration

默认镜像固定到名称、版本与内容摘要：

The default image is pinned by name, version, and content digest:

```text
python:3.12.10-slim@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db
```

每个测试阶段启动独立容器，并强制：

Each test stage starts a separate container and enforces:

- `--pull=never`：运行时不隐式访问镜像仓库。
  No implicit registry access at runtime.
- `--network=none`：没有容器网络。
  No container network.
- `--read-only`：容器根文件系统只读。
  A read-only container root filesystem.
- `--volume=<temporary-copy>:/workspace:ro`：临时工作区也以只读方式挂载。
  The temporary workspace is also mounted read-only.
- `--tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m`：唯一可写区是受限临时内存文件系统。
  The only writable area is a constrained temporary in-memory filesystem.
- `--user=65534:65534`、`--cap-drop=ALL`、`--security-opt=no-new-privileges`：非 root 且无 Linux Capabilities。
  Non-root execution without Linux capabilities or privilege escalation.
- `--memory=512m`、`--cpus=1.0`、`--pids-limit=128` 和每命令超时。
  Memory, CPU, process, and per-command time limits.
- 固定的 `PYTHONHASHSEED=0`、禁用 `.pyc` 写入，并只设置目标源码 `PYTHONPATH`。
  A fixed `PYTHONHASHSEED=0`, disabled `.pyc` writes, and a target-source-only `PYTHONPATH`.

没有挂载宿主凭据、SSH Agent、Docker Socket、用户 Home 或真实仓库可写路径。

No host credentials, SSH agent, Docker socket, user home, or writable real-repository path is mounted.

## 命令边界 / Command Boundary

MVP 只接受以 `python` 或 `python3` 开头的结构化参数数组，CLI 生成固定的 `python -m unittest discover ... -v`。它不通过 Shell 解释字符串。

The MVP accepts only structured argument arrays beginning with `python` or `python3`; the CLI generates fixed `python -m unittest discover ... -v` commands. No command string is interpreted by a shell.

测试 Bundle 必须位于目标仓库之外，最多 100 个文件且总计不超过 1 MB。复制过程遵守文本、大小和符号链接策略。

Test bundles must remain outside the target repository, contain at most 100 files, and total no more than 1 MB. Copying follows text, size, and symlink policies.

stdout/stderr 各保留有界摘要与完整 SHA-256，防止无限日志撑大回执。摘要可能包含测试输出，因此公开前仍需人工检查敏感信息。

Bounded stdout/stderr excerpts and full SHA-256 hashes prevent unbounded logs from inflating receipts. Excerpts may contain test output and still require human review before publication.

## 使用方式 / Usage

```bash
docker pull python:3.12.10-slim@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db
make shadow-demo
```

或直接调用 CLI：

Or call the CLI directly:

```bash
PYTHONPATH=src python3 -m issuelens patch-validate \
  --repo fixtures/calculator_repo \
  --diff evals/patches/division_by_zero.diff \
  --run-id shadow-example \
  --approved-by "reviewer" \
  --approve-proposal-hash "<proposal-hash>" \
  --audit-dir /tmp/issuelens-shadow-audit \
  --reproduction-tests evals/reproduction/division_by_zero \
  --hidden-tests evals/hidden/division_by_zero
```

默认 Runner 是 Docker。只有可信固定夹具才能显式使用宿主机 Runner：

Docker is the default runner. Host execution is available only by explicit opt-in for trusted fixed fixtures:

```bash
PYTHONPATH=src python3 -m issuelens patch-validate ... \
  --runner local \
  --allow-unsafe-local
```

`--runner local` 不提供容器隔离，绝不能用于陌生仓库、第三方 PR 或来自网络的测试。

`--runner local` provides no container isolation and must never be used for unfamiliar repositories, third-party PRs, or tests obtained from the network.

## 审计回执 / Audit Receipt

成功或失败结果绑定 Run ID、Runner、Proposal Hash、Approval Hash、基础/补丁快照、修改路径、每阶段参数/退出码/耗时/输出哈希以及真实仓库未变结论。

A success or failure result binds the Run ID, runner, Proposal Hash, Approval Hash, base/patched snapshots, changed paths, per-stage arguments/exit code/duration/output hashes, and the real-repository-unchanged conclusion.

JSON 回执以 `receipt_hash` 命名并不可覆盖；加载时拒绝符号链接、大小超限、字段异常、文件名不匹配和内容篡改。相同回执重复保存是幂等的。

JSON receipts are named by `receipt_hash` and cannot be overwritten; loading rejects symlinks, oversized content, invalid fields, filename mismatches, and tampering. Storing an identical receipt again is idempotent.

## 能力边界 / Limitations

- 固定镜像没有依赖安装阶段，因此演示仓库必须能在该 Python 标准库环境中运行。
  The pinned image has no dependency-install phase, so demo repositories must run in its Python standard-library environment.
- 只支持 `unittest discover` 流程，不是通用构建系统。
  Only the `unittest discover` flow is supported; this is not a general build system.
- Docker 加固减少攻击面，但不是经过认证的多租户恶意代码沙箱。
  Docker hardening reduces attack surface but is not a certified multi-tenant hostile-code sandbox.
- Hash 证明内容绑定，不认证审批人身份。
  Hashes prove content binding, not approver identity.
- 回执证明记录的命令预期，不代表补丁语义正确、已写入仓库或已合并。
  A receipt proves the recorded command expectations; it does not establish semantic correctness or imply that the patch was written or merged.
