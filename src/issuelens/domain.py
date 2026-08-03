from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class RunState(str, Enum):
    CREATED = "created"
    ISSUE_PARSED = "issue_parsed"
    REPO_SNAPSHOTTED = "repo_snapshotted"
    INDEX_BUILT = "index_built"
    EVIDENCE_RETRIEVED = "evidence_retrieved"
    PLAN_CREATED = "plan_created"
    REPO_VERIFIED = "repo_verified"
    FINISHED = "finished"
    FAILED = "failed"


@dataclass(frozen=True)
class IssueSpec:
    title: str
    body: str
    identifiers: tuple[str, ...] = ()
    file_hints: tuple[str, ...] = ()
    exception_hints: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    path: str
    start_line: int
    end_line: int
    snippet: str
    reason: str
    content_hash: str
    score: float


@dataclass(frozen=True)
class PlanStep:
    order: int
    action: str
    rationale: str
    evidence_ids: tuple[str, ...] = ()


@dataclass
class AnalysisReport:
    run_id: str
    status: str
    repo_root: str
    repo_snapshot_before: str
    repo_snapshot_after: str
    repository_unchanged: bool
    issue: IssueSpec
    candidate_files: list[str]
    evidence: list[Evidence]
    diagnosis: str
    plan: list[PlanStep]
    proposed_tests: list[str]
    risks: list[str]
    acceptance_criteria: list[str]
    state_history: list[str]
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TraceEvent:
    sequence: int
    state: str
    event: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
