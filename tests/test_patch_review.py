from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from issuelens.approval import PatchApproval
from issuelens.approval_gate import PatchApplicationBlockedError
from issuelens.audit_store import (
    ReceiptAuditStore,
    ReceiptAuditStoreError,
)
from issuelens.patch_preflight import (
    PatchPreflightError,
    preflight_patch_application,
)
from issuelens.patch_proposal import PatchProposal
from issuelens.patch_review import preflight_and_record_patch
from issuelens.repository import ReadOnlyRepository


DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-value = 1
+value = 2
"""
OTHER_DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-value = 1
+value = 3
"""
CONFLICTING_DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-missing = 1
+value = 2
"""


class PatchReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repository_root = self.root / "repository"
        self.repository_root.mkdir()
        self.source_path = self.repository_root / "app.py"
        self.source_path.write_text("value = 1\n", encoding="utf-8")
        self.repository = ReadOnlyRepository(self.repository_root)
        self.audit_root = self.root / "audit"
        self.audit_store = ReceiptAuditStore(self.audit_root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _proposal(self, diff: str = DIFF) -> PatchProposal:
        return PatchProposal.create(
            unified_diff=diff,
            base_snapshot_hash=self.repository.snapshot_hash(),
        )

    @staticmethod
    def _approval(proposal: PatchProposal) -> PatchApproval:
        return PatchApproval.create(
            run_id="run-123",
            proposal=proposal,
            approved_by="reviewer",
        )

    def test_runs_complete_review_and_preserves_repository(self) -> None:
        before_content = self.source_path.read_text(encoding="utf-8")
        before_snapshot = self.repository.snapshot_hash()
        proposal = self._proposal()

        recorded = preflight_and_record_patch(
            repository=self.repository,
            audit_store=self.audit_store,
            run_id="run-123",
            proposal=proposal,
            approval=self._approval(proposal),
        )

        self.assertTrue(recorded.receipt.verify_integrity())
        self.assertEqual(
            recorded.audit_path.name,
            f"{recorded.receipt.receipt_hash}.json",
        )
        self.assertEqual(
            self.audit_store.load(recorded.receipt.receipt_hash),
            recorded.receipt,
        )
        self.assertEqual(
            self.source_path.read_text(encoding="utf-8"),
            before_content,
        )
        self.assertEqual(self.repository.snapshot_hash(), before_snapshot)

    def test_invalid_approval_creates_no_audit_store(self) -> None:
        approved_proposal = self._proposal(OTHER_DIFF)
        candidate_proposal = self._proposal(DIFF)

        with self.assertRaises(PatchApplicationBlockedError):
            preflight_and_record_patch(
                repository=self.repository,
                audit_store=self.audit_store,
                run_id="run-123",
                proposal=candidate_proposal,
                approval=self._approval(approved_proposal),
            )

        self.assertFalse(self.audit_root.exists())

    def test_preflight_conflict_creates_no_audit_store(self) -> None:
        proposal = self._proposal(CONFLICTING_DIFF)

        with self.assertRaises(PatchPreflightError):
            preflight_and_record_patch(
                repository=self.repository,
                audit_store=self.audit_store,
                run_id="run-123",
                proposal=proposal,
                approval=self._approval(proposal),
            )

        self.assertFalse(self.audit_root.exists())

    def test_audit_failure_fails_closed_without_repository_change(self) -> None:
        before_content = self.source_path.read_text(encoding="utf-8")
        proposal = self._proposal()
        approval = self._approval(proposal)
        expected_receipt = preflight_patch_application(
            repository=self.repository,
            run_id="run-123",
            proposal=proposal,
            approval=approval,
        )
        self.audit_root.mkdir()
        occupied_path = (
            self.audit_root
            / f"{expected_receipt.receipt_hash}.json"
        )
        occupied_path.write_text("occupied\n", encoding="utf-8")

        with self.assertRaises(ReceiptAuditStoreError):
            preflight_and_record_patch(
                repository=self.repository,
                audit_store=self.audit_store,
                run_id="run-123",
                proposal=proposal,
                approval=approval,
            )

        self.assertEqual(
            self.source_path.read_text(encoding="utf-8"),
            before_content,
        )
        self.assertEqual(
            occupied_path.read_text(encoding="utf-8"),
            "occupied\n",
        )

    def test_repeated_review_reuses_same_audit_record(self) -> None:
        proposal = self._proposal()
        approval = self._approval(proposal)

        first = preflight_and_record_patch(
            repository=self.repository,
            audit_store=self.audit_store,
            run_id="run-123",
            proposal=proposal,
            approval=approval,
        )
        second = preflight_and_record_patch(
            repository=self.repository,
            audit_store=self.audit_store,
            run_id="run-123",
            proposal=proposal,
            approval=approval,
        )

        self.assertEqual(second, first)
        self.assertEqual(
            list(self.audit_root.glob("*.json")),
            [first.audit_path],
        )


if __name__ == "__main__":
    unittest.main()
