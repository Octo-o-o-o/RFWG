# RFWG 工具链一次装好（macOS + WeChat 4.x）

> 目标：**照抄即可，AI 不用再去调研**。RFWG 只依赖两个外部 CLI + 两个 Python 库；下面给出确切来源、安装命令、密钥落盘位置、故障排查、以及"什么测过/什么没测"。

## 0. 适用边界（先读）

- **仅 macOS + 微信 4.x**。脚本按 macOS 容器路径（`~/Library/Containers/com.tencent.xinWeChat/.../xwechat_files/<account>/`）与 `wxkey` 授权链路编写。
- **Windows**：`wechat-cli` 的 Windows 版会直接扫当前登录的微信进程写 key map，**不需要 `wxkey`**；但 RFWG 脚本里的路径/字体是 macOS 的，需自行适配（未测试）。
- **Linux**：微信本地库形态不同，不适用。
- 前置：微信**已登录且在运行**；已装 **Node.js ≥ 14**（装 wechat-cli）；要取全量原图再装 **Go ≥ 1.21**（装 wxkey，或用 release zip 内置的）。

## 1. wechat-cli —— 文字 / 联系人 / 会话 / 数据库密钥 / 缩略图

RFWG 的**文字与缩略图**全流程只需要它。它负责 `init` 提取**数据库密钥**并支持只读打开加密库。

```bash
npm i -g @canghe_ai/wechat-cli      # 预编译 darwin-arm64；装完自动跑 install.js
wechat-cli --version
wechat-cli init                     # 首次：走 wxkey 提取数据库密钥；可能弹一次 Mac 管理员密码/要求"完全磁盘访问"
```

成功后：`~/.wechat-cli/config.json`（含 `db_dir`）与 `~/.wechat-cli/all_keys.json`（**数据库密钥**，形如 `"sns/sns.db": {"enc_key": "<64 hex>"}`）。

> **关于 fork**：社区里 `wechat-cli` 有多个同源分支（npm 的 `@canghe_ai/wechat-cli`＝仓库 `freestylefly/wechat-cli`，Apache-2.0；另有 `r266-tech/wechat-cli` 一键 release）。RFWG 只要求它能产出 `~/.wechat-cli/{config.json,all_keys.json}` 并支持 `sessions/contacts/members/history`——上面 npm 版实测可用。想要一键把 wechat-cli+wxkey 一起装，也可用 r266 的：`curl -fsSL https://raw.githubusercontent.com/r266-tech/wechat-cli/main/scripts/install-release.sh | zsh`。

## 2. wxkey —— 只在"要全量原图"时需要（派生图片密钥）

`all_keys.json` **没有图片密钥**。V2 图片要 `image_key`(AES-128) + `image_xor_key`(单字节)，用 [`r266-tech/wxkey`](https://github.com/r266-tech/wxkey) 取：

```bash
# 装（二选一）：
go install github.com/r266-tech/wxkey/cmd/wxkey@latest      # 需要 Go；装到 $(go env GOPATH)/bin，确保在 PATH
#   或：用第 1 节 r266 release zip，内置 wxkey，无需单独装

wxkey bootstrap      # 首次：ad-hoc 签名 shadow WeChat + 一次性 sudo 存 Keychain（不需关 SIP）
wxkey image-key      # 派生并验证 image_key / image_xor_key（优先本机 kvcomm 缓存，不读进程内存）
```

- 结果写入 `~/.config/wxcli/config.json`；wxkey **不把 raw key 打到 stdout**（安全设计）。
- RFWG 的 `decrypt_images_v2.py` 会**自动**从该 config（及 `~/.wechat-cli/*.json`）里发现 `image_key/image_xor_key`；发现不了就 `--key/--xor` 或环境变量 `RFWG_IMG_KEY/RFWG_IMG_XOR`。
- 覆盖不全（提示缺某些库/图片的 key）时：在微信里**打开对应聊天/朋友圈页面**让其加载，再 `wxkey image-key` 重试。

## 3. Python 依赖

```bash
pip3 install -r requirements.txt
#   报 externally-managed 时：pip3 install --break-system-packages -r requirements.txt
#   或虚拟环境：python3 -m venv ~/.rfwg-venv && ~/.rfwg-venv/bin/pip install -r requirements.txt
#            （之后用 ~/.rfwg-venv/bin/python3 跑脚本）
```

`pycryptodome`（AES/SQLCipher 解密）+ `pillow`（拼图/截图切片/判读）。已在 Python 3.12 验证。

## 4. 密钥/配置落盘一览

| 文件 | 谁写 | 内容 | 纪律 |
|------|------|------|------|
| `~/.wechat-cli/config.json` | `wechat-cli init` | `db_dir` | 不外泄 |
| `~/.wechat-cli/all_keys.json` | `wechat-cli init` | **数据库**密钥（SQLCipher raw key） | 绝不提交 |
| `~/.config/wxcli/config.json` | `wxkey` | 数据库 key map + **图片** `image_key/image_xor_key` | 绝不提交 |

## 5. 一分钟自检

```bash
wechat-cli --version && python3 -c "import Crypto,PIL;print('py deps ok')"
wechat-cli sessions --limit 3            # 能列会话 = 文字链路通
# 要全量原图再验证：
command -v wxkey && wxkey doctor          # 列出缺 key 的库；image-key 是否可用
```

## 6. 故障排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `wechat-cli init` 失败 / 无密钥 | 微信未登录 / 未授予完全磁盘访问 / 版本非 4.x | 登录微信→系统设置授予磁盘访问→重跑 `init` |
| `sessions`/`history` 空 | 库未同步 / 名字对不上 | 先 `sessions --limit 50` 拿准确 username（群是 `…@chatroom`）|
| `history` 结果被截断 | `--limit` 太小 | 给到 `200000`，用返回 `count` 核对 |
| `collect_images.py` 收不到图 | 该时段图片没被微信加载过缩略图 | 微信里滚动加载对应聊天，或改走 `decrypt_images_v2.py --room` 原图 |
| `decrypt_images_v2.py` 报"缺 image_key" | 没跑 wxkey / config 里无图片 key | `wxkey bootstrap && wxkey image-key`，或 `--key/--xor` 显式传 |
| 解密"全部失败" | image_key/xor 不对 | `wxkey image-key` 重新派生；确认是 4.x V2（头 `07 08 56 32`）|
| `--media` 图片路径都一样 | 上游 bug（见 wechat-local-data §1）| 别用 `--media` 映射，用 `--room` 按 mtime 定位 |
| 浏览器验收 `file://` 打不开 | 浏览器工具拦 file:// | 起本地 http：`python3 -m http.server 8899 -d "$OUT"` |
| 端口被占 | 8899 已用 | 换 8900+，URL 同步改 |

## 7. 什么测过 / 什么没测（诚实边界）

- ✅ **文字/缩略图链路**：`wechat-cli` 导出 + `build_*`/`collect_images` 已在真实群跑通。
- ✅ **V2 解密逻辑**：`try_decrypt` 有**合成加密往返自测**（小图尾部 XOR、>1MB 含 raw 中段两种，逐字节精确还原；错误 xor 被拒），格式又经本机 800+ 真实 `.dat` 头部校验 + 4 个开源实现交叉印证。
- ✅ **源定位**：`--room/--sns/--in` 已对真实 `msg/attach`、`cache/Sns/Img` 跑 `--dry-run` 验证（命中数、时间过滤、variant 过滤正确）。
- ⚠️ **端到端全量解密**：需你本机真实 `image_key`（`wxkey image-key`，交互式一次性 sudo）——打包环境拿不到密钥，故**首次真跑请自校验**：先 `--limit 5` 解几张、打开确认是清晰图，再全量。
