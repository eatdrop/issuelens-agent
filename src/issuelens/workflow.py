from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from .domain import AnalysisReport, RunState, TraceEvent
from .issue_parser import parse_issue
from .reasoner import DeterministicReasoner
from .reporting import RunArtifacts
from .repository import ReadOnlyRepository
from .state_machine import StateMachine


class IssueAnalysisWorkflow:
    def __init__(self, reasoner: DeterministicReasoner | None = None) -> None:
        self.reasoner = reasoner or DeterministicReasoner()

    def run(
        self,
        *,
        repo_path: str | Path,
        issue_text: str,
        run_dir: str | Path,
        run_id: str | None = None,
    ) -> AnalysisReport:
        started = time.perf_counter()
        run_id = run_id or _new_run_id()
        artifacts = RunArtifacts(run_dir, run_id)
        machine = StateMachine()
        sequence = 0

        def record(event: str, details: dict[str, Any] | None = None) -> None:
            nonlocal sequence
            sequence += 1
            artifacts.append_trace(
                TraceEvent(
                    sequence=sequence,
                    state=machine.current.value,
                    event=event,
                    details=details or {},
                )
            )

        record("run_created")
        repository = ReadOnlyRepository(repo_path)
        try:
            issue = parse_issue(issue_text)
            machine.transition(RunState.ISSUE_PARSED)
            record(
                "issue_parsed",
                {
                    "title": issue.title,
                    "identifiers": list(issue.identifiers),
                    "file_hints": list(issue.file_hints),
                },
            )

            snapshot_before = repository.snapshot_hash()
            machine.transition(RunState.REPO_SNAPSHOTTED)
            record(
                "repository_snapshotted",
                {
                    "snapshot": snapshot_before,
                    "readable_files": len(repository.list_files()),
                },
            )

            symbols = repository.build_symbol_index()
            machine.transition(RunState.INDEX_BUILT)
            record("symbol_index_built", {"symbol_count": len(symbols)})

            evidence = self.reasoner.retrieve(issue, repository, symbols)
            machine.transition(RunState.EVIDENCE_RETRIEVED)
            record(
                "evidence_retrieved",
                {
                    "evidence_count": len(evidence),
                    "files": sorted({item.path for item in evidence}),
                },
            )

            (
                candidate_files,
                diagnosis,
                plan,
                proposed_tests,
                risks,
                acceptance_criteria,
            ) = self.reasoner.build_analysis(issue, evidence)
            machine.transition(RunState.PLAN_CREATED)
            record(
                "plan_created",
                {
                    "candidate_files": candidate_files,
                    "plan_steps": len(plan),
                    "status": (
                        "insufficient_evidence"
                        if diagnosis.startswith("insufficient_evidence")
                        else "ready_for_human_review"
                    ),
                },
            )

            snapshot_after = repository.snapshot_hash()
            unchanged = snapshot_before == snapshot_after
            if not unchanged:
                raise RuntimeError("target repository changed during read-only analysis")
            machine.transition(RunState.REPO_VERIFIED)
            record("repository_verified", {"unchanged": unchanged})
            machine.transition(RunState.FINISHED)
            record("run_finished")

            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            cited_steps = sum(1 for step in plan if step.evidence_ids)
            report = AnalysisReport(
                run_id=run_id,
                status=(
                    "insufficient_evidence"
                    if diagnosis.startswith("insufficient_evidence")
                    else "ready_for_human_review"
                ),
                repo_root=str(repository.root),
                repo_snapshot_before=snapshot_before,
                repo_snapshot_after=snapshot_after,
                repository_unchanged=unchanged,
                issue=issue,
                candidate_files=candidate_files,
                evidence=evidence,
                diagnosis=diagnosis,
                plan=plan,
                proposed_tests=proposed_tests,
                risks=risks,
                acceptance_criteria=acceptance_criteria,
                state_history=[state.value for state in machine.history],
                metrics={
                    "elapsed_ms": elapsed_ms,
                    "readable_file_count": len(repository.list_files()),
                    "symbol_count": len(symbols),
                    "evidence_count": len(evidence),
                    "candidate_file_count": len(candidate_files),
                    "plan_evidence_coverage": (
                        round(cited_steps / len(plan), 4) if plan else 0.0
                    ),
                    "target_repo_write_count": 0,
                },
            )
            artifacts.write_report(report)
            return report
        except Exception as exc:
            machine.fail()
            record("run_failed", {"error_type": type(exc).__name__, "message": str(exc)})
            raise


def _new_run_id() -> str:
    return f"run-{int(time.time())}-{uuid.uuid4().hex[:8]}"
