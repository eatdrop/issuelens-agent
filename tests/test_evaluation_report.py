from __future__ import annotations

import unittest

from issuelens.evaluation_report import (
    EvaluationReportError,
    render_evaluation_report,
)


def _summary() -> dict[str, object]:
    return {
        "case_count": 2,
        "hit_at_1": 1.0,
        "gold_file_recall_at_3": 1.0,
        "mean_reciprocal_rank": 1.0,
        "status_accuracy": 1.0,
        "safe_abstention_rate": 1.0,
        "repository_unchanged_rate": 1.0,
        "plan_evidence_coverage": 1.0,
        "median_elapsed_ms": 2.5,
        "cases": [
            {
                "case_id": "case|<one>",
                "gold_files": ("src/app.py",),
                "candidates": ("src/app.py",),
                "expected_status": "ready_for_human_review",
                "actual_status": "ready_for_human_review",
                "status_match": True,
                "hit_at_1": 1.0,
                "recall_at_3": 1.0,
                "reciprocal_rank": 1.0,
                "repository_unchanged": True,
                "plan_evidence_coverage": 1.0,
                "elapsed_ms": 2.0,
                "failure_category": "none",
            },
            {
                "case_id": "underspecified\ncase",
                "gold_files": (),
                "candidates": (),
                "expected_status": "insufficient_evidence",
                "actual_status": "insufficient_evidence",
                "status_match": True,
                "hit_at_1": None,
                "recall_at_3": None,
                "reciprocal_rank": None,
                "repository_unchanged": True,
                "plan_evidence_coverage": 0.0,
                "elapsed_ms": 3.0,
                "failure_category": "none",
            },
        ],
    }


class EvaluationReportTests(unittest.TestCase):
    def test_renders_deterministic_bilingual_report_with_denominators(self) -> None:
        first = render_evaluation_report(_summary())
        second = render_evaluation_report(_summary())

        self.assertEqual(second, first)
        self.assertTrue(
            first.startswith(
                "# 自动评测汇总 / Automated Evaluation Summary\n"
            )
        )
        self.assertIn("| Hit@1 | 1.0000 / 100.00% | 1 |", first)
        self.assertIn(
            "| 安全拒绝率 / Safe Abstention Rate "
            "| 1.0000 / 100.00% | 1 |",
            first,
        )
        self.assertIn("不适用 / N/A", first)
        self.assertIn("deterministic smoke baseline", first)
        self.assertIn("## 失败分类 / Failure Taxonomy", first)
        self.assertIn("- `none`: 2", first)
        self.assertTrue(first.endswith("\n"))

    def test_escapes_untrusted_table_values(self) -> None:
        report = render_evaluation_report(_summary())

        self.assertIn("<code>case&#124;&lt;one&gt;</code>", report)
        self.assertIn("<code>underspecified&#10;case</code>", report)
        self.assertNotIn("case|<one>", report)

    def test_rejects_inconsistent_or_non_finite_summary(self) -> None:
        inconsistent = _summary()
        inconsistent["case_count"] = 3
        with self.assertRaisesRegex(EvaluationReportError, "case_count"):
            render_evaluation_report(inconsistent)

        non_finite = _summary()
        non_finite["median_elapsed_ms"] = float("nan")
        with self.assertRaisesRegex(EvaluationReportError, "finite"):
            render_evaluation_report(non_finite)


if __name__ == "__main__":
    unittest.main()
