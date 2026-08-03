from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .checkpoint import AgentCheckpoint, CheckpointError, CheckpointStore, issue_digest
from .domain import AnalysisReport, Evidence, PlanStep, TraceEvent
from .issue_parser import parse_issue
from .reporting import RunArtifacts
from .repository import ReadOnlyRepository, Symbol


_TOOL_NAMES = {
    "list_files",
    "find_symbol",
    "search_text",
    "read_file",
    "submit_analysis",
}


class AgentProtocolError(ValueError):
    """Raised when a policy requests an invalid or unsafe action."""


class AgentBudgetExceeded(AgentProtocolError):
    """Raised when an Agent crosses an explicit execution budget."""


class _RetryableModelError(AgentProtocolError):
    pass


@dataclass(frozen=True, slots=True)
class AgentBudget:
    max_steps: int = 8
    max_tool_calls: int = 8
    max_evidence: int = 100
    max_elapsed_seconds: float = 120.0

    def __post_init__(self) -> None:
        for name, value, minimum, maximum in (
            ("max_steps", self.max_steps, 1, 100),
            ("max_tool_calls", self.max_tool_calls, 1, 100),
            ("max_evidence", self.max_evidence, 1, 1_000),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise AgentProtocolError(f"{name} is outside the safe range")
        if (
            isinstance(self.max_elapsed_seconds, bool)
            or not isinstance(self.max_elapsed_seconds, (int, float))
            or not 1.0 <= float(self.max_elapsed_seconds) <= 3_600.0
        ):
            raise AgentProtocolError("max_elapsed_seconds is outside the safe range")


@dataclass(frozen=True)
class AgentAction:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AgentAction":
        name = payload.get("action")
        arguments = payload.get("arguments", {})
        rationale = payload.get("rationale", "")
        if name not in _TOOL_NAMES:
            raise AgentProtocolError(f"unsupported agent action: {name!r}")
        if not isinstance(arguments, dict):
            raise AgentProtocolError("action arguments must be an object")
        if not isinstance(rationale, str) or len(rationale) > 1_000:
            raise AgentProtocolError("action rationale must be a short string")
        return cls(name=name, arguments=arguments, rationale=rationale)


@dataclass(frozen=True)
class SessionView:
    issue_title: str
    issue_body: str
    step: int
    max_steps: int
    observations: tuple[dict[str, Any], ...]
    evidence: tuple[Evidence, ...]


class AgentPolicy(Protocol):
    def next_action(self, view: SessionView) -> AgentAction: ...


class OfflineToolPolicy:
    """A reproducible policy used to exercise the Agent harness without an API."""

    def next_action(self, view: SessionView) -> AgentAction:
        issue = parse_issue(view.issue_body)
        if view.step == 0:
            return AgentAction(
                name="list_files",
                rationale=(
                    "读取代码前先确认受限仓库范围。 / "
                    "Establish the bounded repository surface before reading code."
                ),
            )
        if view.step == 1 and issue.identifiers:
            return AgentAction(
                name="find_symbol",
                arguments={"name": issue.identifiers[0]},
                rationale=(
                    "从 Issue 中最强的显式符号开始。 / "
                    "Start with the strongest explicit symbol from the Issue."
                ),
            )
        if view.step <= 2:
            query = (
                issue.exception_hints[0]
                if issue.exception_hints
                else (issue.keywords[0] if issue.keywords else issue.title)
            )
            return AgentAction(
                name="search_text",
                arguments={"query": query, "glob": "*.py"},
                rationale=(
                    "检索第二个独立代码信号。 / "
                    "Retrieve a second independent code signal."
                ),
            )
        if view.step == 3 and view.evidence:
            strongest = sorted(
                view.evidence,
                key=lambda item: (-item.score, item.path, item.start_line),
            )[0]
            return AgentAction(
                name="read_file",
                arguments={
                    "path": strongest.path,
                    "start_line": max(1, strongest.start_line - 3),
                    "end_line": strongest.end_line + 20,
                },
                rationale=(
                    "读取最强证据附近的受限上下文。 / "
                    "Read bounded context around the strongest evidence."
                ),
            )
        return _offline_submission(view)


class OpenAICompatiblePolicy:
    """Minimal structured-action adapter for OpenAI-compatible chat endpoints.

    The endpoint is supplied explicitly so the core project does not depend on a
    specific model vendor. The model receives no shell or filesystem capability;
    it can only request actions validated by this module.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key or os.environ.get("ISSUELENS_API_KEY")
        self.timeout_seconds = timeout_seconds
        if type(max_retries) is not int or not 0 <= max_retries <= 5:
            raise AgentProtocolError("max_retries is outside the safe range")
        if (
            isinstance(retry_backoff_seconds, bool)
            or not isinstance(retry_backoff_seconds, (int, float))
            or not 0 <= float(retry_backoff_seconds) <= 10.0
        ):
            raise AgentProtocolError("retry_backoff_seconds is outside the safe range")
        self.max_retries = max_retries
        self.retry_backoff_seconds = float(retry_backoff_seconds)

    def next_action(self, view: SessionView) -> AgentAction:
        prompt = {
            "issue": {"title": view.issue_title, "body": view.issue_body},
            "step": view.step,
            "max_steps": view.max_steps,
            "observations": list(view.observations)[-8:],
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "path": item.path,
                    "start_line": item.start_line,
                    "end_line": item.end_line,
                    "snippet": item.snippet[:1_200],
                    "reason": item.reason,
                }
                for item in view.evidence[-16:]
            ],
            "allowed_actions": sorted(_TOOL_NAMES),
        }
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": _SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt, ensure_ascii=False),
                },
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        last_error: _RetryableModelError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._request_action(request)
            except _RetryableModelError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_backoff_seconds * (2**attempt))
        assert last_error is not None
        raise AgentProtocolError(
            f"model request failed after {self.max_retries + 1} attempt(s): "
            f"{last_error}"
        ) from last_error

    def _request_action(self, request: urllib.request.Request) -> AgentAction:
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout_seconds
            ) as response:
                response_body = response.read(_MAX_MODEL_RESPONSE_BYTES + 1)
                if len(response_body) > _MAX_MODEL_RESPONSE_BYTES:
                    raise _RetryableModelError("model response exceeds the size limit")
                payload = json.loads(response_body.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                raise _RetryableModelError(f"HTTP {exc.code}") from exc
            raise AgentProtocolError(f"model request was rejected: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise _RetryableModelError(str(exc)) from exc
        try:
            content = payload["choices"][0]["message"]["content"]
            action_payload = _parse_json_object(content)
            return AgentAction.from_dict(action_payload)
        except (KeyError, IndexError, TypeError, AgentProtocolError) as exc:
            raise _RetryableModelError("model response has an invalid action shape") from exc


class RepositoryToolbox:
    def __init__(self, repository: ReadOnlyRepository, symbols: list[Symbol]) -> None:
        self.repository = repository
        self.symbols = symbols
        self.evidence: dict[str, Evidence] = {}

    def execute(self, action: AgentAction) -> dict[str, Any]:
        args = action.arguments
        if action.name == "list_files":
            files = self.repository.list_files()[:300]
            return {"ok": True, "file_count": len(files), "files": files}
        if action.name == "find_symbol":
            name = _required_string(args, "name", max_length=200)
            matches = [
                symbol
                for symbol in self.symbols
                if symbol.name.casefold() == name.casefold()
            ][:20]
            items = [
                self.repository.symbol_evidence(
                    symbol,
                    reason=(
                        f"Agent 请求 AST 符号 `{name}` / "
                        f"Agent requested AST symbol `{name}`"
                    ),
                    score=5.0,
                )
                for symbol in matches
            ]
            self._store(items)
            return {
                "ok": True,
                "match_count": len(items),
                "evidence_ids": [item.evidence_id for item in items],
            }
        if action.name == "search_text":
            query = _required_string(args, "query", max_length=200)
            glob = args.get("glob", "*.py")
            if not isinstance(glob, str) or len(glob) > 100:
                raise AgentProtocolError("glob must be a short string")
            items = self.repository.search_text(
                query,
                glob=glob,
                limit=20,
                reason="Agent 请求文本搜索 / Agent requested text search",
            )
            self._store(items)
            return {
                "ok": True,
                "match_count": len(items),
                "evidence_ids": [item.evidence_id for item in items],
            }
        if action.name == "read_file":
            path = _required_string(args, "path", max_length=500)
            start = _bounded_int(args.get("start_line", 1), minimum=1, maximum=1_000_000)
            end = _bounded_int(
                args.get("end_line", start + 79),
                minimum=start,
                maximum=min(1_000_000, start + 199),
            )
            item = self.repository.range_evidence(
                path,
                start_line=start,
                end_line=end,
                reason=(
                    "Agent 请求受限文件读取 / "
                    "Agent requested bounded file read"
                ),
                score=2.5,
            )
            self._store([item])
            return {
                "ok": True,
                "evidence_ids": [item.evidence_id],
                "path": item.path,
                "start_line": item.start_line,
                "end_line": item.end_line,
            }
        raise AgentProtocolError(
            "submit_analysis is handled by the workflow and is not a repository tool"
        )

    def _store(self, items: list[Evidence]) -> None:
        for item in items:
            self.evidence[item.evidence_id] = item


class AgentLoopWorkflow:
    def run(
        self,
        *,
        repo_path: str | Path,
        issue_text: str,
        run_dir: str | Path,
        policy: AgentPolicy,
        run_id: str | None = None,
        max_steps: int = 8,
        max_tool_calls: int = 8,
        max_evidence: int = 100,
        max_elapsed_seconds: float = 120.0,
        resume: bool = False,
    ) -> AnalysisReport:
        started = time.perf_counter()
        budget = AgentBudget(
            max_steps=max_steps,
            max_tool_calls=max_tool_calls,
            max_evidence=max_evidence,
            max_elapsed_seconds=max_elapsed_seconds,
        )
        if resume and not run_id:
            raise CheckpointError("resume requires an explicit run_id")
        run_id = run_id or f"agent-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        repository = ReadOnlyRepository(repo_path)
        artifact_root = Path(run_dir).expanduser().resolve()
        if artifact_root == repository.root or repository.root in artifact_root.parents:
            raise AgentProtocolError("run_dir must be outside the target repository")
        artifacts = RunArtifacts(run_dir, run_id, resume=resume)
        checkpoint_store = CheckpointStore(artifacts.path)
        issue = parse_issue(issue_text)
        snapshot_before = repository.snapshot_hash()
        toolbox = RepositoryToolbox(repository, repository.build_symbol_index())
        current_issue_hash = issue_digest(issue_text)
        prior_elapsed_seconds = 0.0
        checkpoint_count = 0
        start_step = 0

        if resume:
            checkpoint = checkpoint_store.load()
            if checkpoint.completed:
                raise CheckpointError("completed runs cannot be resumed")
            if checkpoint.run_id != run_id:
                raise CheckpointError("checkpoint run_id does not match")
            if checkpoint.issue_hash != current_issue_hash:
                raise CheckpointError("issue text changed since the checkpoint")
            if checkpoint.repository_snapshot_hash != snapshot_before:
                raise CheckpointError("repository changed since the checkpoint")
            observations = [dict(item) for item in checkpoint.observations]
            toolbox._store(list(checkpoint.evidence))
            sequence = checkpoint.sequence + 1
            start_step = checkpoint.next_step
            prior_elapsed_seconds = float(checkpoint.elapsed_seconds)
            artifacts.append_trace(
                TraceEvent(
                    sequence=sequence,
                    state="agent_loop",
                    event="run_resumed",
                    details={
                        "checkpoint_hash": checkpoint.checkpoint_hash,
                        "next_step": start_step,
                    },
                )
            )
        else:
            observations = []
            sequence = 0
        submission: dict[str, Any] | None = None

        def elapsed_seconds() -> float:
            return prior_elapsed_seconds + (time.perf_counter() - started)

        def require_time_budget() -> None:
            if elapsed_seconds() > budget.max_elapsed_seconds:
                raise AgentBudgetExceeded("Agent elapsed-time budget was exhausted")

        def save_checkpoint(*, next_step: int, completed: bool = False) -> None:
            nonlocal checkpoint_count
            checkpoint_store.save(
                AgentCheckpoint.create(
                    run_id=run_id,
                    issue_hash=current_issue_hash,
                    repository_snapshot_hash=snapshot_before,
                    next_step=next_step,
                    sequence=sequence,
                    elapsed_seconds=elapsed_seconds(),
                    observations=tuple(observations),
                    evidence=tuple(toolbox.evidence.values()),
                    completed=completed,
                )
            )
            checkpoint_count += 1

        save_checkpoint(next_step=start_step)

        for step in range(start_step, budget.max_steps):
            require_time_budget()
            view = SessionView(
                issue_title=issue.title,
                issue_body=issue.body,
                step=step,
                max_steps=budget.max_steps,
                observations=tuple(observations),
                evidence=tuple(toolbox.evidence.values()),
            )
            action = policy.next_action(view)
            require_time_budget()
            sequence += 1
            artifacts.append_trace(
                TraceEvent(
                    sequence=sequence,
                    state="agent_loop",
                    event="action_requested",
                    details={
                        "step": step,
                        "action": action.name,
                        "arguments": action.arguments,
                        "rationale": action.rationale,
                    },
                )
            )
            if action.name == "submit_analysis":
                submission = _validate_submission(
                    action.arguments, toolbox.evidence, repository
                )
                observations.append(
                    {"step": step, "action": action.name, "ok": True}
                )
                break
            tool_call_count = sum(
                item.get("action") != "submit_analysis" for item in observations
            )
            if tool_call_count >= budget.max_tool_calls:
                raise AgentBudgetExceeded("Agent tool-call budget was exhausted")
            result = toolbox.execute(action)
            if len(toolbox.evidence) > budget.max_evidence:
                raise AgentBudgetExceeded("Agent evidence budget was exhausted")
            observation = {"step": step, "action": action.name, **result}
            observations.append(observation)
            sequence += 1
            artifacts.append_trace(
                TraceEvent(
                    sequence=sequence,
                    state="agent_loop",
                    event="tool_observation",
                    details=observation,
                )
            )
            require_time_budget()
            save_checkpoint(next_step=step + 1)

        if submission is None:
            raise AgentProtocolError("Agent exhausted its step budget without submitting")

        snapshot_after = repository.snapshot_hash()
        unchanged = snapshot_before == snapshot_after
        if not unchanged:
            raise RuntimeError("target repository changed during Agent investigation")

        evidence = list(toolbox.evidence.values())
        status = submission["status"]
        plan = [
            PlanStep(
                order=index,
                action=item["action"],
                rationale=item["rationale"],
                evidence_ids=tuple(item["evidence_ids"]),
            )
            for index, item in enumerate(submission["plan"], start=1)
        ]
        report = AnalysisReport(
            run_id=run_id,
            status=status,
            repo_root=str(repository.root),
            repo_snapshot_before=snapshot_before,
            repo_snapshot_after=snapshot_after,
            repository_unchanged=unchanged,
            issue=issue,
            candidate_files=submission["candidate_files"],
            evidence=evidence,
            diagnosis=submission["diagnosis"],
            plan=plan,
            proposed_tests=submission["proposed_tests"],
            risks=submission["risks"],
            acceptance_criteria=submission["acceptance_criteria"],
            state_history=[
                "created",
                *[f"tool:{item['action']}" for item in observations],
                "awaiting_human_review" if plan else "abstained",
            ],
            metrics={
                "elapsed_ms": round(elapsed_seconds() * 1000, 2),
                "tool_call_count": len(
                    [item for item in observations if item["action"] != "submit_analysis"]
                ),
                "evidence_count": len(evidence),
                "checkpoint_count": checkpoint_count + 1,
                "resumed": resume,
                "budget": {
                    "max_elapsed_seconds": budget.max_elapsed_seconds,
                    "max_evidence": budget.max_evidence,
                    "max_steps": budget.max_steps,
                    "max_tool_calls": budget.max_tool_calls,
                },
                "plan_evidence_coverage": (
                    round(
                        sum(bool(item.evidence_ids) for item in plan) / len(plan), 4
                    )
                    if plan
                    else 0.0
                ),
                "target_repo_write_count": 0,
                "repository_unchanged": unchanged,
            },
        )
        artifacts.write_report(report)
        save_checkpoint(next_step=budget.max_steps, completed=True)
        return report


def _offline_submission(view: SessionView) -> AgentAction:
    evidence = sorted(
        view.evidence,
        key=lambda item: (-item.score, item.path, item.start_line),
    )
    strong = [item for item in evidence if item.score >= 3.5]
    if not strong:
        return AgentAction(
            name="submit_analysis",
            arguments={
                "status": "insufficient_evidence",
                "diagnosis": (
                    "未找到强符号、异常或文件证据。Agent 停止执行，不猜测补丁。\n\n"
                    "No strong symbol, exception, or file evidence was found. "
                    "The Agent stops instead of guessing a patch."
                ),
                "candidate_files": [],
                "plan": [],
                "proposed_tests": [],
                "risks": [
                    "通用关键词重叠可能导致修改无关代码。 / "
                    "Generic keyword overlap can modify unrelated code."
                ],
                "acceptance_criteria": [
                    "先获得可复现案例或明确的失败符号。 / "
                    "Obtain a reproducible example or explicit failing symbol."
                ],
            },
            rationale=(
                "由于证据低于安全阈值，系统选择拒绝规划。 / "
                "Abstain because grounded evidence is below the safety threshold."
            ),
        )
    source_paths = [
        item.path
        for item in strong
        if not item.path.startswith("tests/")
        and not item.path.rsplit("/", 1)[-1].startswith("test_")
    ]
    candidate = source_paths[0] if source_paths else strong[0].path
    evidence_ids = list(dict.fromkeys(item.evidence_id for item in strong[:4]))
    return AgentAction(
        name="submit_analysis",
        arguments={
            "status": "ready_for_human_review",
            "diagnosis": (
                f"证据指向 `{candidate}`，它是首要实现候选文件。"
                "生成任何补丁前必须先建立失败回归测试。\n\n"
                f"Evidence points to `{candidate}` as the primary implementation "
                "candidate. A failing regression test is required before any patch."
            ),
            "candidate_files": list(
                dict.fromkeys([candidate, *[item.path for item in strong]])
            )[:5],
            "plan": [
                {
                    "action": (
                        "在固定基础快照上复现 Issue。 / "
                        "Reproduce the Issue on the pinned base snapshot."
                    ),
                    "rationale": (
                        "修改代码前先确认报告行为。 / "
                        "Confirm the reported behavior before changing code."
                    ),
                    "evidence_ids": evidence_ids,
                },
                {
                    "action": (
                        f"为 `{candidate}` 添加聚焦回归测试。 / "
                        f"Add a focused regression test for `{candidate}`."
                    ),
                    "rationale": (
                        "测试必须在补丁前失败、补丁后通过。 / "
                        "The test must fail before the patch and pass after it."
                    ),
                    "evidence_ids": evidence_ids,
                },
                {
                    "action": (
                        f"准备仅限于 `{candidate}` 的最小补丁。 / "
                        f"Prepare a minimal patch limited to `{candidate}`."
                    ),
                    "rationale": (
                        "修改范围必须保持在代码证据支持的边界内。 / "
                        "Keep the change inside the evidence-backed scope."
                    ),
                    "evidence_ids": evidence_ids,
                },
            ],
            "proposed_tests": [
                "目标回归测试在补丁前失败。 / "
                "Target regression test fails before the patch.",
                "补丁后目标测试和完整测试套件均通过。 / "
                "Target and full test suites pass after the patch.",
            ],
            "risks": [
                "Issue 可能缺少向后兼容约束。 / "
                "The Issue may omit backward-compatibility constraints.",
                "执行测试需要隔离的 Shadow Workspace。 / "
                "Test execution requires an isolated shadow workspace.",
            ],
            "acceptance_criteria": [
                "独立回归测试通过。 / Independent regression test passes.",
                "完整测试套件没有新增失败。 / "
                "No new failures appear in the full suite.",
                "不修改任何未经批准的文件。 / "
                "No unapproved file is modified.",
            ],
        },
        rationale=(
            "提交有证据支持的计划，等待人工审核。 / "
            "Submit a grounded plan for human review."
        ),
    )


def _validate_submission(
    payload: dict[str, Any],
    evidence_store: dict[str, Evidence],
    repository: ReadOnlyRepository,
) -> dict[str, Any]:
    status = payload.get("status")
    if status not in {"ready_for_human_review", "insufficient_evidence"}:
        raise AgentProtocolError("submission status is invalid")
    diagnosis = _required_string(payload, "diagnosis", max_length=8_000)
    candidate_files = _string_list(payload.get("candidate_files", []), 20, 500)
    readable = set(repository.list_files())
    if any(path not in readable for path in candidate_files):
        raise AgentProtocolError("submission references a file outside the repository")
    plan_payload = payload.get("plan", [])
    if not isinstance(plan_payload, list) or len(plan_payload) > 20:
        raise AgentProtocolError("plan must be a bounded list")
    plan: list[dict[str, Any]] = []
    for item in plan_payload:
        if not isinstance(item, dict):
            raise AgentProtocolError("each plan item must be an object")
        evidence_ids = _string_list(item.get("evidence_ids", []), 20, 100)
        if any(evidence_id not in evidence_store for evidence_id in evidence_ids):
            raise AgentProtocolError("plan cites unknown evidence")
        plan.append(
            {
                "action": _required_string(item, "action", max_length=2_000),
                "rationale": _required_string(item, "rationale", max_length=2_000),
                "evidence_ids": evidence_ids,
            }
        )
    if status == "ready_for_human_review" and (
        not plan or any(not item["evidence_ids"] for item in plan)
    ):
        raise AgentProtocolError("actionable plans must cite repository evidence")
    return {
        "status": status,
        "diagnosis": diagnosis,
        "candidate_files": candidate_files,
        "plan": plan,
        "proposed_tests": _string_list(payload.get("proposed_tests", []), 30, 2_000),
        "risks": _string_list(payload.get("risks", []), 30, 2_000),
        "acceptance_criteria": _string_list(
            payload.get("acceptance_criteria", []), 30, 2_000
        ),
    }


def _required_string(
    payload: dict[str, Any], key: str, *, max_length: int
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise AgentProtocolError(f"{key} must be a non-empty bounded string")
    return value.strip()


def _string_list(value: Any, max_items: int, max_length: int) -> list[str]:
    if not isinstance(value, list) or len(value) > max_items:
        raise AgentProtocolError("expected a bounded list of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or len(item) > max_length:
            raise AgentProtocolError("expected a bounded list of strings")
        result.append(item)
    return result


def _bounded_int(value: Any, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AgentProtocolError("line bounds must be integers")
    if value < minimum or value > maximum:
        raise AgentProtocolError("line bounds are outside the allowed range")
    return value


def _parse_json_object(content: Any) -> dict[str, Any]:
    if not isinstance(content, str):
        raise AgentProtocolError("model content must be a string")
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1])
            if stripped.lstrip().startswith("json"):
                stripped = stripped.lstrip()[4:].lstrip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise AgentProtocolError("model did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise AgentProtocolError("model action must be a JSON object")
    return payload


_SYSTEM_PROMPT = """You are the investigation policy inside a read-only Coding Agent.
Return exactly one JSON object with keys: action, arguments, rationale.
Allowed actions are list_files, find_symbol, search_text, read_file, submit_analysis.
Never request shell commands, network access, writes, secrets, or paths outside the repo.
Use tools to gather code evidence before submit_analysis. Every actionable plan item
must cite evidence_ids already returned by tools. If evidence is weak or the Issue is
underspecified, submit status=insufficient_evidence and do not invent a patch.
All human-facing fields in submit_analysis must be bilingual, with Chinese first and
English second: diagnosis, every plan action and rationale, proposed_tests, risks, and
acceptance_criteria. Use either "中文 / English" or separate Chinese and English paragraphs.
"""


_MAX_MODEL_RESPONSE_BYTES = 1_000_000
