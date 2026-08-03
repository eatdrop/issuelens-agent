from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .domain import AnalysisReport, TraceEvent


class RunArtifacts:
    def __init__(self, run_dir: str | Path, run_id: str) -> None:
        self.path = Path(run_dir).expanduser().resolve() / run_id
        self.path.mkdir(parents=True, exist_ok=False)
        self.trace_path = self.path / "trace.jsonl"

    def append_trace(self, event: TraceEvent) -> None:
        with self.trace_path.open("a", encoding="utf-8") as stream:
            json.dump(event.to_dict(), stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")

    def write_report(self, report: AnalysisReport) -> None:
        with (self.path / "report.json").open("w", encoding="utf-8") as stream:
            json.dump(
                report.to_dict(),
                stream,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            stream.write("\n")
        (self.path / "report.md").write_text(
            render_markdown(report),
            encoding="utf-8",
        )


def render_markdown(report: AnalysisReport) -> str:
    issue = report.issue
    lines = [
        f"# IssueLens 运行报告 / Run `{report.run_id}`",
        "",
        f"- 状态 / Status: `{report.status}`",
        f"- 仓库保持不变 / Repository unchanged: `{str(report.repository_unchanged).lower()}`",
        f"- 仓库快照 / Snapshot: `{report.repo_snapshot_before}`",
        "",
        "## 问题描述 / Issue",
        "",
        issue.title,
        "",
        "## 诊断 / Diagnosis",
        "",
        report.diagnosis,
        "",
        "## 候选文件 / Candidate Files",
        "",
    ]
    lines.extend(
        [f"{index}. `{path}`" for index, path in enumerate(report.candidate_files, 1)]
        or ["未找到有代码证据支持的候选文件。 / No evidence-backed candidate file was found."]
    )
    lines.extend(["", "## 代码证据 / Evidence", ""])
    for item in report.evidence:
        lines.extend(
            [
                f"### `{item.evidence_id}` — `{item.path}:{item.start_line}`",
                "",
                f"原因 / Reason: {item.reason} · 分数 / Score `{item.score:.2f}`",
                "",
                "```text",
                item.snippet,
                "```",
                "",
            ]
        )
    lines.extend(["## 修改计划 / Change Plan", ""])
    for step in report.plan:
        refs = ", ".join(f"`{item}`" for item in step.evidence_ids)
        lines.append(
            f"{step.order}. {step.action} — {step.rationale}"
            + (f" 证据 / Evidence: {refs}" if refs else "")
        )
    if not report.plan:
        lines.append(
            "由于证据不足，系统未生成修改计划。 / "
            "No change plan was generated because evidence was insufficient."
        )
    lines.extend(["", "## 建议验证 / Proposed Validation", ""])
    lines.extend(
        [f"- {item}" for item in report.proposed_tests]
        or ["- 无 / None"]
    )
    lines.extend(["", "## 风险 / Risks", ""])
    lines.extend([f"- {item}" for item in report.risks] or ["- 无 / None"])
    lines.extend(["", "## 验收标准 / Acceptance Criteria", ""])
    lines.extend(
        [f"- {item}" for item in report.acceptance_criteria]
        or ["- 无 / None"]
    )
    lines.extend(["", "## 指标 / Metrics", "", "```json"])
    lines.append(json.dumps(report.metrics, ensure_ascii=False, indent=2, sort_keys=True))
    lines.extend(["```", ""])
    return "\n".join(lines)


def load_report(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
