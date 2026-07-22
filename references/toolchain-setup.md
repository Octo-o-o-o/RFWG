# RFWG 工具链一次装好（macOS 与 Windows 分轨）

> 目标：**照抄即可，AI 不用再调研**。给出两平台各自的确切来源、安装命令、密钥/数据落盘位置、交互差异、故障排查，以及"什么测过/什么没测"。

## 0. 平台支持矩阵（先读）

| 维度 | macOS（arm64）| Windows（amd64）|
|------|---------------|-----------------|
| 微信版本 | 微信 4.x | 微信/Weixin 4.x |
| 取库密钥的方式 | `wxkey` 走 shadow WeChat + 一次性 sudo（**不关 SIP**）| 直接 `ReadProcessMemory` 扫 `Weixin.exe` 内存（**需管理员**，无 SIP 之说）|
| 取图片密钥 | `wxkey image-key`（kvcomm 缓存派生）| 社区内存扫描器扫 `Weixin.exe`（如 wechat-decrypt 的 `find_image_key.py`）|
| 微信数据根 | `~/Library/Containers/com.tencent.xinWeChat/.../xwechat_files/<account>/` | `%USERPROFILE%\Documents\xwechat_files\<wxid>\` |
| 子目录布局（`db_storage`/`msg/attach`/`cache/*/Thumb`/`cache/*/Sns/Img`）| **两平台一致** | **两平台一致** |
| V2 图片格式 / SQLCipher4 参数 | **全平台一致** | **全平台一致** |
| RFWG 图片/解密/切图脚本 | ✅ 已测 | ✅ 跨平台可跑（配好 config/keys 后，见 §3）|
| RFWG 文字导出（`history` → `build_report_md`）| ✅ 用 `@canghe_ai/wechat-cli`（**macOS-arm64 独占**）| ⚠️ 该 CLI 无 Windows 版；需换 Windows 工具 + 映射成 raw.json（见 §3.3）|

**一句话**：底层数据与所有解密/图片逻辑全平台通吃；差异只在**装哪个工具、怎么取密钥、数据在哪**，外加 Windows 上"聊天文字导出"要换工具并做一次格式映射。**Linux**：微信本地库形态不同，未适配。

前置：微信**已登录且至少打开过一个聊天**。Python 3 两平台都要（§1）。

## 1. 通用：Python 依赖（两平台相同）

```bash
pip3 install -r requirements.txt        # externally-managed 报错时加 --break-system-packages
# Windows PowerShell 同理：py -m pip install -r requirements.txt
```

`pycryptodome`（AES/SQLCipher 解密）+ `pillow`（拼图/截图切片/长图切分）。已在 Python 3.12 验证。字体：拼图标签会自动在 macOS(PingFang/Arial Unicode) / Windows(微软雅黑 msyh) / Linux(DejaVu) 里挑一个。

---

## 2. macOS 轨（已端到端验证）

### 2.1 wechat-cli —— 文字/联系人/会话/数据库密钥/缩略图（必需）

```bash
npm i -g @canghe_ai/wechat-cli      # 需 Node≥14；预编译 darwin-arm64（仅 Apple Silicon）
wechat-cli init                     # 首次：提取数据库密钥；可能弹 Mac 管理员密码 / 要求"完全磁盘访问"
```

成功后：`~/.wechat-cli/config.json`（含 `db_dir`）+ `~/.wechat-cli/all_keys.json`（**数据库密钥**）。命令：`sessions/contacts/members/history`。

### 2.2 wxkey —— 只在"要全量原图"时需要（派生图片密钥）

```bash
go install github.com/r266-tech/wxkey/cmd/wxkey@latest   # 需 Go≥1.21；或用 r266 wechat-cli release zip 内置版
wxkey bootstrap      # 首次：ad-hoc 签名 shadow WeChat + 一次性 sudo 存 Keychain（不需关 SIP）
wxkey image-key      # 派生并验证 image_key / image_xor_key（优先本机 kvcomm 缓存，不读进程）
```

结果写入 `~/.config/wxcli/config.json`；wxkey **不把 raw key 打到 stdout**。RFWG 的 `decrypt_images_v2.py` 会自动从该 config 发现 `image_key/image_xor_key`。

---

## 3. Windows 轨（数据与脚本可用；文字导出需映射）

Windows 无 SIP，取密钥直接扫进程内存（需**以管理员运行**）。有两条路：

### 3.1 路线 A（推荐，官方多平台）：r266-tech/wechat-cli

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://github.com/r266-tech/wechat-cli/releases/latest/download/install-release.ps1 | iex"
wechat-cli cache refresh --force     # 首次：保持微信登录并打开一个聊天，扫内存写 key map
wechat-cli status --pretty
```
装到 `%LOCALAPPDATA%\wechat-cli`。命令是 `timeline/resolve-chat/sns-feed/context/media/export`（**注意：不是 `history`**）。图片可 `media` 取可读路径、或内置解码到 media-cache。

### 3.2 路线 B（纯 Python 社区工具）：wechat-decrypt 类

如 [`ylytdeng/wechat-decrypt`](https://github.com/ylytdeng/wechat-decrypt)、[`JustLookAtNow/wechat-decrypt`](https://github.com/JustLookAtNow/wechat-decrypt)、[`ZedeX/weixin-decrypte-script`](https://github.com/ZedeX/weixin-decrypte-script)。它们用 `config.json{db_dir, keys_file, wechat_process:"Weixin.exe"}` + `all_keys.json`——**与 RFWG 同 schema**。以管理员跑其 `find_all_keys.py` 扫出 `all_keys.json`，图片密钥用其 `find_image_key.py`。

### 3.3 让 RFWG 的脚本在 Windows 上跑

RFWG 的**图片/朋友圈/切图脚本本身跨平台**，只需让它找到数据与密钥（三选一）：

```powershell
# 数据根：指向 db_storage（微信 设置→文件管理 可查路径）
setx RFWG_DB_DIR "%USERPROFILE%\Documents\xwechat_files\<wxid>\db_storage"
# 数据库密钥 / 图片密钥（如不在默认位置）：
setx RFWG_KEYS   "C:\path\to\all_keys.json"        # decrypt_moments.py 需要
setx RFWG_IMG_KEY "<16位ascii或32hex>"             # decrypt_images_v2.py（图片AES）
setx RFWG_IMG_XOR "0x??"                            # 图片XOR（社区扫描器会给）
```
- 之后 `collect_images.py`（无需密钥）、`decrypt_images_v2.py --room/--sns`、`split_long_image.py`、`sort_images.py`、`decrypt_moments.py` 都能直接用（路径全用 `os.path.join`，字体自动挑 Windows 微软雅黑）。
- 也可不设 env，直接在 `%USERPROFILE%\.wechat-cli\` 放 `config.json`(含 `db_dir`) 与 `all_keys.json`，RFWG 会自动发现（含 `%LOCALAPPDATA%\wechat-cli\`）。

### 3.4 文字导出的一次性映射（Windows 唯一需要手工适配的点）

RFWG 的 `build_report_md.py` / `build_people_md.py` 吃的是 **`@canghe_ai/wechat-cli history --format json`** 的形态，而它 **macOS 独占**。Windows 上用路线 A 的 `wechat-cli export`/`timeline` 或路线 B 读出的消息，**映射成下面这个 `raw.json` 契约**即可（一段脚本的事，AI 可直接生成）：

```json
{ "count": 15852,
  "messages": [
    "[2026-06-21 09:05] 张三: 大家好",
    "[2026-06-21 09:06] 李四: [图片]",
    "[2026-06-21 09:07] 王五: 同意 ↳ 回复 张三: 大家好"
  ] }
```
- 每条是**渲染字符串** `"[YYYY-MM-DD HH:MM] 发送者: 内容"`；系统消息用 `"[YYYY-MM-DD HH:MM] [系统] ..."`；引用在行尾追加 `" ↳ 回复 <被引者>: <被引内容>"`；图片/表情/语音/视频/卡片等媒体正文写 `[图片]`/`[语音]` 等占位。
- 映射好后，第 3~4 步（`build_report_md.py` / `build_people_md.py`）与后续图片、朋友圈、HTML、切图流程**与 macOS 完全一致**。

---

## 4. 密钥/配置落盘一览

| 文件 | macOS | Windows | 内容 | 纪律 |
|------|-------|---------|------|------|
| 数据库 config | `~/.wechat-cli/config.json` | `%LOCALAPPDATA%\wechat-cli\config.json` 或自建 `~/.wechat-cli/config.json`（含 `db_dir`）| `db_dir` | 不外泄 |
| 数据库密钥 | `~/.wechat-cli/all_keys.json` | 同上目录 / `RFWG_KEYS` | SQLCipher raw key | 绝不提交 |
| 图片密钥 | `~/.config/wxcli/config.json`（wxkey）| 社区扫描器输出 / `RFWG_IMG_KEY`+`RFWG_IMG_XOR` | `image_key`/`image_xor_key` | 绝不提交 |

RFWG 优先级：`RFWG_DB_DIR`/`RFWG_KEYS`/`RFWG_IMG_KEY`/`RFWG_IMG_XOR` 环境变量 > 上表默认位置自动发现。

## 5. 一分钟自检

```bash
# 通用
python3 -c "import Crypto,PIL;print('py deps ok')"
# macOS
wechat-cli sessions --limit 3 && command -v wxkey && wxkey doctor
# Windows（PowerShell，管理员）
wechat-cli status --pretty        # 路线A
python3 -c "import wxcommon as w; print(w.wechat_root())"   # 在 scripts/ 下，验证 RFWG 能定位数据根
```

## 6. 故障排查

| 现象 | 平台 | 处理 |
|------|------|------|
| `init`/`cache refresh` 失败、无密钥 | 两 | 微信未登录 / 未授权（mac 完全磁盘访问；win 以管理员运行）/ 版本非 4.x |
| RFWG 报"未找到 config.json / all_keys.json" | 两 | 设 `RFWG_DB_DIR`/`RFWG_KEYS`，或把 config/keys 放到 §4 默认位置 |
| `sessions/timeline` 空 | 两 | 先列会话拿准确 username（群是 `…@chatroom`）|
| `history` 命令不存在 | Windows | 路线 A 是 `timeline/export`，非 `history`；文字导出按 §3.4 映射 |
| `collect_images.py` 收不到图 | 两 | 该时段没加载过缩略图；改走 `decrypt_images_v2.py --room` 原图 |
| 解密"全部失败" | 两 | image_key/xor 不对；mac 重跑 `wxkey image-key`，win 重扫内存密钥；确认是 4.x V2（头 `07 08 56 32`）|
| `--media` 图片路径都一样 | macOS | 上游 bug，别用它映射，用 `--room` 按 mtime 定位（见 wechat-local-data §1）|
| 浏览器验收 `file://` 打不开 / 端口占用 | 两 | 起本地 http：`python3 -m http.server 8899 -d "$OUT"`；占用换 8900+ |

## 7. 什么测过 / 什么没测（诚实边界）

- ✅ **macOS 端到端**：文字（`wechat-cli history`）+ 缩略图 + 报告构建 + 朋友圈 + HTML 验收，真实群跑通。
- ✅ **V2 解密逻辑**（全平台通用）：`try_decrypt` 有**合成加密往返自测**（小图尾部 XOR、>1MB 含 raw 中段逐字节精确还原，错误 xor 被拒），格式经本机 800+ 真实 `.dat` 头部校验 + 4 个开源实现交叉印证。
- ✅ **脚本可移植性**：路径全 `os.path.join`、config/keys 多候选 + env 覆盖、字体多平台兜底；已在 macOS 回归、`RFWG_DB_DIR` 覆盖验证。
- ⚠️ **Windows 未在真机端到端跑过**：逻辑与路径可移植，但请**首次自校验**——先 `collect_images.py` 能出缩略图、`decrypt_images_v2.py --dry-run` 命中数正确，再 `--limit 5` 抽验解密清晰度，最后按 §3.4 映射文字。
- ⚠️ **端到端全量解密**依赖你本机真实图片密钥（交互式取），打包环境无密钥，故两平台首跑都建议 `--limit 5` 抽验。
