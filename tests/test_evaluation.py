import tempfile
import unittest
from pathlib import Path

from issuelens.evaluation import evaluate_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def test_builtin_manifest_has_safe_retrieval_signal(self) -> None:
        with tempfile.TemporaryDirectory() as run_dir:
            summary = evaluate_manifest(
                PROJECT_ROOT / "evals" / "manifest.json",
                run_dir,
            )
            self.assertEqual(summary["case_count"], 3)
            self.assertEqual(summary["repository_unchanged_rate"], 1.0)
            self.assertGreaterEqual(summary["gold_file_recall_at_3"], 1.0)
            self.assertEqual(summary["safe_abstention_rate"], 1.0)
            self.assertTrue(
                (Path(run_dir) / "evaluation-summary.json").is_file()
            )
            markdown_path = Path(run_dir) / "evaluation-summary.md"
            self.assertTrue(markdown_path.is_file())
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn(
                "# 自动评测汇总 / Automated Evaluation Summary",
                markdown,
            )
            self.assertIn(
                "| 仓库保持不变率 / Repository Unchanged Rate "
                "| 1.0000 / 100.00% | 3 |",
                markdown,
            )
            self.assertIn("`evaluation-summary.json`", markdown)


if __name__ == "__main__":
    unittest.main()
