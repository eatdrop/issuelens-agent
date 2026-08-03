from __future__ import annotations

from .approval import InvalidPatchApprovalError, PatchApproval
from .patch_proposal import PatchProposal


class PatchApplicationBlockedError(PermissionError):
    """Raised when patch application lacks a current matching approval."""


_BLOCKED_MESSAGE = "patch application requires a current matching approval"


def require_patch_application_approval(
    *,
    run_id: str,
    proposal: PatchProposal,
    approval: PatchApproval,
    current_snapshot_hash: str,
) -> None:
    """Block patch application unless every approval binding still matches."""

    if not isinstance(run_id, str):
        raise PatchApplicationBlockedError(_BLOCKED_MESSAGE)
    if not isinstance(proposal, PatchProposal):
        raise PatchApplicationBlockedError(_BLOCKED_MESSAGE)
    if not isinstance(approval, PatchApproval):
        raise PatchApplicationBlockedError(_BLOCKED_MESSAGE)

    try:
        approval.require_valid_for(
            run_id=run_id,
            proposal=proposal,
            current_snapshot_hash=current_snapshot_hash,
        )
    except InvalidPatchApprovalError as exc:
        raise PatchApplicationBlockedError(_BLOCKED_MESSAGE) from exc
