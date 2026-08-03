from __future__ import annotations

import dataclasses
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from issuelens.approval import PatchApproval
from issuelens.approval_gate import PatchApplicationBlockedError
from issuelens.patch_preflight import (
    PatchPreflightError,
    PatchPreflightResult,
    preflight_patch_application,
)
from issuelens.patch_proposal import PatchProposal
from issuelens.repository import ReadOnlyRepository


MODIFY_DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 value = 1
-print("old")
+print("new")
"""
OTHER_MODIFY_DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 value = 1
-print("old")
+print("other")
"""
CONFLICTING_DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 value = 1
-print("missing")
+print("new")
"""
NEW_FILE_DIFF = """\
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+answer = 42
+print(answer)
"""
DELETE_FILE_DIFF = """\
--- a/obsolete.py
+++ /dev/null
@@ -1,2 +0,0 @@
-old
-file
"""
UNSUPPORTED_FILE_DIFF = """\
--- /dev/null
+++ b/data.bin
@@ -0,0 +1 @@
+binary-like-content
"""


class PatchPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "app.py").write_text(
            'value = 1\nprint("old")\n',
            encoding="utf-8",
        )
        self.repository = ReadOnlyRepository(self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _proposal(self, diff: str) -> PatchProposal:
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

    def test_previews_modification_without_writing_repository(self) -> None:
        before_content = (self.root / "app.py").read_text(encoding="utf-8")
        before_snapshot = self.repository.snapshot_hash()
        proposal = self._proposal(MODIFY_DIFF)
        approval = self._approval(proposal)

        result = preflight_patch_application(
            repository=self.repository,
            run_id="run-123",
            proposal=proposal,
            approval=approval,
        )

        self.assertEqual(result.base_snapshot_hash, before_snapshot)
        self.assertNotEqual(result.preview_snapshot_hash, before_snapshot)
        self.assertEqual(result.changed_paths, ("app.py",))
        self.assertEqual(result.run_id, "run-123")
        self.assertEqual(result.proposal_hash, proposal.proposal_hash)
        self.assertEqual(result.approval_hash, approval.approval_hash)
        self.assertEqual(len(result.receipt_hash), 64)
        self.assertTrue(result.verify_integrity())
        change = result.file_changes[0]
        self.assertEqual(change.path, "app.py")
        self.assertEqual(change.operation, "modified")
        self.assertEqual(
            change.before_content_hash,
            _content_hash(before_content),
        )
        self.assertEqual(
            change.after_content_hash,
            _content_hash('value = 1\nprint("new")\n'),
        )
        self.assertEqual(change.added_lines, 1)
        self.assertEqual(change.removed_lines, 1)
        self.assertEqual(
            (self.root / "app.py").read_text(encoding="utf-8"),
            before_content,
        )
        self.assertEqual(self.repository.snapshot_hash(), before_snapshot)

    def test_previews_new_file_without_creating_it_in_repository(self) -> None:
        before_snapshot = self.repository.snapshot_hash()
        proposal = self._proposal(NEW_FILE_DIFF)

        result = preflight_patch_application(
            repository=self.repository,
            run_id="run-123",
            proposal=proposal,
            approval=self._approval(proposal),
        )

        self.assertEqual(result.changed_paths, ("new.py",))
        self.assertNotEqual(result.preview_snapshot_hash, before_snapshot)
        change = result.file_changes[0]
        self.assertEqual(change.path, "new.py")
        self.assertEqual(change.operation, "created")
        self.assertIsNone(change.before_content_hash)
        self.assertEqual(
            change.after_content_hash,
            _content_hash("answer = 42\nprint(answer)\n"),
        )
        self.assertEqual(change.added_lines, 2)
        self.assertEqual(change.removed_lines, 0)
        self.assertFalse((self.root / "new.py").exists())
        self.assertEqual(self.repository.snapshot_hash(), before_snapshot)

    def test_previews_deletion_without_removing_repository_file(self) -> None:
        obsolete = self.root / "obsolete.py"
        obsolete.write_text("old\nfile\n", encoding="utf-8")
        before_snapshot = self.repository.snapshot_hash()
        proposal = self._proposal(DELETE_FILE_DIFF)

        result = preflight_patch_application(
            repository=self.repository,
            run_id="run-123",
            proposal=proposal,
            approval=self._approval(proposal),
        )

        self.assertEqual(result.changed_paths, ("obsolete.py",))
        self.assertNotEqual(result.preview_snapshot_hash, before_snapshot)
        change = result.file_changes[0]
        self.assertEqual(change.path, "obsolete.py")
        self.assertEqual(change.operation, "deleted")
        self.assertEqual(
            change.before_content_hash,
            _content_hash("old\nfile\n"),
        )
        self.assertIsNone(change.after_content_hash)
        self.assertEqual(change.added_lines, 0)
        self.assertEqual(change.removed_lines, 2)
        self.assertEqual(
            obsolete.read_text(encoding="utf-8"),
            "old\nfile\n",
        )
        self.assertEqual(self.repository.snapshot_hash(), before_snapshot)

    def test_rejects_hunk_context_mismatch(self) -> None:
        before_content = (self.root / "app.py").read_text(encoding="utf-8")
        proposal = self._proposal(CONFLICTING_DIFF)

        with self.assertRaisesRegex(PatchPreflightError, "does not match"):
            preflight_patch_application(
                repository=self.repository,
                run_id="run-123",
                proposal=proposal,
                approval=self._approval(proposal),
            )

        self.assertEqual(
            (self.root / "app.py").read_text(encoding="utf-8"),
            before_content,
        )

    def test_rejects_approval_for_different_proposal(self) -> None:
        approved_proposal = self._proposal(OTHER_MODIFY_DIFF)
        candidate_proposal = self._proposal(MODIFY_DIFF)

        with self.assertRaises(PatchApplicationBlockedError):
            preflight_patch_application(
                repository=self.repository,
                run_id="run-123",
                proposal=candidate_proposal,
                approval=self._approval(approved_proposal),
            )

    def test_rejects_repository_change_after_approval(self) -> None:
        proposal = self._proposal(MODIFY_DIFF)
        approval = self._approval(proposal)
        (self.root / "app.py").write_text(
            'value = 2\nprint("changed")\n',
            encoding="utf-8",
        )

        with self.assertRaises(PatchApplicationBlockedError):
            preflight_patch_application(
                repository=self.repository,
                run_id="run-123",
                proposal=proposal,
                approval=approval,
            )

        self.assertEqual(
            (self.root / "app.py").read_text(encoding="utf-8"),
            'value = 2\nprint("changed")\n',
        )

    def test_rejects_file_outside_safe_text_policy(self) -> None:
        proposal = self._proposal(UNSUPPORTED_FILE_DIFF)

        with self.assertRaisesRegex(
            PatchPreflightError,
            "outside the safe text policy",
        ):
            preflight_patch_application(
                repository=self.repository,
                run_id="run-123",
                proposal=proposal,
                approval=self._approval(proposal),
            )

        self.assertFalse((self.root / "data.bin").exists())

    def test_receipt_detects_tampered_run_binding(self) -> None:
        proposal = self._proposal(MODIFY_DIFF)
        result = preflight_patch_application(
            repository=self.repository,
            run_id="run-123",
            proposal=proposal,
            approval=self._approval(proposal),
        )

        object.__setattr__(result, "run_id", "run-456")

        self.assertFalse(result.verify_integrity())

    def test_receipt_detects_tampered_file_audit(self) -> None:
        proposal = self._proposal(MODIFY_DIFF)
        result = preflight_patch_application(
            repository=self.repository,
            run_id="run-123",
            proposal=proposal,
            approval=self._approval(proposal),
        )
        tampered_change = dataclasses.replace(
            result.file_changes[0],
            added_lines=999,
        )

        object.__setattr__(
            result,
            "file_changes",
            (tampered_change,),
        )

        self.assertFalse(result.verify_integrity())

    def test_receipt_json_round_trip_is_deterministic(self) -> None:
        proposal = self._proposal(MODIFY_DIFF)
        result = preflight_patch_application(
            repository=self.repository,
            run_id="run-123",
            proposal=proposal,
            approval=self._approval(proposal),
        )

        serialized = result.to_json()
        restored = PatchPreflightResult.from_json(serialized)

        self.assertEqual(restored, result)
        self.assertEqual(restored.to_json(), serialized)
        self.assertEqual(json.loads(serialized)["schema_version"], 1)

    def test_receipt_json_rejects_tampered_content(self) -> None:
        proposal = self._proposal(MODIFY_DIFF)
        result = preflight_patch_application(
            repository=self.repository,
            run_id="run-123",
            proposal=proposal,
            approval=self._approval(proposal),
        )
        payload = json.loads(result.to_json())
        payload["run_id"] = "run-456"

        with self.assertRaisesRegex(
            PatchPreflightError,
            "receipt hash",
        ):
            PatchPreflightResult.from_json(json.dumps(payload))

    def test_receipt_json_rejects_unknown_and_duplicate_fields(self) -> None:
        proposal = self._proposal(MODIFY_DIFF)
        result = preflight_patch_application(
            repository=self.repository,
            run_id="run-123",
            proposal=proposal,
            approval=self._approval(proposal),
        )
        payload = json.loads(result.to_json())
        payload["unexpected"] = True

        with self.assertRaisesRegex(PatchPreflightError, "unknown"):
            PatchPreflightResult.from_json(json.dumps(payload))
        with self.assertRaisesRegex(PatchPreflightError, "duplicate"):
            PatchPreflightResult.from_json(
                '{"schema_version":1,"schema_version":1}'
            )

    def test_receipt_json_rejects_invalid_field_type(self) -> None:
        proposal = self._proposal(MODIFY_DIFF)
        result = preflight_patch_application(
            repository=self.repository,
            run_id="run-123",
            proposal=proposal,
            approval=self._approval(proposal),
        )
        payload = json.loads(result.to_json())
        payload["file_changes"][0]["added_lines"] = True

        with self.assertRaisesRegex(PatchPreflightError, "added_lines"):
            PatchPreflightResult.from_json(json.dumps(payload))


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
