# 固定夹具基线评测 / Fixed-fixture Baseline Evaluation

## 评测结论 / Evaluation Summary

2026-08-03，在 8 个手工维护的双语合成案例上运行 IssueLens deterministic baseline：

On 2026-08-03, the IssueLens deterministic baseline was evaluated on eight manually maintained bilingual synthetic cases:

| 指标 / Metric | 结果 / Result | 有效样本 / Eligible Cases |
|---|---:|---:|
| Hit@1 | 1.0000 / 100% | 6 / 6 |
| Gold File Recall@3 | 1.0000 / 100% | 6 / 6 |
| Mean Reciprocal Rank | 1.0000 / 100% | 6 / 6 |
| 状态准确率 / Status Accuracy | 1.0000 / 100% | 8 / 8 |
| 安全拒绝率 / Safe Abstention Rate | 1.0000 / 100% | 2 / 2 |
| 仓库保持不变率 / Repository Unchanged Rate | 1.0000 / 100% | 8 / 8 |
| 计划证据覆盖率 / Plan Evidence Coverage | 1.0000 / 100% | 6 个可审查案例 / 6 review-ready cases |
| 中位耗时 / Median Elapsed Time | 16.60 ms | 8 cases |

这些结果证明当前确定性基线能在固定合成夹具上复现预期行为。它们不能证明陌生仓库、真实公开 Issue、真实 LLM 或通用 Coding Agent 任务上的质量。

These results show that the deterministic baseline reproduces expected behavior on fixed synthetic fixtures. They do not establish quality on unfamiliar repositories, real public Issues, real LLMs, or general Coding Agent tasks.

## 评测配置 / Evaluation Configuration

- 日期 / Date: `2026-08-03`
- Manifest: `evals/manifest.json`
- 命令 / Command: `make eval`
- 工作流 / Workflow: deterministic `IssueAnalysisWorkflow`
- 案例数 / Cases: 8
- 定位案例 / Localization cases: 6
- 安全拒绝案例 / Safe-abstention cases: 2
- 环境 / Environment: Darwin arm64, Python 3.12.10
- 网络或外部模型 / Network or external model: 无 / None

耗时只描述该次本地运行，会随机器和后台负载变化；它不是跨平台性能基准。

Timing describes only this local run and varies with hardware and background load; it is not a cross-platform performance benchmark.

## 逐案例结果 / Per-case Results

| 案例 / Case | 预期与实际状态 / Expected & Actual | 首位候选 / Top Candidate | Hit@1 | Recall@3 | MRR | 失败分类 / Failure | 未改仓库 / Unchanged | 耗时 / Time |
|---|---|---|---:|---:|---:|---|---|---:|
| `division-by-zero` | `ready_for_human_review` | `src/calculator.py` | 1.0 | 1.0 | 1.0 | `none` | 是 / Yes | 16.28 ms |
| `blank-due-date` | `ready_for_human_review` | `src/task_tracker/parser.py` | 1.0 | 1.0 | 1.0 | `none` | 是 / Yes | 16.92 ms |
| `underspecified-export` | `insufficient_evidence` | `src/calculator.py` | N/A | N/A | N/A | `none` | 是 / Yes | 12.57 ms |
| `missing-config` | `ready_for_human_review` | `src/config/loader.py` | 1.0 | 1.0 | 1.0 | `none` | 是 / Yes | 17.63 ms |
| `boolean-timeout` | `ready_for_human_review` | `src/config/loader.py` | 1.0 | 1.0 | 1.0 | `none` | 是 / Yes | 21.35 ms |
| `unicode-slug` | `ready_for_human_review` | `src/text_tools/slug.py` | 1.0 | 1.0 | 1.0 | `none` | 是 / Yes | 19.30 ms |
| `negative-truncate-limit` | `ready_for_human_review` | `src/text_tools/slug.py` | 1.0 | 1.0 | 1.0 | `none` | 是 / Yes | 16.01 ms |
| `underspecified-dashboard` | `insufficient_evidence` | 无 / None | N/A | N/A | N/A | `none` | 是 / Yes | 14.88 ms |

两项安全拒绝案例没有 Gold 文件，因此不进入 Hit@1、Recall@3 或 MRR 分母。可审查案例与安全拒绝案例分别计算计划覆盖率和拒绝率。

The two safe-abstention cases have no Gold files and are excluded from Hit@1, Recall@3, and MRR denominators. Plan coverage and abstention rate use review-ready and underspecified cases respectively.

## 可用于简历的安全表述 / Resume-safe Statement

> 在 8 个手工维护的合成案例 deterministic baseline 上，6 个代码定位案例的 Hit@1、Gold File Recall@3 与 MRR 均为 1.0；2 个信息不足案例均正确拒绝，8/8 次分析保持目标仓库快照不变。
>
> On an eight-case, manually maintained synthetic deterministic baseline, all six localization cases achieved Hit@1, Gold File Recall@3, and MRR of 1.0; both underspecified cases were correctly rejected, and all 8/8 analyses preserved the target-repository snapshot.

必须保留“手工维护的合成案例”和 “deterministic baseline”限定，不能改写为“真实 Issue 准确率 100%”或 “Resolved@1 100%”。

Keep the qualifiers “manually maintained synthetic cases” and “deterministic baseline.” Do not rewrite this as “100% real-Issue accuracy” or “100% Resolved@1.”

## 限制 / Limitations

- 只有 8 个合成案例，样本量不足以外推。
  Eight synthetic cases are insufficient for generalization.
- 案例与确定性策略由同一项目维护，不是独立 Held-out 数据。
  The cases and deterministic policy are maintained by the same project and are not independent held-out data.
- 安全拒绝率只有 2 个有效样本。
  Safe Abstention Rate has only two eligible samples.
- 当前评测不生成补丁，不计算 Agent-generated Resolved@1。
  The current evaluation does not generate patches or calculate Agent-generated Resolved@1.
- Shadow Demo 的候选补丁为预制夹具，不能混入定位指标。
  The Shadow Demo uses a prepared patch fixture and must not be mixed into localization metrics.
- 不覆盖真实 LLM 的随机性、Token、成本、服务商差异或语义级 Prompt Injection。
  It does not cover real-LLM randomness, tokens, cost, provider differences, or semantic prompt injection.

## 复现 / Reproduction

```bash
make eval
sed -n '1,280p' runs/eval/evaluation-summary.json
sed -n '1,280p' runs/eval/evaluation-summary.md
```

复现报告必须同时列出案例数量、有效分母、运行环境和上述限制，而不是只展示百分比。

A reproduction report must include case count, eligible denominators, environment, and the limitations above—not percentages alone.
