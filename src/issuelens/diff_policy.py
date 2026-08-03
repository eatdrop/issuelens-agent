from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass

from .diff_parser import UnifiedDiff


class DiffPathPolicyError(ValueError):
    """Raised when a parsed diff references a path outside the safe policy."""


@dataclass(frozen=True)
class DiffPathValidation:
    changed_paths: tuple[str, ...]


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def validate_diff_paths(
    diff: UnifiedDiff,
    *,
    allowed_paths: Collection[str] | None = None,
) -> DiffPathValidation:
    """Validate and normalize every file path in a parsed unified diff.

    Git's conventional ``a/`` and ``b/`` prefixes are removed. Renames are
    intentionally rejected in this first policy version because they require a
    separate authorization model for both source and destination paths.
    """

    normalized_allowlist = (
        {_normalize_path(path, expected_prefix=None) for path in allowed_paths}
        if allowed_paths is not None
        else None
    )
    changed_paths: list[str] = []
    seen: set[str] = set()

    for file_patch in diff.files:
        old_path = (
            None
            if file_patch.old_path == "/dev/null"
            else _normalize_path(file_patch.old_path, expected_prefix="a")
        )
        new_path = (
            None
            if file_patch.new_path == "/dev/null"
            else _normalize_path(file_patch.new_path, expected_prefix="b")
        )

        if old_path is None and new_path is None:
            raise DiffPathPolicyError(
                "a file patch cannot use /dev/null for both paths"
            )
        if old_path is not None and new_path is not None and old_path != new_path:
            raise DiffPathPolicyError(
                f"renames are not allowed: {old_path!r} -> {new_path!r}"
            )

        target_path = new_path if new_path is not None else old_path
        assert target_path is not None

        if (
            normalized_allowlist is not None
            and target_path not in normalized_allowlist
        ):
            raise DiffPathPolicyError(
                f"path is not authorized by the allowlist: {target_path!r}"
            )
        if target_path in seen:
            raise DiffPathPolicyError(
                f"duplicate file patch is not allowed: {target_path!r}"
            )

        seen.add(target_path)
        changed_paths.append(target_path)

    return DiffPathValidation(changed_paths=tuple(changed_paths))


def _normalize_path(path: str, *, expected_prefix: str | None) -> str:
    if not isinstance(path, str) or not path:
        raise DiffPathPolicyError("diff path must be non-empty text")
    if "\x00" in path:
        raise DiffPathPolicyError("diff path contains a NUL byte")
    if path.startswith("/") or path.startswith("\\\\") or _WINDOWS_DRIVE.match(path):
        raise DiffPathPolicyError(f"absolute path is not allowed: {path!r}")
    if "\\" in path:
        raise DiffPathPolicyError(
            f"backslash paths are not supported by the safe policy: {path!r}"
        )
    if path.startswith('"') or path.endswith('"'):
        raise DiffPathPolicyError(
            f"quoted diff paths are not supported by the safe policy: {path!r}"
        )

    parts = path.split("/")
    if expected_prefix is not None and len(parts) > 1 and parts[0] == expected_prefix:
        parts = parts[1:]

    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise DiffPathPolicyError(f"unsafe path segments are not allowed: {path!r}")
    if ".git" in parts:
        raise DiffPathPolicyError(f".git paths are not allowed: {path!r}")

    return "/".join(parts)
