from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Literal, Protocol

from .approval import PatchApproval
from .approval_gate import require_patch_application_approval
from .patch_preflight import materialize_approved_patch
from .patch_proposal import PatchProposal
from .repository import ReadOnlyRepository


class ShadowWorkspaceError(RuntimeError):
    """Raised when isolated validation cannot complete safely."""


DEFAULT_DOCKER_IMAGE = (
    "python:3.12.10-slim@"
    "sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db"
)


Expectation = Literal["pass", "fail"]


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    argv: tuple[str, ...]
    expectation: Expectation = "pass"
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ShadowWorkspaceError("command name must be non-empty text")
        if not isinstance(self.argv, tuple) or not self.argv:
            raise ShadowWorkspaceError("command argv must be a non-empty tuple")
        if self.argv[0] not in {"python", "python3"}:
            raise ShadowWorkspaceError(
                "MVP shadow commands must use python or python3"
            )
        if len(self.argv) > 64:
            raise ShadowWorkspaceError("command argv exceeds the item limit")
        for argument in self.argv:
            if (
                not isinstance(argument, str)
                or not argument
                or len(argument) > 1_000
                or "\x00" in argument
            ):
                raise ShadowWorkspaceError("command argv contains an invalid value")
        if self.expectation not in {"pass", "fail"}:
            raise ShadowWorkspaceError("command expectation is invalid")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0.1 <= float(self.timeout_seconds) <= 900.0
        ):
            raise ShadowWorkspaceError("command timeout is outside the safe range")


@dataclass(frozen=True, slots=True)
class CommandResult:
    name: str
    argv: tuple[str, ...]
    expectation: Expectation
    exit_code: int | None
    timed_out: bool
    duration_ms: float
    expectation_met: bool
    stdout_sha256: str
    stderr_sha256: str
    stdout_excerpt: str
    stderr_excerpt: str

    def to_dict(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "duration_ms": self.duration_ms,
            "exit_code": self.exit_code,
            "expectation": self.expectation,
            "expectation_met": self.expectation_met,
            "name": self.name,
            "stderr_excerpt": self.stderr_excerpt,
            "stderr_sha256": self.stderr_sha256,
            "stdout_excerpt": self.stdout_excerpt,
            "stdout_sha256": self.stdout_sha256,
            "timed_out": self.timed_out,
        }

    @classmethod
    def from_dict(cls, value: object) -> CommandResult:
        if not isinstance(value, dict) or set(value) != _COMMAND_RESULT_FIELDS:
            raise ShadowWorkspaceError("validation command result fields are invalid")
        argv = value["argv"]
        if not isinstance(argv, list):
            raise ShadowWorkspaceError("validation command argv must be a list")
        return cls(
            name=value["name"],
            argv=tuple(argv),
            expectation=value["expectation"],
            exit_code=value["exit_code"],
            timed_out=value["timed_out"],
            duration_ms=value["duration_ms"],
            expectation_met=value["expectation_met"],
            stdout_sha256=value["stdout_sha256"],
            stderr_sha256=value["stderr_sha256"],
            stdout_excerpt=value["stdout_excerpt"],
            stderr_excerpt=value["stderr_excerpt"],
        )


@dataclass(frozen=True, slots=True)
class ShadowValidationResult:
    run_id: str
    runner: str
    proposal_hash: str
    approval_hash: str
    base_snapshot_hash: str
    patched_snapshot_hash: str
    changed_paths: tuple[str, ...]
    commands: tuple[CommandResult, ...]
    repository_unchanged: bool
    verdict: Literal["passed", "failed"]
    receipt_hash: str

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        runner: str,
        proposal_hash: str,
        approval_hash: str,
        base_snapshot_hash: str,
        patched_snapshot_hash: str,
        changed_paths: tuple[str, ...],
        commands: tuple[CommandResult, ...],
        repository_unchanged: bool,
    ) -> ShadowValidationResult:
        verdict: Literal["passed", "failed"] = (
            "passed"
            if commands
            and all(item.expectation_met for item in commands)
            and repository_unchanged
            else "failed"
        )
        payload = _validation_payload(
            run_id=run_id,
            runner=runner,
            proposal_hash=proposal_hash,
            approval_hash=approval_hash,
            base_snapshot_hash=base_snapshot_hash,
            patched_snapshot_hash=patched_snapshot_hash,
            changed_paths=changed_paths,
            commands=commands,
            repository_unchanged=repository_unchanged,
            verdict=verdict,
        )
        receipt_hash = _payload_hash(payload)
        result = cls(
            run_id=run_id,
            runner=runner,
            proposal_hash=proposal_hash,
            approval_hash=approval_hash,
            base_snapshot_hash=base_snapshot_hash,
            patched_snapshot_hash=patched_snapshot_hash,
            changed_paths=changed_paths,
            commands=commands,
            repository_unchanged=repository_unchanged,
            verdict=verdict,
            receipt_hash=receipt_hash,
        )
        result._validate()
        return result

    def to_json(self) -> str:
        payload = _validation_payload(
            run_id=self.run_id,
            runner=self.runner,
            proposal_hash=self.proposal_hash,
            approval_hash=self.approval_hash,
            base_snapshot_hash=self.base_snapshot_hash,
            patched_snapshot_hash=self.patched_snapshot_hash,
            changed_paths=self.changed_paths,
            commands=self.commands,
            repository_unchanged=self.repository_unchanged,
            verdict=self.verdict,
        )
        payload["receipt_hash"] = self.receipt_hash
        return _canonical_json(payload)

    @classmethod
    def from_json(cls, value: str) -> ShadowValidationResult:
        if not isinstance(value, str) or len(value) > _MAX_RECEIPT_BYTES:
            raise ShadowWorkspaceError("validation receipt is not bounded text")
        try:
            payload = json.loads(value)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ShadowWorkspaceError("validation receipt is not valid JSON") from exc
        if not isinstance(payload, dict) or set(payload) != _RECEIPT_FIELDS:
            raise ShadowWorkspaceError("validation receipt fields are invalid")
        if payload["schema_version"] != 1:
            raise ShadowWorkspaceError("validation receipt schema is unsupported")
        changed_paths = payload["changed_paths"]
        commands = payload["commands"]
        if not isinstance(changed_paths, list) or not isinstance(commands, list):
            raise ShadowWorkspaceError("validation receipt arrays are invalid")
        result = cls(
            run_id=payload["run_id"],
            runner=payload["runner"],
            proposal_hash=payload["proposal_hash"],
            approval_hash=payload["approval_hash"],
            base_snapshot_hash=payload["base_snapshot_hash"],
            patched_snapshot_hash=payload["patched_snapshot_hash"],
            changed_paths=tuple(changed_paths),
            commands=tuple(CommandResult.from_dict(item) for item in commands),
            repository_unchanged=payload["repository_unchanged"],
            verdict=payload["verdict"],
            receipt_hash=payload["receipt_hash"],
        )
        result._validate()
        if not result.verify_integrity():
            raise ShadowWorkspaceError("validation receipt integrity check failed")
        return result

    def verify_integrity(self) -> bool:
        try:
            payload = _validation_payload(
                run_id=self.run_id,
                runner=self.runner,
                proposal_hash=self.proposal_hash,
                approval_hash=self.approval_hash,
                base_snapshot_hash=self.base_snapshot_hash,
                patched_snapshot_hash=self.patched_snapshot_hash,
                changed_paths=self.changed_paths,
                commands=self.commands,
                repository_unchanged=self.repository_unchanged,
                verdict=self.verdict,
            )
            return hmac.compare_digest(self.receipt_hash, _payload_hash(payload))
        except (AttributeError, TypeError, ValueError):
            return False

    def _validate(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_text(self.runner, "runner")
        if len(self.run_id) > 128 or "\x00" in self.run_id:
            raise ShadowWorkspaceError("validation run_id is invalid")
        if len(self.runner) > 1_000 or "\x00" in self.runner:
            raise ShadowWorkspaceError("validation runner is invalid")
        for name, digest in (
            ("proposal_hash", self.proposal_hash),
            ("approval_hash", self.approval_hash),
            ("base_snapshot_hash", self.base_snapshot_hash),
            ("patched_snapshot_hash", self.patched_snapshot_hash),
            ("receipt_hash", self.receipt_hash),
        ):
            _require_sha256(digest, name)
        if (
            not self.changed_paths
            or len(self.changed_paths) > 1_000
            or not self.commands
            or len(self.commands) > 16
        ):
            raise ShadowWorkspaceError("validation receipt cannot be empty")
        for path in self.changed_paths:
            if not isinstance(path, str) or not path.strip() or "\x00" in path:
                raise ShadowWorkspaceError("validation changed_paths are invalid")
            parsed_path = PurePosixPath(path)
            if parsed_path.is_absolute() or any(
                part in {"", ".", ".."} for part in parsed_path.parts
            ):
                raise ShadowWorkspaceError("validation changed_paths are invalid")
        if type(self.repository_unchanged) is not bool:
            raise ShadowWorkspaceError("repository_unchanged must be boolean")
        if self.verdict not in {"passed", "failed"}:
            raise ShadowWorkspaceError("validation verdict is invalid")
        expected_verdict = (
            "passed"
            if all(item.expectation_met for item in self.commands)
            and self.repository_unchanged
            else "failed"
        )
        if self.verdict != expected_verdict:
            raise ShadowWorkspaceError("validation verdict is inconsistent")
        for command in self.commands:
            _validate_command_result(command)


class ShadowCommandRunner(Protocol):
    name: str

    def run(self, workspace: Path, command: CommandSpec) -> CommandResult: ...


class DockerCommandRunner:

    def __init__(
        self,
        *,
        image: str = DEFAULT_DOCKER_IMAGE,
        memory: str = "512m",
        cpus: str = "1.0",
        pids_limit: int = 128,
    ) -> None:
        if (
            not isinstance(image, str)
            or not image.strip()
            or len(image) > 300
            or any(character.isspace() for character in image)
        ):
            raise ShadowWorkspaceError("Docker image reference is invalid")
        if not re.fullmatch(r"[A-Za-z0-9_./:@+-]+", image):
            raise ShadowWorkspaceError("Docker image reference contains unsafe text")
        if not isinstance(memory, str) or re.fullmatch(r"[1-9][0-9]{1,5}[kKmMgG]", memory) is None:
            raise ShadowWorkspaceError("Docker memory limit is invalid")
        try:
            cpus_value = float(cpus)
        except (TypeError, ValueError) as exc:
            raise ShadowWorkspaceError("Docker CPU limit is invalid") from exc
        if not math.isfinite(cpus_value) or not 0.1 <= cpus_value <= 16.0:
            raise ShadowWorkspaceError("Docker CPU limit is invalid")
        if type(pids_limit) is not int or not 16 <= pids_limit <= 1_024:
            raise ShadowWorkspaceError("Docker process limit is invalid")
        self.image = image
        self.memory = memory.lower()
        self.cpus = str(cpus)
        self.pids_limit = pids_limit
        self.name = (
            f"docker|image={image}|memory={self.memory}|cpus={self.cpus}|"
            f"pids={pids_limit}|network=none|rootfs=ro|workspace=ro|uid=65534"
        )

    def run(self, workspace: Path, command: CommandSpec) -> CommandResult:
        workspace_input = workspace.expanduser().absolute()
        if workspace_input.is_symlink():
            raise ShadowWorkspaceError("Docker workspace must be a real directory")
        root = workspace_input.resolve()
        _prepare_read_only_mount(root)
        container_name = f"issuelens-{os.getpid()}-{uuid.uuid4().hex[:12]}"
        docker_argv = (
            "docker",
            "run",
            "--rm",
            f"--name={container_name}",
            "--pull=never",
            "--network=none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=64m",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--pids-limit={self.pids_limit}",
            f"--memory={self.memory}",
            f"--cpus={self.cpus}",
            "--user=65534:65534",
            "--env=PYTHONDONTWRITEBYTECODE=1",
            "--env=PYTHONHASHSEED=0",
            "--env=PYTHONPATH=/workspace/src",
            f"--volume={root}:/workspace:ro",
            "--workdir=/workspace",
            self.image,
            *command.argv,
        )
        return _run_process(
            docker_argv,
            command,
            timeout_cleanup=("docker", "rm", "-f", container_name),
        )


class UnsafeLocalCommandRunner:
    """Explicit opt-in backend for trusted fixtures and unit tests only."""

    name = "unsafe-local"

    def run(self, workspace: Path, command: CommandSpec) -> CommandResult:
        argv = list(command.argv)
        argv[0] = sys.executable
        environment = {
            "PATH": os.environ.get("PATH", os.defpath),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": str(workspace.resolve() / "src"),
        }
        return _run_process(
            tuple(argv),
            command,
            cwd=workspace.resolve(),
            env=environment,
        )


def validate_approved_patch(
    *,
    repository: ReadOnlyRepository,
    run_id: str,
    proposal: PatchProposal,
    approval: PatchApproval,
    runner: ShadowCommandRunner,
    reproduction_tests: str | Path,
    hidden_tests: str | Path | None = None,
    full_test_dir: str = "tests",
    timeout_seconds: float = 60.0,
) -> ShadowValidationResult:
    """Prove fail-before/pass-after behavior without writing the target repo."""

    if not isinstance(repository, ReadOnlyRepository):
        raise ShadowWorkspaceError("repository must be a ReadOnlyRepository")
    if not isinstance(runner, (DockerCommandRunner, UnsafeLocalCommandRunner)):
        raise ShadowWorkspaceError("runner is not an approved shadow backend")
    if not isinstance(full_test_dir, str):
        raise ShadowWorkspaceError("full test directory is invalid")
    full_test_path = PurePosixPath(full_test_dir)
    if (
        not re.fullmatch(r"[A-Za-z0-9_./-]+", full_test_dir)
        or full_test_path.is_absolute()
        or not full_test_path.parts
        or any(part in {"", ".", ".."} for part in full_test_path.parts)
    ):
        raise ShadowWorkspaceError("full test directory is invalid")

    repository_files = repository.list_files()
    if any(
        path == ".issuelens-tests" or path.startswith(".issuelens-tests/")
        for path in repository_files
    ):
        raise ShadowWorkspaceError(
            "target repository uses the reserved .issuelens-tests namespace"
        )
    for bundle_name, bundle_path in (
        ("reproduction", reproduction_tests),
        ("hidden", hidden_tests),
    ):
        if bundle_path is None:
            continue
        resolved_bundle = Path(bundle_path).expanduser().resolve()
        if (
            resolved_bundle == repository.root
            or repository.root in resolved_bundle.parents
        ):
            raise ShadowWorkspaceError(
                f"{bundle_name} tests must be outside the target repository"
            )

    source_snapshot = repository.snapshot_hash()
    require_patch_application_approval(
        run_id=run_id,
        proposal=proposal,
        approval=approval,
        current_snapshot_hash=source_snapshot,
    )
    commands: list[CommandResult] = []
    targeted_argv = (
        "python",
        "-m",
        "unittest",
        "discover",
        "-s",
        ".issuelens-tests/reproduction",
        "-v",
    )
    full_argv = (
        "python",
        "-m",
        "unittest",
        "discover",
        "-s",
        full_test_dir,
        "-v",
    )
    hidden_argv = (
        "python",
        "-m",
        "unittest",
        "discover",
        "-s",
        ".issuelens-tests/hidden",
        "-v",
    )

    try:
        with TemporaryDirectory(prefix="issuelens-baseline-") as baseline_dir:
            baseline_root = Path(baseline_dir)
            _copy_repository(repository, baseline_root)
            _copy_test_bundle(
                Path(reproduction_tests),
                baseline_root / ".issuelens-tests" / "reproduction",
            )
            commands.append(
                _validate_unittest_execution(
                    runner.run(
                        baseline_root,
                        CommandSpec(
                            name="baseline_reproduction",
                            argv=targeted_argv,
                            expectation="fail",
                            timeout_seconds=timeout_seconds,
                        ),
                    )
                )
            )

        with materialize_approved_patch(
            repository=repository,
            run_id=run_id,
            proposal=proposal,
            approval=approval,
        ) as patched:
            _copy_test_bundle(
                Path(reproduction_tests),
                patched.root / ".issuelens-tests" / "reproduction",
            )
            commands.append(
                _validate_unittest_execution(
                    runner.run(
                        patched.root,
                        CommandSpec(
                            name="patched_reproduction",
                            argv=targeted_argv,
                            expectation="pass",
                            timeout_seconds=timeout_seconds,
                        ),
                    )
                )
            )
            commands.append(
                _validate_unittest_execution(
                    runner.run(
                        patched.root,
                        CommandSpec(
                            name="patched_full_suite",
                            argv=full_argv,
                            expectation="pass",
                            timeout_seconds=timeout_seconds,
                        ),
                    )
                )
            )
            if hidden_tests is not None:
                _copy_test_bundle(
                    Path(hidden_tests),
                    patched.root / ".issuelens-tests" / "hidden",
                )
                commands.append(
                    _validate_unittest_execution(
                        runner.run(
                            patched.root,
                            CommandSpec(
                                name="patched_hidden_suite",
                                argv=hidden_argv,
                                expectation="pass",
                                timeout_seconds=timeout_seconds,
                            ),
                        )
                    )
                )
            patched_snapshot = patched.preview_snapshot_hash
            changed_paths = patched.changed_paths
    except ShadowWorkspaceError:
        raise
    except OSError as exc:
        raise ShadowWorkspaceError("shadow workspace preparation failed") from exc

    final_snapshot = repository.snapshot_hash()
    unchanged = hmac.compare_digest(source_snapshot, final_snapshot)
    return ShadowValidationResult.create(
        run_id=run_id,
        runner=runner.name,
        proposal_hash=proposal.proposal_hash,
        approval_hash=approval.approval_hash,
        base_snapshot_hash=source_snapshot,
        patched_snapshot_hash=patched_snapshot,
        changed_paths=changed_paths,
        commands=tuple(commands),
        repository_unchanged=unchanged,
    )


def render_validation_markdown(result: ShadowValidationResult) -> str:
    if not isinstance(result, ShadowValidationResult) or not result.verify_integrity():
        raise ShadowWorkspaceError("cannot render an invalid validation receipt")
    status = "通过 / Passed" if result.verdict == "passed" else "失败 / Failed"
    isolation = (
        "否，仅可信夹具 / No, trusted fixtures only"
        if result.runner == "unsafe-local"
        else "是，Docker / Yes, Docker"
    )
    lines = [
        f"# IssueLens 隔离验证报告 / Shadow Validation `{result.run_id}`",
        "",
        f"- 状态 / Status: **{status}**",
        f"- 执行后端 / Runner: `{result.runner}`",
        f"- 容器隔离 / Container isolation: **{isolation}**",
        f"- 真实仓库保持不变 / Real repository unchanged: "
        f"`{str(result.repository_unchanged).lower()}`",
        f"- 基础快照 / Base snapshot: `{result.base_snapshot_hash}`",
        f"- 补丁快照 / Patched snapshot: `{result.patched_snapshot_hash}`",
        f"- 提案哈希 / Proposal hash: `{result.proposal_hash}`",
        f"- 审批哈希 / Approval hash: `{result.approval_hash}`",
        f"- 回执哈希 / Receipt hash: `{result.receipt_hash}`",
        "",
        "## 修改范围 / Changed Paths",
        "",
    ]
    lines.extend(f"- `{path}`" for path in result.changed_paths)
    lines.extend(
        [
            "",
            "## 验证阶段 / Validation Stages",
            "",
            "| 阶段 / Stage | 预期 / Expected | 退出码 / Exit | 结果 / Result | 耗时 / Duration |",
            "| --- | --- | ---: | --- | ---: |",
        ]
    )
    for command in result.commands:
        expected = "通过 / Pass" if command.expectation == "pass" else "失败 / Fail"
        outcome = "通过 / Passed" if command.expectation_met else "失败 / Failed"
        exit_code = "timeout" if command.timed_out else str(command.exit_code)
        lines.append(
            f"| `{command.name}` | {expected} | `{exit_code}` | {outcome} | "
            f"{command.duration_ms:.2f} ms |"
        )
    failed = [item for item in result.commands if not item.expectation_met]
    if failed:
        lines.extend(["", "## 失败输出 / Failure Output", ""])
        for command in failed:
            lines.extend(
                [
                    f"### `{command.name}`",
                    "",
                    "```text",
                    (command.stderr_excerpt or command.stdout_excerpt or "<empty>"),
                    "```",
                    "",
                ]
            )
    lines.extend(
        [
            "",
            "## 结论边界 / Interpretation Boundary",
            "",
            "该回执证明指定补丁在记录的执行后端中满足了列出的命令预期，"
            "并且真实目标仓库快照保持不变。",
            "",
            "This receipt proves that the exact patch met the recorded command "
            "expectations in the stated execution backend while the real target "
            "repository snapshot remained unchanged.",
            "",
            "它不认证审批人真实身份，也不代表补丁已写入或合并到目标仓库。",
            "",
            "It does not authenticate the approver's real identity or imply that "
            "the patch was written to or merged into the target repository.",
            "",
        ]
    )
    return "\n".join(lines)


class ValidationAuditStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().absolute()

    def store(self, receipt: ShadowValidationResult) -> Path:
        if not isinstance(receipt, ShadowValidationResult) or not receipt.verify_integrity():
            raise ShadowWorkspaceError("only valid validation receipts can be stored")
        if self.root.is_symlink():
            raise ShadowWorkspaceError("validation audit root cannot be a symlink")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self.root / f"{receipt.receipt_hash}.json"
        serialized = (receipt.to_json() + "\n").encode("utf-8")
        temporary: Path | None = None
        descriptor = -1
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".validation-",
                suffix=".tmp",
                dir=self.root,
            )
            temporary = Path(temporary_name)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError:
                existing = self.load(receipt.receipt_hash)
                if not hmac.compare_digest(existing.to_json(), receipt.to_json()):
                    raise ShadowWorkspaceError("validation receipt hash conflict")
            return target
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def store_report(self, receipt: ShadowValidationResult) -> Path:
        if not isinstance(receipt, ShadowValidationResult) or not receipt.verify_integrity():
            raise ShadowWorkspaceError("cannot store a report for an invalid receipt")
        if self.root.is_symlink():
            raise ShadowWorkspaceError("validation audit root cannot be a symlink")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self.root / f"{receipt.receipt_hash}.md"
        content = render_validation_markdown(receipt)
        try:
            with target.open("x", encoding="utf-8") as stream:
                os.chmod(target, 0o600)
                stream.write(content)
        except FileExistsError:
            if target.is_symlink() or target.read_text(encoding="utf-8") != content:
                raise ShadowWorkspaceError("validation report conflicts with stored content")
        return target

    def load(self, receipt_hash: str) -> ShadowValidationResult:
        _require_sha256(receipt_hash, "receipt_hash")
        if self.root.is_symlink() or not self.root.is_dir():
            raise ShadowWorkspaceError("validation audit root is unavailable")
        target = self.root / f"{receipt_hash}.json"
        try:
            metadata = target.lstat()
        except OSError as exc:
            raise ShadowWorkspaceError("validation receipt was not found safely") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise ShadowWorkspaceError("validation receipt was not found safely")
        if metadata.st_size > _MAX_RECEIPT_BYTES:
            raise ShadowWorkspaceError("validation receipt exceeds the size limit")
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            with os.fdopen(descriptor, "rb") as stream:
                content = stream.read(_MAX_RECEIPT_BYTES + 1)
        except OSError as exc:
            raise ShadowWorkspaceError("validation receipt could not be read safely") from exc
        if len(content) > _MAX_RECEIPT_BYTES:
            raise ShadowWorkspaceError("validation receipt exceeds the size limit")
        try:
            serialized = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ShadowWorkspaceError("validation receipt is not valid UTF-8") from exc
        result = ShadowValidationResult.from_json(serialized)
        if not hmac.compare_digest(result.receipt_hash, receipt_hash):
            raise ShadowWorkspaceError("validation receipt filename mismatch")
        return result


_MAX_RETAINED_OUTPUT = 16_000
_MAX_RECEIPT_BYTES = 2_000_000
_MAX_TEST_FILES = 100
_MAX_TEST_BUNDLE_BYTES = 1_000_000
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_VALIDATION_HASH_DOMAIN = b"issuelens.shadow-validation.v1"
_COMMAND_RESULT_FIELDS = {
    "argv",
    "duration_ms",
    "exit_code",
    "expectation",
    "expectation_met",
    "name",
    "stderr_excerpt",
    "stderr_sha256",
    "stdout_excerpt",
    "stdout_sha256",
    "timed_out",
}
_RECEIPT_FIELDS = {
    "approval_hash",
    "base_snapshot_hash",
    "changed_paths",
    "commands",
    "patched_snapshot_hash",
    "proposal_hash",
    "receipt_hash",
    "repository_unchanged",
    "run_id",
    "runner",
    "schema_version",
    "verdict",
}


def _run_process(
    argv: tuple[str, ...],
    command: CommandSpec,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout_cleanup: tuple[str, ...] | None = None,
) -> CommandResult:
    started = time.perf_counter()
    timed_out = False
    exit_code: int | None
    stdout = b""
    stderr = b""
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=float(command.timeout_seconds),
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        if timeout_cleanup is not None:
            try:
                subprocess.run(
                    timeout_cleanup,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10.0,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
    except FileNotFoundError as exc:
        raise ShadowWorkspaceError(f"shadow runner executable was not found: {argv[0]}") from exc
    duration_ms = round((time.perf_counter() - started) * 1_000, 2)
    expectation_met = (
        not timed_out
        and exit_code is not None
        and (
            (command.expectation == "pass" and exit_code == 0)
            or (command.expectation == "fail" and exit_code != 0)
        )
    )
    return CommandResult(
        name=command.name,
        argv=command.argv,
        expectation=command.expectation,
        exit_code=exit_code,
        timed_out=timed_out,
        duration_ms=duration_ms,
        expectation_met=expectation_met,
        stdout_sha256=hashlib.sha256(stdout).hexdigest(),
        stderr_sha256=hashlib.sha256(stderr).hexdigest(),
        stdout_excerpt=_output_excerpt(stdout),
        stderr_excerpt=_output_excerpt(stderr),
    )


def _copy_repository(repository: ReadOnlyRepository, destination: Path) -> None:
    for relative_path in repository.list_files():
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            repository.read_text(relative_path),
            encoding="utf-8",
            newline="",
        )


def _copy_test_bundle(source: Path, destination: Path) -> None:
    source_input = source.expanduser().absolute()
    if source_input.is_symlink():
        raise ShadowWorkspaceError("test bundle must be a real directory")
    source = source_input.resolve()
    if not source.is_dir():
        raise ShadowWorkspaceError("test bundle must be a real directory")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ShadowWorkspaceError("test bundle cannot contain symlinks")
    files = sorted(source.rglob("*.py"))
    if not files or len(files) > _MAX_TEST_FILES:
        raise ShadowWorkspaceError("test bundle file count is outside the safe range")
    total_bytes = 0
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ShadowWorkspaceError("test bundle cannot contain symlinks")
        relative = path.relative_to(source)
        size = path.stat().st_size
        total_bytes += size
        if total_bytes > _MAX_TEST_BUNDLE_BYTES:
            raise ShadowWorkspaceError("test bundle exceeds the size limit")
        content = path.read_bytes()
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ShadowWorkspaceError("test bundle is not valid UTF-8") from exc
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def _prepare_read_only_mount(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ShadowWorkspaceError("Docker workspace must be a real directory")
    for path in [root, *root.rglob("*")]:
        if path.is_symlink():
            raise ShadowWorkspaceError("Docker workspace cannot contain symlinks")
        if path.is_dir():
            path.chmod(0o755)
        elif path.is_file():
            path.chmod(0o644)


def _output_excerpt(value: bytes) -> str:
    if len(value) <= _MAX_RETAINED_OUTPUT:
        return value.decode("utf-8", errors="replace")
    half = _MAX_RETAINED_OUTPUT // 2
    omitted = len(value) - _MAX_RETAINED_OUTPUT
    return (
        value[:half].decode("utf-8", errors="replace")
        + f"\n... <{omitted} bytes omitted> ...\n"
        + value[-half:].decode("utf-8", errors="replace")
    )


def _validate_unittest_execution(result: CommandResult) -> CommandResult:
    output = f"{result.stdout_excerpt}\n{result.stderr_excerpt}"
    ran_match = re.search(r"\bRan ([0-9]+) tests?\b", output)
    ran_tests = int(ran_match.group(1)) if ran_match else 0
    if result.expectation == "pass":
        structurally_valid = ran_tests > 0 and re.search(r"\bOK\b", output) is not None
    else:
        infrastructure_markers = (
            "Failed to import test module",
            "ModuleNotFoundError",
            "_FailedTest",
        )
        structurally_valid = (
            ran_tests > 0
            and "FAILED (" in output
            and not any(marker in output for marker in infrastructure_markers)
        )
    return replace(
        result,
        expectation_met=result.expectation_met and structurally_valid,
    )


def _validation_payload(
    *,
    run_id: str,
    runner: str,
    proposal_hash: str,
    approval_hash: str,
    base_snapshot_hash: str,
    patched_snapshot_hash: str,
    changed_paths: tuple[str, ...],
    commands: tuple[CommandResult, ...],
    repository_unchanged: bool,
    verdict: str,
) -> dict[str, object]:
    return {
        "approval_hash": approval_hash,
        "base_snapshot_hash": base_snapshot_hash,
        "changed_paths": list(changed_paths),
        "commands": [command.to_dict() for command in commands],
        "patched_snapshot_hash": patched_snapshot_hash,
        "proposal_hash": proposal_hash,
        "repository_unchanged": repository_unchanged,
        "run_id": run_id,
        "runner": runner,
        "schema_version": 1,
        "verdict": verdict,
    }


def _payload_hash(payload: dict[str, object]) -> str:
    digest = hashlib.sha256()
    digest.update(_VALIDATION_HASH_DOMAIN)
    digest.update(b"\0")
    digest.update(_canonical_json(payload).encode("utf-8"))
    return digest.hexdigest()


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ShadowWorkspaceError(f"{name} must be non-empty text")


def _require_sha256(value: object, name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ShadowWorkspaceError(f"{name} must be a lowercase SHA-256 digest")


def _validate_command_result(result: CommandResult) -> None:
    if not isinstance(result, CommandResult):
        raise ShadowWorkspaceError("commands must contain CommandResult values")
    CommandSpec(
        name=result.name,
        argv=result.argv,
        expectation=result.expectation,
        timeout_seconds=60.0,
    )
    if result.exit_code is not None and type(result.exit_code) is not int:
        raise ShadowWorkspaceError("command exit_code is invalid")
    if type(result.timed_out) is not bool or type(result.expectation_met) is not bool:
        raise ShadowWorkspaceError("command boolean fields are invalid")
    basic_expectation_met = (
        not result.timed_out
        and result.exit_code is not None
        and (
            (result.expectation == "pass" and result.exit_code == 0)
            or (result.expectation == "fail" and result.exit_code != 0)
        )
    )
    if result.expectation_met and not basic_expectation_met:
        raise ShadowWorkspaceError("command expectation result is inconsistent")
    if (
        isinstance(result.duration_ms, bool)
        or not isinstance(result.duration_ms, (int, float))
        or not math.isfinite(float(result.duration_ms))
        or result.duration_ms < 0
    ):
        raise ShadowWorkspaceError("command duration is invalid")
    _require_sha256(result.stdout_sha256, "stdout_sha256")
    _require_sha256(result.stderr_sha256, "stderr_sha256")
    if not isinstance(result.stdout_excerpt, str) or not isinstance(
        result.stderr_excerpt, str
    ):
        raise ShadowWorkspaceError("command excerpts must be text")
    if (
        len(result.stdout_excerpt.encode("utf-8")) > _MAX_RETAINED_OUTPUT * 4
        or len(result.stderr_excerpt.encode("utf-8")) > _MAX_RETAINED_OUTPUT * 4
    ):
        raise ShadowWorkspaceError("command excerpts exceed the size limit")
