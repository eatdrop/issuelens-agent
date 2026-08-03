from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .patch_proposal import PatchProposal


class PatchApprovalError(ValueError):
    """Raised when an approval record is malformed or no longer valid."""


class InvalidPatchApprovalError(PatchApprovalError):
    """Raised when an approval does not match the requested patch operation."""


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_HASH_DOMAIN = b"issuelens.patch-approval.v1"


@dataclass(frozen=True, slots=True)
class PatchApproval:
    run_id: str
    proposal_hash: str
    base_snapshot_hash: str
    approved_by: str
    approved_at: str
    approval_hash: str

    def __post_init__(self) -> None:
        _validate_identifier(self.run_id, field_name="run_id")
        _validate_identifier(self.approved_by, field_name="approved_by")
        _validate_sha256(self.proposal_hash, field_name="proposal_hash")
        _validate_sha256(
            self.base_snapshot_hash,
            field_name="base_snapshot_hash",
        )
        normalized_time = _normalize_timestamp_text(self.approved_at)
        if self.approved_at != normalized_time:
            raise PatchApprovalError(
                "approved_at must be a normalized UTC ISO-8601 timestamp"
            )
        expected_hash = _calculate_approval_hash(
            run_id=self.run_id,
            proposal_hash=self.proposal_hash,
            base_snapshot_hash=self.base_snapshot_hash,
            approved_by=self.approved_by,
            approved_at=self.approved_at,
        )
        if not hmac.compare_digest(self.approval_hash, expected_hash):
            raise PatchApprovalError(
                "approval hash does not match approval content"
            )

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        proposal: PatchProposal,
        approved_by: str,
        approved_at: datetime | None = None,
    ) -> "PatchApproval":
        if not proposal.verify_integrity():
            raise PatchApprovalError("cannot approve a proposal with invalid integrity")
        normalized_run_id = _validate_identifier(run_id, field_name="run_id")
        normalized_approver = _validate_identifier(
            approved_by,
            field_name="approved_by",
        )
        normalized_time = _normalize_datetime(
            approved_at or datetime.now(timezone.utc)
        )
        approval_hash = _calculate_approval_hash(
            run_id=normalized_run_id,
            proposal_hash=proposal.proposal_hash,
            base_snapshot_hash=proposal.base_snapshot_hash,
            approved_by=normalized_approver,
            approved_at=normalized_time,
        )
        return cls(
            run_id=normalized_run_id,
            proposal_hash=proposal.proposal_hash,
            base_snapshot_hash=proposal.base_snapshot_hash,
            approved_by=normalized_approver,
            approved_at=normalized_time,
            approval_hash=approval_hash,
        )

    def is_valid_for(
        self,
        *,
        run_id: str,
        proposal: PatchProposal,
        current_snapshot_hash: str,
    ) -> bool:
        if not self.verify_integrity() or not proposal.verify_integrity():
            return False
        if not isinstance(current_snapshot_hash, str):
            return False
        normalized_snapshot_hash = current_snapshot_hash.lower()
        if not _is_valid_sha256(normalized_snapshot_hash):
            return False
        return all(
            (
                hmac.compare_digest(self.run_id, run_id),
                hmac.compare_digest(
                    self.proposal_hash,
                    proposal.proposal_hash,
                ),
                hmac.compare_digest(
                    self.base_snapshot_hash,
                    proposal.base_snapshot_hash,
                ),
                hmac.compare_digest(
                    self.base_snapshot_hash,
                    normalized_snapshot_hash,
                ),
            )
        )

    def require_valid_for(
        self,
        *,
        run_id: str,
        proposal: PatchProposal,
        current_snapshot_hash: str,
    ) -> None:
        if not self.is_valid_for(
            run_id=run_id,
            proposal=proposal,
            current_snapshot_hash=current_snapshot_hash,
        ):
            raise InvalidPatchApprovalError(
                "approval does not match the run, proposal, or current snapshot"
            )

    def verify_integrity(self) -> bool:
        expected_hash = _calculate_approval_hash(
            run_id=self.run_id,
            proposal_hash=self.proposal_hash,
            base_snapshot_hash=self.base_snapshot_hash,
            approved_by=self.approved_by,
            approved_at=self.approved_at,
        )
        return hmac.compare_digest(self.approval_hash, expected_hash)


def _validate_identifier(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise PatchApprovalError(f"{field_name} must be text")
    normalized = value.strip()
    if not normalized or len(normalized) > 200:
        raise PatchApprovalError(
            f"{field_name} must be between 1 and 200 characters"
        )
    if any(ord(character) < 32 for character in normalized):
        raise PatchApprovalError(f"{field_name} contains control characters")
    return normalized


def _validate_sha256(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not _is_valid_sha256(value):
        raise PatchApprovalError(
            f"{field_name} must be a normalized lowercase SHA-256 digest"
        )


def _is_valid_sha256(value: str) -> bool:
    return _SHA256_PATTERN.fullmatch(value) is not None


def _normalize_datetime(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise PatchApprovalError("approved_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _normalize_timestamp_text(value: str) -> str:
    if not isinstance(value, str):
        raise PatchApprovalError("approved_at must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PatchApprovalError("approved_at is not valid ISO-8601 text") from exc
    return _normalize_datetime(parsed)


def _calculate_approval_hash(
    *,
    run_id: str,
    proposal_hash: str,
    base_snapshot_hash: str,
    approved_by: str,
    approved_at: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(_HASH_DOMAIN)
    for value in (
        run_id,
        proposal_hash,
        base_snapshot_hash,
        approved_by,
        approved_at,
    ):
        digest.update(b"\0")
        digest.update(value.encode("utf-8"))
    return digest.hexdigest()
