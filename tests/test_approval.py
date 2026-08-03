import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from issuelens.approval import (
    InvalidPatchApprovalError,
    PatchApproval,
    PatchApprovalError,
)
from issuelens.patch_proposal import PatchProposal


BASE_SNAPSHOT = "a" * 64
OTHER_SNAPSHOT = "b" * 64
APPROVED_AT = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)


def _proposal(
    *,
    path: str = "src/service.py",
    snapshot: str = BASE_SNAPSHOT,
) -> PatchProposal:
    diff = (
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )
    return PatchProposal.create(
        unified_diff=diff,
        base_snapshot_hash=snapshot,
    )


class PatchApprovalTests(unittest.TestCase):
    def test_creates_approval_bound_to_run_proposal_and_snapshot(self) -> None:
        proposal = _proposal()
        approval = PatchApproval.create(
            run_id="run-123",
            proposal=proposal,
            approved_by="reviewer@example.com",
            approved_at=APPROVED_AT,
        )

        self.assertEqual(approval.run_id, "run-123")
        self.assertEqual(approval.proposal_hash, proposal.proposal_hash)
        self.assertEqual(approval.base_snapshot_hash, BASE_SNAPSHOT)
        self.assertTrue(approval.verify_integrity())
        self.assertTrue(
            approval.is_valid_for(
                run_id="run-123",
                proposal=proposal,
                current_snapshot_hash=BASE_SNAPSHOT,
            )
        )

    def test_invalidates_when_run_changes(self) -> None:
        proposal = _proposal()
        approval = PatchApproval.create(
            run_id="run-123",
            proposal=proposal,
            approved_by="reviewer",
            approved_at=APPROVED_AT,
        )

        self.assertFalse(
            approval.is_valid_for(
                run_id="run-456",
                proposal=proposal,
                current_snapshot_hash=BASE_SNAPSHOT,
            )
        )

    def test_invalidates_when_proposal_changes(self) -> None:
        proposal = _proposal()
        changed_proposal = _proposal(path="src/other.py")
        approval = PatchApproval.create(
            run_id="run-123",
            proposal=proposal,
            approved_by="reviewer",
            approved_at=APPROVED_AT,
        )

        with self.assertRaises(InvalidPatchApprovalError):
            approval.require_valid_for(
                run_id="run-123",
                proposal=changed_proposal,
                current_snapshot_hash=BASE_SNAPSHOT,
            )

    def test_invalidates_when_repository_snapshot_changes(self) -> None:
        proposal = _proposal()
        approval = PatchApproval.create(
            run_id="run-123",
            proposal=proposal,
            approved_by="reviewer",
            approved_at=APPROVED_AT,
        )

        self.assertFalse(
            approval.is_valid_for(
                run_id="run-123",
                proposal=proposal,
                current_snapshot_hash=OTHER_SNAPSHOT,
            )
        )

    def test_hash_changes_with_approver_or_time(self) -> None:
        proposal = _proposal()
        first = PatchApproval.create(
            run_id="run-123",
            proposal=proposal,
            approved_by="reviewer-a",
            approved_at=APPROVED_AT,
        )
        other_approver = PatchApproval.create(
            run_id="run-123",
            proposal=proposal,
            approved_by="reviewer-b",
            approved_at=APPROVED_AT,
        )
        other_time = PatchApproval.create(
            run_id="run-123",
            proposal=proposal,
            approved_by="reviewer-a",
            approved_at=APPROVED_AT + timedelta(seconds=1),
        )

        self.assertNotEqual(first.approval_hash, other_approver.approval_hash)
        self.assertNotEqual(first.approval_hash, other_time.approval_hash)

    def test_rejects_naive_approval_time(self) -> None:
        with self.assertRaisesRegex(PatchApprovalError, "timezone-aware"):
            PatchApproval.create(
                run_id="run-123",
                proposal=_proposal(),
                approved_by="reviewer",
                approved_at=datetime(2026, 7, 29, 12, 30),
            )

    def test_rejects_tampered_record(self) -> None:
        approval = PatchApproval.create(
            run_id="run-123",
            proposal=_proposal(),
            approved_by="reviewer",
            approved_at=APPROVED_AT,
        )

        with self.assertRaisesRegex(PatchApprovalError, "approval hash"):
            dataclasses.replace(approval, approval_hash="0" * 64)

    def test_invalid_snapshot_type_fails_closed(self) -> None:
        proposal = _proposal()
        approval = PatchApproval.create(
            run_id="run-123",
            proposal=proposal,
            approved_by="reviewer",
            approved_at=APPROVED_AT,
        )

        self.assertFalse(
            approval.is_valid_for(
                run_id="run-123",
                proposal=proposal,
                current_snapshot_hash=None,  # type: ignore[arg-type]
            )
        )


if __name__ == "__main__":
    unittest.main()
