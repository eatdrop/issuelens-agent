from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from issuelens.audit_store import ReceiptAuditStore
from issuelens.cli import main
from issuelens.repository import ReadOnlyRepository


DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-value = 1
+value = 2
"""
CONFLICTING_DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-missing = 1
+value = 2
"""


class PatchReviewCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repository_root = self.root / "repository"
        self.repository_root.mkdir()
        self.source_path = self.repository_root / "app.py"
        self.source_path.write_text("value = 1\n", encoding="utf-8")
        self.diff_path = self.root / "candidate.diff"
        self.diff_path.write_text(DIFF, encoding="utf-8")
        self.audit_root = self.root / "audit"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _proposal_hash(self) -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "patch-proposal",
                    "--repo",
                    str(self.repository_root),
                    "--diff",
                    str(self.diff_path),
                ]
            )
        self.assertEqual(exit_code, 0)
        return json.loads(output.getvalue())["proposal_hash"]

    def _review(
        self,
        proposal_hash: str,
        *,
        audit_dir: Path | None = None,
    ) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "patch-review",
                    "--repo",
                    str(self.repository_root),
                    "--diff",
                    str(self.diff_path),
                    "--run-id",
                    "run-123",
                    "--approved-by",
                    "reviewer",
                    "--approve-proposal-hash",
                    proposal_hash,
                    "--audit-dir",
                    str(audit_dir or self.audit_root),
                ]
            )
        return exit_code, output.getvalue()

    def test_runs_two_stage_review_without_modifying_repository(self) -> None:
        repository = ReadOnlyRepository(self.repository_root)
        before_snapshot = repository.snapshot_hash()
        before_content = self.source_path.read_bytes()
        before_modified_ns = self.source_path.stat().st_mtime_ns
        proposal_hash = self._proposal_hash()

        exit_code, output = self._review(proposal_hash)
        payload = json.loads(output)
        receipt = ReceiptAuditStore(self.audit_root).load(
            payload["receipt_hash"]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["proposal_hash"], proposal_hash)
        self.assertEqual(payload["run_id"], "run-123")
        self.assertEqual(payload["approval_hash"], receipt.approval_hash)
        self.assertEqual(payload["audit_path"], str(
            self.audit_root.resolve() / f"{receipt.receipt_hash}.json"
        ))
        self.assertTrue(payload["repository_unchanged"])
        self.assertEqual(self.source_path.read_bytes(), before_content)
        self.assertEqual(
            self.source_path.stat().st_mtime_ns,
            before_modified_ns,
        )
        self.assertEqual(repository.snapshot_hash(), before_snapshot)

    def test_rejects_mismatched_hash_without_creating_audit(self) -> None:
        with self.assertRaisesRegex(SystemExit, "does not match"):
            self._review("0" * 64)

        self.assertFalse(self.audit_root.exists())
        self.assertEqual(
            self.source_path.read_text(encoding="utf-8"),
            "value = 1\n",
        )

    def test_rejects_audit_directory_inside_repository(self) -> None:
        proposal_hash = self._proposal_hash()
        inside_audit = self.repository_root / "audit"

        with self.assertRaisesRegex(SystemExit, "outside"):
            self._review(
                proposal_hash,
                audit_dir=inside_audit,
            )

        self.assertFalse(inside_audit.exists())

    def test_preflight_conflict_creates_no_audit(self) -> None:
        self.diff_path.write_text(
            CONFLICTING_DIFF,
            encoding="utf-8",
        )
        proposal_hash = self._proposal_hash()

        with self.assertRaisesRegex(SystemExit, "does not match"):
            self._review(proposal_hash)

        self.assertFalse(self.audit_root.exists())
        self.assertEqual(
            self.source_path.read_text(encoding="utf-8"),
            "value = 1\n",
        )

    def test_rejects_symbolic_link_audit_directory(self) -> None:
        proposal_hash = self._proposal_hash()
        real_audit = self.root / "real-audit"
        real_audit.mkdir()
        audit_link = self.root / "audit-link"
        try:
            audit_link.symlink_to(real_audit, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest("symbolic links are not available")

        with self.assertRaisesRegex(SystemExit, "symbolic link"):
            self._review(
                proposal_hash,
                audit_dir=audit_link,
            )

        self.assertEqual(list(real_audit.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
