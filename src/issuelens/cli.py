from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import stat
from pathlib import Path
from typing import Sequence

from .agent_loop import AgentLoopWorkflow, OfflineToolPolicy, OpenAICompatiblePolicy
from .approval import PatchApproval, PatchApprovalError
from .approval_gate import PatchApplicationBlockedError
from .audit_report import AuditReportError, render_preflight_report
from .audit_store import ReceiptAuditStore, ReceiptAuditStoreError
from .diff_parser import UnifiedDiff, UnifiedDiffParseError, parse_unified_diff
from .diff_policy import DiffPathPolicyError
from .draft_pr import DraftPrError, render_draft_pr_body
from .evaluation import evaluate_manifest
from .issue_parser import MAX_ISSUE_BYTES
from .patch_preflight import PatchPreflightError
from .patch_proposal import PatchProposal, PatchProposalError
from .patch_review import PatchReviewError, preflight_and_record_patch
from .repository import ReadOnlyRepository, RepositoryAccessError
from .shadow_workspace import (
    DEFAULT_DOCKER_IMAGE,
    DockerCommandRunner,
    ShadowWorkspaceError,
    ShadowValidationResult,
    UnsafeLocalCommandRunner,
    ValidationAuditStore,
    validate_approved_patch,
)
from .workflow import IssueAnalysisWorkflow
from .web_ui import WebUiError, create_dashboard_server


_MAX_DIFF_FILE_BYTES = 2_000_000
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class CliInputError(ValueError):
    """Raised when a bounded CLI input cannot be read safely."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="issuelens",
        description="Evidence-grounded analysis for Python repository issues.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze one repository issue.")
    analyze.add_argument("--repo", required=True, help="Path to a local repository.")
    analyze.add_argument("--issue", required=True, help="Path to an issue Markdown file.")
    analyze.add_argument(
        "--run-dir",
        default="runs",
        help="Directory for reports and traces; must be outside the target repository.",
    )
    analyze.add_argument("--run-id", help="Optional stable run identifier.")

    agent = subparsers.add_parser(
        "agent",
        help="Run the bounded tool-calling Agent loop.",
    )
    agent.add_argument("--repo", required=True, help="Path to a local repository.")
    agent.add_argument("--issue", required=True, help="Path to an issue Markdown file.")
    agent.add_argument("--run-dir", default="runs", help="External artifact directory.")
    agent.add_argument("--run-id", help="Optional stable run identifier.")
    agent.add_argument(
        "--policy",
        choices=("offline", "llm"),
        default="offline",
        help="Offline exercises the harness; llm calls a structured chat endpoint.",
    )
    agent.add_argument("--endpoint", help="OpenAI-compatible chat completions endpoint.")
    agent.add_argument("--model", help="Model name for --policy llm.")
    agent.add_argument("--max-steps", type=int, default=8)
    agent.add_argument("--max-tool-calls", type=int, default=8)
    agent.add_argument("--max-evidence", type=int, default=100)
    agent.add_argument("--max-elapsed-seconds", type=float, default=120.0)
    agent.add_argument("--max-retries", type=int, default=2)
    agent.add_argument(
        "--resume",
        action="store_true",
        help="Resume an incomplete run from its integrity-protected checkpoint.",
    )

    evaluate = subparsers.add_parser("eval", help="Run the local evaluation manifest.")
    evaluate.add_argument("--manifest", required=True, help="Path to eval manifest JSON.")
    evaluate.add_argument("--run-dir", default="runs/eval", help="Evaluation output path.")

    audit_report = subparsers.add_parser(
        "audit-report",
        help="Render a verified bilingual Markdown audit report.",
    )
    audit_report.add_argument(
        "--audit-dir",
        required=True,
        help="Path to the content-addressed receipt audit store.",
    )
    audit_report.add_argument(
        "--receipt-hash",
        required=True,
        help="Lowercase SHA-256 hash of the stored receipt.",
    )

    patch_proposal = subparsers.add_parser(
        "patch-proposal",
        help="Inspect a repository-bound Unified Diff proposal.",
    )
    patch_proposal.add_argument(
        "--repo",
        required=True,
        help="Path to the local repository.",
    )
    patch_proposal.add_argument(
        "--diff",
        required=True,
        help="Path to a bounded UTF-8 Unified Diff file.",
    )

    patch_review = subparsers.add_parser(
        "patch-review",
        help="Approve, preflight, and record an exact patch proposal.",
    )
    patch_review.add_argument(
        "--repo",
        required=True,
        help="Path to the local repository.",
    )
    patch_review.add_argument(
        "--diff",
        required=True,
        help="Path to the bounded UTF-8 Unified Diff file.",
    )
    patch_review.add_argument(
        "--run-id",
        required=True,
        help="Stable identifier for this review run.",
    )
    patch_review.add_argument(
        "--approved-by",
        required=True,
        help="Declared identity of the human approver.",
    )
    patch_review.add_argument(
        "--approve-proposal-hash",
        required=True,
        help="Exact Proposal Hash previously shown to the approver.",
    )
    patch_review.add_argument(
        "--audit-dir",
        required=True,
        help="Content-addressed audit directory outside the repository.",
    )

    patch_validate = subparsers.add_parser(
        "patch-validate",
        help="Validate an approved patch in an isolated shadow workspace.",
    )
    patch_validate.add_argument("--repo", required=True)
    patch_validate.add_argument("--diff", required=True)
    patch_validate.add_argument("--run-id", required=True)
    patch_validate.add_argument("--approved-by", required=True)
    patch_validate.add_argument("--approve-proposal-hash", required=True)
    patch_validate.add_argument("--audit-dir", required=True)
    patch_validate.add_argument("--reproduction-tests", required=True)
    patch_validate.add_argument("--hidden-tests")
    patch_validate.add_argument("--full-test-dir", default="tests")
    patch_validate.add_argument("--timeout-seconds", type=float, default=60.0)
    patch_validate.add_argument(
        "--runner",
        choices=("docker", "local"),
        default="docker",
        help="Docker is the safe default; local is only for trusted fixtures.",
    )
    patch_validate.add_argument(
        "--docker-image",
        default=DEFAULT_DOCKER_IMAGE,
        help="Pre-pulled Docker image; validation never pulls implicitly.",
    )
    patch_validate.add_argument(
        "--allow-unsafe-local",
        action="store_true",
        help="Explicitly allow host execution for trusted fixtures only.",
    )

    draft_pr = subparsers.add_parser(
        "draft-pr",
        help="Export bilingual Draft PR Markdown without publishing it.",
    )
    draft_pr.add_argument("--repo", required=True)
    draft_pr.add_argument("--report", required=True)
    draft_pr.add_argument("--diff", required=True)
    draft_pr.add_argument("--output", required=True)
    draft_pr.add_argument("--validation-receipt")

    serve = subparsers.add_parser(
        "serve",
        help="Serve the token-protected local review dashboard on 127.0.0.1.",
    )
    serve.add_argument("--run-dir", default="runs")
    serve.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "analyze":
        repo = Path(args.repo).expanduser().resolve()
        issue_path = Path(args.issue).expanduser().absolute()
        run_dir = Path(args.run_dir).expanduser().resolve()
        if run_dir == repo or repo in run_dir.parents:
            raise SystemExit("--run-dir must be outside the target repository")
        report = IssueAnalysisWorkflow().run(
            repo_path=repo,
            issue_text=_read_bounded_utf8(
                issue_path.expanduser().absolute(),
                max_bytes=MAX_ISSUE_BYTES,
            ),
            run_dir=run_dir,
            run_id=args.run_id,
        )
        print(
            json.dumps(
                {
                    "run_id": report.run_id,
                    "status": report.status,
                    "candidate_files": report.candidate_files,
                    "repository_unchanged": report.repository_unchanged,
                    "report": str(run_dir / report.run_id / "report.md"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "agent":
        repo = Path(args.repo).expanduser().resolve()
        issue_path = Path(args.issue).expanduser().absolute()
        run_dir = Path(args.run_dir).expanduser().resolve()
        if run_dir == repo or repo in run_dir.parents:
            raise SystemExit("--run-dir must be outside the target repository")
        if args.resume and not args.run_id:
            raise SystemExit("--resume requires --run-id")
        if args.policy == "llm":
            if not args.endpoint or not args.model:
                raise SystemExit("--endpoint and --model are required for --policy llm")
            policy = OpenAICompatiblePolicy(
                endpoint=args.endpoint,
                model=args.model,
                max_retries=args.max_retries,
            )
        else:
            policy = OfflineToolPolicy()
        report = AgentLoopWorkflow().run(
            repo_path=repo,
            issue_text=_read_bounded_utf8(
                issue_path.expanduser().absolute(),
                max_bytes=MAX_ISSUE_BYTES,
            ),
            run_dir=run_dir,
            policy=policy,
            run_id=args.run_id,
            max_steps=args.max_steps,
            max_tool_calls=args.max_tool_calls,
            max_evidence=args.max_evidence,
            max_elapsed_seconds=args.max_elapsed_seconds,
            resume=args.resume,
        )
        print(
            json.dumps(
                {
                    "run_id": report.run_id,
                    "status": report.status,
                    "candidate_files": report.candidate_files,
                    "tool_call_count": report.metrics["tool_call_count"],
                    "repository_unchanged": report.repository_unchanged,
                    "report": str(run_dir / report.run_id / "report.md"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "eval":
        summary = evaluate_manifest(args.manifest, args.run_dir)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.command == "audit-report":
        audit_store = ReceiptAuditStore(
            Path(args.audit_dir).expanduser()
        )
        try:
            receipt = audit_store.load(args.receipt_hash)
            report = render_preflight_report(receipt)
        except (ReceiptAuditStoreError, AuditReportError) as exc:
            raise SystemExit(f"audit-report failed: {exc}") from exc
        print(report, end="")
        return 0

    if args.command == "patch-proposal":
        try:
            repository, proposal, parsed = _load_patch_proposal(
                repo_path=Path(args.repo),
                diff_path=Path(args.diff),
            )
        except (
            CliInputError,
            DiffPathPolicyError,
            OSError,
            PatchProposalError,
            RepositoryAccessError,
            UnifiedDiffParseError,
        ) as exc:
            raise SystemExit(f"patch-proposal failed: {exc}") from exc

        added_lines = sum(
            hunk.added_line_count
            for file_patch in parsed.files
            for hunk in file_patch.hunks
        )
        removed_lines = sum(
            hunk.removed_line_count
            for file_patch in parsed.files
            for hunk in file_patch.hunks
        )
        print(
            json.dumps(
                {
                    "added_lines": added_lines,
                    "base_snapshot_hash": proposal.base_snapshot_hash,
                    "changed_file_count": parsed.changed_file_count,
                    "changed_paths": proposal.changed_paths,
                    "proposal_hash": proposal.proposal_hash,
                    "removed_lines": removed_lines,
                    "repository_unchanged": True,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "patch-review":
        try:
            repository, proposal, _ = _load_patch_proposal(
                repo_path=Path(args.repo),
                diff_path=Path(args.diff),
            )
            approved_hash = _require_lowercase_sha256(
                args.approve_proposal_hash,
                field_name="approved Proposal Hash",
            )
            if not hmac.compare_digest(
                proposal.proposal_hash,
                approved_hash,
            ):
                raise CliInputError(
                    "approved Proposal Hash does not match the current proposal"
                )

            audit_dir_input = Path(args.audit_dir).expanduser().absolute()
            if audit_dir_input.is_symlink():
                raise CliInputError(
                    "audit directory cannot be a symbolic link"
                )
            audit_dir = audit_dir_input.resolve()
            if (
                audit_dir == repository.root
                or repository.root in audit_dir.parents
            ):
                raise CliInputError(
                    "audit directory must be outside the target repository"
                )

            approval = PatchApproval.create(
                run_id=args.run_id,
                proposal=proposal,
                approved_by=args.approved_by,
            )
            recorded = preflight_and_record_patch(
                repository=repository,
                audit_store=ReceiptAuditStore(audit_dir),
                run_id=args.run_id,
                proposal=proposal,
                approval=approval,
            )
            final_snapshot = repository.snapshot_hash()
            if not hmac.compare_digest(
                final_snapshot,
                proposal.base_snapshot_hash,
            ):
                raise PatchReviewError(
                    "repository changed before the review result was emitted"
                )
        except (
            CliInputError,
            DiffPathPolicyError,
            OSError,
            PatchApplicationBlockedError,
            PatchApprovalError,
            PatchPreflightError,
            PatchProposalError,
            PatchReviewError,
            ReceiptAuditStoreError,
            RepositoryAccessError,
            UnifiedDiffParseError,
        ) as exc:
            raise SystemExit(f"patch-review failed: {exc}") from exc

        print(
            json.dumps(
                {
                    "approval_hash": approval.approval_hash,
                    "audit_path": str(recorded.audit_path),
                    "base_snapshot_hash": proposal.base_snapshot_hash,
                    "preview_snapshot_hash": (
                        recorded.receipt.preview_snapshot_hash
                    ),
                    "proposal_hash": proposal.proposal_hash,
                    "receipt_hash": recorded.receipt.receipt_hash,
                    "repository_unchanged": True,
                    "run_id": recorded.receipt.run_id,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "patch-validate":
        try:
            repository, proposal, _ = _load_patch_proposal(
                repo_path=Path(args.repo),
                diff_path=Path(args.diff),
            )
            approved_hash = _require_lowercase_sha256(
                args.approve_proposal_hash,
                field_name="approved Proposal Hash",
            )
            if not hmac.compare_digest(proposal.proposal_hash, approved_hash):
                raise CliInputError(
                    "approved Proposal Hash does not match the current proposal"
                )
            reproduction_tests = _require_external_test_directory(
                Path(args.reproduction_tests),
                repository=repository,
                field_name="reproduction tests",
            )
            hidden_tests = (
                _require_external_test_directory(
                    Path(args.hidden_tests),
                    repository=repository,
                    field_name="hidden tests",
                )
                if args.hidden_tests
                else None
            )
            audit_dir = _require_external_output_directory(
                Path(args.audit_dir),
                repository=repository,
                field_name="validation audit directory",
            )
            if args.runner == "local":
                if not args.allow_unsafe_local:
                    raise CliInputError(
                        "--runner local requires --allow-unsafe-local"
                    )
                runner = UnsafeLocalCommandRunner()
            else:
                runner = DockerCommandRunner(image=args.docker_image)
            approval = PatchApproval.create(
                run_id=args.run_id,
                proposal=proposal,
                approved_by=args.approved_by,
            )
            result = validate_approved_patch(
                repository=repository,
                run_id=args.run_id,
                proposal=proposal,
                approval=approval,
                runner=runner,
                reproduction_tests=reproduction_tests,
                hidden_tests=hidden_tests,
                full_test_dir=args.full_test_dir,
                timeout_seconds=args.timeout_seconds,
            )
            store = ValidationAuditStore(audit_dir)
            audit_path = store.store(result)
            report_path = store.store_report(result)
        except (
            CliInputError,
            DiffPathPolicyError,
            OSError,
            PatchApplicationBlockedError,
            PatchApprovalError,
            PatchPreflightError,
            PatchProposalError,
            RepositoryAccessError,
            ShadowWorkspaceError,
            UnifiedDiffParseError,
        ) as exc:
            raise SystemExit(f"patch-validate failed: {exc}") from exc

        print(
            json.dumps(
                {
                    "audit_path": str(audit_path),
                    "command_results": [
                        {
                            "expectation_met": item.expectation_met,
                            "exit_code": item.exit_code,
                            "name": item.name,
                            "timed_out": item.timed_out,
                        }
                        for item in result.commands
                    ],
                    "receipt_hash": result.receipt_hash,
                    "report_path": str(report_path),
                    "repository_unchanged": result.repository_unchanged,
                    "run_id": result.run_id,
                    "runner": result.runner,
                    "verdict": result.verdict,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if result.verdict == "passed" else 1

    if args.command == "draft-pr":
        try:
            repository, proposal, _ = _load_patch_proposal(
                repo_path=Path(args.repo),
                diff_path=Path(args.diff),
            )
            report_text = _read_bounded_utf8(
                Path(args.report).expanduser().absolute(),
                max_bytes=2_000_000,
            )
            report = json.loads(report_text)
            if not isinstance(report, dict):
                raise DraftPrError("analysis report must be a JSON object")
            if report.get("repo_snapshot_before") != repository.snapshot_hash():
                raise DraftPrError(
                    "target repository no longer matches the analysis snapshot"
                )
            validation = (
                ShadowValidationResult.from_json(
                    _read_bounded_utf8(
                        Path(args.validation_receipt).expanduser().absolute(),
                        max_bytes=2_000_000,
                    )
                )
                if args.validation_receipt
                else None
            )
            body = render_draft_pr_body(
                report=report,
                proposal=proposal,
                validation=validation,
            )
            output = _require_external_output_file(
                Path(args.output),
                repository=repository,
                field_name="Draft PR output",
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as stream:
                stream.write(body)
        except (
            CliInputError,
            DiffPathPolicyError,
            DraftPrError,
            FileExistsError,
            json.JSONDecodeError,
            OSError,
            PatchProposalError,
            RepositoryAccessError,
            ShadowWorkspaceError,
            UnifiedDiffParseError,
        ) as exc:
            raise SystemExit(f"draft-pr failed: {exc}") from exc
        print(
            json.dumps(
                {
                    "output": str(output),
                    "proposal_hash": proposal.proposal_hash,
                    "published": False,
                    "validation": (
                        validation.verdict if validation is not None else "not_run"
                    ),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "serve":
        try:
            server, token = create_dashboard_server(
                run_dir=Path(args.run_dir),
                port=args.port,
            )
        except (OSError, WebUiError) as exc:
            raise SystemExit(f"serve failed: {exc}") from exc
        host, port = server.server_address
        print(
            json.dumps(
                {
                    "bind": f"{host}:{port}",
                    "url": f"http://{host}:{port}/?token={token}",
                    "warning": (
                        "Local review decisions are not patch-hash approvals. / "
                        "本地审查决定不等同于补丁哈希审批。"
                    ),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    return 2


def _read_bounded_utf8(path: Path, *, max_bytes: int) -> str:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CliInputError(f"Input file does not exist safely: {path}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise CliInputError("Input file cannot be a symbolic link")
    if not stat.S_ISREG(metadata.st_mode):
        raise CliInputError(f"Input file is not regular: {path}")
    if metadata.st_size > max_bytes:
        raise CliInputError("Input file exceeds the maximum size")
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            content = stream.read(max_bytes + 1)
    except OSError as exc:
        raise CliInputError("Input file could not be read safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(content) > max_bytes:
        raise CliInputError("Input file exceeds the maximum size")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CliInputError("Input file is not valid UTF-8") from exc


def _load_patch_proposal(
    *,
    repo_path: Path,
    diff_path: Path,
) -> tuple[ReadOnlyRepository, PatchProposal, UnifiedDiff]:
    repository = ReadOnlyRepository(
        repo_path.expanduser().resolve()
    )
    before_snapshot = repository.snapshot_hash()
    diff_text = _read_bounded_utf8(
        diff_path.expanduser().absolute(),
        max_bytes=_MAX_DIFF_FILE_BYTES,
    )
    proposal = PatchProposal.create(
        unified_diff=diff_text,
        base_snapshot_hash=before_snapshot,
    )
    parsed = parse_unified_diff(proposal.unified_diff)
    after_snapshot = repository.snapshot_hash()
    if not hmac.compare_digest(before_snapshot, after_snapshot):
        raise CliInputError(
            "repository changed during proposal inspection"
        )
    return repository, proposal, parsed


def _require_lowercase_sha256(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise CliInputError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )
    return value


def _require_external_test_directory(
    path: Path,
    *,
    repository: ReadOnlyRepository,
    field_name: str,
) -> Path:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink():
        raise CliInputError(f"{field_name} cannot be a symbolic link")
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise CliInputError(f"{field_name} must be an existing directory")
    if resolved == repository.root or repository.root in resolved.parents:
        raise CliInputError(f"{field_name} must be outside the target repository")
    return resolved


def _require_external_output_directory(
    path: Path,
    *,
    repository: ReadOnlyRepository,
    field_name: str,
) -> Path:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink():
        raise CliInputError(f"{field_name} cannot be a symbolic link")
    resolved = candidate.resolve()
    if resolved == repository.root or repository.root in resolved.parents:
        raise CliInputError(f"{field_name} must be outside the target repository")
    return resolved


def _require_external_output_file(
    path: Path,
    *,
    repository: ReadOnlyRepository,
    field_name: str,
) -> Path:
    candidate = path.expanduser().absolute()
    if candidate.is_symlink():
        raise CliInputError(f"{field_name} cannot be a symbolic link")
    resolved = candidate.resolve()
    if resolved == repository.root or repository.root in resolved.parents:
        raise CliInputError(f"{field_name} must be outside the target repository")
    return resolved
