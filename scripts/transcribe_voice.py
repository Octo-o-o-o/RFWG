#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把微信语音（明文 SILK v3）本地转写成带时间戳的文字。全程离线，不外发音频。
数据来源（真机确认，见 references/wechat-local-data.md §6）：
  cache/<YYYY-MM>/Message/<md5(room)>/VoiceTemp/<md5(room)>_<unixts>_N.silk
  明文 SILK v3（头 0x02 + #!SILK_V3），无加密、无需密钥；VoiceTemp 只含“被播放过”的语音，非全量。
依赖（可选）：pip install -r requirements-voice.txt   # pilk + faster-whisper
本文件自包含（不依赖 wxcommon），确保单独可跑。
"""
import argparse
import os
import glob
import json
import hashlib
import datetime

SILK_MAGIC = b'#!SILK_V3'


def wechat_root():
    db = os.environ.get('RFWG_DB_DIR')
    if db:
        return os.path.dirname(db.rstrip('/\\'))
    cands = [os.path.expanduser('~/.wechat-cli/config.json'),
             os.path.expanduser('~/.config/wxcli/config.json')]
    la = os.environ.get('LOCALAPPDATA')
    if la:
        cands.append(os.path.join(la, 'wechat-cli', 'config.json'))
    for p in cands:
        if os.path.exists(p):
            try:
                with open(p, encoding='utf-8') as f:
                    d = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if d.get('db_dir'):
                return os.path.dirname(d['db_dir'])
    raise SystemExit('未找到微信数据目录：设 RFWG_DB_DIR 指向 .../xwechat_files/<账号>/db_storage。')


def room_md5(username):
    return hashlib.md5(username.encode()).hexdigest()


def months_between(start, end):
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f'{y:04d}-{m:02d}')
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def day_bounds(start, end):
    try:
        s = datetime.date.fromisoformat(start)
        e = datetime.date.fromisoformat(end)
    except ValueError:
        raise SystemExit('--start/--end 需为 YYYY-MM-DD') from None
    if s > e:
        raise SystemExit('--start 不能晚于 --end')
    return (datetime.datetime.combine(s, datetime.time.min).timestamp(),
            datetime.datetime.combine(e, datetime.time.max).timestamp())


def is_silk(path):
    try:
        with open(path, 'rb') as f:
            return SILK_MAGIC in f.read(12)
    except OSError:
        return False


def parse_ts(fn):
    for p in os.path.splitext(fn)[0].split('_'):
        if p.isdigit() and 10 <= len(p) <= 13:
            return int(p[:10])
    return None


def sources_room(root, room, start, end):
    rmd5 = room_md5(room)
    lo, hi = day_bounds(start, end)
    out = []
    for ym in months_between(datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)):
        d = os.path.join(root, 'cache', ym, 'Message', rmd5, 'VoiceTemp')
        for f in glob.glob(os.path.join(d, '*.silk')):
            ts = parse_ts(os.path.basename(f)) or int(os.path.getmtime(f))
            if lo <= ts <= hi:
                out.append((ts, f))
    return out


def sources_dir(inp):
    out = []
    for f in glob.glob(os.path.join(inp, '**', '*.silk'), recursive=True):
        if os.path.isfile(f):
            out.append((int(os.path.getmtime(f)), f))
    return out


def silk_to_wav(silk_path, wav_path):
    """微信明文 SILK v3 → WAV（本地）。pilk 可直接解带腾讯 0x02 头的 SILK。"""
    import pilk
    pilk.silk_to_wav(silk_path, wav_path)


def main():
    ap = argparse.ArgumentParser(description='把微信明文 SILK 语音本地转写成带时间戳文字（离线）')
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--room', help='群/联系人 username（如 12345678901@chatroom）')
    src.add_argument('--in', dest='inp', help='任意含 .silk 的目录（递归）')
    ap.add_argument('--out', required=True)
    ap.add_argument('--start', help='YYYY-MM-DD（--room 必填）')
    ap.add_argument('--end', help='YYYY-MM-DD（--room 必填）')
    ap.add_argument('--model', default='small', help='faster-whisper 模型 tiny/base/small/medium')
    ap.add_argument('--language', default='zh')
    ap.add_argument('--model-dir', default='')
    ap.add_argument('--offline', action='store_true', help='只用本地已缓存模型，绝不联网')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--dry-run', action='store_true', help='只列出会转写哪些（不需依赖/模型）')
    ap.add_argument('--keep-wav', action='store_true')
    a = ap.parse_args()
    if a.room and not (a.start and a.end):
        raise SystemExit('--room 需要 --start 与 --end（YYYY-MM-DD）。')
    if a.room:
        items = sources_room(wechat_root(), a.room, a.start, a.end)
        label = f'群/人 {a.room}'
    else:
        items = sources_dir(a.inp)
        label = f'目录 {a.inp}'
    items = [(ts, f) for ts, f in items if is_silk(f)]
    items.sort()
    if a.limit:
        items = items[:a.limit]
    print(f'[{label}] 命中明文 SILK 语音 {len(items)} 条（{a.start or "-"}~{a.end or "-"}）')
    if not items:
        print('  未命中：该群该时段无语音，或语音未被播放过（VoiceTemp 只含播放过的明文缓存，非全量）。')
        return
    if a.dry_run:
        for ts, f in items[:10]:
            print('  ', datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M'), os.path.basename(f))
        if len(items) > 10:
            print(f'  … 共 {len(items)} 条。去掉 --dry-run 并装好依赖即可转写。')
        return
    try:
        import pilk  # noqa: F401
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit('缺依赖：pip install -r requirements-voice.txt（pilk + faster-whisper）。') from None
    print(f'  加载本地模型 {a.model}（首次联网下载；之后可 --offline 断网）…')
    model = WhisperModel(a.model, device='cpu', compute_type='int8',
                         download_root=(a.model_dir or None), local_files_only=a.offline)
    os.makedirs(a.out, exist_ok=True)
    manifest, rows, ok, fail = [], [], 0, 0
    for idx, (ts, f) in enumerate(items, 1):
        dt = datetime.datetime.fromtimestamp(ts)
        wav = os.path.join(a.out, f'{idx:03d}_{dt.strftime("%m%d_%H%M")}.wav')
        try:
            silk_to_wav(f, wav)
            segments, info = model.transcribe(wav, language=a.language, vad_filter=True, beam_size=5)
            text = ''.join(s.text for s in segments).strip()
        except Exception as e:
            print(f'  [{idx}] 失败 {os.path.basename(f)}: {e}')
            fail += 1
            if not a.keep_wav and os.path.exists(wav):
                os.remove(wav)
            continue
        dur = round(getattr(info, 'duration', 0) or 0, 1)
        if not a.keep_wav and os.path.exists(wav):
            os.remove(wav)
        manifest.append({'idx': idx, 'time': dt.strftime('%Y-%m-%d %H:%M'), 'duration_s': dur, 'text': text})
        rows.append((dt, dur, text))
        ok += 1
        print(f'  [{idx}/{len(items)}] {dt.strftime("%m-%d %H:%M")} ({dur}s) {text[:40]}')
    with open(os.path.join(a.out, '_manifest.json'), 'w', encoding='utf-8') as w:
        json.dump(manifest, w, ensure_ascii=False, indent=1)
    md = os.path.join(a.out, 'voice_transcripts.md')
    with open(md, 'w', encoding='utf-8') as w:
        w.write('# 语音转写（本地 faster-whisper，可能有少量错字）\n\n')
        w.write(f'> 成功 {ok} 条、失败 {fail} 条。语音属他人隐私，遵守匿名化与用完即删。\n')
        cur = None
        for dt, dur, text in rows:
            d = dt.strftime('%Y-%m-%d')
            if d != cur:
                cur = d
                w.write(f'\n## {d}\n\n')
            w.write(f"- `{dt.strftime('%H:%M')}` [语音 {dur}s] {text or '（空/未识别）'}\n")
    print(f'转写完成：成功 {ok} / 失败 {fail} -> {md}')


if __name__ == '__main__':
    main()
