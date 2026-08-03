from __future__ import annotations

import json
import statistics
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .evaluation_report import render_evaluation_report
from .workflow import IssueAnalysisWorkflow


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    gold_files: tuple[str, ...]
    candidates: tuple[str, ...]
    expected_status: str
    actual_status: str
    status_match: bool
    hit_at_1: float | None
    recall_at_3: float | None
    reciprocal_rank: float | None
    repository_unchanged: bool
    plan_evidence_coverage: float
    elapsed_ms: float


def evaluate_manifest(
    manifest_path: str | Path,
    run_dir: str | Path,
) -> dict[str, Any]:
    manifest_file = Path(manifest_path).expanduser().resolve()
    base = manifest_file.parent
    payload = json.loads(manifest_file.read_text(encoding="utf-8"))
    workflow = IssueAnalysisWorkflow()
    results: list[CaseResult] = []

    for raw_case in payload["cases"]:
        repo = (base / raw_case["repo"]).resolve()
        issue_path = (base / raw_case["issue"]).resolve()
        report = workflow.run(
            repo_path=repo,
            issue_text=issue_path.read_text(encoding="utf-8"),
            run_dir=run_dir,
            run_id=f"eval-{raw_case['id']}-{uuid.uuid4().hex[:8]}",
        )
        gold_files = tuple(raw_case["gold_files"])
        candidates = tuple(report.candidate_files)
        expected_status = raw_case.get("expected_status", "ready_for_human_review")
        gold_set = set(gold_files)
        top_three = set(candidates[:3])
        recall_at_3 = len(gold_set & top_three) / len(gold_set) if gold_set else None
        rank = next(
            (index for index, path in enumerate(candidates, start=1) if path in gold_set),
            None,
        )
        results.append(
            CaseResult(
                case_id=raw_case["id"],
                gold_files=gold_files,
                candidates=candidates,
                expected_status=expected_status,
                actual_status=report.status,
                status_match=report.status == expected_status,
                hit_at_1=(
                    float(bool(candidates and candidates[0] in gold_set))
                    if gold_set
                    else None
                ),
                recall_at_3=round(recall_at_3, 4) if recall_at_3 is not None else None,
                reciprocal_rank=(
                    round(1.0 / rank, 4) if rank else (0.0 if gold_set else None)
                ),
                repository_unchanged=report.repository_unchanged,
                plan_evidence_coverage=float(
                    report.metrics.get("plan_evidence_coverage", 0.0)
                ),
                elapsed_ms=float(report.metrics.get("elapsed_ms", 0.0)),
            )
        )

    summary = {
        "case_count": len(results),
        "hit_at_1": _mean(item.hit_at_1 for item in results),
        "gold_file_recall_at_3": _mean(item.recall_at_3 for item in results),
        "mean_reciprocal_rank": _mean(item.reciprocal_rank for item in results),
        "status_accuracy": _mean(float(item.status_match) for item in results),
        "safe_abstention_rate": _mean(
            float(item.status_match)
            for item in results
            if item.expected_status == "insufficient_evidence"
        ),
        "repository_unchanged_rate": _mean(
            float(item.repository_unchanged) for item in results
        ),
        "plan_evidence_coverage": _mean(
            item.plan_evidence_coverage
            for item in results
            if item.actual_status == "ready_for_human_review"
        ),
        "median_elapsed_ms": (
            round(statistics.median(item.elapsed_ms for item in results), 2)
            if results
            else 0.0
        ),
        "cases": [asdict(item) for item in results],
    }
    output = Path(run_dir).expanduser().resolve() / "evaluation-summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_output = output.with_suffix(".md")
    markdown_output.write_text(
        render_evaluation_report(summary),
        encoding="utf-8",
    )
    return summary


def _mean(values: Any) -> float:
    materialized = [value for value in values if value is not None]
    return round(sum(materialized) / len(materialized), 4) if materialized else 0.0
