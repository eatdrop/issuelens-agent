from __future__ import annotations

import hmac
from dataclasses import dataclass
from pathlib import Path

from .approval import PatchApproval
from .audit_store import ReceiptAuditStore
from .patch_preflight import (
    PatchPreflightResult,
    preflight_patch_application,
)
from .patch_proposal import PatchProposal
from .repository import ReadOnlyRepository


class PatchReviewError(RuntimeError):
    """Raised when the safe patch review workflow cannot be completed."""


@dataclass(frozen=True, slots=True)
class RecordedPatchPreflight:
    receipt: PatchPreflightResult
    audit_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, PatchPreflightResult):
            raise PatchReviewError(
                "recorded preflight must contain a preflight receipt"
            )
        if not self.receipt.verify_integrity():
            raise PatchReviewError(
                "recorded preflight receipt failed integrity validation"
            )
        if not isinstance(self.audit_path, Path):
            raise PatchReviewError(
                "recorded preflight audit path must be a Path"
            )
        if self.audit_path.name != f"{self.receipt.receipt_hash}.json":
            raise PatchReviewError(
                "recorded preflight path does not match the receipt hash"
            )


def preflight_and_record_patch(
    *,
    repository: ReadOnlyRepository,
    audit_store: ReceiptAuditStore,
    run_id: str,
    proposal: PatchProposal,
    approval: PatchApproval,
) -> RecordedPatchPreflight:
    """Run every safe review step and return only after verified persistence."""

    if not isinstance(audit_store, ReceiptAuditStore):
        raise PatchReviewError(
            "audit_store must be a ReceiptAuditStore"
        )

    receipt = preflight_patch_application(
        repository=repository,
        run_id=run_id,
        proposal=proposal,
        approval=approval,
    )
    audit_path = audit_store.store(receipt)
    stored_receipt = audit_store.load(receipt.receipt_hash)
    if not hmac.compare_digest(
        stored_receipt.to_json(),
        receipt.to_json(),
    ):
        raise PatchReviewError(
            "stored preflight receipt does not match the generated receipt"
        )
    return RecordedPatchPreflight(
        receipt=stored_receipt,
        audit_path=audit_path,
    )
