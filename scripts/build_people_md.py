#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按指定发言人拆分群聊，为每人生成「全量」+「实质发言」两份 Markdown。

用法：
  python build_people_md.py --raw raw.json --out ./research/people \
      --people "群友A,群友B,群友C"

说明：
- 发言人名以群内昵称精确匹配；先跑一次 `wechat-cli members "<群名>"` 或看 01-完整消息.md 的 Top 发言人核对别名。
- 「实质发言」= 去掉纯图片/表情占位与极短应答（见 wxcommon.is_substantive）。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wxcommon import load_messages, parse_line, is_substantive, weekday_cn  # noqa: E402


def render(p):
    content = (p['content'] or '').replace('\n', ' ').strip()
    line = f"- `{p['date']} {p['time']}` {content}"
    if p['quote']:
        qw, qc = p['quote']
        qc = (qc or '').replace('\n', ' ').strip()
        if len(qc) > 160:
            qc = qc[:160] + '…'
        line += f"\n    - ↳ 引用 {qw + ': ' if qw else ''}{qc}"
    return line


def dump(name, rows, out_path, title_suffix):
    L = [f'# {name} — {title_suffix}', '', f'> 共 {len(rows)} 条。', '']
    cur = None
    for p in rows:
        if p['date'] != cur:
            cur = p['date']
            L += ['', f"## {cur}（周{weekday_cn(cur)}）", '']
        L.append(render(p))
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', required=True)
    ap.add_argument('--out', default='./people')
    ap.add_argument('--people', required=True, help='逗号分隔的群内昵称')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    msgs, _ = load_messages(a.raw)
    parsed = [parse_line(m) for m in msgs]
    import re as _re
    used = {}
    for name in [x.strip() for x in a.people.split(',') if x.strip()]:
        mine = [p for p in parsed if p['sender'] == name]
        subs = [p for p in mine if is_substantive(p)]
        # 文件名安全化：非字母数字下划线连字符一律替换，避免不同昵称归一到同名而互相覆盖
        safe = _re.sub(r'[^\w\-]', '_', name) or 'user'
        if safe in used:
            used[safe] += 1
            safe = f'{safe}_{used[safe]}'
        else:
            used[safe] = 0
        dump(name, mine, os.path.join(a.out, f'{safe}_full.md'), '全部发言')
        dump(name, subs, os.path.join(a.out, f'{safe}_substantive.md'), '实质发言（去噪）')
        print(f'{name}: total={len(mine)} substantive={len(subs)}')


if __name__ == '__main__':
    main()
