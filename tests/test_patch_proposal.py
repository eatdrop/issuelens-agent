import dataclasses
import unittest

from issuelens.diff_policy import DiffPathPolicyError
from issuelens.patch_proposal import (
    PatchProposal,
    PatchProposalError,
    StalePatchProposalError,
)


BASE_SNAPSHOT = "a" * 64
OTHER_SNAPSHOT = "b" * 64


def _diff(path: str = "src/service.py", *, newline: str = "\n") -> str:
    lines = [
        f"--- a/{path}",
        f"+++ b/{path}",
        "@@ -1 +1 @@",
        "-old",
        "+new",
        "",
    ]
    return newline.join(lines)


class PatchProposalTests(unittest.TestCase):
    def test_creates_snapshot_bound_proposal(self) -> None:
        proposal = PatchProposal.create(
            unified_diff=_diff(),
            base_snapshot_hash=BASE_SNAPSHOT,
            allowed_paths={"src/service.py"},
        )

        self.assertEqual(proposal.changed_paths, ("src/service.py",))
        self.assertEqual(len(proposal.proposal_hash), 64)
        self.assertTrue(proposal.verify_integrity())
        self.assertTrue(proposal.is_valid_for_snapshot(BASE_SNAPSHOT))
        self.assertFalse(proposal.is_valid_for_snapshot(OTHER_SNAPSHOT))

    def test_normalizes_crlf_and_uppercase_snapshot(self) -> None:
        lf_proposal = PatchProposal.create(
            unified_diff=_diff(),
            base_snapshot_hash=BASE_SNAPSHOT,
        )
        crlf_proposal = PatchProposal.create(
            unified_diff=_diff(newline="\r\n"),
            base_snapshot_hash=BASE_SNAPSHOT.upper(),
        )

        self.assertEqual(crlf_proposal.unified_diff, lf_proposal.unified_diff)
        self.assertEqual(crlf_proposal.base_snapshot_hash, BASE_SNAPSHOT)
        self.assertEqual(crlf_proposal.proposal_hash, lf_proposal.proposal_hash)

    def test_hash_changes_with_diff_or_snapshot(self) -> None:
        original = PatchProposal.create(
            unified_diff=_diff("src/service.py"),
            base_snapshot_hash=BASE_SNAPSHOT,
        )
        changed_diff = PatchProposal.create(
            unified_diff=_diff("src/other.py"),
            base_snapshot_hash=BASE_SNAPSHOT,
        )
        changed_snapshot = PatchProposal.create(
            unified_diff=_diff("src/service.py"),
            base_snapshot_hash=OTHER_SNAPSHOT,
        )

        self.assertNotEqual(original.proposal_hash, changed_diff.proposal_hash)
        self.assertNotEqual(original.proposal_hash, changed_snapshot.proposal_hash)

    def test_rejects_invalid_snapshot_hash(self) -> None:
        with self.assertRaisesRegex(PatchProposalError, "SHA-256"):
            PatchProposal.create(
                unified_diff=_diff(),
                base_snapshot_hash="not-a-sha256",
            )

    def test_rejects_path_outside_allowlist(self) -> None:
        with self.assertRaises(DiffPathPolicyError):
            PatchProposal.create(
                unified_diff=_diff("src/service.py"),
                base_snapshot_hash=BASE_SNAPSHOT,
                allowed_paths={"src/other.py"},
            )

    def test_requires_matching_current_snapshot(self) -> None:
        proposal = PatchProposal.create(
            unified_diff=_diff(),
            base_snapshot_hash=BASE_SNAPSHOT,
        )

        proposal.require_current_snapshot(BASE_SNAPSHOT)
        with self.assertRaises(StalePatchProposalError):
            proposal.require_current_snapshot(OTHER_SNAPSHOT)

    def test_frozen_model_rejects_tampering(self) -> None:
        proposal = PatchProposal.create(
            unified_diff=_diff(),
            base_snapshot_hash=BASE_SNAPSHOT,
        )

        with self.assertRaises(dataclasses.FrozenInstanceError):
            proposal.proposal_hash = "0" * 64  # type: ignore[misc]

    def test_integrity_rejects_tampered_changed_paths(self) -> None:
        proposal = PatchProposal.create(
            unified_diff=_diff(),
            base_snapshot_hash=BASE_SNAPSHOT,
        )
        object.__setattr__(
            proposal,
            "changed_paths",
            ("src/other.py",),
        )

        self.assertFalse(proposal.verify_integrity())


if __name__ == "__main__":
    unittest.main()
