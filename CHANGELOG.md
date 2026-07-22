# Changelog

本项目所有值得注意的变更都记录在此文件。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.3.0] - 2026-07-22

### 新增
- **语音转写（可选，完全本地离线）**：新增 `transcribe_voice.py`——把微信语音（`cache/*/Message/<md5>/VoiceTemp` 下的**明文 SILK v3**，无需密钥）收集 → 本地 `pilk` 解码为 WAV → 本地 `faster-whisper` 转写成带时间戳的中文，产出 `voice_transcripts.md` 并入时间线。不调用任何云 ASR、音频不外发；模型可预下载后 `--offline` 断网运行；中间 wav 转写后即删。
- `requirements-voice.txt`（可选依赖 pilk + faster-whisper）；`references` 固化语音格式（wechat-local-data §6）与离线安装（toolchain-setup §8）。
- 语音单测 7 项（SILK 头识别 / 文件名时间戳解析）；SILK→WAV 解码经 `pilk` 合成往返验证。测试总数 22 → 29。

### 说明
- 语音覆盖“被播放过”的语音（`VoiceTemp` 明文缓存，非全量）；端到端转写首次需联网下模型、建议真机 `--dry-run`/`--limit` 抽验。

## [1.2.0] - 2026-07-22

面向开源的专业化加固（多角度评审后的统一优化）。

### 新增
- 单元测试 `tests/`：V2 图片解密的合成往返自测（极小图 / 含明文中段的大图 / 错误密钥被拒）+ 共享库纯函数测试，共 22 项。
- 开源标准文件：`SECURITY.md`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`DISCLAIMER.md`、`CHANGELOG.md`。
- 工程配置：`pyproject.toml`（ruff + pytest）、`requirements-dev.txt`、`.editorconfig`、GitHub Actions CI 与 issue / PR 模板。
- 脱敏示例报告 `docs/sample-report.html`；README 增加徽章、目录、快速开始与效果预览。
- 共享工具函数 `day_bounds()`（时间范围解析 + 校验）与 `write_manifest()`。
- README 增补「核心能力与标准用法」（按用法组织的能力总览）与「法律声明与第三方归属」（第三方项目 / 商标 / 无关联声明）。
- 统一小写标识：skill 目录名、GitHub 仓库名与文档中的仓库 URL 一律用 `rfwg`（品牌缩写 `RFWG` 与 `$RFWG` 变量名保留大写）。

### 修复
- **报告模板未随仓库发布**：`.gitignore` 的 `report*.html` 误伤 `assets/report-template.html`，导致克隆后缺少报告骨架（第 7 步开箱即坏）。
- **解密临时库清理**：`decrypt_moments.py` 在 HMAC 变体不匹配时先删仍被打开的临时库，Windows 上会崩溃并残留含他人隐私的明文；改为先关连接、收窄异常类型、`0600` 权限。
- 消除全部 12 处 `open()` 句柄泄漏（统一 `with`）。
- `decrypt_images_v2.py` 区分“未命中文件”与“解密全失败”，不再把无输入误报为密钥错误。
- 三个脚本对 `--start/--end` 加入格式与顺序校验，坏输入给清晰报错。

### 变更
- SKILL frontmatter：`name` 规范为小写 `rfwg`；`description` 改第三人称并补负向触发；新增 `compatibility`；`version` 移入 `metadata`。
- 统一 macOS / Windows 平台支持口径（诚实边界，消除自相矛盾表述）。
- 修正模板引用为 `$RFWG/assets/report-template.html`。
- `.gitignore` 加固：补 `images_full/`、`moments_img/` 等他人原图目录，覆盖多轮深化产物编号。

## [1.1.0] - 2026-07-22

### 新增
- macOS / Windows 双平台支持：分轨工具链文档，脚本跨平台化（`RFWG_DB_DIR` / `RFWG_KEYS` 等环境变量）。
- 过长图纵向切分 `split_long_image.py`：长截图分段读，避免降采样糊字。
- 全量原图解密 `decrypt_images_v2.py`：`wxkey image-key` → 聊天 `msg/attach` + 朋友圈 `Sns/Img`。

## [1.0.0] - 2026-07-21

### 新增
- RFWG 首个版本：从微信群 / 用户 / 主题做离线调研并生成报告（Markdown 分件 + 单文件 HTML + SVG）。
- 发言轮次合并、图片缩略图收集与判读分拣、朋友圈 `sns.db` 解密、报告模板与浏览器验收流程。

[1.3.0]: https://github.com/Octo-o-o-o/rfwg/releases/tag/v1.3.0
[1.2.0]: https://github.com/Octo-o-o-o/rfwg/releases/tag/v1.2.0
[1.1.0]: https://github.com/Octo-o-o-o/rfwg/releases/tag/v1.1.0
[1.0.0]: https://github.com/Octo-o-o-o/rfwg/releases/tag/v1.0.0
