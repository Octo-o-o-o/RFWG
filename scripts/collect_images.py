#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从微信缓存目录收集某会话的【已解密缩略图】，按时间命名复制到 images/，
并生成带编号标签的索引拼图（sheets），便于逐张判读。

用法：
  python collect_images.py --room 12345678901@chatroom --out ./research/images \
      --start 2026-06-21 --end 2026-07-21

原理：
- 微信 4.x 把聊天原图存成 V2 加密 .dat（需图片专用 AES 密钥才能解，见 references/wechat-local-data.md）；
- 但缓存目录 cache/<YYYY-MM>/Message/<md5(room)>/Thumb/*.jpg 是【已解密】缩略图，可直接读。
- 缩略图分辨率多为 120~1080px，信息图/长截图的文字通常可读，足够做判读与分拣。

分拣建议（脚本只做收集+拼图，判读留给 AI）：
- AI 逐张看 sheets，识别"有价值"（截图/架构图/数据图/产品/行业实质）vs"噪音"（表情/风景/头像/封面）。
- 之后可调用 sort_images.py 把有用留 images/、无用移到 images/_archived/。
"""
import argparse
import os
import glob
import json
import shutil
import datetime
import subprocess
import hashlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wxcommon import wechat_root  # noqa: E402


def months_between(start, end):
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--room', required=True, help='群/联系人 username，如 12345678901@chatroom 或 wxid_xxx')
    ap.add_argument('--out', default='./images')
    ap.add_argument('--start', required=True)
    ap.add_argument('--end', required=True)
    ap.add_argument('--sheet-cols', type=int, default=3)
    ap.add_argument('--sheet-rows', type=int, default=4)
    a = ap.parse_args()

    root = wechat_root()
    rmd5 = hashlib.md5(a.room.encode()).hexdigest()
    start = datetime.date.fromisoformat(a.start)
    end = datetime.date.fromisoformat(a.end)
    lo = datetime.datetime.combine(start, datetime.time.min).timestamp()
    hi = datetime.datetime.combine(end, datetime.time.max).timestamp()

    thumbs = []
    for ym in months_between(start, end):
        d = os.path.join(root, 'cache', ym, 'Message', rmd5, 'Thumb')
        for f in glob.glob(os.path.join(d, '*.jpg')):
            fn = os.path.basename(f)
            parts = fn.replace('_thumb.jpg', '').split('_')
            try:
                ts = int(parts[1])
                seq = parts[0]
            except Exception:
                ts = int(os.path.getmtime(f))
                seq = '0'
            if lo <= ts <= hi:
                thumbs.append((ts, seq, f))
    thumbs.sort()
    os.makedirs(a.out, exist_ok=True)
    manifest = []
    for idx, (ts, seq, src) in enumerate(thumbs, 1):
        dt = datetime.datetime.fromtimestamp(ts)
        name = f"{idx:03d}_{dt.strftime('%m%d_%H%M')}.jpg"
        shutil.copy2(src, os.path.join(a.out, name))
        # 只记相对文件名，不写含本机用户名/微信 account 的绝对 src 路径（避免单独分享 images/ 时泄漏本地信息）
        manifest.append({'idx': idx, 'time': dt.strftime('%Y-%m-%d %H:%M'), 'file': name})
    json.dump(manifest, open(os.path.join(a.out, '_manifest.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'copied {len(manifest)} thumbnails -> {a.out}')

    if not manifest:
        print('未找到缩略图。可能：该会话该时间段无图片，或需先在微信里滚动加载过这些图片。')
        return
    make_sheets(a.out, manifest, a.sheet_cols, a.sheet_rows)


def make_sheets(out, manifest, cols, rows):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print('未安装 Pillow，跳过拼图。pip install --break-system-packages pillow 后重试。')
        return
    sd = os.path.join(out, '_sheets')
    os.makedirs(sd, exist_ok=True)
    TILE, PAD, PER = 380, 26, cols * rows
    font = _font(18)
    fonts = _font(15)

    def tile(it):
        cell = Image.new('RGB', (TILE, TILE + PAD), (245, 245, 245))
        d = ImageDraw.Draw(cell)
        try:
            im = Image.open(os.path.join(out, it['file'])).convert('RGB')
            im.thumbnail((TILE, TILE - PAD))
            cell.paste(im, ((TILE - im.width) // 2, PAD + (TILE - PAD - im.height) // 2))
        except Exception:
            d.text((5, PAD + 5), 'ERR', fill=(200, 0, 0), font=font)
        d.rectangle([0, 0, TILE, PAD], fill=(30, 30, 60))
        d.text((5, 3), f"#{it['idx']} {it['time'][5:]}", fill=(255, 255, 255), font=fonts)
        return cell

    sheets = 0
    for s in range(0, len(manifest), PER):
        grp = manifest[s:s + PER]
        W, H = cols * (TILE + 6), rows * (TILE + PAD + 6)
        sheet = Image.new('RGB', (W, H), (255, 255, 255))
        for i, it in enumerate(grp):
            r, c = divmod(i, cols)
            sheet.paste(tile(it), (c * (TILE + 6), r * (TILE + PAD + 6)))
        sheets += 1
        sheet.save(os.path.join(sd, f'sheet_{sheets:02d}.jpg'), quality=82)
    print(f'made {sheets} index sheets -> {sd}')


def _font(size):
    from PIL import ImageFont
    for p in ['/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
              '/System/Library/Fonts/PingFang.ttc',
              '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


if __name__ == '__main__':
    main()
