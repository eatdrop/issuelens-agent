from __future__ import annotations

from collections import Counter

from .domain import Evidence, IssueSpec, PlanStep
from .repository import ReadOnlyRepository, Symbol


class DeterministicReasoner:
    """A reproducible retrieval baseline that does not require an LLM."""

    def retrieve(
        self,
        issue: IssueSpec,
        repository: ReadOnlyRepository,
        symbols: list[Symbol],
        *,
        max_evidence: int = 24,
    ) -> list[Evidence]:
        ranked: dict[str, Evidence] = {}
        queries = self._queries(issue)
        normalized_identifiers = {item.casefold() for item in issue.identifiers}
        normalized_exceptions = {item.casefold() for item in issue.exception_hints}

        for symbol in symbols:
            key = symbol.name.casefold()
            if key in normalized_identifiers:
                evidence = repository.symbol_evidence(
                    symbol,
                    reason=(
                        f"AST 符号匹配 Issue 标识符 `{symbol.name}` / "
                        f"AST symbol matches Issue identifier `{symbol.name}`"
                    ),
                    score=5.0,
                )
                ranked[evidence.evidence_id] = evidence
            elif any(query.casefold() == key for query in queries[:8]):
                evidence = repository.symbol_evidence(
                    symbol,
                    reason=(
                        f"AST 符号匹配 Issue 查询 `{symbol.name}` / "
                        f"AST symbol matches Issue query `{symbol.name}`"
                    ),
                    score=3.5,
                )
                ranked[evidence.evidence_id] = evidence

        for query_index, query in enumerate(queries):
            base_score = max(1.0, 3.0 - (query_index * 0.08))
            for evidence in repository.search_text(
                query,
                glob="*.py",
                limit=12,
                reason="由 Issue 生成的搜索 / Issue-derived search",
            ):
                bonus = 0.0
                if query.casefold() in normalized_identifiers:
                    bonus += 2.0
                if query.casefold() in normalized_exceptions:
                    bonus += 1.0
                scored = Evidence(
                    evidence_id=evidence.evidence_id,
                    path=evidence.path,
                    start_line=evidence.start_line,
                    end_line=evidence.end_line,
                    snippet=evidence.snippet,
                    reason=evidence.reason,
                    content_hash=evidence.content_hash,
                    score=base_score + bonus,
                )
                previous = ranked.get(scored.evidence_id)
                if previous is None or scored.score > previous.score:
                    ranked[scored.evidence_id] = scored

        return sorted(
            ranked.values(),
            key=lambda item: (-item.score, item.path, item.start_line),
        )[:max_evidence]

    def build_analysis(
        self, issue: IssueSpec, evidence: list[Evidence]
    ) -> tuple[
        list[str],
        str,
        list[PlanStep],
        list[str],
        list[str],
        list[str],
    ]:
        path_scores: Counter[str] = Counter()
        for item in evidence:
            path_scores[item.path] += item.score
        ranked_paths = [path for path, _ in path_scores.most_common()]
        source_candidates = [
            path for path in ranked_paths if not _looks_like_test(path)
        ]
        test_candidates = [path for path in ranked_paths if _looks_like_test(path)]
        # Implementation files answer "where should behavior change?" while test
        # files answer "how should it be verified?". Keep both, but do not let
        # repeated assertions in a test file bury the implementation candidate.
        candidate_files = (source_candidates + test_candidates)[:5]
        primary = source_candidates[0] if source_candidates else (
            candidate_files[0] if candidate_files else None
        )

        strong_evidence = [item for item in evidence if item.score >= 3.5]
        if not strong_evidence or primary is None:
            diagnosis = (
                "insufficient_evidence：仓库中没有足够强的标识符、符号、异常或"
                "文件级匹配，无法证明修改是安全的。\n\n"
                "insufficient_evidence: the repository does not contain a strong "
                "identifier, symbol, exception, or file-level match that justifies "
                "a safe change."
            )
            risks = [
                "Issue 可能缺少失败符号、堆栈或预期行为。 / "
                "The Issue may omit the failing symbol, stack trace, or expected behavior.",
                "通用关键词重叠可能指向无关实现文件。 / "
                "Generic keyword overlap can point to an unrelated implementation file.",
                "缺少强证据时生成补丁可能修改无关代码。 / "
                "Generating a patch without strong evidence could modify unrelated code.",
            ]
            return (
                candidate_files,
                diagnosis,
                [],
                [],
                risks,
                [
                    "修改代码前先获得可复现案例或堆栈。 / "
                    "Collect a reproducible example or stack trace before changing code."
                ],
            )

        top_evidence = evidence[: min(4, len(evidence))]
        evidence_ids = tuple(item.evidence_id for item in top_evidence)
        diagnosis = (
            f"排名最高的实现候选文件是 `{primary}`。该判断基于 "
            f"{len(evidence)} 条仓库证据；生成补丁前仍需通过失败回归测试确认行为。\n\n"
            f"The highest-ranked implementation candidate is `{primary}`. "
            f"This conclusion is grounded in {len(evidence)} repository evidence items; "
            "the exact behavior still requires a failing regression test before a patch."
        )
        plan = [
            PlanStep(
                order=1,
                action=(
                    f"在 `{primary}` 上复现报告行为。 / "
                    f"Reproduce the reported behavior against `{primary}`."
                ),
                rationale=(
                    "失败测试可以区分真实缺陷与猜测。 / "
                    "A failing test separates the reported bug from speculation."
                ),
                evidence_ids=evidence_ids,
            ),
            PlanStep(
                order=2,
                action=(
                    "添加能够表达预期行为的最小回归测试。 / "
                    "Add the smallest regression test that captures expected behavior."
                ),
                rationale=(
                    f"优先使用现有测试模块，例如 `{test_candidates[0]}`。 / "
                    f"Prefer an existing test module such as `{test_candidates[0]}`."
                    if test_candidates
                    else (
                        "在现有测试套件旁创建聚焦测试。 / "
                        "Create a focused test beside the existing test suite."
                    )
                ),
                evidence_ids=evidence_ids,
            ),
            PlanStep(
                order=3,
                action=(
                    f"在 `{primary}` 中实施最小修改。 / "
                    f"Implement a minimal change in `{primary}`."
                ),
                rationale=(
                    "只修改有证据支持的文件，并保持既有公开行为。 / "
                    "Limit the diff to evidence-backed files and preserve public behavior."
                ),
                evidence_ids=evidence_ids,
            ),
            PlanStep(
                order=4,
                action=(
                    "先运行目标回归测试，再运行完整测试套件。 / "
                    "Run the targeted regression test, then the full test suite."
                ),
                rationale=(
                    "必须同时证明问题已解决且没有引入回归。 / "
                    "Both bug resolution and non-regression must be demonstrated."
                ),
                evidence_ids=evidence_ids,
            ),
        ]
        proposed_tests = [
            "回归测试在基础快照上失败，并在补丁后通过。 / "
            "A regression test fails on the base snapshot and passes after the patch.",
            "既有测试继续通过。 / Existing tests continue to pass.",
            "错误类型和消息符合公开契约。 / "
            "The error type and message match the documented public contract.",
        ]
        risks = [
            "Issue 描述可能没有完整规定向后兼容要求。 / "
            "The Issue description may not fully specify backward compatibility.",
            "由同一 Agent 编写的测试可能意外迎合候选补丁。 / "
            "A test written by the same Agent can accidentally overfit the proposed patch.",
            "仓库代码只能在隔离验证环境中运行。 / "
            "Repository code must run only inside an isolated validation environment.",
        ]
        acceptance = [
            f"修改前成功复现 Issue“{issue.title}”描述的行为。 / "
            f'The behavior described by the Issue "{issue.title}" is reproduced before modification.',
            "最小补丁通过独立定义的回归测试。 / "
            "The minimal patch passes an independently defined regression test.",
            "完整既有测试套件没有新增失败。 / "
            "The full existing test suite has no new failures.",
            "不修改批准快照范围之外的文件。 / "
            "No files outside the approved repository snapshot are modified.",
        ]
        return candidate_files, diagnosis, plan, proposed_tests, risks, acceptance

    @staticmethod
    def _queries(issue: IssueSpec) -> list[str]:
        ordered = [
            *issue.identifiers,
            *issue.file_hints,
            *issue.exception_hints,
            *issue.keywords,
        ]
        seen: set[str] = set()
        result: list[str] = []
        for item in ordered:
            query = item.rsplit("/", 1)[-1]
            if query.endswith(".py"):
                query = query[:-3]
            normalized = query.casefold()
            if len(normalized) < 3 or normalized in seen:
                continue
            seen.add(normalized)
            result.append(query)
            if len(result) >= 18:
                break
        return result


def _looks_like_test(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return path.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py")
