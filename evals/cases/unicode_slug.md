# `slugify` 应明确处理 Unicode 标题 / `slugify` Should Define Unicode Title Handling

`slugify("智能 Agent")` 当前删除全部中文字符，只保留 `agent`。请在 `src/text_tools/slug.py` 中实现并测试明确的 Unicode 转写契约。

`slugify("智能 Agent")` currently removes all Chinese characters and keeps only `agent`. Define and test an explicit Unicode transliteration contract in `src/text_tools/slug.py`.

不得修改无关的 `truncate` 行为。

Do not change unrelated `truncate` behavior.
