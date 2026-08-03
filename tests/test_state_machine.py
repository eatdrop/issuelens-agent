import unittest

from issuelens.domain import RunState
from issuelens.state_machine import StateMachine


class StateMachineTests(unittest.TestCase):
    def test_rejects_illegal_transition(self) -> None:
        machine = StateMachine()
        with self.assertRaises(ValueError):
            machine.transition(RunState.PLAN_CREATED)

    def test_happy_path(self) -> None:
        machine = StateMachine()
        for state in (
            RunState.ISSUE_PARSED,
            RunState.REPO_SNAPSHOTTED,
            RunState.INDEX_BUILT,
            RunState.EVIDENCE_RETRIEVED,
            RunState.PLAN_CREATED,
            RunState.REPO_VERIFIED,
            RunState.FINISHED,
        ):
            machine.transition(state)
        self.assertEqual(machine.current, RunState.FINISHED)


if __name__ == "__main__":
    unittest.main()
