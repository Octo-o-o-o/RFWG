# RFWG · Research From WeChat Group

> English summary. Full documentation is in Chinese: **[README.md](README.md)**.

**RFWG** is an offline deep-research **Agent Skill** for AI coding assistants (Claude Code / Cursor). Point it at **your own** WeChat group / contact / topic and it turns your local, on-device chat history into a structured report — split Markdown files plus a single-file HTML with hand-drawn SVG diagrams.

> ⚠️ **Local & personal use only.** RFWG reads, decrypts and analyzes **your own** WeChat data **on your own device**, fully offline — nothing is uploaded. You are responsible for complying with local laws and WeChat's Terms of Service. Third-party personal information (names, wxid, employers, message/Moments text) must be anonymized before sharing anything. See [DISCLAIMER.md](DISCLAIMER.md).

## What it does

Given any combination of **which group**, **whom to focus on**, and **which topic** (with an optional time range, default: last month), RFWG will:

1. locate the target group/person in your local WeChat store;
2. export the full chat history for the range and clean out XML noise;
3. focus on the topic via keyword hits with ±N lines of context;
4. split key people's messages and distill their opinions;
5. pull images (decrypted thumbnails by default; full-resolution originals via an image key when needed), read them, and keep only the valuable ones — long screenshots are sliced vertically so text stays legible;
6. optionally decrypt Moments (`sns.db`) as supporting material;
7. weave everything into a human- and AI-friendly HTML report, verified in a real browser;
8. produce hand-off notes (data-integrity check + reading guide) for sharing or deeper follow-up rounds.

See the anonymized [sample report](docs/sample-report.html) (all data is fictional).

## Platforms

End-to-end verified on **macOS (arm64) + WeChat 4.x**. **Windows (amd64)** is supported in principle — the data formats and the decrypt/image scripts are cross-platform — but has not yet been verified end-to-end on real hardware. **Linux** is not adapted. Details in [`references/toolchain-setup.md`](references/toolchain-setup.md).

## Install (as a Skill)

```bash
# Claude Code (user-level)
git clone https://github.com/Octo-o-o-o/RFWG ~/.claude/skills/rfwg
# Cursor
git clone https://github.com/Octo-o-o-o/RFWG ~/.cursor/skills/rfwg
```

Then ask your assistant, e.g. *"Research what group XXX discussed about YYY last month, focus on A and B, and generate a report."* — the skill triggers automatically.

## Docs

- Full Chinese README: [README.md](README.md)
- Skill definition: [SKILL.md](SKILL.md)
- Toolchain setup: [references/toolchain-setup.md](references/toolchain-setup.md)
- Security policy: [SECURITY.md](SECURITY.md) · Disclaimer: [DISCLAIMER.md](DISCLAIMER.md) · Contributing: [CONTRIBUTING.md](CONTRIBUTING.md)

## License

MIT — see [LICENSE](LICENSE).
