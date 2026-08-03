from __future__ import annotations

from dataclasses import dataclass, field

from .domain import RunState


_ALLOWED: dict[RunState, set[RunState]] = {
    RunState.CREATED: {RunState.ISSUE_PARSED, RunState.FAILED},
    RunState.ISSUE_PARSED: {RunState.REPO_SNAPSHOTTED, RunState.FAILED},
    RunState.REPO_SNAPSHOTTED: {RunState.INDEX_BUILT, RunState.FAILED},
    RunState.INDEX_BUILT: {RunState.EVIDENCE_RETRIEVED, RunState.FAILED},
    RunState.EVIDENCE_RETRIEVED: {RunState.PLAN_CREATED, RunState.FAILED},
    RunState.PLAN_CREATED: {RunState.REPO_VERIFIED, RunState.FAILED},
    RunState.REPO_VERIFIED: {RunState.FINISHED, RunState.FAILED},
    RunState.FINISHED: set(),
    RunState.FAILED: set(),
}


@dataclass
class StateMachine:
    current: RunState = RunState.CREATED
    history: list[RunState] = field(default_factory=lambda: [RunState.CREATED])

    def transition(self, next_state: RunState) -> None:
        if next_state not in _ALLOWED[self.current]:
            raise ValueError(
                f"illegal state transition: {self.current.value} -> {next_state.value}"
            )
        self.current = next_state
        self.history.append(next_state)

    def fail(self) -> None:
        if self.current not in {RunState.FINISHED, RunState.FAILED}:
            self.transition(RunState.FAILED)
