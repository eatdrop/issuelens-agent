from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import stat
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .domain import Evidence


class CheckpointError(ValueError):
    """Raised when a resumable Agent checkpoint is invalid or unsafe."""


@dataclass(frozen=True, slots=True)
class AgentCheckpoint:
    run_id: str
    issue_hash: str
    repository_snapshot_hash: str
    next_step: int
    sequence: int
    elapsed_seconds: float
    observations: tuple[dict[str, Any], ...]
    evidence: tuple[Evidence, ...]
    completed: bool
    checkpoint_hash: str

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        issue_hash: str,
        repository_snapshot_hash: str,
        next_step: int,
        sequence: int,
        elapsed_seconds: float,
        observations: tuple[dict[str, Any], ...],
        evidence: tuple[Evidence, ...],
        completed: bool = False,
    ) -> AgentCheckpoint:
        payload = _checkpoint_payload(
            run_id=run_id,
            issue_hash=issue_hash,
            repository_snapshot_hash=repository_snapshot_hash,
            next_step=next_step,
            sequence=sequence,
            elapsed_seconds=elapsed_seconds,
            observations=observations,
            evidence=evidence,
            completed=completed,
        )
        result = cls(
            run_id=run_id,
            issue_hash=issue_hash,
            repository_snapshot_hash=repository_snapshot_hash,
            next_step=next_step,
            sequence=sequence,
            elapsed_seconds=elapsed_seconds,
            observations=observations,
            evidence=evidence,
            completed=completed,
            checkpoint_hash=_checkpoint_hash(payload),
        )
        result._validate()
        return result

    def to_json(self) -> str:
        payload = _checkpoint_payload(
            run_id=self.run_id,
            issue_hash=self.issue_hash,
            repository_snapshot_hash=self.repository_snapshot_hash,
            next_step=self.next_step,
            sequence=self.sequence,
            elapsed_seconds=self.elapsed_seconds,
            observations=self.observations,
            evidence=self.evidence,
            completed=self.completed,
        )
        payload["checkpoint_hash"] = self.checkpoint_hash
        return _canonical_json(payload)

    @classmethod
    def from_json(cls, value: str) -> AgentCheckpoint:
        if not isinstance(value, str) or len(value.encode("utf-8")) > _MAX_BYTES:
            raise CheckpointError("checkpoint is not bounded UTF-8 text")
        try:
            payload = json.loads(value)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise CheckpointError("checkpoint is not valid JSON") from exc
        if not isinstance(payload, dict) or set(payload) != _CHECKPOINT_FIELDS:
            raise CheckpointError("checkpoint fields are invalid")
        if payload["schema_version"] != 1:
            raise CheckpointError("checkpoint schema version is unsupported")
        observations = payload["observations"]
        evidence_payload = payload["evidence"]
        if not isinstance(observations, list) or not isinstance(evidence_payload, list):
            raise CheckpointError("checkpoint arrays are invalid")
        evidence: list[Evidence] = []
        for item in evidence_payload:
            if not isinstance(item, dict) or set(item) != _EVIDENCE_FIELDS:
                raise CheckpointError("checkpoint evidence fields are invalid")
            evidence.append(Evidence(**item))
        result = cls(
            run_id=payload["run_id"],
            issue_hash=payload["issue_hash"],
            repository_snapshot_hash=payload["repository_snapshot_hash"],
            next_step=payload["next_step"],
            sequence=payload["sequence"],
            elapsed_seconds=payload["elapsed_seconds"],
            observations=tuple(observations),
            evidence=tuple(evidence),
            completed=payload["completed"],
            checkpoint_hash=payload["checkpoint_hash"],
        )
        result._validate()
        if not result.verify_integrity():
            raise CheckpointError("checkpoint integrity validation failed")
        return result

    def verify_integrity(self) -> bool:
        try:
            payload = _checkpoint_payload(
                run_id=self.run_id,
                issue_hash=self.issue_hash,
                repository_snapshot_hash=self.repository_snapshot_hash,
                next_step=self.next_step,
                sequence=self.sequence,
                elapsed_seconds=self.elapsed_seconds,
                observations=self.observations,
                evidence=self.evidence,
                completed=self.completed,
            )
            return hmac.compare_digest(
                self.checkpoint_hash,
                _checkpoint_hash(payload),
            )
        except (AttributeError, TypeError, ValueError):
            return False

    def _validate(self) -> None:
        if (
            not isinstance(self.run_id, str)
            or not self.run_id.strip()
            or len(self.run_id) > 128
            or "\x00" in self.run_id
        ):
            raise CheckpointError("checkpoint run_id is invalid")
        _require_sha256(self.issue_hash, "issue_hash")
        _require_sha256(self.repository_snapshot_hash, "repository_snapshot_hash")
        _require_sha256(self.checkpoint_hash, "checkpoint_hash")
        if type(self.next_step) is not int or not 0 <= self.next_step <= 10_000:
            raise CheckpointError("checkpoint next_step is invalid")
        if type(self.sequence) is not int or not 0 <= self.sequence <= 100_000:
            raise CheckpointError("checkpoint sequence is invalid")
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, (int, float))
            or not 0 <= float(self.elapsed_seconds) <= 86_400
        ):
            raise CheckpointError("checkpoint elapsed time is invalid")
        if type(self.completed) is not bool:
            raise CheckpointError("checkpoint completed flag is invalid")
        if len(self.observations) > 10_000 or len(self.evidence) > 10_000:
            raise CheckpointError("checkpoint collections exceed their limits")
        if any(not isinstance(item, dict) for item in self.observations):
            raise CheckpointError("checkpoint observations must be objects")
        for item in self.evidence:
            if not isinstance(item, Evidence):
                raise CheckpointError("checkpoint evidence type is invalid")
            for name, value, limit in (
                ("evidence_id", item.evidence_id, 200),
                ("path", item.path, 1_000),
                ("snippet", item.snippet, 20_000),
                ("reason", item.reason, 4_000),
            ):
                if not isinstance(value, str) or not value or len(value) > limit:
                    raise CheckpointError(f"checkpoint evidence {name} is invalid")
            if (
                type(item.start_line) is not int
                or type(item.end_line) is not int
                or item.start_line < 1
                or item.end_line < item.start_line
            ):
                raise CheckpointError("checkpoint evidence line range is invalid")
            _require_sha256(item.content_hash, "evidence content_hash")
            if (
                isinstance(item.score, bool)
                or not isinstance(item.score, (int, float))
                or not math.isfinite(float(item.score))
            ):
                raise CheckpointError("checkpoint evidence score is invalid")


class CheckpointStore:
    def __init__(self, run_path: str | Path) -> None:
        self.run_path = Path(run_path).expanduser().resolve()
        self.path = self.run_path / "checkpoint.json"

    def save(self, checkpoint: AgentCheckpoint) -> Path:
        if not isinstance(checkpoint, AgentCheckpoint) or not checkpoint.verify_integrity():
            raise CheckpointError("only valid checkpoints can be saved")
        if self.run_path.is_symlink() or not self.run_path.is_dir():
            raise CheckpointError("checkpoint run directory is invalid")
        serialized = (checkpoint.to_json() + "\n").encode("utf-8")
        if len(serialized) > _MAX_BYTES:
            raise CheckpointError("checkpoint exceeds the size limit")
        descriptor = -1
        temporary: Path | None = None
        try:
            descriptor, name = tempfile.mkstemp(
                prefix=".checkpoint-",
                suffix=".tmp",
                dir=self.run_path,
            )
            temporary = Path(name)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.is_symlink():
                raise CheckpointError("checkpoint path cannot be a symlink")
            os.replace(temporary, self.path)
            temporary = None
            return self.path
        except CheckpointError:
            raise
        except OSError as exc:
            raise CheckpointError("checkpoint could not be saved atomically") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def load(self) -> AgentCheckpoint:
        try:
            metadata = self.path.lstat()
        except OSError as exc:
            raise CheckpointError("checkpoint was not found safely") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CheckpointError("checkpoint was not found safely")
        if metadata.st_size > _MAX_BYTES:
            raise CheckpointError("checkpoint exceeds the size limit")
        descriptor = -1
        try:
            descriptor = os.open(
                self.path,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = -1
                content = stream.read(_MAX_BYTES + 1)
            if len(content) > _MAX_BYTES:
                raise CheckpointError("checkpoint exceeds the size limit")
            return AgentCheckpoint.from_json(content.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise CheckpointError("checkpoint is not valid UTF-8") from exc
        except OSError as exc:
            raise CheckpointError("checkpoint could not be read safely") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)


_MAX_BYTES = 2_000_000
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_HASH_DOMAIN = b"issuelens.agent-checkpoint.v1"
_CHECKPOINT_FIELDS = {
    "checkpoint_hash",
    "completed",
    "elapsed_seconds",
    "evidence",
    "issue_hash",
    "next_step",
    "observations",
    "repository_snapshot_hash",
    "run_id",
    "schema_version",
    "sequence",
}
_EVIDENCE_FIELDS = {
    "content_hash",
    "end_line",
    "evidence_id",
    "path",
    "reason",
    "score",
    "snippet",
    "start_line",
}


def issue_digest(issue_text: str) -> str:
    if not isinstance(issue_text, str):
        raise CheckpointError("issue text must be text")
    return hashlib.sha256(issue_text.encode("utf-8")).hexdigest()


def _checkpoint_payload(
    *,
    run_id: str,
    issue_hash: str,
    repository_snapshot_hash: str,
    next_step: int,
    sequence: int,
    elapsed_seconds: float,
    observations: tuple[dict[str, Any], ...],
    evidence: tuple[Evidence, ...],
    completed: bool,
) -> dict[str, object]:
    return {
        "completed": completed,
        "elapsed_seconds": round(float(elapsed_seconds), 6),
        "evidence": [asdict(item) for item in evidence],
        "issue_hash": issue_hash,
        "next_step": next_step,
        "observations": list(observations),
        "repository_snapshot_hash": repository_snapshot_hash,
        "run_id": run_id,
        "schema_version": 1,
        "sequence": sequence,
    }


def _checkpoint_hash(payload: dict[str, object]) -> str:
    digest = hashlib.sha256()
    digest.update(_HASH_DOMAIN)
    digest.update(b"\0")
    digest.update(_canonical_json(payload).encode("utf-8"))
    return digest.hexdigest()


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _require_sha256(value: object, name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise CheckpointError(f"checkpoint {name} is invalid")
