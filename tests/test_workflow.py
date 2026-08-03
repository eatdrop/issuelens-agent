import tempfile
import unittest
from pathlib import Path

from issuelens.workflow import IssueAnalysisWorkflow


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def test_locates_divide_implementation_and_preserves_repository(self) -> None:
        repo = PROJECT_ROOT / "fixtures" / "calculator_repo"
        issue = (
            PROJECT_ROOT / "evals" / "cases" / "division_by_zero.md"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as run_dir:
            report = IssueAnalysisWorkflow().run(
                repo_path=repo,
                issue_text=issue,
                run_dir=run_dir,
                run_id="test-run",
            )
            self.assertTrue(report.repository_unchanged)
            self.assertEqual(report.candidate_files[0], "src/calculator.py")
            self.assertEqual(report.metrics["target_repo_write_count"], 0)
            self.assertEqual(report.metrics["plan_evidence_coverage"], 1.0)
            markdown_path = Path(run_dir) / "test-run" / "report.md"
            self.assertTrue(markdown_path.is_file())
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("诊断 / Diagnosis", markdown)
            self.assertIn("排名最高的实现候选文件", markdown)
            self.assertIn("The highest-ranked implementation candidate", markdown)

    def test_abstains_when_only_generic_keywords_overlap(self) -> None:
        repo = PROJECT_ROOT / "fixtures" / "calculator_repo"
        issue = (
            PROJECT_ROOT / "evals" / "cases" / "underspecified_export.md"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as run_dir:
            report = IssueAnalysisWorkflow().run(
                repo_path=repo,
                issue_text=issue,
                run_dir=run_dir,
                run_id="abstention-run",
            )
            self.assertEqual(report.status, "insufficient_evidence")
            self.assertEqual(report.plan, [])
            self.assertTrue(report.repository_unchanged)


if __name__ == "__main__":
    unittest.main()
