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
import datetime

HOME = os.path.expanduser("~")


# ---- 微信本地根目录自动探测（macOS + Windows 微信 4.x）----
def _candidates(filename, env):
    """config.json / all_keys.json 的候选位置（跨平台）。env 变量优先。"""
    out = []
    e = os.environ.get(env)
    if e:
        out.append(e)
    out.append(os.path.join(HOME, ".wechat-cli", filename))              # macOS Family A / 社区工具
    la = os.environ.get("LOCALAPPDATA")
    if la:
        out.append(os.path.join(la, "wechat-cli", filename))            # Windows r266 安装位
    out.append(os.path.join(HOME, ".config", "wxcli", filename))         # r266 macOS
    out.append(os.path.join(HOME, ".config", "wechat-cli", filename))
    return out


def wechat_config():
    """读取 wechat-cli 的 config.json（多候选 + RFWG_CONFIG 覆盖）。"""
    for p in _candidates("config.json", "RFWG_CONFIG"):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    raise SystemExit("未找到 wechat-cli config.json（找过 ~/.wechat-cli/、"
                     "%LOCALAPPDATA%\\wechat-cli\\ 等）。先按 references/toolchain-setup.md "
                     "装好 wechat-cli 并提取密钥；或设 RFWG_DB_DIR 指向 db_storage。")


def wechat_root():
    """返回 xwechat_files/<account> 根（db_storage 的上一级）。可用 RFWG_DB_DIR 直接指定 db_storage。"""
    db = os.environ.get("RFWG_DB_DIR")
    if db:
        return os.path.dirname(db.rstrip("/\\"))
    db_dir = wechat_config().get("db_dir")             # .../<account>/db_storage
    if not db_dir:
        raise SystemExit("config.json 里没有 db_dir。设 RFWG_DB_DIR 指向 .../xwechat_files/<账号>/db_storage。")
    return os.path.dirname(db_dir)


def load_keys():
    """返回数据库密钥 all_keys.json（键形如 'sns/sns.db' -> {'enc_key': hex}）；多候选 + RFWG_KEYS 覆盖。"""
    for p in _candidates("all_keys.json", "RFWG_KEYS"):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    raise SystemExit("未找到 all_keys.json（数据库密钥）。macOS：`wechat-cli init`；"
                     "Windows：用社区内存扫描器提取（见 references/toolchain-setup.md 的 Windows 一节）。")


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
    with open(raw_json_path, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("messages", []), d


MEDIA_ONLY = re.compile(
    r'^(\[图片\]|\[表情\]|\[语音\]|\[视频\]|\[卡片\]|\[文件\]|\[链接\]|\[链接/文件\]|\[位置\]|\[撤回消息\].*)( \(local_id=\d+\))?$')  # noqa: E501
_TRIVIAL = {'哈哈', '哈哈哈', '哈哈哈哈', '对的', '是的', '好的', '可以', '牛', '强', '厉害', '这样',
            '收到', '嗯嗯', '对啊', '？？？', '。。。', '哦哦', '好家伙', '同意', '摸', '蹲',
            '学习了', '感谢', '谢谢'}


def is_substantive(p):
    """粗过滤：去掉纯媒体占位与极短应答/语气词，保留有信息量的发言。"""
    c = re.sub(r'\s*\(local_id=\d+\)', '', (p['content'] or '').strip())
    return not (MEDIA_ONLY.match(c) or len(c) <= 3 or c in _TRIVIAL)


def weekday_cn(datestr):
    try:
        return ['一', '二', '三', '四', '五', '六', '日'][datetime.date.fromisoformat(datestr).weekday()]
    except (ValueError, TypeError):
        return '?'


IMG_RE = re.compile(r'^\[图片\]')


def _dt(p):
    try:
        return datetime.datetime.fromisoformat(p['date'] + ' ' + p['time'])
    except (ValueError, TypeError):
        return None


def group_consecutive(parsed, max_gap_min=2, max_block=12):
    """把「同一发送者、在流中相邻、时间间隔≤max_gap_min 分钟」的消息合并成一个 block。
    这样"文字 + 紧跟的图片"、以及一个人连发的几条会归成一条（更接近一次"发言轮次"）。
    只在流中真正相邻时合并（中间插了别人就断开），并按 max_block 封顶避免超长块。
    返回 block 列表：{sender,date,t_start,t_end,items:[原始 parsed dict,...]}。"""
    blocks = []
    cur = None
    for p in parsed:
        if (cur and p['sender'] == cur['sender'] and p['sender'] != '[系统]'
                and len(cur['items']) < max_block):
            t0, t1 = cur['_last'], _dt(p)
            gap = abs((t1 - t0).total_seconds()) / 60 if (t0 and t1) else 999
            if gap <= max_gap_min:
                cur['items'].append(p)
                cur['t_end'] = p['time']
                cur['_last'] = t1 or t0
                continue
        if cur:
            cur.pop('_last', None)
            blocks.append(cur)
        cur = {'sender': p['sender'], 'date': p['date'], 't_start': p['time'],
               't_end': p['time'], 'items': [p], '_last': _dt(p)}
    if cur:
        cur.pop('_last', None)
        blocks.append(cur)
    return blocks


def load_image_index(images_dir):
    """读 images/_manifest.json，返回 {'YYYY-MM-DD HH:MM': [缩略图文件名,...]}，用于给 [图片] 贴图。"""
    idx = {}
    if not images_dir:
        return idx
    mf = os.path.join(images_dir, '_manifest.json')
    if not os.path.exists(mf):
        return idx
    with open(mf, encoding='utf-8') as f:
        for m in json.load(f):
            idx.setdefault(m['time'], []).append(m['file'])
    return idx


def months_between(start, end):
    """返回 [start, end] 覆盖到的 'YYYY-MM' 月份列表（含端点），用于遍历缓存/附件按月分目录。"""
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def day_bounds(start, end, required=True):
    """把 'YYYY-MM-DD' 的 start/end 解析成当天 [00:00:00, 23:59:59] 的时间戳 (lo, hi)。
    - start 与 end 都为空且 required=False 时返回 (None, None)（用于无时间过滤的目录模式）。
    - 格式非法或 start>end 时以清晰的 SystemExit 报错（而非裸 traceback），便于 AI 诊断。"""
    if not start and not end:
        if required:
            raise SystemExit('缺少时间范围：需要 --start 与 --end（格式 YYYY-MM-DD）。')
        return None, None
    if not (start and end):
        raise SystemExit('--start 与 --end 需同时提供（格式 YYYY-MM-DD）。')
    try:
        s = datetime.date.fromisoformat(start)
        e = datetime.date.fromisoformat(end)
    except ValueError:
        raise SystemExit(f'--start/--end 需为零填充的 YYYY-MM-DD（如 2026-06-01）；'
                         f'收到 start={start!r}, end={end!r}。') from None
    if s > e:
        raise SystemExit(f'--start（{start}）不能晚于 --end（{end}）。')
    lo = datetime.datetime.combine(s, datetime.time.min).timestamp()
    hi = datetime.datetime.combine(e, datetime.time.max).timestamp()
    return lo, hi


def write_manifest(out_dir, manifest):
    """统一写 _manifest.json：只含相对文件名（绝不写含本机用户名的绝对路径），UTF-8。"""
    with open(os.path.join(out_dir, '_manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)


# ---- 索引拼图（收图 collect_images 与全量解图 decrypt_images_v2 共用）----
def _font(size):
    from PIL import ImageFont
    for p in ['/System/Library/Fonts/Supplemental/Arial Unicode.ttf',   # macOS
              '/System/Library/Fonts/PingFang.ttc',
              r'C:\Windows\Fonts\msyh.ttc',                              # Windows 微软雅黑
              r'C:\Windows\Fonts\segoeui.ttf',
              r'C:\Windows\Fonts\arial.ttf',
              '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:        # Linux
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def make_sheets(out, manifest, cols=3, rows=4):
    """把 out/ 下 manifest 里的图拼成带编号标签的索引大图，写到 out/_sheets/sheet_NN.jpg，便于 AI 逐张判读。
    manifest 项形如 {'idx':int,'time':'YYYY-MM-DD HH:MM','file':'NNN_….jpg'}。缺 Pillow 时静默跳过。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print('未安装 Pillow，跳过拼图。pip install --break-system-packages pillow 后重试。')
        return
    if not manifest:
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
