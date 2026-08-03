from __future__ import annotations

import re
from dataclasses import dataclass


class UnifiedDiffParseError(ValueError):
    """Raised when text is not a supported, internally consistent unified diff."""


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    section: str
    lines: tuple[str, ...]

    @property
    def added_line_count(self) -> int:
        return sum(1 for line in self.lines if line.startswith("+"))

    @property
    def removed_line_count(self) -> int:
        return sum(1 for line in self.lines if line.startswith("-"))


@dataclass(frozen=True)
class FilePatch:
    old_path: str
    new_path: str
    hunks: tuple[DiffHunk, ...]

    @property
    def is_new_file(self) -> bool:
        return self.old_path == "/dev/null"

    @property
    def is_deleted_file(self) -> bool:
        return self.new_path == "/dev/null"


@dataclass(frozen=True)
class UnifiedDiff:
    files: tuple[FilePatch, ...]

    @property
    def changed_file_count(self) -> int:
        return len(self.files)


_HUNK_HEADER = re.compile(
    r"^@@ "
    r"-(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? "
    r"@@(?: (?P<section>.*))?$"
)

_IGNORABLE_METADATA_PREFIXES = (
    "diff --git ",
    "index ",
    "new file mode ",
    "deleted file mode ",
    "old mode ",
    "new mode ",
    "similarity index ",
    "dissimilarity index ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
)


def parse_unified_diff(text: str) -> UnifiedDiff:
    """Parse a textual unified diff without applying or executing it.

    The parser supports common Git-style metadata, multiple files, new/deleted
    files, optional hunk counts, and the no-newline marker. It validates that
    every hunk body matches the old/new line counts declared in its header.
    """

    if not isinstance(text, str) or not text.strip():
        raise UnifiedDiffParseError("unified diff must be non-empty text")

    lines = text.splitlines()
    file_patches: list[FilePatch] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.startswith("--- "):
            if _is_ignorable_outside_hunk(line):
                index += 1
                continue
            raise UnifiedDiffParseError(
                f"unexpected content before file header at line {index + 1}: {line!r}"
            )

        old_path = _parse_file_header(line, "---", index + 1)
        index += 1
        if index >= len(lines) or not lines[index].startswith("+++ "):
            raise UnifiedDiffParseError(
                f"missing new-file header after line {index}"
            )
        new_path = _parse_file_header(lines[index], "+++", index + 1)
        index += 1

        hunks: list[DiffHunk] = []
        while index < len(lines):
            line = lines[index]
            if line.startswith("--- ") or line.startswith("diff --git "):
                break
            if not line.startswith("@@ "):
                if _is_ignorable_outside_hunk(line):
                    index += 1
                    continue
                raise UnifiedDiffParseError(
                    f"unexpected content outside hunk at line {index + 1}: {line!r}"
                )

            hunk, index = _parse_hunk(lines, index)
            hunks.append(hunk)

        if not hunks:
            raise UnifiedDiffParseError(
                f"file patch {old_path!r} -> {new_path!r} contains no hunks"
            )
        file_patches.append(
            FilePatch(
                old_path=old_path,
                new_path=new_path,
                hunks=tuple(hunks),
            )
        )

    if not file_patches:
        raise UnifiedDiffParseError("no file patches were found")
    return UnifiedDiff(files=tuple(file_patches))


def _parse_hunk(lines: list[str], header_index: int) -> tuple[DiffHunk, int]:
    header = lines[header_index]
    match = _HUNK_HEADER.fullmatch(header)
    if match is None:
        raise UnifiedDiffParseError(
            f"malformed hunk header at line {header_index + 1}: {header!r}"
        )

    old_start = int(match.group("old_start"))
    old_count = int(match.group("old_count") or "1")
    new_start = int(match.group("new_start"))
    new_count = int(match.group("new_count") or "1")
    section = match.group("section") or ""

    body: list[str] = []
    old_seen = 0
    new_seen = 0
    index = header_index + 1

    while index < len(lines):
        line = lines[index]
        if line.startswith("@@ ") or line.startswith("--- ") or line.startswith(
            "diff --git "
        ):
            break
        if line == r"\ No newline at end of file":
            body.append(line)
            index += 1
            continue
        if not line or line[0] not in {" ", "+", "-"}:
            raise UnifiedDiffParseError(
                f"invalid hunk body line at line {index + 1}: {line!r}"
            )
        body.append(line)
        if line[0] in {" ", "-"}:
            old_seen += 1
        if line[0] in {" ", "+"}:
            new_seen += 1
        index += 1

    if old_seen != old_count or new_seen != new_count:
        raise UnifiedDiffParseError(
            "hunk line counts do not match header at line "
            f"{header_index + 1}: expected old/new {old_count}/{new_count}, "
            f"observed {old_seen}/{new_seen}"
        )

    return (
        DiffHunk(
            old_start=old_start,
            old_count=old_count,
            new_start=new_start,
            new_count=new_count,
            section=section,
            lines=tuple(body),
        ),
        index,
    )


def _parse_file_header(line: str, marker: str, line_number: int) -> str:
    payload = line[len(marker) + 1 :]
    path = payload.split("\t", 1)[0].strip()
    if not path:
        raise UnifiedDiffParseError(
            f"empty file path in {marker} header at line {line_number}"
        )
    return path


def _is_ignorable_outside_hunk(line: str) -> bool:
    return not line or line.startswith(_IGNORABLE_METADATA_PREFIXES)
