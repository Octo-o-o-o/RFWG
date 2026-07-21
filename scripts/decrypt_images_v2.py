#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""（可选/进阶）解密微信 4.x V2 加密图片 .dat 为原图。

前提：需要【图片专用 AES 密钥】。它不在 all_keys.json 里（那是数据库密钥），
只存在于微信运行进程内存 / 可由 `wxkey image-key` 从本机 kvcomm 缓存派生。
本脚本不负责取密钥，只负责在已知密钥时做解密。

用法：
  # 先拿到 16 字节图片 AES 密钥（ascii 或 32 位 hex）：
  #   方式A: wxkey image-key            （推荐，需一次性 sudo 授权）
  #   方式B: 自备从进程内存提取的密钥
  python decrypt_images_v2.py --key <YOUR_IMAGE_KEY> --in <dir_of_dat> --out <dir>
  # 或用环境变量避免密钥进 shell history：RFWG_IMG_KEY=xxx python decrypt_images_v2.py --in ... --out ...

V2 结构（15 字节头）：
  [0:6]  magic 07 08 56 32 08 07
  [6:10] aes_size (LE, 明文段字节数)
  [10:14] xor_size (LE, 末段 XOR 字节数)
  [14]   padding
  之后：AES-128-ECB 密文（PKCS7，长度 = 对齐后的 aes_size）+ raw + XOR 段
解密：AES 段用 image_key 解 + 去 PKCS7；XOR 段用单字节 xor_key（默认 0x37/0x88，或用尾部 FFD9 反推）。
"""
import argparse
import os
import glob
import struct
import io


def try_decrypt(data, key, xor_key):
    """按 V2 三段结构解密：AES 段(PKCS7) + raw 中段(原样) + 末段 xor_size 字节(单字节 XOR)。"""
    from Crypto.Cipher import AES
    if data[:6] != bytes([7, 8, 0x56, 0x32, 8, 7]):
        return None
    aes_size, xor_size = struct.unpack_from('<II', data, 6)
    aligned = aes_size + (16 - aes_size % 16 if aes_size % 16 else 16)  # PKCS7 恒补一块
    dec = AES.new(key, AES.MODE_ECB).decrypt(data[15:15 + aligned])
    pad = dec[-1]
    if 1 <= pad <= 16 and all(x == pad for x in dec[-pad:]):
        dec = dec[:-pad]
    n = len(data)
    raw = data[15 + aligned:n - xor_size]           # 中段明文，原样保留
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
    if len(k) == 16:
        return k.encode()
    if len(k) == 32:
        try:
            return bytes.fromhex(k)
        except Exception:
            pass
    return k.encode()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', default=os.environ.get('RFWG_IMG_KEY', ''),
                    help='图片 AES 密钥（16 字节 ascii 或 32 hex）；也可用环境变量 RFWG_IMG_KEY')
    ap.add_argument('--in', dest='inp', required=True, help='含 .dat 的目录')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    if not a.key:
        raise SystemExit('缺图片密钥：用 --key 或环境变量 RFWG_IMG_KEY 提供（见 `wxkey image-key`）。')
    key = norm_key(a.key)
    os.makedirs(a.out, exist_ok=True)
    files = [f for f in glob.glob(os.path.join(a.inp, '**', '*'), recursive=True) if os.path.isfile(f)]
    ok = fail = 0
    for f in files:
        try:
            data = open(f, 'rb').read()
        except Exception:
            continue
        if len(data) < 16 or data[:6] != bytes([7, 8, 0x56, 0x32, 8, 7]):
            continue
        done = False
        for xk in (0x37, 0x88, 0x00) + tuple(range(256)):
            try:
                out = try_decrypt(data, key, xk)
            except Exception:
                break  # AES 解密就报错（如 key 长度不对/文件截断），换文件
            if out and valid(out):
                ext = 'png' if out[:4] == b'\x89PNG' else 'jpg'
                open(os.path.join(a.out, os.path.basename(f) + '.' + ext), 'wb').write(out)
                ok += 1
                done = True
                break
        if not done:
            fail += 1
    print(f'decrypted {ok}, failed {fail} -> {a.out}')
    if ok == 0:
        print('全部失败：密钥可能不对。用 `wxkey image-key` 重新派生，或确认微信版本为 4.x V2。')


if __name__ == '__main__':
    main()
