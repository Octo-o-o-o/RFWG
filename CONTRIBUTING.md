# 贡献指南 Contributing

感谢你对 RFWG 的兴趣！本文档说明如何参与开发。

## 第一条铁律：绝不提交真实数据

RFWG 处理真实的微信隐私数据。向本仓库提交任何以下内容都是**严格禁止**的：

- 密钥文件：`all_keys.json`、`config.json`、图片密钥等；
- 原始导出与解密产物：`raw*.json`、`*.db`、`moments*.json`；
- 调研报告与中间产物：各类 `NN-*.md`、`*-调研报告.html`、`images*/`、`people/`；
- 任何含真实姓名、wxid、实名雇主、聊天 / 朋友圈原文的内容（包括 issue、PR 描述、截图）。

`.gitignore` 已尽力屏蔽上述产物，但**提交前请务必 `git status` 自查**。演示 / 测试一律使用虚构占位数据（如 `wxid_example`、`12345678901@chatroom`）。

## 开发环境

```bash
git clone https://github.com/Octo-o-o-o/RFWG && cd RFWG
pip install -r requirements.txt -r requirements-dev.txt   # 运行时 + 开发依赖
```

## 提交前检查

```bash
ruff check .                        # 代码风格 / 静态检查
pytest -q                           # 单元测试（合成数据，无需真实微信库）
python -m py_compile scripts/*.py
```

三项都应通过。CI 会在 PR 上自动跑同样的检查。

## 代码约定

- Python 3.10+，遵循 `pyproject.toml` 里的 ruff 规则（行宽 120）。
- 文件读写一律用 `with`；对外部 / 坏输入给**清晰可诊断**的 `SystemExit` 报错，而非裸 traceback。
- 脚本是“确定性步骤”，新增脚本请配套单元测试（只用合成 / 占位数据）。
- 保持跨平台：路径用 `os.path.join`，不硬编码家目录。

## 提交流程

1. Fork 并新建分支；
2. 完成改动并通过上述检查；
3. 提交信息用简洁的一句话说明「为什么」；
4. 发起 PR，填写模板，关联相关 issue。

## 报告问题

- Bug / 功能建议：使用对应的 issue 模板。
- 安全 / 隐私问题：见 [SECURITY.md](SECURITY.md)，**不要**走公开 issue。
