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
from wxcommon import (load_messages, parse_line, weekday_cn,  # noqa: E402
                      group_consecutive, load_image_index, IMG_RE)


def _annotate_img(content, date, time, img_index):
    """给 [图片] 行贴上已解密缩略图文件名（若该分钟有图）。"""
    if not img_index or not IMG_RE.match(content):
        return content
    files = img_index.get(f'{date} {time}')
    if files:
        return content + f"  【图:{files[0]}】"
    return content


def _quote_str(p, max_quote=160):
    if not p['quote']:
        return ''
    qw, qc = p['quote']
    qc = (qc or '').replace('\n', ' ').strip()
    if len(qc) > max_quote:
        qc = qc[:max_quote] + '…'
    return f"↳ 引用 {qw + ': ' if qw else ''}{qc}"


def render_block(b, img_index=None, max_quote=160):
    """把一个「发言轮次」block 渲染成一条：同一人相邻的文字+图片合并，保留各自引用。"""
    trange = b['t_start'] if b['t_start'] == b['t_end'] else f"{b['t_start']}–{b['t_end']}"
    items = b['items']
    # 单条：直接内联
    if len(items) == 1:
        p = items[0]
        c = _annotate_img(p['content'].replace('\n', ' ').strip(), b['date'], p['time'], img_index)
        line = f"- `{trange}` **{b['sender']}**：{c}"
        q = _quote_str(p, max_quote)
        if q:
            line += f"\n    - {q}"
        return line
    # 多条：合并为一条，子项分行（文字与其图片自然连在一起）
    line = f"- `{trange}` **{b['sender']}**："
    subs = []
    for p in items:
        c = _annotate_img(p['content'].replace('\n', ' ').strip(), b['date'], p['time'], img_index)
        seg = f"    · {c}"
        q = _quote_str(p, max_quote)
        if q:
            seg += f"  （{q}）"
        subs.append(seg)
    return line + "\n" + "\n".join(subs)


def build_full(parsed, chat, out, img_index=None):
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
    L += ['', '---', '', '## 完整消息（按时间顺序，同一人相邻的文字+图片已合并为一条）', '',
          '> 同一发送者相邻且≤2 分钟的消息合并为一个"发言轮次"，子项以 `·` 列出（文字与其紧跟的图片自然连在一起）；'
          '引用以 `↳ 引用` 标注；有对应缩略图的图片标 `【图:文件名】`；撤回显示为 `[撤回消息]`。', '']
    cur = None
    for b in group_consecutive(parsed):
        if b['date'] != cur:
            cur = b['date']
            L += ['', f"### {cur}（周{weekday_cn(cur)}）", '']
        L.append(render_block(b, img_index))
    open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    return len(parsed)


def build_topic(parsed, topic, keywords, ctx, out, img_index=None):
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
         f'> 命中 **{len(hits)}** 条，合并为 **{len(segs)}** 个片段。命中的发言轮次以 `>>>` 标注；'
         f'同一人相邻的文字+图片已合并为一条；有对应缩略图的图片标 `【图:文件名】`。', '']
    for si, (lo, hi, hset) in enumerate(segs, 1):
        hset = set(hset)
        d0, d1 = parsed[lo]['date'], parsed[hi]['date']
        L += [f"## 片段 {si}（{d0 if d0 == d1 else d0 + ' ~ ' + d1}，#{lo}–#{hi}）", '']
        # 段内按发言轮次合并（保留每条的全局下标以判定是否命中行）
        seg_items = [dict(parsed[j], _gi=j) for j in range(lo, hi + 1)]
        for b in group_consecutive(seg_items):
            is_hit = any(it.get('_gi') in hset for it in b['items'])
            mark = '>>> ' if is_hit else '    '
            trange = b['t_start'] if b['t_start'] == b['t_end'] else f"{b['t_start']}–{b['t_end']}"
            if len(b['items']) == 1:
                p = b['items'][0]
                c = _annotate_img((p['content'] or '').replace('\n', ' ').strip(), b['date'], p['time'], img_index)
                L.append(f"{mark}`{b['date']} {p['time']}` **{b['sender']}**：{c}")
                q = _quote_str(p, 200)
                if q:
                    L.append(f"        {q}")
            else:
                L.append(f"{mark}`{b['date']} {trange}` **{b['sender']}**：")
                for p in b['items']:
                    c = _annotate_img((p['content'] or '').replace('\n', ' ').strip(), b['date'], p['time'], img_index)
                    q = _quote_str(p, 200)
                    L.append(f"        · {c}" + (f"  （{q}）" if q else ""))
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
    ap.add_argument('--images', default='', help='可选：images 目录（含 _manifest.json），用于给 [图片] 贴对应缩略图文件名')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    img_index = load_image_index(a.images) if a.images else {}
    msgs, meta = load_messages(a.raw)
    chat = a.chat or meta.get('chat', '会话')
    parsed = [parse_line(m) for m in msgs]
    full = os.path.join(a.out, '01-完整消息.md')
    n = build_full(parsed, chat, full, img_index)
    print(f'[full] {n} 条 -> {full}（图片索引 {len(img_index)} 分钟）')
    if a.topic and a.keywords:
        kws = [k.strip() for k in a.keywords.split(',') if k.strip()]
        topic_out = os.path.join(a.out, f'02-{a.topic}-精华.md')
        h, s = build_topic(parsed, a.topic, kws, a.context, topic_out, img_index)
        print(f'[topic] 命中 {h} 条 / {s} 片段 -> {topic_out}')
    elif a.topic or a.keywords:
        print('[topic] 已跳过主题精华：--topic 与 --keywords 必须同时提供。')


if __name__ == '__main__':
    main()
