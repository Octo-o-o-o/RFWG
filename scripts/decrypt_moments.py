#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解密微信 sns.db 并导出指定用户近一段时间的朋友圈（文字 + 媒体清单）。

用法：
  python decrypt_moments.py --user wxid_example --start 2026-06-21 --end 2026-07-21 \
      --out ./research/moments.json

流程：
1. 读 ~/.wechat-cli/all_keys.json 里 'sns/sns.db' 的 enc_key；
2. 用 WeChat 4.x SQLCipher 参数（AES-256-CBC + HMAC-SHA512，4096B 分页，salt=前16字节）离线解密到临时 db；
3. 查 SnsTimeLine（user_name = 目标 wxid），解析 <TimelineObject> XML 得到 createTime/contentDesc/media；
4. 只导出目标用户，按时间范围过滤，写 JSON；用完删除完整解密库（含他人隐私）。

如何拿到目标用户的 wxid：`wechat-cli contacts --query "<昵称>"`（取 personal 账号，gh_ 开头是公众号）。

隐私：临时解密出的完整 sns.db 含**所有联系人**的朋友圈明文，本脚本用 try/finally 保证任何退出路径都删除它。
`--keep-db` 会保留该全员明文库，仅供调试，正常使用切勿开启。
"""
import argparse
import contextlib
import os
import json
import re
import html
import datetime
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wxcommon import wechat_config, load_keys, day_bounds  # noqa: E402


def decrypt_sqlcipher(src, key, hmac_len=64, page=4096):
    """WeChat 4.x：每页 = [salt(仅第1页16B)] + AES-256-CBC 密文 + reserve(iv+hmac)。返回明文 bytes。"""
    from Crypto.Cipher import AES
    with open(src, 'rb') as f:
        data = f.read()
    reserve = 16 + hmac_len
    if reserve % 16:
        reserve = ((reserve // 16) + 1) * 16
    out = bytearray()
    npages = len(data) // page
    for i in range(npages):
        p = data[i * page:(i + 1) * page]
        start = 16 if i == 0 else 0
        enc = p[start:page - reserve]
        iv = p[page - reserve:page - reserve + 16]
        dec = AES.new(key, AES.MODE_CBC, iv).decrypt(enc)
        out += (b'SQLite format 3\x00' + dec) if i == 0 else dec
        out += p[page - reserve:]
    return bytes(out)


def g(pat, s, d=''):
    m = re.search(pat, s, re.S)
    return m.group(1) if m else d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', required=True, help='目标朋友圈 wxid（如 wxid_example）')
    ap.add_argument('--start', required=True)
    ap.add_argument('--end', required=True)
    ap.add_argument('--out', default='./moments.json')
    ap.add_argument('--keep-db', action='store_true',
                    help='[危险] 保留完整解密库（含所有联系人朋友圈明文），仅供调试；默认用完即删')
    a = ap.parse_args()
    lo, hi = day_bounds(a.start, a.end)      # 先校验时间范围（坏格式/顺序即时报错，不白解密）

    db_dir = wechat_config()['db_dir']
    src = os.path.join(db_dir, 'sns', 'sns.db')
    if not os.path.exists(src):
        raise SystemExit(f'未找到 {src}')
    keys = load_keys()
    if 'sns/sns.db' not in keys or 'enc_key' not in keys.get('sns/sns.db', {}):
        raise SystemExit('all_keys.json 里缺 sns/sns.db 的 enc_key，请重跑 `wechat-cli init`。')
    key = bytes.fromhex(keys['sns/sns.db']['enc_key'])

    out_dir = os.path.dirname(os.path.abspath(a.out))
    os.makedirs(out_dir, exist_ok=True)
    tmp = a.out + '.decrypted.db'
    try:
        # 依次尝试 HMAC-SHA512/SHA1/SHA256（WeChat 4.x 常见为 SHA512）
        ok = False
        for hl in (64, 20, 32):
            try:
                with open(tmp, 'wb') as f:
                    f.write(decrypt_sqlcipher(src, key, hmac_len=hl))
                with contextlib.suppress(OSError):
                    os.chmod(tmp, 0o600)     # 临时明文库（含他人隐私）仅本人可读；Windows 上无害
                con = sqlite3.connect(tmp)
                try:
                    con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone()
                finally:
                    con.close()              # 先关句柄，Windows 才能删除临时文件
                ok = True
                break
            except sqlite3.DatabaseError:
                # 只吞"不是有效数据库"（HMAC 变体不对）；IO/依赖等真错误照常抛出，避免误导诊断
                if os.path.exists(tmp):
                    with contextlib.suppress(OSError):
                        os.remove(tmp)
        if not ok:
            raise SystemExit('sns.db 解密失败（HMAC 变体都不匹配）。')

        con = sqlite3.connect(tmp)
        try:
            rows = con.execute("SELECT tid,content FROM SnsTimeLine WHERE user_name=?", (a.user,)).fetchall()
        finally:
            con.close()
        items = []
        for tid, c in rows:
            ct = g(r'<createTime>(\d+)</createTime>', c)
            if not ct:
                continue
            try:
                ts = int(ct)
            except ValueError:
                continue
            if not (lo <= ts <= hi):
                continue
            medias = []
            for mb in re.findall(r'<media>(.*?)</media>', c, re.S):
                medias.append({'mtype': g(r'<type>(\d+)</type>', mb),
                               'url': html.unescape(g(r'<url[^>]*>(.*?)</url>', mb)),
                               'thumb': html.unescape(g(r'<thumb[^>]*>(.*?)</thumb>', mb)),
                               'md5': g(r'md5="([0-9a-f]+)"', mb)})
            items.append({'tid': str(tid), 'ts': ts,
                          'time': datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M'),
                          'desc': html.unescape(g(r'<contentDesc>(.*?)</contentDesc>', c)),
                          'link_title': html.unescape(g(r'<title>(.*?)</title>', c)),
                          'link_url': html.unescape(g(r'<contentUrl>(.*?)</contentUrl>', c)),
                          'medias': medias})
        items.sort(key=lambda x: x['ts'])
        with open(a.out, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
    finally:
        # 任何退出路径都清理含他人隐私的完整解密库
        if not a.keep_db and os.path.exists(tmp):
            os.remove(tmp)
    print(f'{a.user} 朋友圈 {len(items)} 条，媒体 {sum(len(i["medias"]) for i in items)} 张 -> {a.out}')
    print('注：配图为 V2 加密，需图片密钥才能取像素（见 decrypt_images_v2.py / references）。')


if __name__ == '__main__':
    main()
