from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from issuelens.approval import PatchApproval
from issuelens.audit_report import render_preflight_report
from issuelens.audit_store import ReceiptAuditStore
from issuelens.cli import main
from issuelens.patch_preflight import preflight_patch_application
from issuelens.patch_proposal import PatchProposal
from issuelens.repository import ReadOnlyRepository


DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-value = 1
+value = 2
"""


class AuditReportCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        repository_root = self.root / "repository"
        repository_root.mkdir()
        (repository_root / "app.py").write_text(
            "value = 1\n",
            encoding="utf-8",
        )
        repository = ReadOnlyRepository(repository_root)
        proposal = PatchProposal.create(
            unified_diff=DIFF,
            base_snapshot_hash=repository.snapshot_hash(),
        )
        approval = PatchApproval.create(
            run_id="run-123",
            proposal=proposal,
            approved_by="reviewer",
        )
        self.receipt = preflight_patch_application(
            repository=repository,
            run_id="run-123",
            proposal=proposal,
            approval=approval,
        )
        self.audit_root = self.root / "audit"
        self.store = ReceiptAuditStore(self.audit_root)
        self.receipt_path = self.store.store(self.receipt)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run(self, receipt_hash: str) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "audit-report",
                    "--audit-dir",
                    str(self.audit_root),
                    "--receipt-hash",
                    receipt_hash,
                ]
            )
        return exit_code, output.getvalue()

    def test_outputs_verified_report_without_modifying_receipt(self) -> None:
        before_content = self.receipt_path.read_bytes()
        before_modified_ns = self.receipt_path.stat().st_mtime_ns
        before_entries = sorted(self.audit_root.iterdir())

        exit_code, output = self._run(self.receipt.receipt_hash)

        self.assertEqual(exit_code, 0)
        self.assertEqual(output, render_preflight_report(self.receipt))
        self.assertEqual(self.receipt_path.read_bytes(), before_content)
        self.assertEqual(
            self.receipt_path.stat().st_mtime_ns,
            before_modified_ns,
        )
        self.assertEqual(sorted(self.audit_root.iterdir()), before_entries)

    def test_rejects_invalid_receipt_hash(self) -> None:
        with self.assertRaisesRegex(SystemExit, "SHA-256"):
            self._run("../receipt")

    def test_rejects_missing_receipt(self) -> None:
        with self.assertRaisesRegex(SystemExit, "not found"):
            self._run("0" * 64)

    def test_rejects_tampered_receipt(self) -> None:
        payload = json.loads(
            self.receipt_path.read_text(encoding="utf-8")
        )
        payload["run_id"] = "run-456"
        self.receipt_path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(SystemExit, "integrity"):
            self._run(self.receipt.receipt_hash)


if __name__ == "__main__":
    unittest.main()
