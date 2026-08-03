# `divide` 对零分母应抛出 `ValueError` / `divide` Should Reject a Zero Denominator with `ValueError`

调用 `divide(10, 0)` 时，当前实现会泄露底层 `ZeroDivisionError`。计算器公共 API 约定领域校验错误统一使用 `ValueError`。

Calling `divide(10, 0)` currently leaks a low-level `ZeroDivisionError`. The calculator public API documents domain-validation failures as `ValueError`.

预期行为 / Expected behavior:

- `divide(10, 0)` 抛出 `ValueError`。
  `divide(10, 0)` raises `ValueError`.
- 正常除法行为保持不变。
  Normal division remains unchanged.
- 在 `tests/test_calculator.py` 中添加聚焦的回归测试。
  Add a focused regression test in `tests/test_calculator.py`.
