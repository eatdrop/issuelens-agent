from __future__ import annotations

import argparse
import hmac
import json
import re
from pathlib import Path
from typing import Sequence

from .agent_loop import AgentLoopWorkflow, OfflineToolPolicy, OpenAICompatiblePolicy
from .approval import PatchApproval, PatchApprovalError
from .approval_gate import PatchApplicationBlockedError
from .audit_report import AuditReportError, render_preflight_report
from .audit_store import ReceiptAuditStore, ReceiptAuditStoreError
from .diff_parser import UnifiedDiff, UnifiedDiffParseError, parse_unified_diff
from .diff_policy import DiffPathPolicyError
from .evaluation import evaluate_manifest
from .patch_preflight import PatchPreflightError
from .patch_proposal import PatchProposal, PatchProposalError
from .patch_review import PatchReviewError, preflight_and_record_patch
from .repository import ReadOnlyRepository, RepositoryAccessError
from .workflow import IssueAnalysisWorkflow


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "analyze":
        repo = Path(args.repo).expanduser().resolve()
        issue_path = Path(args.issue).expanduser().resolve()
        run_dir = Path(args.run_dir).expanduser().resolve()
        if run_dir == repo or repo in run_dir.parents:
            raise SystemExit("--run-dir must be outside the target repository")
        report = IssueAnalysisWorkflow().run(
            repo_path=repo,
            issue_text=issue_path.read_text(encoding="utf-8"),
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
        issue_path = Path(args.issue).expanduser().resolve()
        run_dir = Path(args.run_dir).expanduser().resolve()
        if run_dir == repo or repo in run_dir.parents:
            raise SystemExit("--run-dir must be outside the target repository")
        if args.policy == "llm":
            if not args.endpoint or not args.model:
                raise SystemExit("--endpoint and --model are required for --policy llm")
            policy = OpenAICompatiblePolicy(
                endpoint=args.endpoint,
                model=args.model,
            )
        else:
            policy = OfflineToolPolicy()
        report = AgentLoopWorkflow().run(
            repo_path=repo,
            issue_text=issue_path.read_text(encoding="utf-8"),
            run_dir=run_dir,
            policy=policy,
            run_id=args.run_id,
            max_steps=args.max_steps,
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
    return 2


def _read_bounded_utf8(path: Path, *, max_bytes: int) -> str:
    if path.is_symlink():
        raise CliInputError("Diff file cannot be a symbolic link")
    if not path.is_file():
        raise CliInputError(f"Diff file does not exist: {path}")
    if path.stat().st_size > max_bytes:
        raise CliInputError("Diff file exceeds the maximum size")
    content = path.read_bytes()
    if len(content) > max_bytes:
        raise CliInputError("Diff file exceeds the maximum size")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CliInputError("Diff file is not valid UTF-8") from exc


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
        diff_path.expanduser().resolve(),
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
