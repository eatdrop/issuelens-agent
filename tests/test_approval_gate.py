from __future__ import annotations

import unittest
from datetime import datetime, timezone

from issuelens.approval import PatchApproval
from issuelens.approval_gate import (
    PatchApplicationBlockedError,
    require_patch_application_approval,
)
from issuelens.patch_proposal import PatchProposal


BASE_SNAPSHOT = "a" * 64
OTHER_SNAPSHOT = "b" * 64
APPROVED_AT = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
DIFF = """\
--- a/src/example.py
+++ b/src/example.py
@@ -1 +1 @@
-old_value = 1
+new_value = 2
"""
OTHER_DIFF = """\
--- a/src/example.py
+++ b/src/example.py
@@ -1 +1 @@
-old_value = 1
+new_value = 3
"""


def _proposal(
    *,
    unified_diff: str = DIFF,
    base_snapshot_hash: str = BASE_SNAPSHOT,
) -> PatchProposal:
    return PatchProposal.create(
        unified_diff=unified_diff,
        base_snapshot_hash=base_snapshot_hash,
    )


def _approval(proposal: PatchProposal) -> PatchApproval:
    return PatchApproval.create(
        run_id="run-123",
        proposal=proposal,
        approved_by="reviewer",
        approved_at=APPROVED_AT,
    )


class PatchApplicationApprovalGateTests(unittest.TestCase):
    def test_allows_exactly_matching_approval(self) -> None:
        proposal = _proposal()

        result = require_patch_application_approval(
            run_id="run-123",
            proposal=proposal,
            approval=_approval(proposal),
            current_snapshot_hash=BASE_SNAPSHOT,
        )

        self.assertIsNone(result)

    def test_blocks_different_run(self) -> None:
        proposal = _proposal()

        with self.assertRaises(PatchApplicationBlockedError):
            require_patch_application_approval(
                run_id="run-456",
                proposal=proposal,
                approval=_approval(proposal),
                current_snapshot_hash=BASE_SNAPSHOT,
            )

    def test_blocks_different_proposal(self) -> None:
        approved_proposal = _proposal()
        replacement_proposal = _proposal(unified_diff=OTHER_DIFF)

        with self.assertRaises(PatchApplicationBlockedError):
            require_patch_application_approval(
                run_id="run-123",
                proposal=replacement_proposal,
                approval=_approval(approved_proposal),
                current_snapshot_hash=BASE_SNAPSHOT,
            )

    def test_blocks_changed_repository_snapshot(self) -> None:
        proposal = _proposal()

        with self.assertRaises(PatchApplicationBlockedError):
            require_patch_application_approval(
                run_id="run-123",
                proposal=proposal,
                approval=_approval(proposal),
                current_snapshot_hash=OTHER_SNAPSHOT,
            )

    def test_blocks_invalid_snapshot_input(self) -> None:
        proposal = _proposal()

        with self.assertRaises(PatchApplicationBlockedError):
            require_patch_application_approval(
                run_id="run-123",
                proposal=proposal,
                approval=_approval(proposal),
                current_snapshot_hash=None,  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
