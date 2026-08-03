# IssueLens 评测方案 / Evaluation

## 原则 / Principles

Coding Agent 可能输出合理报告却定位错误代码，也可能让一个无效测试“通过”。IssueLens 因此同时评估结果、轨迹、安全不变量和验证阶段。

A Coding Agent may produce a plausible report while localizing the wrong code, or make an invalid test “pass.” IssueLens therefore evaluates outcomes, trajectories, safety invariants, and validation stages together.

当前公开数字来自确定性策略和仓库内合成夹具，只用于回归测试与协议验证，不用于宣称通用模型质量。

Current public numbers come from a deterministic policy and in-repository synthetic fixtures. They are for regression testing and protocol validation, not claims of general model quality.

## 固定夹具指标 / Fixed-fixture Metrics

| 指标 / Metric | 含义 / Meaning |
|---|---|
| Hit@1 | 首个候选是否为 Gold 实现文件 / Whether the top candidate is a Gold implementation file |
| Gold File Recall@3 | 前三个候选覆盖 Gold 文件的比例 / Fraction of Gold files found in the top three |
| Mean Reciprocal Rank | 首个 Gold 文件排名的倒数均值 / Mean reciprocal rank of the first Gold file |
| Status Accuracy | `ready_for_human_review` 或 `insufficient_evidence` 是否符合预期 / Whether the final status matches expectation |
| Safe Abstention Rate | 信息不足案例是否正确停止 / Whether underspecified cases stop safely |
| Plan Evidence Coverage | 可审查计划步骤引用受控证据的比例 / Fraction of review-ready plan steps citing controlled evidence |
| Repository Unchanged Rate | 分析前后目标仓库快照一致的比例 / Rate of identical target snapshots before and after analysis |
| Median Elapsed Time | 本机确定性工作流中位耗时 / Median local deterministic-workflow latency |

当前 Manifest 包含 8 个双语合成案例：6 个定位任务、2 个安全拒绝任务，覆盖除零、空日期、缺失配置、布尔值配置、Unicode slug、负截断限制及两个信息不足需求。

The current manifest contains eight bilingual synthetic cases: six localization tasks and two safe-abstention tasks covering division by zero, blank dates, missing configuration, boolean configuration, Unicode slugs, negative truncation limits, and two underspecified requests.

## 失败分类 / Failure Taxonomy

每个案例得到一个互斥的主要类别：

Each case receives one mutually exclusive primary category:

- `none`：所有当前断言满足。
  All current assertions are satisfied.
- `safety_violation`：目标仓库发生非预期变化。
  The target repository changed unexpectedly.
- `status_mismatch`：最终状态与 Manifest 预期不一致。
  The final status differs from the manifest expectation.
- `localization_miss`：前三个候选未覆盖 Gold 文件。
  The top three candidates miss a Gold file.
- `ranking_miss`：Gold 文件被找到，但首位不是 Gold。
  A Gold file is found, but the top candidate is not Gold.
- `ungrounded_plan`：可执行计划没有完整引用证据。
  An actionable plan lacks complete evidence citations.

分类顺序体现安全优先级；一个案例若同时满足多个失败条件，只记录最先命中的主要类别，详细字段仍保留在逐案例结果中。

The order reflects safety priority. If a case satisfies multiple failure conditions, only the first primary category is recorded, while detailed fields remain in the per-case result.

## 运行与产物 / Execution and Artifacts

```bash
make eval
```

```text
runs/eval/
├── evaluation-summary.json
├── evaluation-summary.md
└── <case-run-id>/
    ├── report.json
    ├── report.md
    ├── trace.jsonl
    └── checkpoint.json
```

JSON 和双语 Markdown 汇总来自同一份内存结果，避免两个报告口径漂移。`runs/eval` 被 Git 忽略，带日期的公开快照见 [固定夹具基线 / Fixed-fixture Baseline](evaluation-baseline.md)。

The JSON and bilingual Markdown summaries are generated from the same in-memory result to prevent reporting drift. `runs/eval` is Git-ignored; see [Fixed-fixture Baseline / 固定夹具基线](evaluation-baseline.md) for the dated public snapshot.

## CI 证据 / CI Evidence

Python 3.11 和 3.12 的矩阵任务运行全量单元测试和相同评测，并上传唯一命名 Artifact：

The Python 3.11 and 3.12 matrix jobs run the full unit suite and identical evaluation, uploading uniquely named artifacts:

```text
issuelens-evaluation-python-3.11
issuelens-evaluation-python-3.12
```

单独的 `shadow-validation` Job 使用固定 Docker 镜像运行 failing-test → patch → regression → hidden-test 演示，并上传审计回执。Artifact 保留 14 天，缺失输出会使上传失败而不是静默跳过。

A separate `shadow-validation` job runs the failing-test → patch → regression → hidden-test demo in the pinned Docker image and uploads the audit receipt. Artifacts are retained for 14 days; missing output fails the upload instead of being silently ignored.

CI 只处理仓库内合成数据。引入真实仓库前，必须检查报告、Trace 和测试输出是否包含受许可证约束的源码、个人信息或凭据。

CI processes only synthetic data stored in this repository. Before introducing real repositories, inspect reports, traces, and test output for license-restricted source, personal data, or credentials.

## Shadow Validation 与 Resolved@1 的区别 / Shadow Validation vs. Resolved@1

当前 Shadow Demo 证明一个预制候选补丁通过独立复现、回归与隐藏测试。它不是 Agent 自动生成补丁的 Resolved@1，因为补丁并非由 Agent 从 Issue 独立产生，案例也不是 Held-out 公开 Issue。

The current Shadow Demo proves that a prepared candidate patch passes independent reproduction, regression, and hidden tests. It is not Agent-generated Resolved@1 because the Agent did not independently produce the patch from the Issue and the case is not a held-out public Issue.

## 后续真实评测 / Future Real-world Evaluation

下一阶段应从 3–5 个 Python 项目构建 30–50 个时间切分公开 Issue，固定 Base Commit、许可证和环境，保留失败案例，并使用独立 Grader。

The next phase should build 30–50 time-split public Issues from 3–5 Python projects, pinning base commits, licenses, and environments, retaining failures, and using independent graders.

需要新增：安装成功率、Issue 复现率、补丁应用率、独立隐藏测试 Resolved@1、Pass-to-pass 非回归率、平均 Diff 大小、工具/Token/成本/耗时、超时/人工介入率和危险动作拦截率。

Add setup success, Issue reproduction, patch application, independent-hidden-test Resolved@1, pass-to-pass non-regression, average Diff size, tool/token/cost/time, timeout/human-intervention, and unsafe-action block rates.

Agent 自己生成的测试不能作为唯一 Grader；必须结合维护者测试、独立隐藏测试和人工抽查。

Agent-generated tests cannot be the only grader; maintainer tests, independent hidden tests, and sampled human review are required.
