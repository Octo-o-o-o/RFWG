# 安全策略 Security Policy

RFWG 会在**你本机**读取、解密并分析**你自己账号**的微信数据，涉及数据库 / 图片密钥与他人隐私。安全与隐私是本项目的第一原则。

## 报告漏洞 Reporting a Vulnerability

请**不要**通过公开 issue 报告安全问题，也**切勿在任何工单 / PR 中粘贴真实的聊天记录、密钥、wxid 或未脱敏报告**。

- 首选：在本仓库 **Security → Report a vulnerability**（GitHub Security Advisory）私密提交；
- 或通过 GitHub 私信仓库维护者 [@Octo-o-o-o](https://github.com/Octo-o-o-o)。

我们会尽快确认，并在修复后致谢（若你愿意）。

## 数据与密钥安全边界

- **全程离线**：所有脚本只读本机文件、只写本地输出目录，不发起任何用于上传 / 外发数据的网络请求。
- **密钥绝不入库**：`all_keys.json`、`config.json`、`~/.config/wxcli/*`、图片密钥等由 `.gitignore` 屏蔽；脚本从不把密钥明文打印到 stdout（仅打印发现密钥的配置文件路径）。
- **临时明文库用完即删**：`decrypt_moments.py` 解密出的完整 `sns.db`（含所有联系人朋友圈）以 `try/finally` 保证任何退出路径都删除，权限收紧为 `0600`。
- **产物隔离**：调研产物（`raw*.json`、报告 MD/HTML、`images*/`、`moments*`、`people/` 等）一律被 `.gitignore` 屏蔽；请始终把输出目录 `$OUT` 放在**本仓库之外**。

## 第三方工具信任边界

RFWG 依赖外部工具读取本地库 / 取密钥（`wechat-cli`、`wxkey`，及 Windows 侧社区内存扫描器）。这些工具会接触你的密钥或进程内存，请：

- 从官方来源安装，**核验版本与来源**，尽量固定版本而非盲目 `@latest`；
- 对 `irm ... | iex` 一类一键脚本，先审阅再执行；
- 遵循最小权限：仅在取密钥时临时提权，用完即恢复。

## 合规

详见 [DISCLAIMER.md](DISCLAIMER.md) 与 README 的「隐私与合规」章节。本工具仅供对**自有数据**做个人研究，使用者须遵守当地法律与微信用户协议。
