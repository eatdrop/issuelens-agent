from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .domain import AnalysisReport, TraceEvent


class RunArtifacts:
    def __init__(
        self,
        run_dir: str | Path,
        run_id: str,
        *,
        resume: bool = False,
    ) -> None:
        if (
            not isinstance(run_id, str)
            or _RUN_ID_PATTERN.fullmatch(run_id) is None
            or run_id in {".", ".."}
        ):
            raise ValueError("run_id must be 1-128 safe filename characters")
        root = Path(run_dir).expanduser().resolve()
        self.path = root / run_id
        if resume:
            if self.path.is_symlink() or not self.path.is_dir():
                raise FileNotFoundError("run directory is unavailable for resume")
        else:
            self.path.mkdir(parents=True, exist_ok=False)
        self.trace_path = self.path / "trace.jsonl"
        for name in ("trace.jsonl", "report.json", "report.md", "checkpoint.json"):
            target = self.path / name
            if target.is_symlink():
                raise ValueError(f"run artifact cannot be a symbolic link: {name}")

    def append_trace(self, event: TraceEvent) -> None:
        descriptor = -1
        try:
            descriptor = os.open(
                self.trace_path,
                os.O_WRONLY
                | os.O_APPEND
                | os.O_CREAT
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except OSError as exc:
            raise ValueError("trace artifact could not be opened safely") from exc
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            json.dump(event.to_dict(), stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()

    def write_report(self, report: AnalysisReport) -> None:
        report_json = (
            json.dumps(
                report.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        _atomic_write(self.path / "report.json", report_json.encode("utf-8"))
        _atomic_write(
            self.path / "report.md",
            render_markdown(report).encode("utf-8"),
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


_RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")


def _atomic_write(target: Path, content: bytes) -> None:
    if target.is_symlink():
        raise ValueError(f"run artifact cannot be a symbolic link: {target.name}")
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{target.name}-",
            suffix=".tmp",
            dir=target.parent,
        )
        temporary = Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if target.is_symlink():
            raise ValueError(
                f"run artifact cannot be a symbolic link: {target.name}"
            )
        os.replace(temporary, target)
        temporary = None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
