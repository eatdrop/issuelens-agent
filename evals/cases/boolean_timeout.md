# `get_timeout` 不应接受布尔值 / `get_timeout` Should Reject Boolean Values

Python 中 `bool` 是 `int` 的子类，因此 `get_timeout({"timeout": true})` 当前会把布尔值当作超时秒数。

Because `bool` subclasses `int` in Python, `get_timeout({"timeout": true})` currently accepts a Boolean as a timeout in seconds.

预期行为 / Expected behavior:

- `get_timeout` 对布尔值抛出 `ValueError`。
  `get_timeout` raises `ValueError` for Boolean values.
- 正整数和默认值行为保持不变。
  Positive integers and the default value remain unchanged.
