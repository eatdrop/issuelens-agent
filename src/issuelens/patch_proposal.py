from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Collection
from dataclasses import dataclass

from .diff_parser import UnifiedDiffParseError, parse_unified_diff
from .diff_policy import DiffPathPolicyError, validate_diff_paths


class PatchProposalError(ValueError):
    """Raised when a candidate patch cannot be represented safely."""


class StalePatchProposalError(PatchProposalError):
    """Raised when a candidate patch targets a different repository snapshot."""


_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_HASH_DOMAIN = b"issuelens.patch-proposal.v1"


@dataclass(frozen=True, slots=True)
class PatchProposal:
    unified_diff: str
    base_snapshot_hash: str
    changed_paths: tuple[str, ...]
    proposal_hash: str

    def __post_init__(self) -> None:
        normalized_snapshot = _normalize_snapshot_hash(self.base_snapshot_hash)
        normalized_diff = _normalize_diff(self.unified_diff)
        parsed = parse_unified_diff(normalized_diff)
        validated = validate_diff_paths(parsed)
        expected_hash = _calculate_proposal_hash(
            normalized_diff,
            normalized_snapshot,
        )

        if self.base_snapshot_hash != normalized_snapshot:
            raise PatchProposalError("base snapshot hash must be normalized lowercase")
        if self.unified_diff != normalized_diff:
            raise PatchProposalError("unified diff must use normalized LF line endings")
        if self.changed_paths != validated.changed_paths:
            raise PatchProposalError(
                "changed paths do not match the paths derived from the unified diff"
            )
        if not hmac.compare_digest(self.proposal_hash, expected_hash):
            raise PatchProposalError("proposal hash does not match proposal content")

    @classmethod
    def create(
        cls,
        *,
        unified_diff: str,
        base_snapshot_hash: str,
        allowed_paths: Collection[str] | None = None,
    ) -> "PatchProposal":
        normalized_diff = _normalize_diff(unified_diff)
        normalized_snapshot = _normalize_snapshot_hash(base_snapshot_hash)
        parsed = parse_unified_diff(normalized_diff)
        validated = validate_diff_paths(
            parsed,
            allowed_paths=allowed_paths,
        )
        proposal_hash = _calculate_proposal_hash(
            normalized_diff,
            normalized_snapshot,
        )
        return cls(
            unified_diff=normalized_diff,
            base_snapshot_hash=normalized_snapshot,
            changed_paths=validated.changed_paths,
            proposal_hash=proposal_hash,
        )

    def is_valid_for_snapshot(self, current_snapshot_hash: str) -> bool:
        try:
            normalized_current = _normalize_snapshot_hash(current_snapshot_hash)
        except PatchProposalError:
            return False
        return hmac.compare_digest(
            self.base_snapshot_hash,
            normalized_current,
        )

    def require_current_snapshot(self, current_snapshot_hash: str) -> None:
        if not self.is_valid_for_snapshot(current_snapshot_hash):
            raise StalePatchProposalError(
                "candidate patch does not match the current repository snapshot"
            )

    def verify_integrity(self) -> bool:
        try:
            normalized_snapshot = _normalize_snapshot_hash(
                self.base_snapshot_hash
            )
            normalized_diff = _normalize_diff(self.unified_diff)
            parsed = parse_unified_diff(normalized_diff)
            validated = validate_diff_paths(parsed)
        except (
            PatchProposalError,
            UnifiedDiffParseError,
            DiffPathPolicyError,
        ):
            return False

        if self.base_snapshot_hash != normalized_snapshot:
            return False
        if self.unified_diff != normalized_diff:
            return False
        if self.changed_paths != validated.changed_paths:
            return False

        expected_hash = _calculate_proposal_hash(
            normalized_diff,
            normalized_snapshot,
        )
        return hmac.compare_digest(self.proposal_hash, expected_hash)


def _normalize_snapshot_hash(value: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise PatchProposalError(
            "repository snapshot must be a 64-character SHA-256 hex digest"
        )
    return value.lower()


def _normalize_diff(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PatchProposalError("candidate unified diff must be non-empty text")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def _calculate_proposal_hash(
    unified_diff: str,
    base_snapshot_hash: str,
) -> str:
    digest = hashlib.sha256()
    digest.update(_HASH_DOMAIN)
    digest.update(b"\0")
    digest.update(base_snapshot_hash.encode("ascii"))
    digest.update(b"\0")
    digest.update(unified_diff.encode("utf-8"))
    return digest.hexdigest()
