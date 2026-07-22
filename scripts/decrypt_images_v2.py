#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解密微信 4.x V2 加密图片 .dat 为原图——支持按【群聊】/【朋友圈】/【任意目录】三种来源批量解，
按时间命名、生成 _manifest.json 与索引拼图，无缝接入 RFWG 的读图/分拣管线。

它解决什么：collect_images.py 只能拿到 ~16% 的【已解密缩略图】；要看全部原图（聊天 msg/attach、
朋友圈 cache/Sns/Img），得先拿到【图片专用密钥】再解 V2 .dat。本脚本负责后半段。

━━━ 前提：图片密钥（不在 all_keys.json 里）━━━
V2 图片用 image_key(AES-128) + image_xor_key(单字节 XOR) 加密。二者都不在数据库密钥文件里，
需用 wxkey 现取（macOS，一次性 sudo；见 references/wechat-local-data.md §5）：
    wxkey bootstrap      # 首次：准备 shadow WeChat + 存一次 sudo 到 Keychain
    wxkey image-key      # 派生并验证 image_key / image_xor_key，写入 ~/.config/wxcli/config.json
本脚本会【自动】从 wxkey/wechat-cli 的 config 里找 image_key / image_xor_key；找不到再用
    --key / --xor 或环境变量 RFWG_IMG_KEY / RFWG_IMG_XOR 显式传入。
拿到 image_xor_key 时【不再暴力枚举】XOR，直接用，解得更快更准；只有缺 xor 时才回退枚举。

━━━ 用法 ━━━
  # 群聊原图（一个群一段时间的全部原图）：
  python decrypt_images_v2.py --room 12345678901@chatroom --start 2026-06-21 --end 2026-07-21 --out "$OUT/images_full"
  # 朋友圈图（cache/Sns/Img，注意是全账号共享缓存，见下方隐私提示）：
  python decrypt_images_v2.py --sns --start 2026-06-21 --end 2026-07-21 --out "$OUT/moments_img"
  # 任意 .dat 目录（兼容旧用法）：
  python decrypt_images_v2.py --in <dir_of_dat> --out <dir>
  # 先探查不解密（不需要密钥，核对能找到多少张、时间对不对）：
  python decrypt_images_v2.py --room 12345678901@chatroom --start ... --end ... --out /tmp/x --dry-run

━━━ V2 结构（15 字节头，已用真实文件 + 多个开源实现交叉验证）━━━
  [0:6]   magic 07 08 56 32 08 07
  [6:10]  aes_size (LE，恒 1024：只 AES 加密前 1KB)
  [10:14] xor_size (LE，尾段 XOR 字节数，上限 1MB)
  [14]    padding(0x01)
  数据段：AES-128-ECB 密文(PKCS7，对齐到 aes_size 上取整+整块) + raw 明文中段 + 末段 xor_size 字节 XOR
"""
import argparse
import os
import glob
import json
import struct
import io
import datetime
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wxcommon import wechat_root, room_md5, make_sheets, months_between  # noqa: E402

V2_MAGIC = bytes([7, 8, 0x56, 0x32, 8, 7])


def try_decrypt(data, key, xor_key):
    """按 V2 三段结构解密：AES 段(PKCS7) + raw 中段(原样) + 末段 xor_size 字节(单字节 XOR)。"""
    from Crypto.Cipher import AES
    if data[:6] != V2_MAGIC:
        return None
    aes_size, xor_size = struct.unpack_from('<II', data, 6)
    aligned = aes_size + (16 - aes_size % 16 if aes_size % 16 else 16)  # PKCS7 恒补一块
    dec = AES.new(key, AES.MODE_ECB).decrypt(data[15:15 + aligned])
    pad = dec[-1]
    if 1 <= pad <= 16 and all(x == pad for x in dec[-pad:]):
        dec = dec[:-pad]
    n = len(data)
    raw = data[15 + aligned:n - xor_size]            # 中段明文，原样保留
    tail = data[n - xor_size:] if xor_size else b''  # 末段，只对它做 XOR
    return dec + raw + bytes(b ^ xor_key for b in tail)


def valid(b):
    """装了 Pillow 就以 verify() 为准（能真正区分 xor key 对错）；只有未装库才退回 magic 头判断。"""
    try:
        from PIL import Image
    except ImportError:
        return b[:3] == b'\xff\xd8\xff' or b[:4] == b'\x89PNG'
    try:
        Image.open(io.BytesIO(b)).verify()
        return True
    except Exception:
        return False


def norm_key(k):
    """image_key 常见形态：16 字节 ascii 或 32 位 hex。归一成 16 字节。"""
    k = k.strip()
    if len(k) == 16:
        return k.encode()
    if len(k) == 32:
        try:
            return bytes.fromhex(k)
        except ValueError:
            pass
    return k.encode()[:16].ljust(16, b'\0')


def parse_xor(x):
    """把 xor key 字符串解析成 0-255。接受 '0x37'、十进制 '55'、裸 hex 'a3'。"""
    if x is None or x == '':
        return None
    if isinstance(x, int):
        return x & 0xFF
    x = str(x).strip()
    try:
        return int(x, 0) & 0xFF
    except ValueError:
        return int(x, 16) & 0xFF


# ---- 从 wxkey / wechat-cli 的 config 自动发现图片密钥 ----
def _walk_find(obj, want):
    """在嵌套 dict/list 里找键名匹配的值。want('aes'|'xor') -> 返回第一个命中的原始值或 None。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            nk = str(k).lower().replace('_', '').replace('-', '')
            if want == 'aes' and 'image' in nk and 'xor' not in nk and 'key' in nk and isinstance(v, str):
                return v
            if want == 'xor' and 'xor' in nk and isinstance(v, (str, int)):
                return v
            r = _walk_find(v, want)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for it in obj:
            r = _walk_find(it, want)
            if r is not None:
                return r
    return None


def discover_keys(cli_key, cli_xor):
    """按优先级取 (aes_key_str, xor_int)：命令行 > 环境变量 > wxkey/wechat-cli config 自动发现。"""
    home = os.path.expanduser('~')
    aes = cli_key or os.environ.get('RFWG_IMG_KEY') or ''
    xor = cli_xor if cli_xor is not None else os.environ.get('RFWG_IMG_XOR')
    if aes and xor is not None:
        return aes, parse_xor(xor)
    cands = [os.path.join(home, '.config', 'wxcli', 'config.json'),
             os.path.join(home, '.wechat-cli', 'all_keys.json'),
             os.path.join(home, '.wechat-cli', 'config.json'),
             os.path.join(home, '.config', 'wechat-cli', 'config.json')]
    la = os.environ.get('LOCALAPPDATA')
    if la:
        cands.append(os.path.join(la, 'wechat-cli', 'config.json'))     # Windows
    for cfg in cands:
        if not os.path.exists(cfg):
            continue
        try:
            data = json.load(open(cfg, encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        if not aes:
            found = _walk_find(data, 'aes')
            if found:
                aes = found
                print(f'  自动发现 image_key ← {cfg}')
        if xor is None:
            fx = _walk_find(data, 'xor')
            if fx is not None:
                xor = fx
                print(f'  自动发现 image_xor_key ← {cfg}')
    return aes, parse_xor(xor)


# ---- 三种来源：都返回 [(mtime_ts, srcpath), ...] ----
def _in_range(ts, lo, hi):
    return lo is None or (lo <= ts <= hi)


def sources_room(root, room, start, end, variant):
    rmd5 = room_md5(room)
    lo, hi = _range_ts(start, end)
    keep = {'orig': lambda f: f.endswith('.dat') and not f.endswith(('_t.dat', '_h.dat')),
            'hd': lambda f: f.endswith('_h.dat'),
            'thumb': lambda f: f.endswith('_t.dat'),
            'all': lambda f: f.endswith('.dat')}[variant]
    out = []
    for ym in months_between(datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)):
        d = os.path.join(root, 'msg', 'attach', rmd5, ym, 'Img')
        for f in glob.glob(os.path.join(d, '*.dat')):
            if keep(os.path.basename(f)) and _in_range(os.path.getmtime(f), lo, hi):
                out.append((os.path.getmtime(f), f))
    return out


def sources_sns(root, start, end):
    lo, hi = _range_ts(start, end)
    out = []
    for ym in months_between(datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)):
        base = os.path.join(root, 'cache', ym, 'Sns', 'Img')
        for f in glob.glob(os.path.join(base, '**', '*'), recursive=True):
            if os.path.isfile(f) and _in_range(os.path.getmtime(f), lo, hi):
                out.append((os.path.getmtime(f), f))
    return out


def sources_dir(inp, start, end):
    lo, hi = _range_ts(start, end)
    out = []
    for f in glob.glob(os.path.join(inp, '**', '*'), recursive=True):
        if os.path.isfile(f) and _in_range(os.path.getmtime(f), lo, hi):
            out.append((os.path.getmtime(f), f))
    return out


def _range_ts(start, end):
    if not start or not end:
        return None, None
    s = datetime.date.fromisoformat(start)
    e = datetime.date.fromisoformat(end)
    return (datetime.datetime.combine(s, datetime.time.min).timestamp(),
            datetime.datetime.combine(e, datetime.time.max).timestamp())


def main():
    ap = argparse.ArgumentParser(description='解密微信 V2 图片（群聊原图 / 朋友圈图 / 任意目录）')
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--room', help='群/联系人 username（如 12345678901@chatroom），解 msg/attach 原图')
    src.add_argument('--sns', action='store_true', help='解朋友圈缓存 cache/*/Sns/Img（全账号共享，注意隐私）')
    src.add_argument('--in', dest='inp', help='任意含 .dat 的目录（递归）')
    ap.add_argument('--out', required=True)
    ap.add_argument('--start', help='YYYY-MM-DD（--room/--sns 必填）')
    ap.add_argument('--end', help='YYYY-MM-DD（--room/--sns 必填）')
    ap.add_argument('--variant', choices=['orig', 'hd', 'thumb', 'all'], default='orig',
                    help='--room 解哪种：orig 原图(默认)/hd 高清/thumb 缩略/all 全部')
    ap.add_argument('--key', help='image_key（16 字节 ascii 或 32 hex）；也可用 RFWG_IMG_KEY / config 自动发现')
    ap.add_argument('--xor', help='image_xor_key（单字节，如 0x37）；也可用 RFWG_IMG_XOR / config 自动发现')
    ap.add_argument('--limit', type=int, default=0, help='最多解前 N 张（调试用，0=不限）')
    ap.add_argument('--dry-run', action='store_true', help='只列出会解哪些文件，不需要密钥、不写文件')
    a = ap.parse_args()

    root = wechat_root()
    if a.room or a.sns:
        if not (a.start and a.end):
            raise SystemExit('--room / --sns 需要 --start 与 --end（YYYY-MM-DD）。')

    if a.room:
        items = sources_room(root, a.room, a.start, a.end, a.variant)
        label = f'群聊原图 room={a.room} variant={a.variant}'
    elif a.sns:
        items = sources_sns(root, a.start, a.end)
        label = '朋友圈缓存 Sns/Img'
    else:
        items = sources_dir(a.inp, a.start, a.end)
        label = f'目录 {a.inp}'
    # 只保留 V2 .dat（读头 6 字节判定），并按时间排序
    v2 = []
    for ts, f in items:
        try:
            with open(f, 'rb') as fh:
                if fh.read(6) == V2_MAGIC:
                    v2.append((ts, f))
        except OSError:
            continue
    v2.sort()
    if a.limit:
        v2 = v2[:a.limit]
    print(f'[{label}] 命中 V2 图片 {len(v2)} 张（时间范围 {a.start or "-"}~{a.end or "-"}）')

    if a.dry_run:
        for ts, f in v2[:8]:
            print('  ', datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M'), os.path.basename(f))
        if len(v2) > 8:
            print(f'  … 共 {len(v2)} 张。去掉 --dry-run 并提供密钥即可解密。')
        return
    if a.sns:
        print('  ⚠️ 隐私：Sns/Img 是【全账号共享】的朋友圈缓存，可能含他人朋友圈配图；'
              '解出后请只保留目标对象的（用 sort_images.py），其余回档/删除。')

    aes_str, xor = discover_keys(a.key, a.xor)
    if not aes_str:
        raise SystemExit('缺 image_key。先跑 `wxkey bootstrap && wxkey image-key`，'
                         '再用 --key / RFWG_IMG_KEY 提供，或让脚本从 ~/.config/wxcli/config.json 自动发现。')
    key = norm_key(aes_str)
    xors = [xor] if xor is not None else [0x37, 0x88, 0x00] + list(range(256))
    if xor is None:
        print('  未提供 image_xor_key：回退暴力枚举 XOR（较慢/可能误判）。建议 `wxkey image-key` 拿到 xor 后用 --xor。')

    os.makedirs(a.out, exist_ok=True)
    manifest, ok, fail = [], 0, 0
    for ts, f in v2:
        try:
            data = open(f, 'rb').read()
        except OSError:
            fail += 1
            continue
        out = None
        for xk in xors:
            try:
                cand = try_decrypt(data, key, xk)
            except Exception:
                break  # AES 报错（key 长度/文件截断）→ 换下一个文件
            if cand and valid(cand):
                out = cand
                break
        if not out:
            fail += 1
            continue
        dt = datetime.datetime.fromtimestamp(ts)
        ext = 'png' if out[:4] == b'\x89PNG' else 'jpg'
        name = f'{ok + 1:03d}_{dt.strftime("%m%d_%H%M")}.{ext}'
        with open(os.path.join(a.out, name), 'wb') as w:
            w.write(out)
        # 只记相对文件名+时间，不写含本机用户名的绝对源路径
        manifest.append({'idx': ok + 1, 'time': dt.strftime('%Y-%m-%d %H:%M'), 'file': name})
        ok += 1
    json.dump(manifest, open(os.path.join(a.out, '_manifest.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'decrypted {ok}, failed {fail} -> {a.out}')
    if ok == 0:
        print('全部失败：image_key/xor 可能不对。用 `wxkey image-key` 重新派生，或确认是微信 4.x V2 图片。')
        return
    make_sheets(a.out, manifest)
    print(f'索引拼图见 {a.out}/_sheets/，AI 逐张判读后写 keep.json，再用 sort_images.py 分拣。')


if __name__ == '__main__':
    main()
