# `load_config` 应转换缺失文件错误 / `load_config` Should Translate Missing-File Errors

当配置文件不存在时，`load_config` 当前直接泄露 `FileNotFoundError`，调用方无法区分配置领域错误。

When the configuration file is absent, `load_config` currently leaks `FileNotFoundError`, so callers cannot handle a configuration-domain error consistently.

预期行为 / Expected behavior:

- 在 `src/config/loader.py` 中转换缺失文件错误。
  Translate the missing-file error in `src/config/loader.py`.
- 有效 JSON 配置仍能正常读取。
  Valid JSON configuration must still load.
