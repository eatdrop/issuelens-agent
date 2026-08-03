from __future__ import annotations

import math
from html import escape
from typing import Any, Mapping, Sequence


class EvaluationReportError(ValueError):
    """Raised when an evaluation summary cannot be rendered safely."""


_RATE_FIELDS = (
    "hit_at_1",
    "gold_file_recall_at_3",
    "mean_reciprocal_rank",
    "status_accuracy",
    "safe_abstention_rate",
    "repository_unchanged_rate",
    "plan_evidence_coverage",
)

_CASE_FIELDS = (
    "case_id",
    "gold_files",
    "candidates",
    "expected_status",
    "actual_status",
    "status_match",
    "hit_at_1",
    "recall_at_3",
    "reciprocal_rank",
    "repository_unchanged",
    "plan_evidence_coverage",
    "elapsed_ms",
)


def render_evaluation_report(summary: Mapping[str, Any]) -> str:
    """Render a deterministic bilingual Markdown report from one summary."""

    case_count, cases = _validate_summary(summary)
    localization_count = sum(bool(case["gold_files"]) for case in cases)
    abstention_count = sum(
        case["expected_status"] == "insufficient_evidence"
        for case in cases
    )
    review_ready_count = sum(
        case["actual_status"] == "ready_for_human_review"
        for case in cases
    )

    lines = [
        "# 自动评测汇总 / Automated Evaluation Summary",
        "",
        "> 本报告由 `evaluation-summary.json` 的同一份内存数据自动生成。 / "
        "This report is generated automatically from the same in-memory data "
        "as `evaluation-summary.json`.",
        "",
        "## 汇总指标 / Summary Metrics",
        "",
        "| 指标 / Metric | 结果 / Result | 有效样本 / Eligible Cases |",
        "| --- | ---: | ---: |",
        _metric_row(
            "案例数 / Case Count",
            str(case_count),
            f"{case_count}",
        ),
        _metric_row(
            "Hit@1",
            _rate(summary["hit_at_1"]),
            f"{localization_count}",
        ),
        _metric_row(
            "Gold File Recall@3",
            _rate(summary["gold_file_recall_at_3"]),
            f"{localization_count}",
        ),
        _metric_row(
            "平均倒数排名 / Mean Reciprocal Rank",
            _rate(summary["mean_reciprocal_rank"]),
            f"{localization_count}",
        ),
        _metric_row(
            "状态准确率 / Status Accuracy",
            _rate(summary["status_accuracy"]),
            f"{case_count}",
        ),
        _metric_row(
            "安全拒绝率 / Safe Abstention Rate",
            _rate(summary["safe_abstention_rate"]),
            f"{abstention_count}",
        ),
        _metric_row(
            "仓库保持不变率 / Repository Unchanged Rate",
            _rate(summary["repository_unchanged_rate"]),
            f"{case_count}",
        ),
        _metric_row(
            "计划证据覆盖率 / Plan Evidence Coverage",
            _rate(summary["plan_evidence_coverage"]),
            f"{review_ready_count}",
        ),
        _metric_row(
            "中位耗时 / Median Elapsed Time",
            f"{summary['median_elapsed_ms']:.2f} ms",
            f"{case_count}",
        ),
        "",
        "## 逐案例结果 / Per-case Results",
        "",
        (
            "| 案例 / Case | 预期状态 / Expected | 实际状态 / Actual | "
            "首位候选 / Top Candidate | Hit@1 | Recall@3 | MRR | "
            "仓库未变 / Repo Unchanged | 耗时 / Elapsed |"
        ),
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: |",
    ]

    for case in cases:
        candidates = case["candidates"]
        lines.append(
            "| "
            f"{_code(case['case_id'])} | "
            f"{_code(case['expected_status'])} | "
            f"{_code(case['actual_status'])} | "
            f"{_code(candidates[0]) if candidates else '无 / None'} | "
            f"{_optional_rate(case['hit_at_1'])} | "
            f"{_optional_rate(case['recall_at_3'])} | "
            f"{_optional_rate(case['reciprocal_rank'])} | "
            f"{_yes_no(case['repository_unchanged'])} | "
            f"{case['elapsed_ms']:.2f} ms |"
        )

    lines.extend(
        [
            "",
            "## 解释与限制 / Interpretation and Limitations",
            "",
            (
                f"- 案例总数 / Total cases: **{case_count}**；"
                f"定位指标有效案例 / localization-eligible cases: "
                f"**{localization_count}**；安全拒绝有效案例 / "
                f"safe-abstention-eligible cases: **{abstention_count}**。"
            ),
            (
                "- 这是固定合成夹具上的 deterministic smoke baseline，"
                "不能代表真实公开 Issue 或通用模型质量。 / "
                "This is a deterministic smoke baseline on fixed synthetic "
                "fixtures; it does not represent quality on real public "
                "Issues or general model quality."
            ),
            (
                "- 评测不生成补丁、不执行目标仓库测试，也不计算 "
                "Resolved@1。 / The evaluation does not generate patches, "
                "execute target-repository tests, or calculate Resolved@1."
            ),
            (
                "- 耗时只描述本次本地运行，会随硬件和负载变化。 / "
                "Timing describes only this local run and varies with "
                "hardware and load."
            ),
            (
                "- 报告百分比必须与案例数量和有效分母一起引用。 / "
                "Report percentages only together with case counts and "
                "eligible denominators."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _validate_summary(
    summary: Mapping[str, Any],
) -> tuple[int, list[Mapping[str, Any]]]:
    if not isinstance(summary, Mapping):
        raise EvaluationReportError("summary must be a mapping")

    case_count = summary.get("case_count")
    if (
        isinstance(case_count, bool)
        or not isinstance(case_count, int)
        or case_count < 0
    ):
        raise EvaluationReportError("case_count must be a non-negative integer")

    raw_cases = summary.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != case_count:
        raise EvaluationReportError("cases must match case_count")

    for field in _RATE_FIELDS:
        _require_rate(summary.get(field), field_name=field)
    _require_non_negative_number(
        summary.get("median_elapsed_ms"),
        field_name="median_elapsed_ms",
    )

    cases: list[Mapping[str, Any]] = []
    for index, case in enumerate(raw_cases):
        if not isinstance(case, Mapping):
            raise EvaluationReportError(f"cases[{index}] must be a mapping")
        missing = [field for field in _CASE_FIELDS if field not in case]
        if missing:
            raise EvaluationReportError(
                f"cases[{index}] is missing fields: {', '.join(missing)}"
            )
        _validate_case(case, index=index)
        cases.append(case)
    return case_count, cases


def _validate_case(case: Mapping[str, Any], *, index: int) -> None:
    for field in ("case_id", "expected_status", "actual_status"):
        value = case[field]
        if not isinstance(value, str) or not value.strip():
            raise EvaluationReportError(
                f"cases[{index}].{field} must be non-empty text"
            )

    for field in ("gold_files", "candidates"):
        value = case[field]
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes))
            or any(not isinstance(item, str) for item in value)
        ):
            raise EvaluationReportError(
                f"cases[{index}].{field} must contain text values"
            )

    for field in ("status_match", "repository_unchanged"):
        if not isinstance(case[field], bool):
            raise EvaluationReportError(
                f"cases[{index}].{field} must be boolean"
            )

    for field in ("hit_at_1", "recall_at_3", "reciprocal_rank"):
        value = case[field]
        if value is not None:
            _require_rate(value, field_name=f"cases[{index}].{field}")

    _require_rate(
        case["plan_evidence_coverage"],
        field_name=f"cases[{index}].plan_evidence_coverage",
    )
    _require_non_negative_number(
        case["elapsed_ms"],
        field_name=f"cases[{index}].elapsed_ms",
    )


def _require_rate(value: Any, *, field_name: str) -> None:
    number = _number(value, field_name=field_name)
    if number < 0.0 or number > 1.0:
        raise EvaluationReportError(f"{field_name} must be between 0 and 1")


def _require_non_negative_number(value: Any, *, field_name: str) -> None:
    if _number(value, field_name=field_name) < 0.0:
        raise EvaluationReportError(f"{field_name} must be non-negative")


def _number(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationReportError(f"{field_name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise EvaluationReportError(f"{field_name} must be finite")
    return number


def _metric_row(label: str, result: str, eligible: str) -> str:
    return f"| {label} | {result} | {eligible} |"


def _rate(value: Any) -> str:
    number = float(value)
    return f"{number:.4f} / {number * 100:.2f}%"


def _optional_rate(value: Any) -> str:
    return "不适用 / N/A" if value is None else f"{float(value):.4f}"


def _yes_no(value: bool) -> str:
    return "是 / Yes" if value else "否 / No"


def _code(value: str) -> str:
    escaped = escape(value, quote=False)
    escaped = escaped.replace("|", "&#124;")
    escaped = escaped.replace("\r", "&#13;").replace("\n", "&#10;")
    return f"<code>{escaped}</code>"
