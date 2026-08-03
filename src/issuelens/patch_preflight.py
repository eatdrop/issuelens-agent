from __future__ import annotations

import hashlib
import hmac
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator, Literal

from .approval import PatchApproval
from .approval_gate import require_patch_application_approval
from .diff_parser import DiffHunk, FilePatch, parse_unified_diff
from .diff_policy import validate_diff_paths
from .patch_proposal import PatchProposal
from .repository import ReadOnlyRepository, RepositoryAccessError


class PatchPreflightError(ValueError):
    """Raised when a patch cannot be applied safely to a temporary copy."""


@dataclass(frozen=True, slots=True)
class PatchFileChange:
    path: str
    operation: Literal["created", "modified", "deleted"]
    before_content_hash: str | None
    after_content_hash: str | None
    added_lines: int
    removed_lines: int


@dataclass(frozen=True, slots=True)
class PatchPreflightResult:
    run_id: str
    proposal_hash: str
    approval_hash: str
    base_snapshot_hash: str
    preview_snapshot_hash: str
    changed_paths: tuple[str, ...]
    file_changes: tuple[PatchFileChange, ...]
    receipt_hash: str

    def __post_init__(self) -> None:
        _validate_preflight_result(self)
        if not self.verify_integrity():
            raise PatchPreflightError(
                "preflight receipt hash does not match its content"
            )

    def to_json(self) -> str:
        payload = _receipt_payload(
            run_id=self.run_id,
            proposal_hash=self.proposal_hash,
            approval_hash=self.approval_hash,
            base_snapshot_hash=self.base_snapshot_hash,
            preview_snapshot_hash=self.preview_snapshot_hash,
            changed_paths=self.changed_paths,
            file_changes=self.file_changes,
        )
        payload["receipt_hash"] = self.receipt_hash
        return _canonical_json(payload)

    @classmethod
    def from_json(cls, value: str) -> PatchPreflightResult:
        if not isinstance(value, str):
            raise PatchPreflightError("preflight receipt JSON must be text")
        if len(value) > _MAX_RECEIPT_JSON_CHARACTERS:
            raise PatchPreflightError(
                "preflight receipt JSON exceeds the maximum size"
            )
        try:
            payload = json.loads(
                value,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except PatchPreflightError:
            raise
        except (json.JSONDecodeError, RecursionError) as exc:
            raise PatchPreflightError(
                "preflight receipt is not valid JSON"
            ) from exc

        if not isinstance(payload, dict):
            raise PatchPreflightError(
                "preflight receipt JSON must contain an object"
            )
        _require_exact_keys(
            payload,
            _RECEIPT_JSON_FIELDS,
            context="preflight receipt",
        )
        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] != _SCHEMA_VERSION
        ):
            raise PatchPreflightError(
                "unsupported preflight receipt schema version"
            )

        changed_paths_value = payload["changed_paths"]
        file_changes_value = payload["file_changes"]
        if not isinstance(changed_paths_value, list):
            raise PatchPreflightError("changed_paths must be a JSON array")
        if not isinstance(file_changes_value, list):
            raise PatchPreflightError("file_changes must be a JSON array")

        file_changes: list[PatchFileChange] = []
        for index, item in enumerate(file_changes_value):
            if not isinstance(item, dict):
                raise PatchPreflightError(
                    f"file_changes[{index}] must be a JSON object"
                )
            _require_exact_keys(
                item,
                _FILE_CHANGE_JSON_FIELDS,
                context=f"file_changes[{index}]",
            )
            file_changes.append(
                PatchFileChange(
                    path=item["path"],
                    operation=item["operation"],
                    before_content_hash=item["before_content_hash"],
                    after_content_hash=item["after_content_hash"],
                    added_lines=item["added_lines"],
                    removed_lines=item["removed_lines"],
                )
            )

        return cls(
            run_id=payload["run_id"],
            proposal_hash=payload["proposal_hash"],
            approval_hash=payload["approval_hash"],
            base_snapshot_hash=payload["base_snapshot_hash"],
            preview_snapshot_hash=payload["preview_snapshot_hash"],
            changed_paths=tuple(changed_paths_value),
            file_changes=tuple(file_changes),
            receipt_hash=payload["receipt_hash"],
        )

    def verify_integrity(self) -> bool:
        if not isinstance(self.receipt_hash, str):
            return False
        try:
            expected_hash = _calculate_receipt_hash(
                run_id=self.run_id,
                proposal_hash=self.proposal_hash,
                approval_hash=self.approval_hash,
                base_snapshot_hash=self.base_snapshot_hash,
                preview_snapshot_hash=self.preview_snapshot_hash,
                changed_paths=self.changed_paths,
                file_changes=self.file_changes,
            )
        except (AttributeError, TypeError, ValueError):
            return False
        return hmac.compare_digest(self.receipt_hash, expected_hash)


@dataclass(frozen=True, slots=True)
class PatchedWorkspace:
    """A temporary, approved patch preview that exists only in its context."""

    root: Path
    base_snapshot_hash: str
    preview_snapshot_hash: str
    changed_paths: tuple[str, ...]
    file_changes: tuple[PatchFileChange, ...]


_NO_NEWLINE_MARKER = r"\ No newline at end of file"
_RECEIPT_HASH_DOMAIN = b"issuelens.patch-preflight-receipt.v1"
_SCHEMA_VERSION = 1
_MAX_RECEIPT_JSON_CHARACTERS = 1_000_000
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_OPERATIONS = {"created", "modified", "deleted"}
_RECEIPT_JSON_FIELDS = {
    "schema_version",
    "run_id",
    "proposal_hash",
    "approval_hash",
    "base_snapshot_hash",
    "preview_snapshot_hash",
    "changed_paths",
    "file_changes",
    "receipt_hash",
}
_FILE_CHANGE_JSON_FIELDS = {
    "path",
    "operation",
    "before_content_hash",
    "after_content_hash",
    "added_lines",
    "removed_lines",
}


def preflight_patch_application(
    *,
    repository: ReadOnlyRepository,
    run_id: str,
    proposal: PatchProposal,
    approval: PatchApproval,
) -> PatchPreflightResult:
    """Apply an approved proposal to an isolated temporary repository copy."""

    with materialize_approved_patch(
        repository=repository,
        run_id=run_id,
        proposal=proposal,
        approval=approval,
    ) as workspace:
        receipt_hash = _calculate_receipt_hash(
            run_id=run_id,
            proposal_hash=proposal.proposal_hash,
            approval_hash=approval.approval_hash,
            base_snapshot_hash=workspace.base_snapshot_hash,
            preview_snapshot_hash=workspace.preview_snapshot_hash,
            changed_paths=workspace.changed_paths,
            file_changes=workspace.file_changes,
        )
        return PatchPreflightResult(
            run_id=run_id,
            proposal_hash=proposal.proposal_hash,
            approval_hash=approval.approval_hash,
            base_snapshot_hash=workspace.base_snapshot_hash,
            preview_snapshot_hash=workspace.preview_snapshot_hash,
            changed_paths=workspace.changed_paths,
            file_changes=workspace.file_changes,
            receipt_hash=receipt_hash,
        )


@contextmanager
def materialize_approved_patch(
    *,
    repository: ReadOnlyRepository,
    run_id: str,
    proposal: PatchProposal,
    approval: PatchApproval,
) -> Iterator[PatchedWorkspace]:
    """Yield a temporary patched copy after enforcing the approval gate."""

    if not isinstance(repository, ReadOnlyRepository):
        raise PatchPreflightError("repository must be a ReadOnlyRepository")

    try:
        current_snapshot_hash = repository.snapshot_hash()
    except (OSError, RepositoryAccessError) as exc:
        raise PatchPreflightError(
            "could not calculate the repository snapshot"
        ) from exc

    require_patch_application_approval(
        run_id=run_id,
        proposal=proposal,
        approval=approval,
        current_snapshot_hash=current_snapshot_hash,
    )

    parsed = parse_unified_diff(proposal.unified_diff)
    validated = validate_diff_paths(parsed)
    if validated.changed_paths != proposal.changed_paths:
        raise PatchPreflightError(
            "proposal paths changed after integrity validation"
        )

    try:
        with TemporaryDirectory(prefix="issuelens-preflight-") as temp_dir:
            temporary_root = Path(temp_dir)
            original_paths = tuple(repository.list_files())
            _copy_repository_files(
                repository,
                temporary_root,
                original_paths,
            )

            preview_repository = ReadOnlyRepository(
                temporary_root,
                max_file_bytes=repository.max_file_bytes,
            )
            copied_snapshot_hash = preview_repository.snapshot_hash()
            if not hmac.compare_digest(
                copied_snapshot_hash,
                current_snapshot_hash,
            ):
                raise PatchPreflightError(
                    "repository changed while creating the temporary copy"
                )

            original_path_set = set(original_paths)
            file_changes: list[PatchFileChange] = []
            for file_patch, changed_path in zip(
                parsed.files,
                validated.changed_paths,
                strict=True,
            ):
                file_changes.append(
                    _apply_file_patch(
                        temporary_root,
                        file_patch,
                        changed_path,
                        original_path_set,
                    )
                )

            _require_visible_preview_paths(
                preview_repository,
                parsed.files,
                validated.changed_paths,
            )
            preview_snapshot_hash = preview_repository.snapshot_hash()
            try:
                yield PatchedWorkspace(
                    root=temporary_root,
                    base_snapshot_hash=current_snapshot_hash,
                    preview_snapshot_hash=preview_snapshot_hash,
                    changed_paths=validated.changed_paths,
                    file_changes=tuple(file_changes),
                )
            finally:
                final_snapshot_hash = repository.snapshot_hash()
                if not hmac.compare_digest(
                    final_snapshot_hash,
                    current_snapshot_hash,
                ):
                    raise PatchPreflightError(
                        "repository changed during patch preflight"
                    )
    except PatchPreflightError:
        raise
    except (OSError, RepositoryAccessError) as exc:
        raise PatchPreflightError(
            "temporary patch application failed safely"
        ) from exc


def _copy_repository_files(
    repository: ReadOnlyRepository,
    temporary_root: Path,
    relative_paths: tuple[str, ...],
) -> None:
    for relative_path in relative_paths:
        target = _temporary_target(temporary_root, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            repository.read_text(relative_path).encode("utf-8")
        )


def _apply_file_patch(
    temporary_root: Path,
    file_patch: FilePatch,
    changed_path: str,
    original_paths: set[str],
) -> PatchFileChange:
    target = _temporary_target(temporary_root, changed_path)

    if file_patch.is_new_file:
        if changed_path in original_paths or target.exists():
            raise PatchPreflightError(
                f"new file already exists: {changed_path!r}"
            )
        source_text = ""
    else:
        if changed_path not in original_paths or not target.is_file():
            raise PatchPreflightError(
                f"source file does not exist: {changed_path!r}"
            )
        source_text = target.read_text(encoding="utf-8")

    before_content_hash = (
        None if file_patch.is_new_file else _content_hash(source_text)
    )
    output_lines, has_trailing_newline, newline = _apply_hunks(
        source_text,
        file_patch.hunks,
        path=changed_path,
        is_new_file=file_patch.is_new_file,
    )

    if file_patch.is_deleted_file:
        if output_lines:
            raise PatchPreflightError(
                f"deleted file patch leaves content behind: {changed_path!r}"
            )
        target.unlink()
        return _file_change(
            path=changed_path,
            operation="deleted",
            before_content_hash=before_content_hash,
            after_content_hash=None,
            file_patch=file_patch,
        )

    output_text = newline.join(output_lines)
    if output_lines and has_trailing_newline:
        output_text += newline
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(output_text, encoding="utf-8", newline="")
    return _file_change(
        path=changed_path,
        operation="created" if file_patch.is_new_file else "modified",
        before_content_hash=before_content_hash,
        after_content_hash=_content_hash(output_text),
        file_patch=file_patch,
    )


def _apply_hunks(
    source_text: str,
    hunks: tuple[DiffHunk, ...],
    *,
    path: str,
    is_new_file: bool,
) -> tuple[list[str], bool, str]:
    newline = _detect_newline(source_text, path=path)
    source_lines = source_text.splitlines()
    source_has_trailing_newline = source_text.endswith(("\n", "\r"))
    output_lines: list[str] = []
    source_cursor = 0

    for hunk in hunks:
        target_index = (
            hunk.old_start
            if hunk.old_count == 0
            else hunk.old_start - 1
        )
        if (
            target_index < source_cursor
            or target_index > len(source_lines)
        ):
            raise PatchPreflightError(
                f"hunk position is invalid for {path!r}"
            )

        output_lines.extend(source_lines[source_cursor:target_index])
        source_index = target_index

        for line in hunk.lines:
            if line == _NO_NEWLINE_MARKER:
                continue

            marker = line[0]
            content = line[1:]
            if marker == "+":
                output_lines.append(content)
                continue

            if (
                source_index >= len(source_lines)
                or source_lines[source_index] != content
            ):
                raise PatchPreflightError(
                    f"hunk context does not match {path!r}"
                )

            if marker == " ":
                output_lines.append(content)
            source_index += 1

        source_cursor = source_index

    output_lines.extend(source_lines[source_cursor:])
    has_trailing_newline = _result_has_trailing_newline(
        source_lines=source_lines,
        source_has_trailing_newline=source_has_trailing_newline,
        output_lines=output_lines,
        hunks=hunks,
        is_new_file=is_new_file,
    )
    return output_lines, has_trailing_newline, newline


def _result_has_trailing_newline(
    *,
    source_lines: list[str],
    source_has_trailing_newline: bool,
    output_lines: list[str],
    hunks: tuple[DiffHunk, ...],
    is_new_file: bool,
) -> bool:
    if not output_lines:
        return False

    last_hunk = hunks[-1]
    old_range_end = (
        last_hunk.old_start + last_hunk.old_count - 1
        if last_hunk.old_count
        else last_hunk.old_start
    )
    touches_old_end = old_range_end >= len(source_lines)
    if not is_new_file and not touches_old_end:
        return source_has_trailing_newline

    new_range_end = (
        last_hunk.new_start + last_hunk.new_count - 1
        if last_hunk.new_count
        else last_hunk.new_start
    )
    if last_hunk.new_count and new_range_end >= len(output_lines):
        return not _new_side_ends_with_no_newline(last_hunk)
    return True


def _new_side_ends_with_no_newline(hunk: DiffHunk) -> bool:
    last_new_line_index: int | None = None
    for index, line in enumerate(hunk.lines):
        if line != _NO_NEWLINE_MARKER and line.startswith((" ", "+")):
            last_new_line_index = index
    if last_new_line_index is None:
        return False
    marker_index = last_new_line_index + 1
    return (
        marker_index < len(hunk.lines)
        and hunk.lines[marker_index] == _NO_NEWLINE_MARKER
    )


def _detect_newline(source_text: str, *, path: str) -> str:
    without_crlf = source_text.replace("\r\n", "")
    if "\r" in without_crlf:
        raise PatchPreflightError(
            f"bare carriage returns are not supported: {path!r}"
        )
    if "\r\n" in source_text and "\n" in without_crlf:
        raise PatchPreflightError(
            f"mixed line endings are not supported: {path!r}"
        )
    return "\r\n" if "\r\n" in source_text else "\n"


def _require_visible_preview_paths(
    preview_repository: ReadOnlyRepository,
    file_patches: tuple[FilePatch, ...],
    changed_paths: tuple[str, ...],
) -> None:
    preview_paths = set(preview_repository.list_files())
    for file_patch, changed_path in zip(
        file_patches,
        changed_paths,
        strict=True,
    ):
        if file_patch.is_deleted_file:
            if changed_path in preview_paths:
                raise PatchPreflightError(
                    f"deleted file remains visible: {changed_path!r}"
                )
        elif changed_path not in preview_paths:
            raise PatchPreflightError(
                "changed file is outside the safe text policy: "
                f"{changed_path!r}"
            )


def _temporary_target(root: Path, relative_path: str) -> Path:
    target = (root / relative_path).resolve()
    resolved_root = root.resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise PatchPreflightError(
            f"temporary path escapes repository copy: {relative_path!r}"
        )
    return target


def _file_change(
    *,
    path: str,
    operation: Literal["created", "modified", "deleted"],
    before_content_hash: str | None,
    after_content_hash: str | None,
    file_patch: FilePatch,
) -> PatchFileChange:
    return PatchFileChange(
        path=path,
        operation=operation,
        before_content_hash=before_content_hash,
        after_content_hash=after_content_hash,
        added_lines=sum(
            hunk.added_line_count for hunk in file_patch.hunks
        ),
        removed_lines=sum(
            hunk.removed_line_count for hunk in file_patch.hunks
        ),
    )


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _calculate_receipt_hash(
    *,
    run_id: str,
    proposal_hash: str,
    approval_hash: str,
    base_snapshot_hash: str,
    preview_snapshot_hash: str,
    changed_paths: tuple[str, ...],
    file_changes: tuple[PatchFileChange, ...],
) -> str:
    payload = _receipt_payload(
        run_id=run_id,
        proposal_hash=proposal_hash,
        approval_hash=approval_hash,
        base_snapshot_hash=base_snapshot_hash,
        preview_snapshot_hash=preview_snapshot_hash,
        changed_paths=changed_paths,
        file_changes=file_changes,
    )
    canonical_payload = _canonical_json(payload).encode("utf-8")
    digest = hashlib.sha256()
    digest.update(_RECEIPT_HASH_DOMAIN)
    digest.update(b"\0")
    digest.update(canonical_payload)
    return digest.hexdigest()


def _receipt_payload(
    *,
    run_id: str,
    proposal_hash: str,
    approval_hash: str,
    base_snapshot_hash: str,
    preview_snapshot_hash: str,
    changed_paths: tuple[str, ...],
    file_changes: tuple[PatchFileChange, ...],
) -> dict[str, object]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "approval_hash": approval_hash,
        "base_snapshot_hash": base_snapshot_hash,
        "changed_paths": list(changed_paths),
        "file_changes": [
            {
                "added_lines": change.added_lines,
                "after_content_hash": change.after_content_hash,
                "before_content_hash": change.before_content_hash,
                "operation": change.operation,
                "path": change.path,
                "removed_lines": change.removed_lines,
            }
            for change in file_changes
        ],
        "preview_snapshot_hash": preview_snapshot_hash,
        "proposal_hash": proposal_hash,
        "run_id": run_id,
    }


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _validate_preflight_result(result: PatchPreflightResult) -> None:
    _require_non_empty_text(result.run_id, field_name="run_id")
    _require_sha256(result.proposal_hash, field_name="proposal_hash")
    _require_sha256(result.approval_hash, field_name="approval_hash")
    _require_sha256(
        result.base_snapshot_hash,
        field_name="base_snapshot_hash",
    )
    _require_sha256(
        result.preview_snapshot_hash,
        field_name="preview_snapshot_hash",
    )
    _require_sha256(result.receipt_hash, field_name="receipt_hash")

    if not isinstance(result.changed_paths, tuple) or not result.changed_paths:
        raise PatchPreflightError(
            "changed_paths must be a non-empty tuple"
        )
    if not isinstance(result.file_changes, tuple) or not result.file_changes:
        raise PatchPreflightError(
            "file_changes must be a non-empty tuple"
        )
    for path in result.changed_paths:
        _require_non_empty_text(path, field_name="changed path")
        if "\x00" in path:
            raise PatchPreflightError("changed path contains a NUL byte")

    for change in result.file_changes:
        _validate_file_change(change)
    if result.changed_paths != tuple(
        change.path for change in result.file_changes
    ):
        raise PatchPreflightError(
            "changed_paths must match file_changes in order"
        )


def _validate_file_change(change: PatchFileChange) -> None:
    if not isinstance(change, PatchFileChange):
        raise PatchPreflightError(
            "file_changes must contain PatchFileChange values"
        )
    _require_non_empty_text(change.path, field_name="file change path")
    if change.operation not in _OPERATIONS:
        raise PatchPreflightError("file change operation is invalid")
    _require_line_count(change.added_lines, field_name="added_lines")
    _require_line_count(change.removed_lines, field_name="removed_lines")

    if change.operation == "created":
        if change.before_content_hash is not None:
            raise PatchPreflightError(
                "created files cannot have a before_content_hash"
            )
        _require_sha256(
            change.after_content_hash,
            field_name="after_content_hash",
        )
    elif change.operation == "modified":
        _require_sha256(
            change.before_content_hash,
            field_name="before_content_hash",
        )
        _require_sha256(
            change.after_content_hash,
            field_name="after_content_hash",
        )
    else:
        _require_sha256(
            change.before_content_hash,
            field_name="before_content_hash",
        )
        if change.after_content_hash is not None:
            raise PatchPreflightError(
                "deleted files cannot have an after_content_hash"
            )


def _require_non_empty_text(value: object, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PatchPreflightError(f"{field_name} must be non-empty text")


def _require_sha256(value: object, *, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise PatchPreflightError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


def _require_line_count(value: object, *, field_name: str) -> None:
    if type(value) is not int or value < 0:
        raise PatchPreflightError(
            f"{field_name} must be a non-negative integer"
        )


def _require_exact_keys(
    value: dict[str, object],
    expected: set[str],
    *,
    context: str,
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append(f"missing={missing}")
        if unknown:
            details.append(f"unknown={unknown}")
        raise PatchPreflightError(
            f"{context} fields are invalid: {', '.join(details)}"
        )


def _unique_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PatchPreflightError(
                f"duplicate JSON object key: {key!r}"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise PatchPreflightError(
        f"non-standard JSON constant is not allowed: {value}"
    )
