from __future__ import annotations

import ast
import fnmatch
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .domain import Evidence


_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}

_TEXT_SUFFIXES = {
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


class RepositoryAccessError(ValueError):
    """Raised when a requested repository operation violates the read policy."""


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    path: str
    line: int
    end_line: int


class ReadOnlyRepository:
    def __init__(self, root: str | Path, max_file_bytes: int = 512_000) -> None:
        self.root = Path(root).expanduser().resolve()
        self.max_file_bytes = max_file_bytes
        if not self.root.is_dir():
            raise RepositoryAccessError(f"repository does not exist: {self.root}")

    def _resolve(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise RepositoryAccessError("absolute paths are not allowed")
        if ".." in candidate.parts:
            raise RepositoryAccessError("parent path traversal is not allowed")
        resolved = (self.root / candidate).resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise RepositoryAccessError("path escapes repository root")
        if resolved.is_symlink():
            raise RepositoryAccessError("symbolic links are not readable")
        return resolved

    def list_files(self) -> list[str]:
        files: list[str] = []
        for path in self.root.rglob("*"):
            relative = path.relative_to(self.root)
            if any(part in _EXCLUDED_DIRS for part in relative.parts):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            if path.stat().st_size > self.max_file_bytes:
                continue
            files.append(relative.as_posix())
        return sorted(files)

    def read_text(self, relative_path: str) -> str:
        path = self._resolve(relative_path)
        if not path.is_file():
            raise RepositoryAccessError(f"file does not exist: {relative_path}")
        if path.suffix.casefold() not in _TEXT_SUFFIXES:
            raise RepositoryAccessError(f"unsupported file type: {path.suffix}")
        if path.stat().st_size > self.max_file_bytes:
            raise RepositoryAccessError("file exceeds configured size limit")
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RepositoryAccessError("file is not valid UTF-8 text") from exc

    def snapshot_hash(self) -> str:
        digest = hashlib.sha256()
        for relative_path in self.list_files():
            content = self.read_text(relative_path).encode("utf-8")
            digest.update(relative_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(content).digest())
            digest.update(b"\0")
        return digest.hexdigest()

    def search_text(
        self,
        query: str,
        *,
        glob: str = "*",
        limit: int = 40,
        reason: str = "文本匹配 / text match",
    ) -> list[Evidence]:
        normalized_query = query.strip().casefold()
        if not normalized_query:
            return []
        results: list[Evidence] = []
        for relative_path in self.list_files():
            if not fnmatch.fnmatch(relative_path, glob):
                continue
            text = self.read_text(relative_path)
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            for line_number, line in enumerate(text.splitlines(), start=1):
                if normalized_query not in line.casefold():
                    continue
                evidence_id = _evidence_id(
                    relative_path, line_number, line_number, normalized_query
                )
                results.append(
                    Evidence(
                        evidence_id=evidence_id,
                        path=relative_path,
                        start_line=line_number,
                        end_line=line_number,
                        snippet=line.strip()[:500],
                        reason=f"{reason}: {query}",
                        content_hash=content_hash,
                        score=1.0,
                    )
                )
                if len(results) >= limit:
                    return results
        return results

    def build_symbol_index(self) -> list[Symbol]:
        symbols: list[Symbol] = []
        for relative_path in self.list_files():
            if not relative_path.endswith(".py"):
                continue
            source = self.read_text(relative_path)
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(
                        Symbol(
                            name=node.name,
                            kind="function",
                            path=relative_path,
                            line=node.lineno,
                            end_line=getattr(node, "end_lineno", node.lineno),
                        )
                    )
                elif isinstance(node, ast.ClassDef):
                    symbols.append(
                        Symbol(
                            name=node.name,
                            kind="class",
                            path=relative_path,
                            line=node.lineno,
                            end_line=getattr(node, "end_lineno", node.lineno),
                        )
                    )
        return sorted(symbols, key=lambda item: (item.path, item.line, item.name))

    def symbol_evidence(
        self, symbol: Symbol, *, reason: str, score: float = 2.0
    ) -> Evidence:
        source = self.read_text(symbol.path)
        lines = source.splitlines()
        start = max(1, symbol.line)
        end = min(len(lines), max(start, symbol.end_line))
        snippet = "\n".join(lines[start - 1 : min(end, start + 5)])
        content_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        return Evidence(
            evidence_id=_evidence_id(symbol.path, start, end, symbol.name),
            path=symbol.path,
            start_line=start,
            end_line=end,
            snippet=snippet[:800],
            reason=reason,
            content_hash=content_hash,
            score=score,
        )

    def range_evidence(
        self,
        relative_path: str,
        *,
        start_line: int = 1,
        end_line: int | None = None,
        reason: str = "有界文件读取 / bounded file read",
        score: float = 2.0,
    ) -> Evidence:
        source = self.read_text(relative_path)
        lines = source.splitlines()
        if not lines:
            raise RepositoryAccessError("cannot create evidence from an empty file")
        start = max(1, start_line)
        requested_end = end_line if end_line is not None else start + 79
        end = min(len(lines), max(start, requested_end))
        snippet = "\n".join(lines[start - 1 : end])
        content_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        return Evidence(
            evidence_id=_evidence_id(relative_path, start, end, reason),
            path=relative_path,
            start_line=start,
            end_line=end,
            snippet=snippet[:8_000],
            reason=reason,
            content_hash=content_hash,
            score=score,
        )


def _evidence_id(path: str, start: int, end: int, query: str) -> str:
    raw = f"{path}:{start}:{end}:{query}".encode("utf-8")
    return "ev-" + hashlib.sha256(raw).hexdigest()[:12]
