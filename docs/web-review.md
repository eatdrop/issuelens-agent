# 本地审阅与 Draft PR 导出 / Local Review and Draft PR Export

## 本地 Dashboard / Local Dashboard

Dashboard 用于查看已完成 Agent Run 的状态、摘要、风险、计划和代码证据，并记录批准或拒绝计划的人工决策。

The dashboard displays the status, summary, risks, plan, and code evidence of completed Agent runs and records a human decision to approve or reject the plan.

```bash
make demo
make dashboard
```

服务只绑定 `127.0.0.1`，操作系统随机分配端口也受支持。启动时生成高熵随机 Token，只有带正确 Token 的 URL 和 POST 请求才能访问。

The server binds only to `127.0.0.1`; an operating-system-assigned port is also supported. A high-entropy random token is created at startup, and only URLs and POST requests carrying that token are accepted.

安全响应包含严格 CSP、`X-Content-Type-Options: nosniff`、Referrer Policy 和 `Cache-Control: no-store`。不可信报告内容经过 HTML 转义，Host Header 也会校验。

Security responses include a strict CSP, `X-Content-Type-Options: nosniff`, Referrer Policy, and `Cache-Control: no-store`. Untrusted report content is HTML-escaped, and the Host header is validated.

## 决策语义 / Decision Semantics

网页中的“批准 / Approve”表示审阅人认为当前分析计划可以进入下一轮人工工作；“拒绝 / Reject”表示需要补充证据或修改计划。

“Approve” in the page means the reviewer considers the current analysis plan ready for the next human-controlled step; “Reject” means more evidence or plan changes are required.

它不是补丁 Proposal Hash 审批，不会启动 Shadow Validation，不会应用 Diff，也不会发布 PR。审阅人名称是声明式元数据，不是认证身份。

It is not patch Proposal Hash approval, does not start Shadow Validation, apply a Diff, or publish a PR. The reviewer name is declared metadata, not an authenticated identity.

每个决策记录绑定 Run ID、决策、审阅人、备注、时间和内容哈希，并以追加方式保存；已有记录不会被覆盖。

Each decision record binds the Run ID, decision, reviewer, note, timestamp, and content hash and is stored append-only; existing records are never overwritten.

## Draft PR Markdown / Draft PR Markdown

`draft-pr` 组合经过验证的 Agent 报告、候选 Diff 元数据和可选 Shadow Validation 回执，生成中英双语 PR 草稿正文。

`draft-pr` combines a validated Agent report, candidate-Diff metadata, and an optional Shadow Validation receipt into a bilingual PR draft body.

```bash
PYTHONPATH=src python3 -m issuelens draft-pr \
  --repo fixtures/calculator_repo \
  --report runs/<run-id>/report.json \
  --diff evals/patches/division_by_zero.diff \
  --validation-receipt /tmp/issuelens-shadow-audit/<receipt-hash>.json \
  --output /tmp/issuelens-draft-pr.md
```

导出前会检查：报告为 `ready_for_human_review`、报告基础快照仍与目标仓库一致、证据与计划结构有效、Diff 路径通过策略、可选验证回执完整且属于同一基础快照。

Before export, the command checks that the report is `ready_for_human_review`, its base snapshot still matches the target repository, evidence and plan structures are valid, Diff paths pass policy, and any optional validation receipt is intact and belongs to the same base snapshot.

输出包括摘要、证据、修改范围、验证状态、风险、人工检查清单和 AI 辅助披露。它只写目标仓库之外的新 Markdown 文件；如果目标已存在则失败。

The output contains a summary, evidence, change scope, validation state, risks, a human checklist, and AI-assistance disclosure. It writes only a new Markdown file outside the target repository and fails if the target already exists.

## 产品边界 / Product Boundary

当前版本有意不调用 GitHub API。这使“形成建议”和“向外部协作空间发布”保持为两个不同权限等级。

The current version intentionally does not call the GitHub API. This keeps “forming a proposal” and “publishing to an external collaboration surface” as distinct authority levels.

未来若加入自动 Draft PR 发布，应默认关闭，并额外要求可信身份、仓库授权、分支策略检查、精确补丁审批和显式发布确认。

If automatic Draft PR publication is added later, it should remain disabled by default and require trusted identity, repository authorization, branch-policy checks, exact patch approval, and explicit publication confirmation.
