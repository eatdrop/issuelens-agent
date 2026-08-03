from __future__ import annotations

import re

from .domain import IssueSpec


_STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "before",
    "being",
    "does",
    "expected",
    "from",
    "have",
    "into",
    "issue",
    "should",
    "that",
    "their",
    "there",
    "these",
    "this",
    "when",
    "where",
    "with",
    "would",
}


def _unique(values: list[str], limit: int = 20) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if len(result) >= limit:
            break
    return tuple(result)


def parse_issue(text: str) -> IssueSpec:
    if not isinstance(text, str):
        raise ValueError("Issue must be text")
    try:
        encoded_size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("Issue must be valid UTF-8 text") from exc
    if encoded_size > MAX_ISSUE_BYTES:
        raise ValueError("Issue exceeds the size limit")
    if "\x00" in text:
        raise ValueError("Issue contains a NUL character")
    lines = [line.rstrip() for line in text.splitlines()]
    first_content = next(
        (line for line in lines if line.strip()),
        "未命名问题 / Untitled Issue",
    )
    title = first_content.lstrip("# ").strip()
    if len(title) > 500:
        title = title[:497] + "..."

    identifiers = re.findall(r"`([A-Za-z_][A-Za-z0-9_.]*)`", text)
    file_hints = re.findall(
        r"(?<![\w./-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.py)\b", text
    )
    exception_hints = re.findall(r"\b([A-Z][A-Za-z]+(?:Error|Exception))\b", text)
    raw_words = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b", text)
    keywords = [
        word
        for word in raw_words
        if word.casefold() not in _STOP_WORDS
        and not word.endswith(("Error", "Exception"))
    ]

    return IssueSpec(
        title=title,
        body=text.strip(),
        identifiers=_unique(identifiers, 12),
        file_hints=_unique(file_hints, 8),
        exception_hints=_unique(exception_hints, 8),
        keywords=_unique(keywords, 20),
    )


MAX_ISSUE_BYTES = 256_000
