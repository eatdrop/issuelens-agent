from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from issuelens.agent_loop import (
    AgentAction,
    AgentBudgetExceeded,
    AgentLoopWorkflow,
    AgentProtocolError,
    OfflineToolPolicy,
    OpenAICompatiblePolicy,
    SessionView,
)
from issuelens.checkpoint import AgentCheckpoint, CheckpointError, CheckpointStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InterruptingPolicy:
    def __init__(self, fail_step: int) -> None:
        self.fail_step = fail_step
        self.delegate = OfflineToolPolicy()

    def next_action(self, view: SessionView) -> AgentAction:
        if view.step == self.fail_step:
            raise RuntimeError("simulated interruption")
        return self.delegate.next_action(view)


class EndlessToolPolicy:
    def next_action(self, view: SessionView) -> AgentAction:
        return AgentAction(name="list_files", rationale="bounded test action")


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        content = json.dumps(self.payload).encode("utf-8")
        return content if size < 0 else content[:size]


class CheckpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.issue = (
            PROJECT_ROOT / "evals" / "cases" / "division_by_zero.md"
        ).read_text(encoding="utf-8")
        self.repository = PROJECT_ROOT / "fixtures" / "calculator_repo"

    def test_resumes_after_interruption_without_repeating_completed_steps(self) -> None:
        with tempfile.TemporaryDirectory() as run_dir:
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                AgentLoopWorkflow().run(
                    repo_path=self.repository,
                    issue_text=self.issue,
                    run_dir=run_dir,
                    run_id="resume-test",
                    policy=InterruptingPolicy(fail_step=2),
                )
            checkpoint = CheckpointStore(Path(run_dir) / "resume-test").load()
            self.assertEqual(checkpoint.next_step, 2)
            self.assertFalse(checkpoint.completed)

            report = AgentLoopWorkflow().run(
                repo_path=self.repository,
                issue_text=self.issue,
                run_dir=run_dir,
                run_id="resume-test",
                policy=OfflineToolPolicy(),
                resume=True,
            )

            self.assertEqual(report.status, "ready_for_human_review")
            self.assertTrue(report.metrics["resumed"])
            final_checkpoint = CheckpointStore(
                Path(run_dir) / "resume-test"
            ).load()
            self.assertTrue(final_checkpoint.completed)
            trace = [
                json.loads(line)
                for line in (Path(run_dir) / "resume-test" / "trace.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            sequences = [item["sequence"] for item in trace]
            self.assertEqual(sequences, sorted(set(sequences)))
            self.assertIn("run_resumed", [item["event"] for item in trace])

    def test_resume_rejects_repository_drift(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            repository = Path(root) / "repository"
            repository.mkdir()
            source = repository / "app.py"
            source.write_text("def target():\n    return 1\n", encoding="utf-8")
            run_dir = Path(root) / "runs"
            issue = "# target returns the wrong value\n\n`target` should return 2."
            with self.assertRaises(RuntimeError):
                AgentLoopWorkflow().run(
                    repo_path=repository,
                    issue_text=issue,
                    run_dir=run_dir,
                    run_id="drift-test",
                    policy=InterruptingPolicy(fail_step=1),
                )
            source.write_text("def target():\n    return 9\n", encoding="utf-8")

            with self.assertRaisesRegex(CheckpointError, "repository changed"):
                AgentLoopWorkflow().run(
                    repo_path=repository,
                    issue_text=issue,
                    run_dir=run_dir,
                    run_id="drift-test",
                    policy=OfflineToolPolicy(),
                    resume=True,
                )

    def test_tool_call_budget_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as run_dir:
            with self.assertRaises(AgentBudgetExceeded):
                AgentLoopWorkflow().run(
                    repo_path=self.repository,
                    issue_text=self.issue,
                    run_dir=run_dir,
                    run_id="budget-test",
                    policy=EndlessToolPolicy(),
                    max_tool_calls=1,
                )
            checkpoint = CheckpointStore(Path(run_dir) / "budget-test").load()
            self.assertEqual(checkpoint.next_step, 1)
            self.assertFalse(checkpoint.completed)

    def test_checkpoint_integrity_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as run_dir:
            with self.assertRaises(RuntimeError):
                AgentLoopWorkflow().run(
                    repo_path=self.repository,
                    issue_text=self.issue,
                    run_dir=run_dir,
                    run_id="tamper-test",
                    policy=InterruptingPolicy(fail_step=1),
                )
            store = CheckpointStore(Path(run_dir) / "tamper-test")
            checkpoint = store.load()
            tampered = dataclasses.replace(checkpoint, next_step=7)

            self.assertFalse(tampered.verify_integrity())

    def test_checkpoint_load_rejects_symbolic_link(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_path = Path(root) / "run"
            run_path.mkdir()
            external = Path(root) / "external.json"
            external.write_text("{}", encoding="utf-8")
            (run_path / "checkpoint.json").symlink_to(external)

            with self.assertRaisesRegex(CheckpointError, "safely"):
                CheckpointStore(run_path).load()

    def test_checkpoint_save_rejects_oversized_payload(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_path = Path(root) / "run"
            run_path.mkdir()
            checkpoint = AgentCheckpoint.create(
                run_id="oversized",
                issue_hash="1" * 64,
                repository_snapshot_hash="2" * 64,
                next_step=0,
                sequence=0,
                elapsed_seconds=0,
                observations=({"blob": "x" * 2_000_000},),
                evidence=(),
            )

            with self.assertRaisesRegex(CheckpointError, "size limit"):
                CheckpointStore(run_path).save(checkpoint)

    @patch("issuelens.agent_loop.time.sleep")
    @patch("issuelens.agent_loop.urllib.request.urlopen")
    def test_llm_policy_retries_transient_failure(
        self, urlopen: object, sleep: object
    ) -> None:
        urlopen.side_effect = [
            urllib.error.URLError("temporary"),
            _Response(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "action": "list_files",
                                        "arguments": {},
                                        "rationale": "inspect",
                                    }
                                )
                            }
                        }
                    ]
                }
            ),
        ]
        policy = OpenAICompatiblePolicy(
            endpoint="https://example.invalid/v1/chat/completions",
            model="test-model",
            max_retries=1,
            retry_backoff_seconds=0.01,
        )

        action = policy.next_action(
            SessionView(
                issue_title="issue",
                issue_body="body",
                step=0,
                max_steps=2,
                observations=(),
                evidence=(),
            )
        )

        self.assertEqual(action.name, "list_files")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.01)

    @patch("issuelens.agent_loop.urllib.request.urlopen")
    def test_llm_policy_rejects_oversized_response(self, urlopen: object) -> None:
        urlopen.return_value = _Response(
            {
                "choices": [
                    {
                        "message": {
                            "content": "x" * 1_100_000,
                        }
                    }
                ]
            }
        )
        policy = OpenAICompatiblePolicy(
            endpoint="https://example.invalid/v1/chat/completions",
            model="test-model",
            max_retries=0,
        )

        with self.assertRaisesRegex(AgentProtocolError, "size limit"):
            policy.next_action(
                SessionView(
                    issue_title="issue",
                    issue_body="body",
                    step=0,
                    max_steps=2,
                    observations=(),
                    evidence=(),
                )
            )


if __name__ == "__main__":
    unittest.main()
