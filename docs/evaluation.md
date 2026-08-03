# IssueLens 评测方案 / Evaluation

## 为什么结果和轨迹都重要 / Why Outcome and Trajectory Both Matter

Coding Agent 可能输出看似合理的报告，却检索了错误文件；也可能通过一个没有真正验证需求的测试。因此 IssueLens 同时记录结果和过程。

A Coding Agent may produce a plausible report while searching the wrong files, or pass a test that does not validate the actual requirement. IssueLens therefore records both outcome and process.

- **结果指标 / Outcome metrics**：是否找到预期实现文件。
  Whether the expected implementation file was found.
- **轨迹指标 / Trajectory metrics**：证据数量、计划引用、状态迁移、耗时和写入次数。
  Evidence count, plan citations, state transitions, elapsed time, and write count.

## V0.1 指标 / V0.1 Metrics

| 指标 / Metric | 含义 / Meaning |
|---|---|
| Hit@1 | 首个候选文件是否为 Gold 实现文件 / Whether the top candidate is a gold implementation file |
| Gold File Recall@3 | 前三个候选文件覆盖的 Gold 实现文件比例 / Gold implementation files found in the top three |
| MRR | 首个 Gold 文件的排名质量 / Rank quality of the first gold file |
| Plan Evidence Coverage | 引用代码证据的计划步骤比例 / Fraction of plan steps citing code evidence |
| Repository Unchanged Rate | 目标仓库哈希保持不变的比例 / Rate at which target repository hashes remain unchanged |
| Safe Abstention Rate | 信息不足时正确停止的比例 / Rate of correct abstention on underspecified tasks |
| Median Elapsed Time | 确定性分析的中位耗时 / Median deterministic-analysis latency |

内置三个案例只是冒烟测试，不能用于宣称模型质量。

The three built-in cases are smoke tests, not a claim of model quality.

当前固定夹具实测结果：

Current measured fixed-fixture results:

- [基线评测报告 / Baseline Evaluation Report](evaluation-baseline.md)

每次运行 `make eval` 都会从同一份内存 summary 自动生成以下本地产物：

Every `make eval` run automatically generates these local artifacts from the same in-memory summary:

```text
runs/eval/
├── evaluation-summary.json    # 结构化汇总 / Structured summary
└── evaluation-summary.md      # 中英双语自动报告 / Bilingual generated report
```

`runs/eval` 被 Git 忽略，因此自动报告代表最新本地运行；上方链接的文档是带日期的公开评测快照。

`runs/eval` is Git-ignored, so the generated report represents the latest local run; the linked document above is a dated public evaluation snapshot.

## CI 评测证据 / CI Evaluation Evidence

GitHub Actions 会在 Python 3.11 和 3.12 的矩阵任务中分别运行相同的 deterministic evaluation，并上传唯一命名的 Artifact：

GitHub Actions runs the same deterministic evaluation in the Python 3.11 and 3.12 matrix jobs and uploads uniquely named artifacts:

```text
issuelens-evaluation-python-3.11
issuelens-evaluation-python-3.12
```

每个 Artifact 包含该矩阵任务生成的结构化汇总、双语 Markdown 汇总、逐案例报告和 `trace.jsonl`。进入对应的 GitHub Actions Run 后，可以在 Run Summary 的 Artifacts 区域下载。

Each artifact contains the structured summary, bilingual Markdown summary, per-case reports, and `trace.jsonl` produced by that matrix job. Open the corresponding GitHub Actions run and download it from the Artifacts section of the run summary.

Artifact 保留 14 天；如果评测目录不存在或没有文件，上传步骤会失败，而不是静默跳过证据。

Artifacts are retained for 14 days. If the evaluation directory is missing or empty, the upload step fails instead of silently omitting evidence.

当前 CI 评测只使用仓库内的合成夹具。加入真实 Issue 或外部仓库前，必须先检查 Trace 和报告是否包含源码、个人信息、凭据或其他不应上传的内容。

The current CI evaluation uses only synthetic fixtures stored in this repository. Before adding real Issues or external repositories, inspect traces and reports for source code, personal data, credentials, or other content that must not be uploaded.

## V1 评测目标 / V1 Evaluation Target

从 3–5 个 Python 仓库中构建 30–50 个时间切分 Issue，固定 Base Commit 和许可证信息，不得只挑成功案例。

Create 30–50 time-split Issues from 3–5 Python repositories. Pin base commits and license metadata; do not select only successful examples.

新增指标包括：

Additional metrics include:

- 环境安装成功率 / Environment setup success rate
- Issue 复现率 / Issue reproduction rate
- 失败测试正确率 / Failing-test correctness
- 补丁应用成功率 / Patch application rate
- 独立隐藏测试下的 Resolved@1 / Resolved@1 using independent hidden tests
- Pass-to-pass 非回归率 / Pass-to-pass non-regression rate
- 平均 Diff 大小 / Average diff size
- 工具调用、Token、成本与耗时 / Tool calls, tokens, cost, and wall time
- 超时率和人工介入率 / Timeout and human-intervention rate
- 危险动作拦截率 / Unsafe-action block rate
- 被接受和合并的公开 PR 数 / Accepted and merged public pull requests

Agent 自己生成的测试不能是唯一 Grader。评测必须结合确定性测试、维护者测试和人工抽查。

Agent-generated tests cannot be the only grader. Evaluation must combine deterministic tests, maintainer tests, and sampled human review.
