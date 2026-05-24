# Bug 修复记录

日期: 2026-05-24

## Bug 1: `max_content_length` 配置项未识别

**现象**: 构建时出现警告 `Unrecognised configuration name: max_content_length`

**原因**: `plugin.py` 的 `config_scheme` 中没有声明 `max_content_length` 配置项，`truncate_content` 方法硬编码了 `max_length=2000`。

**修复**:
- `plugin.py`: 在 `config_scheme` 中添加 `('max_content_length', config_options.Type(int, default=2000))`
- `plugin.py`: `on_config` 中将 `max_content_length` 传递给 `ContentProcessor`
- `content_processor.py`: `__init__` 新增 `max_content_length` 参数并存储为 `self.max_content_length`
- `content_processor.py`: `truncate_content` 使用 `self.max_content_length` 替代硬编码默认值

---

## Bug 2: 所有页面被跳过（不生成摘要）

**现象**: 所有页面都显示 `⏭️ 跳过`，无 AI 摘要生成

**原因**: `_discover_docs_structure` 返回的路径是相对于项目根目录的（如 `docs/计算机/...`），但 `page.file.src_path` 是相对于 `docs_dir` 的（如 `计算机/...`）。`should_generate_summary` 中的 `startswith` 匹配永远失败。

**修复**:
- `plugin.py`: `_discover_docs_structure` 现在返回相对于 `docs_dir` 的路径，根目录用空字符串 `''` 表示
- `content_processor.py`: 新增 `_normalize_enabled_folders` 方法，自动去除用户配置中 `enabled_folders` 的 `docs_dir` 前缀
- `content_processor.py`: `should_generate_summary` 中空字符串 `''` 匹配所有文件
- `plugin.py`: 默认 `enabled_folders` 从 `['blog/']` 改为 `[]`（空列表触发自动发现）

**补充修复 (2026-05-24)**: MkDocs 在 `on_config` 阶段已将 `docs_dir` 解析为绝对路径（如 `/home/.../bag/docs`），而用户配置的 `enabled_folders: ["docs"]` 只是短名称。`_normalize_enabled_folders` 之前只匹配完整绝对路径前缀，导致短名称无法被识别。
- `content_processor.py`: `_normalize_enabled_folders` 增加对 `docs_dir` 目录名（basename）的匹配 —— 当 folder 等于 `docs_dir` 的 basename（如 `docs`）或以它开头时，同样去除前缀

---

## Bug 3: exclude_patterns 不支持 glob 模式

**现象**: 用户配置了 `**/api/**`、`*.adoc` 等 glob 模式，但排除规则不生效

**原因**: `should_generate_summary` 使用 Python 的 `in` 运算符做简单子串匹配，无法识别 glob 通配符

**修复**:
- `content_processor.py`: 导入 `fnmatch` 模块
- `content_processor.py`: `should_generate_summary` 中的排除匹配改为 `pattern in file_path or fnmatch.fnmatch(file_path, pattern)`

---

## Bug 4: `!!! abstract` admonition 不渲染，显示为原始文本

**现象**: 页面显示 `!!! abstract "💡 AI摘要 (QWEN)" 本文档介绍了...` 原始文本，未被渲染成 admonition 提示框。实际 HTML 为 `<p>!!! abstract ...</p>`。

**原因**: `format_summary` 中 `\n\n` 在标题行和内容之间插入了一个空行，且 `markdown_extensions` 未显式声明 `admonition` 扩展。

**修复**:
- `content_processor.py`: 去掉标题行与内容之间的空行（`\n\n` → `\n`）
- `content_processor.py`: 对多行摘要每行加 4 空格缩进，防止多行内容跳出 admonition 块
- `content_processor.py`: 图标映射新增 `qwen`、`siliconflow`，查找改用 `service.lower()` 大小写不敏感
- `mkdocs.yml`: `markdown_extensions` 显式添加 `admonition`、`pymdownx.details`、`pymdownx.superfences`

---

## Bug 5: Google Fonts 加载超时

**现象**: 浏览器控制台报错 `fonts.googleapis.com Failed to load resource: net::ERR_CONNECTION_TIMED_OUT`

**原因**: MkDocs Material 主题默认加载 Google Fonts，国内网络无法访问

**修复**:
- `mkdocs.yml`: `theme` 下添加 `font: false`，禁用 Google Fonts，改用系统默认字体
