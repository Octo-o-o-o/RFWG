#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2 图片解密的合成往返自测（不依赖任何真实微信数据或密钥）。

覆盖 references/wechat-local-data.md §5.1 宣称的三段结构：
  - 极小图：整体落在 AES 段（无 XOR 尾段）；
  - <1MB：前 1KB AES + 其余 XOR 尾段（无 raw 中段）；
  - >1MB：前 1KB AES + raw 明文中段 + 最后 1MB XOR 尾段，逐字节精确还原；
  - 错误 xor 被拒；非 V2 magic 返回 None。
"""
import os
import sys
import struct
import random

from Crypto.Cipher import AES

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import decrypt_images_v2 as dv  # noqa: E402

KEY = b'0123456789abcdef'  # 16 字节 AES-128 测试密钥（非真实密钥）


def _rb(n, seed=0):
    """确定性随机字节，保证测试可复现。"""
    return random.Random(seed).randbytes(n)


def synth(plaintext, key, xor_key, aes_size, xor_size):
    """按 V2 三段结构把明文合成为加密 .dat（与 try_decrypt 严格互逆）。"""
    aes_plain = plaintext[:aes_size]
    pad_len = 16 - (len(aes_plain) % 16) if (len(aes_plain) % 16) else 16   # PKCS7 恒补一块
    padded = aes_plain + bytes([pad_len]) * pad_len
    aes_ct = AES.new(key, AES.MODE_ECB).encrypt(padded)
    raw = plaintext[aes_size:len(plaintext) - xor_size] if xor_size else plaintext[aes_size:]
    tail = plaintext[len(plaintext) - xor_size:] if xor_size else b''
    tail_ct = bytes(b ^ xor_key for b in tail)
    header = dv.V2_MAGIC + struct.pack('<II', aes_size, xor_size) + bytes([1])
    return header + aes_ct + raw + tail_ct


def test_roundtrip_tiny_all_aes():
    plain = bytes(range(200))
    data = synth(plain, KEY, 0x37, aes_size=len(plain), xor_size=0)
    assert dv.try_decrypt(data, KEY, 0x37) == plain


def test_roundtrip_small_with_xor_tail():
    # 1KB < 文件 < 1MB：前 1KB AES、其余全在 XOR 尾段（中段为空）
    plain = _rb(1024, 1) + _rb(400, 2)
    data = synth(plain, KEY, 0x37, aes_size=1024, xor_size=400)
    assert dv.try_decrypt(data, KEY, 0x37) == plain


def test_roundtrip_large_with_raw_middle():
    # >1MB：前 1KB AES + raw 明文中段 + 最后 1MB XOR，逐字节精确还原
    plain = _rb(1024, 1) + _rb(3000, 2) + _rb(1048576, 3)
    data = synth(plain, KEY, 0x88, aes_size=1024, xor_size=1048576)
    assert dv.try_decrypt(data, KEY, 0x88) == plain


def test_wrong_xor_rejected():
    plain = _rb(1024, 1) + _rb(1048576, 3)
    data = synth(plain, KEY, 0x37, aes_size=1024, xor_size=1048576)
    assert dv.try_decrypt(data, KEY, 0x37) == plain    # 正确 xor 完整还原
    assert dv.try_decrypt(data, KEY, 0x00) != plain    # 错误 xor 的尾段解错


def test_non_v2_magic_returns_none():
    assert dv.try_decrypt(b'not a v2 file...' + b'\x00' * 16, KEY, 0x37) is None


def test_norm_key_ascii_and_hex():
    assert dv.norm_key('0123456789abcdef') == b'0123456789abcdef'
    hexkey = '00112233445566778899aabbccddeeff'
    assert dv.norm_key(hexkey) == bytes.fromhex(hexkey)


def test_parse_xor_forms():
    assert dv.parse_xor('0x37') == 0x37
    assert dv.parse_xor('55') == 55
    assert dv.parse_xor('a3') == 0xa3
    assert dv.parse_xor(None) is None
    assert dv.parse_xor(0x137) == 0x37   # 截断到单字节
