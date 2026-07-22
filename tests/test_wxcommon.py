#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wxcommon 纯函数单测：消息解析/清洗、发言轮次合并、时间工具、密钥辅助。

全部为确定性测试，不触碰任何真实微信数据或本机路径。
"""
import os
import sys
import datetime
import hashlib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import wxcommon as wx  # noqa: E402


def test_parse_line_basic():
    p = wx.parse_line('[2026-06-21 09:05] 张三: 大家好')
    assert (p['date'], p['time'], p['sender'], p['content']) == ('2026-06-21', '09:05', '张三', '大家好')
    assert p['quote'] is None


def test_parse_line_with_quote():
    p = wx.parse_line('[2026-06-21 09:07] 王五: 同意 ↳ 回复 张三: 大家好')
    assert p['sender'] == '王五'
    assert p['content'] == '同意'
    assert p['quote'] == ('张三', '大家好')


def test_parse_line_system():
    p = wx.parse_line('[2026-06-21 09:00] [系统] 群公告更新')
    assert p['sender'] == '[系统]'
    assert p['content'] == '群公告更新'


def test_clean_blob_image_and_plain():
    assert wx.clean_blob('<msg><img cdnthumburl="x"/></msg>') == '[图片]'
    assert wx.clean_blob('  hello  ') == 'hello'
    assert wx.clean_blob('') == ''


def test_is_substantive():
    assert wx.is_substantive({'content': '这是一段有信息量的观点陈述'}) is True
    assert wx.is_substantive({'content': '哈哈'}) is False
    assert wx.is_substantive({'content': '[图片]'}) is False


def test_months_between():
    d = datetime.date
    assert wx.months_between(d(2026, 6, 21), d(2026, 7, 3)) == ['2026-06', '2026-07']
    assert wx.months_between(d(2025, 12, 1), d(2026, 2, 1)) == ['2025-12', '2026-01', '2026-02']
    assert wx.months_between(d(2026, 6, 1), d(2026, 6, 30)) == ['2026-06']


def test_room_md5_matches_stdlib():
    u = '12345678901@chatroom'
    assert wx.room_md5(u) == hashlib.md5(u.encode()).hexdigest()


def test_day_bounds_ok():
    lo, hi = wx.day_bounds('2026-06-21', '2026-06-21')
    assert lo < hi
    assert hi - lo >= 86399   # 同一天覆盖 00:00:00 ~ 23:59:59


def test_day_bounds_none_when_optional():
    assert wx.day_bounds(None, None, required=False) == (None, None)


def test_day_bounds_bad_format_raises():
    with pytest.raises(SystemExit):
        wx.day_bounds('2026/06/21', '2026-06-22')


def test_day_bounds_reversed_raises():
    with pytest.raises(SystemExit):
        wx.day_bounds('2026-07-01', '2026-06-01')


def test_day_bounds_required_missing_raises():
    with pytest.raises(SystemExit):
        wx.day_bounds(None, None, required=True)


def _msg(sender, time, content):
    return {'sender': sender, 'date': '2026-06-21', 'time': time, 'content': content, 'quote': None}


def test_group_consecutive_merges_same_sender():
    parsed = [_msg('A', '09:00', '一'), _msg('A', '09:01', '[图片]'), _msg('B', '09:05', '三')]
    blocks = wx.group_consecutive(parsed)
    assert len(blocks) == 2
    assert len(blocks[0]['items']) == 2      # A 相邻两条（文字+图片）合并为一个轮次
    assert blocks[1]['sender'] == 'B'


def test_group_consecutive_breaks_on_time_gap():
    parsed = [_msg('A', '09:00', '一'), _msg('A', '09:30', '二')]   # 间隔 30 分钟 > 2
    blocks = wx.group_consecutive(parsed)
    assert len(blocks) == 2


def test_group_consecutive_breaks_on_interleave():
    parsed = [_msg('A', '09:00', '一'), _msg('B', '09:00', '插话'), _msg('A', '09:01', '二')]
    blocks = wx.group_consecutive(parsed)
    assert [b['sender'] for b in blocks] == ['A', 'B', 'A']   # 中间插了别人就断开
