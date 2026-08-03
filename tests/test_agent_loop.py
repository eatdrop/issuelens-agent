import tempfile
import unittest
from pathlib import Path

from issuelens.agent_loop import (
    AgentAction,
    AgentLoopWorkflow,
    AgentProtocolError,
    OfflineToolPolicy,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class AgentLoopTests(unittest.TestCase):
    def test_offline_policy_exercises_bounded_tool_loop(self) -> None:
        issue = (
            PROJECT_ROOT / "evals" / "cases" / "division_by_zero.md"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as run_dir:
            report = AgentLoopWorkflow().run(
                repo_path=PROJECT_ROOT / "fixtures" / "calculator_repo",
                issue_text=issue,
                run_dir=run_dir,
                policy=OfflineToolPolicy(),
                run_id="agent-loop-test",
            )
            self.assertEqual(report.status, "ready_for_human_review")
            self.assertEqual(report.candidate_files[0], "src/calculator.py")
            self.assertTrue(report.repository_unchanged)
            self.assertGreaterEqual(report.metrics["tool_call_count"], 3)
            self.assertEqual(report.metrics["target_repo_write_count"], 0)
            self.assertEqual(report.metrics["plan_evidence_coverage"], 1.0)
            markdown = (
                Path(run_dir) / "agent-loop-test" / "report.md"
            ).read_text(encoding="utf-8")
            self.assertIn("证据指向", markdown)
            self.assertIn("Evidence points to", markdown)

    def test_action_schema_rejects_shell(self) -> None:
        with self.assertRaises(AgentProtocolError):
            AgentAction.from_dict(
                {
                    "action": "shell",
                    "arguments": {"command": "curl example.com"},
                    "rationale": "unsafe",
                }
            )


if __name__ == "__main__":
    unittest.main()
