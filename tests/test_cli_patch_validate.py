from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from issuelens.cli import main
from issuelens.shadow_workspace import ValidationAuditStore


DIFF = """\
--- a/src/calculator.py
+++ b/src/calculator.py
@@ -2,1 +2,3 @@
-    return left / right
+    if right == 0:
+        raise ValueError("right must not be zero")
+    return left / right
"""


class PatchValidateCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repository = self.root / "repository"
        (self.repository / "src").mkdir(parents=True)
        (self.repository / "tests").mkdir()
        (self.repository / "src" / "calculator.py").write_text(
            "def divide(left, right):\n    return left / right\n",
            encoding="utf-8",
        )
        (self.repository / "tests" / "test_existing.py").write_text(
            """\
import unittest
from src.calculator import divide


class ExistingTests(unittest.TestCase):
    def test_divide(self):
        self.assertEqual(divide(6, 3), 2)
""",
            encoding="utf-8",
        )
        self.diff = self.root / "candidate.diff"
        self.diff.write_text(DIFF, encoding="utf-8")
        self.reproduction = self.root / "reproduction"
        self.reproduction.mkdir()
        (self.reproduction / "test_reproduction.py").write_text(
            """\
import unittest
from src.calculator import divide


class ReproductionTests(unittest.TestCase):
    def test_zero(self):
        with self.assertRaises(ValueError):
            divide(1, 0)
""",
            encoding="utf-8",
        )
        self.hidden = self.root / "hidden"
        self.hidden.mkdir()
        (self.hidden / "test_hidden.py").write_text(
            """\
import unittest
from src.calculator import divide


class HiddenTests(unittest.TestCase):
    def test_message(self):
        with self.assertRaisesRegex(ValueError, "right must not be zero"):
            divide(1, 0)
""",
            encoding="utf-8",
        )
        self.audit = self.root / "audit"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _proposal_hash(self) -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                main(
                    [
                        "patch-proposal",
                        "--repo",
                        str(self.repository),
                        "--diff",
                        str(self.diff),
                    ]
                ),
                0,
            )
        return json.loads(output.getvalue())["proposal_hash"]

    def _arguments(self) -> list[str]:
        return [
            "patch-validate",
            "--repo",
            str(self.repository),
            "--diff",
            str(self.diff),
            "--run-id",
            "validation-123",
            "--approved-by",
            "reviewer",
            "--approve-proposal-hash",
            self._proposal_hash(),
            "--audit-dir",
            str(self.audit),
            "--reproduction-tests",
            str(self.reproduction),
            "--hidden-tests",
            str(self.hidden),
            "--runner",
            "local",
        ]

    def test_validates_and_records_bilingual_report(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main([*self._arguments(), "--allow-unsafe-local"])

        payload = json.loads(output.getvalue())
        receipt = ValidationAuditStore(self.audit).load(payload["receipt_hash"])
        report = Path(payload["report_path"]).read_text(encoding="utf-8")
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["verdict"], "passed")
        self.assertTrue(payload["repository_unchanged"])
        self.assertEqual(receipt.verdict, "passed")
        self.assertIn("隔离验证报告 / Shadow Validation", report)
        self.assertIn("No, trusted fixtures only", report)
        self.assertNotIn("stated isolated backend", report)

    def test_local_runner_requires_explicit_unsafe_flag(self) -> None:
        with self.assertRaisesRegex(SystemExit, "allow-unsafe-local"):
            main(self._arguments())

        self.assertFalse(self.audit.exists())

    def test_rejects_hidden_tests_inside_target_repository(self) -> None:
        arguments = self._arguments()
        hidden_index = arguments.index("--hidden-tests") + 1
        arguments[hidden_index] = str(self.repository / "tests")

        with self.assertRaisesRegex(SystemExit, "outside"):
            main([*arguments, "--allow-unsafe-local"])


if __name__ == "__main__":
    unittest.main()
