from __future__ import annotations

import hmac
import os
import re
import stat
import tempfile
from pathlib import Path

from .patch_preflight import (
    PatchPreflightError,
    PatchPreflightResult,
)


class ReceiptAuditStoreError(ValueError):
    """Raised when a receipt cannot be stored or loaded safely."""


class ReceiptNotFoundError(ReceiptAuditStoreError):
    """Raised when a requested receipt is absent from the audit store."""


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_RECEIPT_FILE_BYTES = 4_000_000


class ReceiptAuditStore:
    def __init__(self, root: str | Path) -> None:
        if isinstance(root, str) and not root.strip():
            raise ReceiptAuditStoreError(
                "audit store root must be a non-empty path"
            )
        try:
            self.root = Path(root).expanduser().absolute()
        except TypeError as exc:
            raise ReceiptAuditStoreError(
                "audit store root must be a filesystem path"
            ) from exc

    def store(self, receipt: PatchPreflightResult) -> Path:
        if (
            not isinstance(receipt, PatchPreflightResult)
            or not receipt.verify_integrity()
        ):
            raise ReceiptAuditStoreError(
                "only valid preflight receipts can be stored"
            )

        self._prepare_root()
        target = self._receipt_path(receipt.receipt_hash)
        serialized = (receipt.to_json() + "\n").encode("utf-8")
        file_descriptor = -1
        temporary_path: Path | None = None

        try:
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=".receipt-",
                suffix=".tmp",
                dir=self.root,
            )
            temporary_path = Path(temporary_name)
            os.fchmod(file_descriptor, 0o600)
            handle = os.fdopen(file_descriptor, "wb")
            file_descriptor = -1
            with handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())

            try:
                os.link(
                    temporary_path,
                    target,
                    follow_symlinks=False,
                )
            except FileExistsError:
                existing = self.load(receipt.receipt_hash)
                if not hmac.compare_digest(
                    existing.to_json(),
                    receipt.to_json(),
                ):
                    raise ReceiptAuditStoreError(
                        "receipt hash collision or conflicting stored content"
                    )
                return target

            _sync_directory(self.root)
            return target
        except ReceiptAuditStoreError:
            raise
        except OSError as exc:
            raise ReceiptAuditStoreError(
                "could not publish the receipt atomically"
            ) from exc
        finally:
            if file_descriptor >= 0:
                os.close(file_descriptor)
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def load(self, receipt_hash: str) -> PatchPreflightResult:
        normalized_hash = _require_receipt_hash(receipt_hash)
        self._require_existing_root()
        target = self._receipt_path(normalized_hash)

        try:
            metadata = target.lstat()
        except FileNotFoundError as exc:
            raise ReceiptNotFoundError(
                f"receipt was not found: {normalized_hash}"
            ) from exc
        except OSError as exc:
            raise ReceiptAuditStoreError(
                "could not inspect the stored receipt"
            ) from exc

        if stat.S_ISLNK(metadata.st_mode):
            raise ReceiptAuditStoreError(
                "symbolic-link receipts are not allowed"
            )
        if not stat.S_ISREG(metadata.st_mode):
            raise ReceiptAuditStoreError(
                "stored receipt must be a regular file"
            )
        if metadata.st_size > _MAX_RECEIPT_FILE_BYTES:
            raise ReceiptAuditStoreError(
                "stored receipt exceeds the maximum size"
            )

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            file_descriptor = os.open(target, flags)
            with os.fdopen(file_descriptor, "rb") as handle:
                content = handle.read(_MAX_RECEIPT_FILE_BYTES + 1)
        except OSError as exc:
            raise ReceiptAuditStoreError(
                "could not read the stored receipt safely"
            ) from exc

        if len(content) > _MAX_RECEIPT_FILE_BYTES:
            raise ReceiptAuditStoreError(
                "stored receipt exceeds the maximum size"
            )
        try:
            serialized = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReceiptAuditStoreError(
                "stored receipt is not valid UTF-8"
            ) from exc

        try:
            receipt = PatchPreflightResult.from_json(serialized)
        except PatchPreflightError as exc:
            raise ReceiptAuditStoreError(
                "stored receipt failed integrity validation"
            ) from exc
        if not hmac.compare_digest(
            receipt.receipt_hash,
            normalized_hash,
        ):
            raise ReceiptAuditStoreError(
                "stored receipt does not match its filename"
            )
        return receipt

    def _prepare_root(self) -> None:
        if self.root.is_symlink():
            raise ReceiptAuditStoreError(
                "audit store root cannot be a symbolic link"
            )
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise ReceiptAuditStoreError(
                "could not create the audit store root"
            ) from exc
        if self.root.is_symlink() or not self.root.is_dir():
            raise ReceiptAuditStoreError(
                "audit store root must be a real directory"
            )

    def _require_existing_root(self) -> None:
        if self.root.is_symlink():
            raise ReceiptAuditStoreError(
                "audit store root cannot be a symbolic link"
            )
        if not self.root.exists():
            raise ReceiptNotFoundError("audit store does not exist")
        if not self.root.is_dir():
            raise ReceiptAuditStoreError(
                "audit store root must be a directory"
            )

    def _receipt_path(self, receipt_hash: str) -> Path:
        return self.root / f"{_require_receipt_hash(receipt_hash)}.json"


def _require_receipt_hash(value: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ReceiptAuditStoreError(
            "receipt hash must be a lowercase SHA-256 digest"
        )
    return value


def _sync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        file_descriptor = os.open(path, flags)
        try:
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)
    except OSError:
        pass
