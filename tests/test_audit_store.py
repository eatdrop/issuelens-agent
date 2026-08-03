from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from issuelens.approval import PatchApproval
from issuelens.audit_store import (
    ReceiptAuditStore,
    ReceiptAuditStoreError,
)
from issuelens.patch_preflight import (
    PatchPreflightResult,
    preflight_patch_application,
)
from issuelens.patch_proposal import PatchProposal
from issuelens.repository import ReadOnlyRepository


DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-value = 1
+value = 2
"""


class ReceiptAuditStoreTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_stores_and_loads_content_addressed_receipt(self) -> None:
        path = self.store.store(self.receipt)

        self.assertEqual(
            path.name,
            f"{self.receipt.receipt_hash}.json",
        )
        self.assertEqual(self.store.load(self.receipt.receipt_hash), self.receipt)
        self.assertEqual(
            path.read_text(encoding="utf-8"),
            self.receipt.to_json() + "\n",
        )
        if os.name == "posix":
            self.assertEqual(
                stat.S_IMODE(path.stat().st_mode),
                0o600,
            )

    def test_repeated_store_is_idempotent_without_overwrite(self) -> None:
        first_path = self.store.store(self.receipt)
        first_metadata = first_path.stat()
        first_content = first_path.read_bytes()

        second_path = self.store.store(self.receipt)

        self.assertEqual(second_path, first_path)
        self.assertEqual(second_path.stat().st_ino, first_metadata.st_ino)
        self.assertEqual(second_path.read_bytes(), first_content)
        self.assertEqual(
            list(self.audit_root.glob(".receipt-*.tmp")),
            [],
        )

    def test_refuses_to_overwrite_preoccupied_receipt_path(self) -> None:
        self.audit_root.mkdir()
        target = (
            self.audit_root
            / f"{self.receipt.receipt_hash}.json"
        )
        target.write_text("occupied\n", encoding="utf-8")

        with self.assertRaises(ReceiptAuditStoreError):
            self.store.store(self.receipt)

        self.assertEqual(target.read_text(encoding="utf-8"), "occupied\n")

    def test_rejects_tampered_stored_receipt(self) -> None:
        path = self.store.store(self.receipt)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["run_id"] = "run-456"
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(
            ReceiptAuditStoreError,
            "integrity",
        ):
            self.store.load(self.receipt.receipt_hash)

    def test_rejects_invalid_receipt_hash(self) -> None:
        with self.assertRaisesRegex(
            ReceiptAuditStoreError,
            "SHA-256",
        ):
            self.store.load("../receipt")

    def test_rejects_symbolic_link_receipt(self) -> None:
        self.audit_root.mkdir()
        outside = self.root / "outside.json"
        outside.write_text(self.receipt.to_json(), encoding="utf-8")
        target = (
            self.audit_root
            / f"{self.receipt.receipt_hash}.json"
        )
        try:
            target.symlink_to(outside)
        except (NotImplementedError, OSError):
            self.skipTest("symbolic links are not available")

        with self.assertRaisesRegex(
            ReceiptAuditStoreError,
            "symbolic-link",
        ):
            self.store.load(self.receipt.receipt_hash)


if __name__ == "__main__":
    unittest.main()
