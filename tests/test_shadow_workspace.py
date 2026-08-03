from __future__ import annotations

import dataclasses
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from issuelens.approval import PatchApproval
from issuelens.approval_gate import PatchApplicationBlockedError
from issuelens.patch_proposal import PatchProposal
from issuelens.repository import ReadOnlyRepository
from issuelens.shadow_workspace import (
    CommandSpec,
    DockerCommandRunner,
    ShadowValidationResult,
    ShadowWorkspaceError,
    UnsafeLocalCommandRunner,
    ValidationAuditStore,
    validate_approved_patch,
)


PATCH = """\
--- a/src/calculator.py
+++ b/src/calculator.py
@@ -2,1 +2,3 @@
-    return left / right
+    if right == 0:
+        raise ValueError("right must not be zero")
+    return left / right
"""


class ShadowWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repository_root = self.root / "repository"
        (self.repository_root / "src").mkdir(parents=True)
        (self.repository_root / "tests").mkdir()
        (self.repository_root / "src" / "calculator.py").write_text(
            "def divide(left, right):\n    return left / right\n",
            encoding="utf-8",
        )
        (self.repository_root / "tests" / "test_existing.py").write_text(
            """\
import unittest
from src.calculator import divide


class ExistingTests(unittest.TestCase):
    def test_divide(self):
        self.assertEqual(divide(6, 3), 2)
""",
            encoding="utf-8",
        )
        self.reproduction = self.root / "reproduction"
        self.reproduction.mkdir()
        (self.reproduction / "test_reproduction.py").write_text(
            """\
import unittest
from src.calculator import divide


class ReproductionTests(unittest.TestCase):
    def test_zero_divisor_uses_domain_error(self):
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
    def test_error_message_is_actionable(self):
        with self.assertRaisesRegex(ValueError, "right must not be zero"):
            divide(-1, 0)
""",
            encoding="utf-8",
        )
        self.repository = ReadOnlyRepository(self.repository_root)
        self.proposal = PatchProposal.create(
            unified_diff=PATCH,
            base_snapshot_hash=self.repository.snapshot_hash(),
        )
        self.approval = PatchApproval.create(
            run_id="shadow-run",
            proposal=self.proposal,
            approved_by="reviewer",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _validate(self) -> ShadowValidationResult:
        return validate_approved_patch(
            repository=self.repository,
            run_id="shadow-run",
            proposal=self.proposal,
            approval=self.approval,
            runner=UnsafeLocalCommandRunner(),
            reproduction_tests=self.reproduction,
            hidden_tests=self.hidden,
            timeout_seconds=10,
        )

    def test_proves_fail_before_and_pass_after_without_writing_source(self) -> None:
        before = self.repository.snapshot_hash()
        before_content = (self.repository_root / "src" / "calculator.py").read_text(
            encoding="utf-8"
        )

        result = self._validate()

        self.assertEqual(result.verdict, "passed")
        self.assertTrue(result.repository_unchanged)
        self.assertTrue(result.verify_integrity())
        self.assertEqual(
            [item.name for item in result.commands],
            [
                "baseline_reproduction",
                "patched_reproduction",
                "patched_full_suite",
                "patched_hidden_suite",
            ],
        )
        self.assertTrue(all(item.expectation_met for item in result.commands))
        self.assertNotEqual(result.base_snapshot_hash, result.patched_snapshot_hash)
        self.assertEqual(self.repository.snapshot_hash(), before)
        self.assertEqual(
            (self.repository_root / "src" / "calculator.py").read_text(
                encoding="utf-8"
            ),
            before_content,
        )

    def test_receipt_round_trip_and_content_addressed_store(self) -> None:
        result = self._validate()
        restored = ShadowValidationResult.from_json(result.to_json())
        store = ValidationAuditStore(self.root / "audit")

        path = store.store(result)

        self.assertEqual(restored, result)
        self.assertEqual(path.name, f"{result.receipt_hash}.json")
        self.assertEqual(store.load(result.receipt_hash), result)

    def test_receipt_rejects_tampered_verdict(self) -> None:
        payload = json.loads(self._validate().to_json())
        payload["verdict"] = "failed"

        with self.assertRaisesRegex(ShadowWorkspaceError, "inconsistent|integrity"):
            ShadowValidationResult.from_json(json.dumps(payload))

    def test_hidden_failure_fails_the_verdict(self) -> None:
        (self.hidden / "test_hidden.py").write_text(
            """\
import unittest
from src.calculator import divide


class HiddenTests(unittest.TestCase):
    def test_deliberate_failure(self):
        self.assertEqual(divide(4, 2), 999)
""",
            encoding="utf-8",
        )

        result = self._validate()

        self.assertEqual(result.verdict, "failed")
        self.assertFalse(result.commands[-1].expectation_met)

    def test_import_error_does_not_count_as_expected_reproduction_failure(self) -> None:
        (self.reproduction / "test_reproduction.py").write_text(
            "import module_that_does_not_exist\n",
            encoding="utf-8",
        )

        result = self._validate()

        self.assertEqual(result.verdict, "failed")
        self.assertFalse(result.commands[0].expectation_met)
        self.assertIn("errors=1", result.commands[0].stderr_excerpt)

    def test_rejects_non_python_commands(self) -> None:
        with self.assertRaisesRegex(ShadowWorkspaceError, "python"):
            CommandSpec(name="shell", argv=("sh", "-c", "echo unsafe"))

    def test_rejects_absolute_full_test_directory(self) -> None:
        with self.assertRaisesRegex(ShadowWorkspaceError, "full test directory"):
            validate_approved_patch(
                repository=self.repository,
                run_id="shadow-run",
                proposal=self.proposal,
                approval=self.approval,
                runner=UnsafeLocalCommandRunner(),
                reproduction_tests=self.reproduction,
                full_test_dir="/tmp/tests",
            )

    def test_rejects_test_bundle_inside_target_repository(self) -> None:
        with self.assertRaisesRegex(ShadowWorkspaceError, "outside"):
            validate_approved_patch(
                repository=self.repository,
                run_id="shadow-run",
                proposal=self.proposal,
                approval=self.approval,
                runner=UnsafeLocalCommandRunner(),
                reproduction_tests=self.repository_root / "tests",
            )

    def test_rejects_reserved_test_namespace_in_target_repository(self) -> None:
        reserved = self.repository_root / ".issuelens-tests"
        reserved.mkdir()
        (reserved / "injected.py").write_text("raise RuntimeError\n", encoding="utf-8")
        repository = ReadOnlyRepository(self.repository_root)
        proposal = PatchProposal.create(
            unified_diff=PATCH,
            base_snapshot_hash=repository.snapshot_hash(),
        )
        approval = PatchApproval.create(
            run_id="shadow-run",
            proposal=proposal,
            approved_by="reviewer",
        )

        with self.assertRaisesRegex(ShadowWorkspaceError, "reserved"):
            validate_approved_patch(
                repository=repository,
                run_id="shadow-run",
                proposal=proposal,
                approval=approval,
                runner=UnsafeLocalCommandRunner(),
                reproduction_tests=self.reproduction,
            )

    @patch.object(UnsafeLocalCommandRunner, "run")
    def test_rejects_invalid_approval_before_running_tests(self, run: object) -> None:
        approval = PatchApproval.create(
            run_id="another-run",
            proposal=self.proposal,
            approved_by="reviewer",
        )

        with self.assertRaises(PatchApplicationBlockedError):
            validate_approved_patch(
                repository=self.repository,
                run_id="shadow-run",
                proposal=self.proposal,
                approval=approval,
                runner=UnsafeLocalCommandRunner(),
                reproduction_tests=self.reproduction,
            )

        run.assert_not_called()

    @patch("issuelens.shadow_workspace.subprocess.run")
    def test_docker_runner_enforces_isolation_flags(self, run: object) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=b"ok\n",
            stderr=b"",
        )
        runner = DockerCommandRunner(image="python:3.12-slim")

        result = runner.run(
            self.repository_root,
            CommandSpec(name="tests", argv=("python", "-m", "unittest")),
        )

        argv = run.call_args.args[0]
        self.assertIn("--network=none", argv)
        self.assertIn("--read-only", argv)
        self.assertIn("--cap-drop=ALL", argv)
        self.assertIn("--security-opt=no-new-privileges", argv)
        self.assertIn("--user=65534:65534", argv)
        self.assertIn("--pull=never", argv)
        self.assertTrue(any(value.startswith("--name=issuelens-") for value in argv))
        self.assertTrue(any(value.endswith(":/workspace:ro") for value in argv))
        self.assertTrue(result.expectation_met)
        self.assertEqual(result.name, "tests")
        self.assertIn("image=python:3.12-slim", runner.name)
        self.assertIn("memory=512m", runner.name)
        self.assertIn("network=none", runner.name)

    @patch("issuelens.shadow_workspace.subprocess.run")
    def test_docker_timeout_force_removes_named_container(self, run: object) -> None:
        run.side_effect = [
            subprocess.TimeoutExpired(cmd=("docker", "run"), timeout=0.1),
            subprocess.CompletedProcess(args=[], returncode=0),
        ]
        runner = DockerCommandRunner(image="python:3.12-slim")

        result = runner.run(
            self.repository_root,
            CommandSpec(
                name="timeout",
                argv=("python", "-m", "unittest"),
                timeout_seconds=0.1,
            ),
        )

        self.assertTrue(result.timed_out)
        self.assertFalse(result.expectation_met)
        container_name = next(
            value.removeprefix("--name=")
            for value in run.call_args_list[0].args[0]
            if value.startswith("--name=")
        )
        self.assertEqual(
            run.call_args_list[1].args[0],
            ("docker", "rm", "-f", container_name),
        )

    def test_integrity_detects_dataclass_tampering(self) -> None:
        result = self._validate()
        tampered = dataclasses.replace(result, runner="different")

        self.assertFalse(tampered.verify_integrity())


if __name__ == "__main__":
    unittest.main()
