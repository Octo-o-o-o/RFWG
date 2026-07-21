#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 wechat-cli 导出的群聊 JSON 生成两份 Markdown：
  1) <out>/01-完整消息.md      —— 全量清洗后的时间线（含统计概览）
  2) <out>/02-<主题>-精华.md   —— 命中主题关键词 ±N 条上下文的合并片段

用法：
  python build_report_md.py --raw raw.json --out ./research \
      --topic "某主题" --keywords "关键词,keyword,英文词" --context 5

设计意图：把「完整梳理」与「主题聚焦」两步固化下来，避免每次手写解析/清洗逻辑。
"""
import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wxcommon import load_messages, parse_line, weekday_cn  # noqa: E402


def render(p, max_quote=160):
    content = (p['content'] or '').replace('\n', ' ').strip()
    line = f"- `{p['time']}` **{p['sender']}**：{content}"
    if p['quote']:
        qw, qc = p['quote']
        qc = (qc or '').replace('\n', ' ').strip()
        if len(qc) > max_quote:
            qc = qc[:max_quote] + '…'
        line += f"\n    - ↳ 引用 {qw + ': ' if qw else ''}{qc}"
    return line


def build_full(parsed, chat, out):
    per_day = Counter(p['date'] for p in parsed if p['date'])
    sender = Counter(p['sender'] for p in parsed)
    L = [f'# {chat} 完整消息梳理', '',
         f'> 数据来源：本地微信数据库（wechat-cli 解密导出）',
         f'> 消息总数：**{len(parsed)}** 条', '', '## 概览统计', '', '### 每日消息量', '',
         '| 日期 | 星期 | 消息数 |', '|------|------|-------:|']
    for k in sorted(per_day):
        L.append(f'| {k} | 周{weekday_cn(k)} | {per_day[k]} |')
    L += ['', '### 主要发言人（Top 25）', '', '| 发言人 | 消息数 |', '|--------|-------:|']
    for s, c in sender.most_common(25):
        L.append(f'| {s} | {c} |')
    L += ['', '---', '', '## 完整消息（按时间顺序）', '',
          '> 图片/表情/语音/视频/卡片已折叠为标记；引用以 `↳` 标注；撤回显示为 `[撤回消息]`。', '']
    cur = None
    for p in parsed:
        if p['date'] != cur:
            cur = p['date']
            L += ['', f"### {cur}（周{weekday_cn(cur)}）", '']
        L.append(render(p))
    open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return len(parsed)


def build_topic(parsed, topic, keywords, ctx, out):
    def hit(p):
        blob = (p['content'] or '')
        if p['quote']:
            blob += ' ' + (p['quote'][1] or '')
        low = blob.lower()
        # 统一小写比较：英文不区分大小写；中文小写化无副作用，兼容"Agent智能体"这类中英混排关键词
        return any(kw.lower() in low for kw in keywords)

    n = len(parsed)
    hits = [i for i, p in enumerate(parsed) if hit(p)]
    segs = []
    for i in hits:
        lo, hi = max(0, i - ctx), min(n - 1, i + ctx)
        if segs and lo <= segs[-1][1] + 1:
            segs[-1][1] = max(segs[-1][1], hi)
            segs[-1][2].append(i)
        else:
            segs.append([lo, hi, [i]])
    L = [f'# 「{topic}」主题精华摘录（每处命中 ±{ctx} 条上下文）', '',
         f'> 关键词：{", ".join(keywords)}',
         f'> 命中 **{len(hits)}** 条，合并为 **{len(segs)}** 个片段。命中行以 `>>>` 标注。', '']
    for si, (lo, hi, hset) in enumerate(segs, 1):
        hset = set(hset)
        d0, d1 = parsed[lo]['date'], parsed[hi]['date']
        L += [f"## 片段 {si}（{d0 if d0 == d1 else d0 + ' ~ ' + d1}，#{lo}–#{hi}）", '']
        for j in range(lo, hi + 1):
            p = parsed[j]
            mark = '>>> ' if j in hset else '    '
            content = (p['content'] or '').replace('\n', ' ').strip()
            L.append(f"{mark}`{p['date']} {p['time']}` **{p['sender']}**：{content}")
            if p['quote']:
                qw, qc = p['quote']
                qc = (qc or '').replace('\n', ' ').strip()
                if len(qc) > 200:
                    qc = qc[:200] + '…'
                L.append(f"        ↳ 引用 {qw + ': ' if qw else ''}{qc}")
        L.append('')
    open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return len(hits), len(segs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', required=True, help='wechat-cli --format json 导出文件')
    ap.add_argument('--out', default='.', help='输出目录')
    ap.add_argument('--chat', default='', help='会话名（仅用于标题）')
    ap.add_argument('--topic', default='', help='主题名，留空则跳过主题精华')
    ap.add_argument('--keywords', default='', help='逗号分隔关键词（中英混合，英文不区分大小写）')
    ap.add_argument('--context', type=int, default=5, help='命中前后各取 N 条')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    msgs, meta = load_messages(a.raw)
    chat = a.chat or meta.get('chat', '会话')
    parsed = [parse_line(m) for m in msgs]
    full = os.path.join(a.out, '01-完整消息.md')
    n = build_full(parsed, chat, full)
    print(f'[full] {n} 条 -> {full}')
    if a.topic and a.keywords:
        kws = [k.strip() for k in a.keywords.split(',') if k.strip()]
        topic_out = os.path.join(a.out, f'02-{a.topic}-精华.md')
        h, s = build_topic(parsed, a.topic, kws, a.context, topic_out)
        print(f'[topic] 命中 {h} 条 / {s} 片段 -> {topic_out}')
    elif a.topic or a.keywords:
        print('[topic] 已跳过主题精华：--topic 与 --keywords 必须同时提供。')


if __name__ == '__main__':
    main()
