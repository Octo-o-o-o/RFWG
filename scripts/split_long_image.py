#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把【过长图】纵向切成多段，供 AI 逐段清晰阅读。

为什么需要：长截图（聊天长图、整理成一张的清单、报告长图…）整张喂给大模型时，模型会把它
downscale 到长边上限，**文字被糊掉读不清**。把它按上下切成若干段（每段接近一屏、且相邻段
留重叠避免切断文字行），每段就落在"无需大幅缩放"的区间，AI 逐段读即可看清全部文字。

用法：
  # 切单张长图：
  python split_long_image.py --in "$OUT/images/029_0716_1221.jpg" --out "$OUT/images/_slices"
  # 批量：把一个目录里所有过长图都切（正常比例的图会跳过）：
  python split_long_image.py --in "$OUT/images" --out "$OUT/images/_slices"
  # 也可切浏览器整页截图 full.png（第 8 步验收用）：
  python split_long_image.py --in "$OUT/full.png" --out "$OUT/_shots" --slice-height 2200

判定与切分：
- 仅当 高/宽 > --max-aspect（默认 2.0）才切；否则跳过（除非 --force）。
- 每段像素高 = --slice-height（0=自动=宽 × --slice-aspect，默认 1.5）；相邻段重叠 --overlap（默认 0.12）避免切断文字。
- 窄图可 --min-width N 放大到该宽度（LANCZOS）提升小字可读性；默认不放大。
- 输出 <原名>_p01.<ext>, _p02… 按顺序命名，AI 按序读即可。默认存 PNG（文字无 JPEG 伪影）。
"""
import argparse
import os
import glob
import sys

EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')


def is_image(f):
    return os.path.isfile(f) and f.lower().endswith(EXTS)


def gather(inp):
    if os.path.isdir(inp):
        # 只取该目录直下的图，不递归进 _slices/_sheets/_archived，避免把切好的段又当输入
        out = []
        for f in sorted(glob.glob(os.path.join(inp, '*'))):
            if is_image(f):
                out.append(f)
        return out
    return [inp] if is_image(inp) else []


def split_one(path, outdir, max_aspect, slice_height, slice_aspect, overlap, min_width, fmt, force):
    from PIL import Image
    im = Image.open(path).convert('RGB')
    w, h = im.size
    stem = os.path.splitext(os.path.basename(path))[0]

    if min_width and w < min_width:
        nh = round(h * min_width / w)
        im = im.resize((min_width, nh), Image.LANCZOS)
        w, h = im.size

    if not force and h <= max_aspect * w:
        return 0  # 不算过长，跳过

    sh = slice_height if slice_height > 0 else max(1, round(w * slice_aspect))
    sh = min(sh, h)
    ov = max(0, min(0.9, overlap))
    step = max(1, round(sh * (1 - ov)))

    # 起点序列：覆盖到底，最后一段与底部对齐（避免末尾多出一条极窄片）
    starts = list(range(0, max(1, h - sh + 1), step))
    if not starts or starts[-1] + sh < h:
        starts.append(h - sh)
    starts = sorted(set(s for s in starts if s >= 0))

    os.makedirs(outdir, exist_ok=True)
    pad = 2 if len(starts) < 100 else 3
    ext = 'png' if fmt == 'png' else 'jpg'
    for i, y in enumerate(starts, 1):
        tile = im.crop((0, y, w, min(y + sh, h)))
        name = f'{stem}_p{i:0{pad}d}.{ext}'
        dst = os.path.join(outdir, name)
        if ext == 'png':
            tile.save(dst, 'PNG', optimize=True)
        else:
            tile.save(dst, 'JPEG', quality=92)
    print(f'  {os.path.basename(path)}  {w}x{h}  → {len(starts)} 段（每段高≈{sh}px，重叠{int(ov*100)}%）')
    return len(starts)


def main():
    ap = argparse.ArgumentParser(description='把过长图纵向切成多段，供 AI 逐段清晰阅读')
    ap.add_argument('--in', dest='inp', required=True, help='单张图或含图的目录（目录只取直下、不递归）')
    ap.add_argument('--out', required=True, help='切片输出目录')
    ap.add_argument('--max-aspect', type=float, default=2.0, help='高/宽 超过此值才切（默认 2.0）')
    ap.add_argument('--slice-height', type=int, default=0, help='每段像素高；0=自动=宽×--slice-aspect')
    ap.add_argument('--slice-aspect', type=float, default=1.5, help='自动模式下每段高宽比（默认 1.5≈一屏）')
    ap.add_argument('--overlap', type=float, default=0.12, help='相邻段重叠比例，避免切断文字（默认 0.12）')
    ap.add_argument('--min-width', type=int, default=0, help='窄图放大到该宽度提升可读性（默认 0=不放大）')
    ap.add_argument('--format', choices=['png', 'jpg'], default='png', help='切片格式（默认 png，文字更清晰）')
    ap.add_argument('--force', action='store_true', help='不论比例都切（如强制切 full.png）')
    a = ap.parse_args()

    try:
        import PIL  # noqa: F401
    except ImportError:
        raise SystemExit('需要 Pillow：pip3 install -r requirements.txt（或 --break-system-packages pillow）。')

    imgs = gather(a.inp)
    if not imgs:
        raise SystemExit(f'--in 未找到图片：{a.inp}')

    total_slices = split_files = skipped = 0
    print(f'扫描 {len(imgs)} 张图（max-aspect={a.max_aspect}）：')
    for f in imgs:
        try:
            n = split_one(f, a.out, a.max_aspect, a.slice_height, a.slice_aspect,
                          a.overlap, a.min_width, a.format, a.force)
        except Exception as e:
            print(f'  跳过（读图失败）{os.path.basename(f)}: {e}')
            continue
        if n:
            total_slices += n
            split_files += 1
        else:
            skipped += 1
    print(f'完成：{split_files} 张过长图 → {total_slices} 段，{skipped} 张正常图跳过 -> {a.out}')
    if total_slices:
        print('AI 按 _pNN 顺序逐段读（相邻段有重叠，衔接处以后一段为准）；读完把长图里的信息写进 04-图片信息提取.md。')


if __name__ == '__main__':
    main()
