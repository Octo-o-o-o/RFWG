#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 AI 判读结果分拣缩略图：有价值的留在 images/，无价值的移到 images/_archived/，
并生成 images/_USEFUL.md 清单。

用法（keep.json 由 AI 判读后写出）：
  keep.json 形如 {"5":"模型清单截图...","29":"发布会海报: 角色X=公司Y", ...}
  python sort_images.py --images ./research/images --keep keep.json

约定：keep.json 的 key 是图片编号（**不带前导零**，如 "5" 而非 "005"），value 是价值描述（一句话）。
     例：{"5":"模型清单截图","29":"发布会海报: 角色X=公司Y"}
未列入 keep 的一律回档到 _archived/（可逆，不删除）。
"""
import argparse
import os
import json
import shutil


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--images', required=True)
    ap.add_argument('--keep', required=True, help='JSON: {"图号":"价值描述"}')
    a = ap.parse_args()
    manifest = {str(x['idx']): x for x in json.load(open(os.path.join(a.images, '_manifest.json'), encoding='utf-8'))}
    raw_keep = json.load(open(a.keep, encoding='utf-8'))
    # 归一化图号：容忍 "005"/" 5 " 这类写法，并对匹配不上 manifest 的 key 告警
    keep = {}
    for k, v in raw_keep.items():
        try:
            nk = str(int(str(k).strip()))
        except ValueError:
            print(f'[warn] keep.json 的 key "{k}" 不是数字，已忽略。')
            continue
        if nk not in manifest:
            print(f'[warn] keep.json 的图号 "{k}" 在 _manifest.json 中不存在，已忽略。')
            continue
        keep[nk] = v
    arch = os.path.join(a.images, '_archived')
    os.makedirs(arch, exist_ok=True)
    kept = moved = 0
    for idx, it in manifest.items():
        f = os.path.join(a.images, it['file'])
        if not os.path.exists(f):
            continue
        if idx in keep:
            kept += 1
        else:
            shutil.move(f, os.path.join(arch, it['file']))
            moved += 1
    with open(os.path.join(a.images, '_USEFUL.md'), 'w', encoding='utf-8') as w:
        w.write('# 有价值图片清单\n\n')
        w.write(f'> 保留 {kept} 张（images/ 根目录），回档 {moved} 张（images/_archived/）。\n\n')
        w.write('| # | 时间 | 文件 | 价值 |\n|---|------|------|------|\n')
        for idx in sorted(keep, key=lambda x: int(x)):
            it = manifest.get(idx)
            if it:
                w.write(f"| {idx} | {it['time']} | {it['file']} | {keep[idx]} |\n")
    print(f'kept {kept}, archived {moved} -> {a.images}/_USEFUL.md')


if __name__ == '__main__':
    main()
