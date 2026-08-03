from __future__ import annotations

from html import escape

from .patch_preflight import PatchPreflightResult


class AuditReportError(ValueError):
    """Raised when a trustworthy audit report cannot be rendered."""


_OPERATION_LABELS = {
    "created": "新建 / Created",
    "modified": "修改 / Modified",
    "deleted": "删除 / Deleted",
}


def render_preflight_report(receipt: PatchPreflightResult) -> str:
    """Render a deterministic bilingual Markdown report without source text."""

    if (
        not isinstance(receipt, PatchPreflightResult)
        or not receipt.verify_integrity()
    ):
        raise AuditReportError(
            "a valid preflight receipt is required"
        )

    total_added = sum(
        change.added_lines for change in receipt.file_changes
    )
    total_removed = sum(
        change.removed_lines for change in receipt.file_changes
    )
    lines = [
        "# 补丁预检审计报告 / Patch Preflight Audit Report",
        "",
        "## 结果 / Result",
        "",
        "- 状态 / Status: **通过 / Passed**",
        "- 真实仓库写入 / Real repository write: **否 / No**",
        f"- 文件数 / Files: **{len(receipt.file_changes)}**",
        f"- 新增行 / Added lines: **{total_added}**",
        f"- 删除行 / Removed lines: **{total_removed}**",
        "",
        "## 安全绑定 / Security Bindings",
        "",
        "| 字段 / Field | 值 / Value |",
        "| --- | --- |",
        f"| 运行标识 / Run ID | {_code(receipt.run_id)} |",
        f"| 提案哈希 / Proposal Hash | {_code(receipt.proposal_hash)} |",
        f"| 审批哈希 / Approval Hash | {_code(receipt.approval_hash)} |",
        (
            "| 原仓库快照 / Base Snapshot | "
            f"{_code(receipt.base_snapshot_hash)} |"
        ),
        (
            "| 预览仓库快照 / Preview Snapshot | "
            f"{_code(receipt.preview_snapshot_hash)} |"
        ),
        f"| 回执哈希 / Receipt Hash | {_code(receipt.receipt_hash)} |",
        "",
        "## 文件变更 / File Changes",
        "",
        (
            "| 路径 / Path | 操作 / Operation | 新增 / Added | "
            "删除 / Removed | 修改前哈希 / Before Hash | "
            "修改后哈希 / After Hash |"
        ),
        "| --- | --- | ---: | ---: | --- | --- |",
    ]

    for change in receipt.file_changes:
        lines.append(
            "| "
            f"{_code(change.path)} | "
            f"{_OPERATION_LABELS[change.operation]} | "
            f"{change.added_lines} | "
            f"{change.removed_lines} | "
            f"{_optional_hash(change.before_content_hash)} | "
            f"{_optional_hash(change.after_content_hash)} |"
        )

    lines.extend(
        [
            "",
            "## 完整性与限制 / Integrity and Limitations",
            "",
            "- 回执完整性 / Receipt integrity: **已验证 / Verified**",
            (
                "- 源码正文 / Source content: "
                "**未包含 / Not included**"
            ),
            (
                "- SHA-256 可检测内容变化，但不等同于数字签名。 / "
                "SHA-256 detects content changes but is not a digital signature."
            ),
            (
                "- 本报告证明补丁已在临时副本中通过预检，不代表补丁已写入"
                "真实仓库。 / This report proves the patch passed preflight "
                "in a temporary copy; it does not mean the real repository "
                "was modified."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _code(value: str) -> str:
    escaped = escape(value, quote=False).replace("|", "&#124;")
    return f"<code>{escaped}</code>"


def _optional_hash(value: str | None) -> str:
    return "无 / None" if value is None else _code(value)
