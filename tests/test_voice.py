#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""transcribe_voice 纯函数单测：SILK 头识别、文件名时间戳解析。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import transcribe_voice as tv  # noqa: E402

WECHAT_SILK_HEAD = bytes.fromhex('02232153494c4b5f56330a')   # \x02#!SILK_V3\n


def test_is_silk_wechat_head(tmp_path):
    p = tmp_path / 'a.silk'
    p.write_bytes(WECHAT_SILK_HEAD + b'\x00' * 32)
    assert tv.is_silk(str(p)) is True


def test_is_silk_plain_head(tmp_path):
    p = tmp_path / 'b.silk'
    p.write_bytes(b'#!SILK_V3' + b'\x00' * 8)
    assert tv.is_silk(str(p)) is True


def test_is_silk_rejects_non_silk(tmp_path):
    p = tmp_path / 'c.dat'
    p.write_bytes(bytes.fromhex('07085632080700000000000000'))
    assert tv.is_silk(str(p)) is False


def test_parse_ts_wechat_name():
    assert tv.parse_ts('17034dcf3b9ebd5242b1b2b5fbb234c6_1749720549_2.silk') == 1749720549


def test_parse_ts_millis():
    assert tv.parse_ts('abc_1749720549123_0.silk') == 1749720549


def test_parse_ts_none_when_absent():
    assert tv.parse_ts('voicenote.silk') is None
