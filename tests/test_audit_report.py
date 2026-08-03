from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from issuelens.approval import PatchApproval
from issuelens.audit_report import (
    AuditReportError,
    render_preflight_report,
)
from issuelens.patch_preflight import preflight_patch_application
from issuelens.patch_proposal import PatchProposal
from issuelens.repository import ReadOnlyRepository


RUN_ID = "run|<123>"
DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-value = 1
+value = 2
--- /dev/null
+++ b/new.py
@@ -0,0 +1 @@
+new_value = 3
--- a/obsolete.py
+++ /dev/null
@@ -1 +0,0 @@
-remove_me = True
"""


class AuditReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "app.py").write_text(
            "value = 1\n",
            encoding="utf-8",
        )
        (self.root / "obsolete.py").write_text(
            "remove_me = True\n",
            encoding="utf-8",
        )
        repository = ReadOnlyRepository(self.root)
        proposal = PatchProposal.create(
            unified_diff=DIFF,
            base_snapshot_hash=repository.snapshot_hash(),
        )
        approval = PatchApproval.create(
            run_id=RUN_ID,
            proposal=proposal,
            approved_by="reviewer",
        )
        self.receipt = preflight_patch_application(
            repository=repository,
            run_id=RUN_ID,
            proposal=proposal,
            approval=approval,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_renders_deterministic_bilingual_report(self) -> None:
        first = render_preflight_report(self.receipt)
        second = render_preflight_report(self.receipt)

        self.assertEqual(second, first)
        self.assertTrue(
            first.startswith(
                "# 补丁预检审计报告 / Patch Preflight Audit Report\n"
            )
        )
        self.assertIn("## 结果 / Result", first)
        self.assertIn("## 安全绑定 / Security Bindings", first)
        self.assertIn("## 文件变更 / File Changes", first)
        self.assertIn("新建 / Created", first)
        self.assertIn("修改 / Modified", first)
        self.assertIn("删除 / Deleted", first)
        self.assertIn("- 文件数 / Files: **3**", first)
        self.assertIn("- 新增行 / Added lines: **2**", first)
        self.assertIn("- 删除行 / Removed lines: **2**", first)
        self.assertIn("<code>run&#124;&lt;123&gt;</code>", first)
        self.assertIn(self.receipt.receipt_hash, first)
        self.assertTrue(first.endswith("\n"))

    def test_report_omits_source_content(self) -> None:
        report = render_preflight_report(self.receipt)

        self.assertNotIn("value = 2", report)
        self.assertNotIn("new_value = 3", report)
        self.assertNotIn("remove_me = True", report)
        self.assertIn(
            "源码正文 / Source content: **未包含 / Not included**",
            report,
        )

    def test_rejects_tampered_receipt(self) -> None:
        object.__setattr__(self.receipt, "run_id", "run-456")

        with self.assertRaises(AuditReportError):
            render_preflight_report(self.receipt)


if __name__ == "__main__":
    unittest.main()
