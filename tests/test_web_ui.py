from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from issuelens.web_ui import (
    ArtifactDashboard,
    ReviewDecision,
    WebUiError,
    create_dashboard_server,
)
from issuelens.workflow import IssueAnalysisWorkflow


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WebUiTests(unittest.TestCase):
    def _create_run(self, run_dir: Path, run_id: str = "web-run") -> Path:
        issue = (
            PROJECT_ROOT / "evals" / "cases" / "division_by_zero.md"
        ).read_text(encoding="utf-8")
        IssueAnalysisWorkflow().run(
            repo_path=PROJECT_ROOT / "fixtures" / "calculator_repo",
            issue_text=issue,
            run_dir=run_dir,
            run_id=run_id,
        )
        return run_dir / run_id

    def test_renders_escaped_evidence_and_records_append_only_decision(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_dir = Path(root) / "runs"
            run_path = self._create_run(run_dir)
            report_path = run_path / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["issue"]["title"] = "<script>alert(1)</script>"
            report_path.write_text(
                json.dumps(report, ensure_ascii=False),
                encoding="utf-8",
            )
            dashboard = ArtifactDashboard(run_dir)

            page = dashboard.render_run("web-run", "0123456789abcdef")
            decision = dashboard.record_decision(
                run_id="web-run",
                decision="approve",
                reviewer="XD",
                note="证据充分 / Evidence is sufficient.",
            )

            self.assertNotIn("<script>alert(1)</script>", page)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
            self.assertIn("人工决定 / Human Decision", page)
            decisions = dashboard.list_decisions("web-run")
            self.assertEqual(decisions[0]["decision_hash"], decision.decision_hash)
            self.assertEqual(decisions[0]["report_sha256"], decision.report_sha256)

    def test_rejects_path_traversal_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_dir = Path(root) / "runs"
            run_dir.mkdir()
            dashboard = ArtifactDashboard(run_dir)

            with self.assertRaisesRegex(WebUiError, "run_id"):
                dashboard.render_run("../escape", "0123456789abcdef")

    def test_rejects_symbolic_link_report(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_dir = Path(root) / "runs"
            run_path = self._create_run(run_dir)
            report = run_path / "report.json"
            external = Path(root) / "external.json"
            external.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
            report.unlink()
            report.symlink_to(external)

            with self.assertRaisesRegex(WebUiError, "safely"):
                ArtifactDashboard(run_dir).load_report("web-run")

    def test_review_decision_requires_timezone(self) -> None:
        with self.assertRaisesRegex(WebUiError, "timezone"):
            ReviewDecision.create(
                run_id="web-run",
                report_sha256="a" * 64,
                decision="approve",
                reviewer="reviewer",
                note="",
                decided_at="2026-08-03T12:00:00",
            )

    def test_server_requires_token_and_sets_security_headers(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_dir = Path(root) / "runs"
            self._create_run(run_dir)
            try:
                server, token = create_dashboard_server(
                    run_dir=run_dir,
                    port=0,
                    token="0123456789abcdef0123456789abcdef",
                )
            except PermissionError:
                self.skipTest("loopback sockets are blocked by the test sandbox")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address
            try:
                with urllib.request.urlopen(
                    f"http://{host}:{port}/?{urllib.parse.urlencode({'token': token})}",
                    timeout=5,
                ) as response:
                    body = response.read().decode("utf-8")
                    self.assertEqual(response.status, 200)
                    self.assertIn("IssueLens 审查台", body)
                    self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])

                with self.assertRaises(urllib.error.HTTPError) as context:
                    urllib.request.urlopen(f"http://{host}:{port}/", timeout=5)
                self.assertEqual(context.exception.code, 403)
                self.assertEqual(
                    context.exception.headers["Cache-Control"],
                    "no-store",
                )
                self.assertIn(
                    "default-src 'none'",
                    context.exception.headers["Content-Security-Policy"],
                )

                form = urllib.parse.urlencode(
                    {
                        "token": token,
                        "decision": "reject",
                        "reviewer": "reviewer",
                        "note": "needs more evidence",
                    }
                ).encode("utf-8")
                request = urllib.request.Request(
                    f"http://{host}:{port}/runs/web-run/decision",
                    data=form,
                    method="POST",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                self.assertEqual(
                    ArtifactDashboard(run_dir).list_decisions("web-run")[0]["decision"],
                    "reject",
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_refuses_non_loopback_bind(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_dir = Path(root) / "runs"
            run_dir.mkdir()

            with self.assertRaisesRegex(WebUiError, "127.0.0.1"):
                create_dashboard_server(run_dir=run_dir, host="0.0.0.0")


if __name__ == "__main__":
    unittest.main()
