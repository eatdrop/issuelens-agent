# `truncate` 应拒绝负数限制 / `truncate` Should Reject a Negative Limit

`truncate("abcdef", -1)` 当前利用切片返回 `abcde`，而不是拒绝无效限制。

`truncate("abcdef", -1)` currently relies on slicing and returns `abcde` instead of rejecting an invalid limit.

预期行为 / Expected behavior:

- `truncate` 对负数 `limit` 抛出 `ValueError`。
  `truncate` raises `ValueError` for a negative `limit`.
- 零和正数限制继续按字符数截断。
  Zero and positive limits continue to truncate by character count.
