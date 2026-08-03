from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from issuelens.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DraftPrTests(unittest.TestCase):
    def _analyze(self, run_dir: Path, issue_name: str, run_id: str) -> Path:
        with redirect_stdout(io.StringIO()):
            self.assertEqual(
                main(
                    [
                        "analyze",
                        "--repo",
                        str(PROJECT_ROOT / "fixtures" / "calculator_repo"),
                        "--issue",
                        str(PROJECT_ROOT / "evals" / "cases" / issue_name),
                        "--run-dir",
                        str(run_dir),
                        "--run-id",
                        run_id,
                    ]
                ),
                0,
            )
        return run_dir / run_id / "report.json"

    def test_exports_bilingual_markdown_without_publishing(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            temp = Path(root)
            report = self._analyze(temp / "runs", "division_by_zero.md", "draft")
            output = temp / "draft-pr.md"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "draft-pr",
                        "--repo",
                        str(PROJECT_ROOT / "fixtures" / "calculator_repo"),
                        "--report",
                        str(report),
                        "--diff",
                        str(PROJECT_ROOT / "evals" / "patches" / "division_by_zero.diff"),
                        "--output",
                        str(output),
                    ]
                )

            payload = json.loads(stdout.getvalue())
            body = output.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertFalse(payload["published"])
            self.assertEqual(payload["validation"], "not_run")
            self.assertIn("背景 / Context", body)
            self.assertIn("Human Review Checklist", body)
            self.assertIn("Shadow validation is required before merge", body)
            self.assertIn("Proposal Hash", body)

    def test_rejects_insufficient_evidence_report(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            temp = Path(root)
            report = self._analyze(
                temp / "runs",
                "underspecified_export.md",
                "insufficient",
            )

            with self.assertRaisesRegex(SystemExit, "review-ready"):
                main(
                    [
                        "draft-pr",
                        "--repo",
                        str(PROJECT_ROOT / "fixtures" / "calculator_repo"),
                        "--report",
                        str(report),
                        "--diff",
                        str(PROJECT_ROOT / "evals" / "patches" / "division_by_zero.diff"),
                        "--output",
                        str(temp / "draft.md"),
                    ]
                )

    def test_refuses_to_write_draft_inside_target_repository(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            report = self._analyze(Path(root) / "runs", "division_by_zero.md", "inside")
            target = PROJECT_ROOT / "fixtures" / "calculator_repo" / "draft-pr.md"
            try:
                with self.assertRaisesRegex(SystemExit, "outside"):
                    main(
                        [
                            "draft-pr",
                            "--repo",
                            str(PROJECT_ROOT / "fixtures" / "calculator_repo"),
                            "--report",
                            str(report),
                            "--diff",
                            str(PROJECT_ROOT / "evals" / "patches" / "division_by_zero.diff"),
                            "--output",
                            str(target),
                        ]
                    )
            finally:
                target.unlink(missing_ok=True)

    def test_rejects_report_without_unchanged_repository_proof(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            temp = Path(root)
            report_path = self._analyze(
                temp / "runs",
                "division_by_zero.md",
                "tampered",
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["repository_unchanged"] = False
            report_path.write_text(json.dumps(report), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "unchanged repository"):
                main(
                    [
                        "draft-pr",
                        "--repo",
                        str(PROJECT_ROOT / "fixtures" / "calculator_repo"),
                        "--report",
                        str(report_path),
                        "--diff",
                        str(
                            PROJECT_ROOT
                            / "evals"
                            / "patches"
                            / "division_by_zero.diff"
                        ),
                        "--output",
                        str(temp / "draft.md"),
                    ]
                )


if __name__ == "__main__":
    unittest.main()
