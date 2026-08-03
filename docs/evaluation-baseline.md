# 固定夹具基线评测 / Fixed-fixture Baseline Evaluation

## 评测结论 / Evaluation Summary

2026-07-29，在 3 个内置合成案例上运行 IssueLens deterministic baseline：

On 2026-07-29, the IssueLens deterministic baseline was evaluated on three built-in synthetic cases:

| 指标 / Metric | 结果 / Result | 有效样本 / Eligible Cases |
| --- | ---: | ---: |
| Hit@1 | 1.0000 / 100% | 2 / 2 |
| Gold File Recall@3 | 1.0000 / 100% | 2 / 2 |
| Mean Reciprocal Rank | 1.0000 / 100% | 2 / 2 |
| 状态准确率 / Status Accuracy | 1.0000 / 100% | 3 / 3 |
| 安全拒绝率 / Safe Abstention Rate | 1.0000 / 100% | 1 / 1 |
| 仓库保持不变率 / Repository Unchanged Rate | 1.0000 / 100% | 3 / 3 |
| 计划证据覆盖率 / Plan Evidence Coverage | 1.0000 / 100% | 2 个可审查案例 / 2 review-ready cases |
| 中位耗时 / Median Elapsed Time | 15.71 ms | 3 cases |

这些结果证明当前 deterministic baseline 能在固定冒烟夹具上复现预期行为。它们不能证明系统在真实公开 Issue、陌生仓库或通用 Coding Agent 任务上的质量。

These results show that the current deterministic baseline reproduces the expected behavior on the fixed smoke-test fixtures. They do not establish quality on real public Issues, unfamiliar repositories, or general Coding Agent tasks.

## 评测配置 / Evaluation Configuration

- 评测清单 / Manifest: `evals/manifest.json`
- 执行命令 / Command: `make eval`
- 工作流 / Workflow: deterministic `IssueAnalysisWorkflow`
- 案例数 / Case count: 3
- 有 Gold 文件的定位案例 / Localization cases with Gold files: 2
- 信息不足的安全拒绝案例 / Underspecified safe-abstention cases: 1
- 操作系统与架构 / Operating system and architecture: Darwin arm64
- Python: 3.12.10
- 网络或外部模型调用 / Network or external model calls: 无 / None

评测输出写入 Git 忽略的 `runs/eval/evaluation-summary.json`，每个案例还会生成报告和 Trace。

Evaluation output is written to the Git-ignored `runs/eval/evaluation-summary.json`; each case also produces a report and trace.

## 逐案例结果 / Per-case Results

| 案例 / Case | 预期状态 / Expected | 实际状态 / Actual | 首位候选 / Top Candidate | Hit@1 | Recall@3 | MRR | 仓库未变 / Repo Unchanged | 耗时 / Elapsed |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| `division-by-zero` | `ready_for_human_review` | `ready_for_human_review` | `src/calculator.py` | 1.0 | 1.0 | 1.0 | 是 / Yes | 15.71 ms |
| `blank-due-date` | `ready_for_human_review` | `ready_for_human_review` | `src/task_tracker/parser.py` | 1.0 | 1.0 | 1.0 | 是 / Yes | 18.43 ms |
| `underspecified-export` | `insufficient_evidence` | `insufficient_evidence` | `src/calculator.py` | 不适用 / N/A | 不适用 / N/A | 不适用 / N/A | 是 / Yes | 14.49 ms |

`underspecified-export` 没有 Gold 文件，因此不进入 Hit@1、Recall@3 或 MRR 的分母。它用于检查系统是否返回 `insufficient_evidence`，而不是根据弱证据编造可执行计划。

`underspecified-export` has no Gold file, so it is excluded from the denominators of Hit@1, Recall@3, and MRR. It checks whether the system returns `insufficient_evidence` instead of fabricating an actionable plan from weak evidence.

## 指标解释 / Metric Interpretation

- **Hit@1 = 2/2**：两个定位案例的首位候选都是唯一 Gold 实现文件。
  In both localization cases, the top candidate was the sole Gold implementation file.
- **Gold File Recall@3 = 2/2**：两个定位案例都在前三个候选中覆盖了唯一 Gold 文件。
  Both localization cases covered their sole Gold file within the top three candidates.
- **MRR = 1.0**：两个定位案例的首个 Gold 文件排名均为第一。
  The first Gold file ranked first in both localization cases.
- **状态准确率 = 3/3**：两个可审查案例和一个信息不足案例的状态都符合清单预期。
  Status matched the manifest for two review-ready cases and one underspecified case.
- **安全拒绝率 = 1/1**：唯一信息不足案例被正确拒绝。
  The only underspecified case was correctly rejected.
- **仓库保持不变率 = 3/3**：所有案例在分析前后都保持相同仓库快照。
  All cases retained identical repository snapshots before and after analysis.
- **计划证据覆盖率 = 1.0**：两个 `ready_for_human_review` 案例的计划步骤都满足当前证据引用检查。
  Plan steps in both `ready_for_human_review` cases satisfied the current evidence-reference check.
- **中位耗时 = 15.71 ms**：该数字只描述本次本地 deterministic 运行，不是跨机器性能基准。
  This value describes only this local deterministic run and is not a cross-machine performance benchmark.

## 可用于简历的安全表述 / Resume-safe Statement

> 在 3 个合成冒烟案例的 deterministic baseline 上，两个代码定位案例均实现 Hit@1、Gold File Recall@3 和 MRR 1.0；唯一信息不足案例被正确拒绝，3/3 次运行保持目标仓库快照不变。
>
> On a three-case synthetic smoke evaluation of the deterministic baseline, both localization cases achieved Hit@1, Gold File Recall@3, and MRR of 1.0; the sole underspecified case was correctly rejected, and all 3/3 runs preserved the target-repository snapshot.

使用该表述时必须保留“3 个合成冒烟案例”和 “deterministic baseline”的限定，不能简化为“真实 Issue 准确率 100%”。

Keep the qualifiers “three synthetic smoke cases” and “deterministic baseline” whenever using this statement. Do not shorten it to “100% accuracy on real Issues.”

## 限制 / Limitations

- 只有 3 个手工维护的合成案例，样本量过小。
  There are only three manually maintained synthetic cases, which is far too small for generalization.
- 案例与 deterministic 策略来自同一项目，不是独立 Held-out 数据。
  The cases and deterministic policy come from the same project; this is not independent held-out data.
- 安全拒绝率只有 1 个有效样本。
  Safe Abstention Rate has only one eligible sample.
- 评测不生成补丁、不执行目标测试，也不计算 Resolved@1。
  The evaluation does not generate patches, execute target tests, or calculate Resolved@1.
- 评测不覆盖真实 LLM 的随机性、Token、成本或 Prompt Injection 鲁棒性。
  It does not cover real-LLM randomness, tokens, cost, or prompt-injection robustness.
- 耗时会随硬件、操作系统和后台负载变化。
  Timing varies with hardware, operating system, and background load.

## 复现方式 / Reproduction

```bash
make eval
```

检查结构化汇总：

Inspect the structured summary:

```bash
sed -n '1,260p' runs/eval/evaluation-summary.json
```

复现时应同时报告案例数量、有效分母和限制，而不是只报告百分比。

When reproducing the evaluation, report the case count, eligible denominators, and limitations alongside percentages.
