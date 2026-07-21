#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RFWG 共享库：微信本地数据的定位、消息清洗、密钥加载。

被本目录其它脚本复用。不直接运行。
关键约定：
- wechat-cli 的配置在 ~/.wechat-cli/config.json（db_dir），密钥在 ~/.wechat-cli/all_keys.json。
- 群聊房间目录名 = md5(<roomid>@chatroom 的 username)，如 md5('12345678901@chatroom')。
"""
import os
import re
import json
import html
import hashlib
import glob

HOME = os.path.expanduser("~")

# ---- 微信本地根目录自动探测（macOS 微信 4.x）----
def wechat_config():
    """读取 wechat-cli 的 config.json，返回 db_dir。"""
    p = os.path.join(HOME, ".wechat-cli", "config.json")
    if not os.path.exists(p):
        raise SystemExit("未找到 ~/.wechat-cli/config.json，请先运行 `wechat-cli init`。")
    return json.load(open(p, encoding="utf-8"))


def wechat_root():
    """由 db_dir 反推 xwechat_files/<account> 根（db_storage 的上一级）。"""
    db_dir = wechat_config()["db_dir"]              # .../<account>/db_storage
    return os.path.dirname(db_dir)


def load_keys():
    """返回 all_keys.json（键形如 'sns/sns.db' -> {'enc_key': hex}）。"""
    p = os.path.join(HOME, ".wechat-cli", "all_keys.json")
    if not os.path.exists(p):
        raise SystemExit("未找到 ~/.wechat-cli/all_keys.json，请先运行 `wechat-cli init`。")
    return json.load(open(p, encoding="utf-8"))


def room_md5(username):
    """群/联系人在缓存目录里的哈希名。username 例如 '12345678901@chatroom' 或 wxid。"""
    return hashlib.md5(username.encode()).hexdigest()


# ---- 消息清洗：把 wechat-cli 导出的富文本行解析成结构 ----
HEAD_RE = re.compile(r'^\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\] (.*?): (.*)$', re.S)
SYS_RE = re.compile(r'^\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})\] \[系统\] (.*)$', re.S)


def _title(xml):
    m = re.search(r'<title>(.*?)</title>', xml, re.S)
    return html.unescape(m.group(1)).strip() if m else None


def clean_blob(text):
    """把可能含 XML 的一段消息压成可读标记（图片/语音/卡片/撤回等）。"""
    t = (text or "").strip()
    if not t:
        return ""
    if 'revokemsg' in t:
        mm = re.search(r'<content>"?(.*?)"?\s*撤回了一条消息', t)
        who = mm.group(1) if mm else ''
        return f'[撤回消息]{("（" + who + "）") if who else ""}'
    if '<appmsg' in t or '<?xml' in t or '<msg>' in t:
        title = _title(t)
        if title:
            return '[图片]' if ('<' in title and '>' in title) else title
        if '<img ' in t or 'cdnthumburl' in t or 'cdnbigimgurl' in t:
            return '[图片]'
        if '<voicemsg' in t or 'voicelength' in t:
            return '[语音]'
        if '<videomsg' in t or 'cdnvideourl' in t:
            return '[视频]'
        return '[卡片]'
    return t


def parse_line(msg):
    """解析一条 wechat-cli 消息字符串 -> dict(date,time,sender,content,quote)。"""
    quote = None
    main = msg
    idx = msg.find('↳')
    if idx != -1:
        main = msg[:idx].rstrip()
        qline = msg[idx + 1:].strip()
        qm = re.match(r'回复\s*(.*?):\s*(.*)$', qline, re.S)
        quote = (qm.group(1).strip(), clean_blob(qm.group(2))) if qm else ('', clean_blob(qline))
    sm = SYS_RE.match(main)
    if sm:
        return {'date': sm.group(1), 'time': sm.group(2), 'sender': '[系统]',
                'content': clean_blob(sm.group(3)), 'quote': quote}
    hm = HEAD_RE.match(main)
    if hm:
        d, t, s, b = hm.groups()
        return {'date': d, 'time': t, 'sender': s.strip(), 'content': clean_blob(b), 'quote': quote}
    return {'date': '', 'time': '', 'sender': '?', 'content': clean_blob(main), 'quote': quote}


def load_messages(raw_json_path):
    """读取 wechat-cli --format json 的导出，返回 messages 列表（字符串）。"""
    d = json.load(open(raw_json_path, encoding="utf-8"))
    return d.get("messages", []), d


MEDIA_ONLY = re.compile(
    r'^(\[图片\]|\[表情\]|\[语音\]|\[视频\]|\[卡片\]|\[文件\]|\[链接\]|\[链接/文件\]|\[位置\]|\[撤回消息\].*)( \(local_id=\d+\))?$')
_TRIVIAL = {'哈哈', '哈哈哈', '哈哈哈哈', '对的', '是的', '好的', '可以', '牛', '强', '厉害', '这样',
            '收到', '嗯嗯', '对啊', '？？？', '。。。', '哦哦', '好家伙', '同意', '摸', '蹲',
            '学习了', '感谢', '谢谢'}


def is_substantive(p):
    """粗过滤：去掉纯媒体占位与极短应答/语气词，保留有信息量的发言。"""
    c = re.sub(r'\s*\(local_id=\d+\)', '', (p['content'] or '').strip())
    if MEDIA_ONLY.match(c) or len(c) <= 3 or c in _TRIVIAL:
        return False
    return True


def weekday_cn(datestr):
    import datetime
    try:
        return ['一', '二', '三', '四', '五', '六', '日'][datetime.date.fromisoformat(datestr).weekday()]
    except (ValueError, TypeError):
        return '?'
