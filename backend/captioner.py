import subprocess
import ffmpeg_utils
import os
import json
import re
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List

CAPTION_STYLES: Dict[str, Dict[str, Any]] = {
  "classic_white": {
    "name": "Classic White",
    "font": "Arial-Bold",
    "fontsize": 95,
    "primary_color": "&H00FFFFFF",   # white
    "outline_color": "&H00000000",   # black outline
    "outline_width": 5,
    "shadow": 2,
    "background": False,
    "animation": "word_by_word",
    "max_chars_per_line": 15,
    "highlight_color": None
  },
  "yellow_bold": {
    "name": "Yellow Bold",
    "font": "Arial-Bold",
    "fontsize": 105,
    "primary_color": "&H0000FFFF",   # yellow
    "outline_color": "&H00000000",   # black
    "outline_width": 6,
    "shadow": 0,
    "background": False,
    "animation": "word_by_word",
    "max_chars_per_line": 14,
    "highlight_color": None
  },
  "neon_green": {
    "name": "Neon Green",
    "font": "Arial-Bold",
    "fontsize": 95,
    "primary_color": "&H0000FF66",   # neon green
    "outline_color": "&H00003300",   # dark green outline
    "outline_width": 5,
    "shadow": 2,
    "background": False,
    "animation": "highlight",
    "max_chars_per_line": 15,
    "highlight_color": "&H0000FF66"  # same green for highlight
  },
  "highlight_yellow": {
    "name": "Highlight Yellow",
    "font": "Arial-Bold",
    "fontsize": 95,
    "primary_color": "&H00FFFFFF",   # white default
    "outline_color": "&H00000000",
    "outline_width": 4,
    "shadow": 0,
    "background": True,
    "bg_color": "&H99000000",        # semi-transparent black bg
    "animation": "highlight",
    "max_chars_per_line": 15,
    "highlight_color": "&H0000FFFF"  # yellow highlight
  },
  "white_box": {
    "name": "White Box",
    "font": "Arial-Bold",
    "fontsize": 90,
    "primary_color": "&H00000000",   # black text
    "outline_color": "&H00FFFFFF",
    "outline_width": 0,
    "shadow": 0,
    "background": True,
    "bg_color": "&HFFFFFFFF",        # solid white background
    "animation": "word_by_word",
    "max_chars_per_line": 14,
    "highlight_color": None
  },
  "purple_glow": {
    "name": "Purple Glow",
    "font": "Arial-Bold",
    "fontsize": 100,
    "primary_color": "&H00FF66FF",   # purple/pink
    "outline_color": "&H00330033",
    "outline_width": 5,
    "shadow": 3,
    "background": False,
    "animation": "word_by_word",
    "max_chars_per_line": 14,
    "highlight_color": None
  },
  "tiktok_style": {
    "name": "TikTok Style",
    "font": "Arial-Bold",
    "fontsize": 110,
    "primary_color": "&H00FFFFFF",   # white
    "outline_color": "&H00000000",   # black
    "outline_width": 7,
    "shadow": 0,
    "background": False,
    "animation": "highlight",
    "max_chars_per_line": 12,
    "highlight_color": "&H0000FFFF"  # yellow highlight
  },
  "minimal_clean": {
    "name": "Minimal Clean",
    "font": "Arial",
    "fontsize": 46,
    "primary_color": "&H00FFFFFF",
    "outline_color": "&H00000000",
    "outline_width": 2,
    "shadow": 0,
    "background": False,
    "animation": "word_by_word",
    "max_chars_per_line": 28,
    "highlight_color": None
  },
  "viral_word": {
    "name": "Viral Word",
    "font": "Arial-Black",
    "fontsize": 95,
    "primary_color": "&H00FFFFFF",
    "outline_color": "&H00000000",
    "outline_width": 8,
    "shadow": 3,
    "shadow_color": "&H55000000",
    "background": False,
    "animation": "one_word",
    "max_chars_per_line": 8,
    "highlight_color": None,
    "uppercase": True,
    "letter_spacing": 2
  }
}

def _extract_clip_segments(transcript: list[dict], clip_start: float, clip_end: float) -> list[dict]:
    result = []
    for seg in transcript:
        # Ignore segments outside clip window
        if seg['end'] <= clip_start or seg['start'] >= clip_end:
            continue
        clean_text = re.sub(r"\[.*?\]", "", seg.get('text', '')).strip()
        if not clean_text:
            continue
        adj_start = max(0.0, seg['start'] - clip_start)
        adj_end = min(clip_end - clip_start, seg['end'] - clip_start)
        if adj_end - adj_start <= 0.1:
            continue
        adjusted = {
            "start": adj_start,
            "end": adj_end,
            "text": clean_text
        }
        if 'words' in seg:
            adj_words = []
            for w in seg['words']: # type: ignore
                w_start = w['start'] - clip_start
                w_end = w['end'] - clip_start
                if w_end > 0 and w_start < (clip_end - clip_start):
                    adj_words.append({
                        "word": w['word'],
                        "start": max(0.0, w_start),
                        "end": min(clip_end - clip_start, w_end)
                    })
            if adj_words:
                adjusted['words'] = adj_words
        result.append(adjusted)

    # Strictly sort and clamp consecutive segments to eliminate overlaps
    result.sort(key=lambda s: s['start'])
    for i in range(len(result) - 1):
        if result[i]['end'] > result[i + 1]['start']:
            result[i]['end'] = max(result[i]['start'] + 0.05, result[i + 1]['start'])

    return result

def _build_caption_groups(segments: list[dict], max_chars: int) -> list[dict]:
    groups: List[Dict[str, Any]] = []
    current_text: str = ""
    current_start: float = 0.0
    current_end: float = 0.0
    current_words: list = []

    for seg in segments:
        words_data = seg.get('words')
        
        if words_data:
            # We have exact word-level timings from transcriber
            for w_data in words_data:
                word_str = str(w_data['word'])
                word_start = float(w_data['start'])
                word_end = float(w_data['end'])
                
                test_text = f"{current_text} {word_str}".strip()
                if len(test_text) > max_chars and current_text:
                    groups.append({
                        "start": current_start,
                        "end": current_end,
                        "text": current_text,
                        "words": current_words
                    })
                    current_text = word_str
                    current_start = word_start
                    current_end = word_end
                    current_words = [{
                        "word": word_str,
                        "start": word_start,
                        "end": word_end
                    }]
                else:
                    if not current_text:
                        current_start = word_start
                    current_text = test_text
                    current_end = max(current_end, word_end)
                    current_words.append({ # type: ignore
                        "word": word_str,
                        "start": word_start,
                        "end": word_end
                    })
            continue

        words: list[str] = seg['text'].split()
        seg_duration = float(seg['end']) - float(seg['start'])
        word_duration = seg_duration / max(len(words), 1)

        for i, word in enumerate(words):
            word_start = seg['start'] + i * word_duration
            word_end = word_start + word_duration

            word_str = str(word)
            test_text = f"{current_text} {word_str}".strip()

            if len(test_text) > max_chars and current_text:
                # Flush current group
                groups.append({
                    "start": current_start,
                    "end": current_end,
                    "text": current_text,
                    "words": current_words
                })
                current_text = word_str
                current_start = word_start
                current_end = word_end
                current_words = [{
                    "word": word_str,
                    "start": word_start,
                    "end": word_end
                }]
            else:
                if not current_text:
                    current_start = word_start
                current_text = test_text
                current_end = word_end
                current_words.append({ # type: ignore
                    "word": word_str,
                    "start": word_start,
                    "end": word_end
                })

    if current_text:
        groups.append({
            "start": current_start,
            "end": current_end,
            "text": current_text,
            "words": current_words
        })

    return groups

def _add_word_timing(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for group in groups:
        duration = group['end'] - group['start']
        words = group['words']
        if not words:
            continue

        # Weight by word length
        weights = []
        for w in words:
            l = len(w['word'])
            if l <= 2:
                weights.append(0.6)
            elif l >= 8:
                weights.append(1.3)
            else:
                weights.append(1.0)

        total_weight = sum(weights)
        t = float(group['start'])
        for i, (w, weight) in enumerate(zip(words, weights)):
            word_dur = float(duration) * (float(weight) / float(total_weight))
            # Only assign generated timing if actual word timings missing
            if w['start'] == w['end']: # meaning we built naive fallback
                w['start'] = float(t)
                w['end'] = float(t) + float(word_dur)
            t += word_dur

    return groups

def _write_ass_file(ass_path: str, groups: List[Dict[str, Any]], style: Dict[str, Any]) -> None:
    def seconds_to_ass(t: float) -> str:
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    primary = style['primary_color']
    outline = style['outline_color']
    outline_w = style['outline_width']
    shadow = style['shadow']
    fontsize = style['fontsize']
    font = style['font']
    bold = -1  # bold on
    highlight = style.get('highlight_color', '&H0000FFFF')

    bg_color = style.get('bg_color', '&H00000000')
    border_style = 4 if style.get('background') else 1
    # Use shadow_color as BackColour when in outline mode (no background)
    back_colour = bg_color if style.get('background') else style.get('shadow_color', bg_color)
    spacing = style.get('letter_spacing', 0)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{fontsize},{primary},{highlight},{outline},{back_colour},{bold},0,0,0,100,100,{spacing},0,{border_style},{outline_w},{shadow},2,80,80,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    raw_events: List[Dict[str, Any]] = []

    for g_idx, group in enumerate(groups):
        animation = style['animation']

        if animation == 'word_by_word':
            shown_words = []
            for i, word_data in enumerate(group['words']):
                shown_words.append(word_data['word'])
                display_text = " ".join(shown_words)
                start_time = float(word_data['start'])
                if i + 1 < len(group['words']):
                    end_time = float(group['words'][i+1]['start'])
                else:
                    end_time = float(group['end'])
                    if g_idx + 1 < len(groups):
                        next_words: list = groups[g_idx+1].get('words', [])
                        if next_words:
                            end_time = min(end_time, float(next_words[0]['start']))
                    end_time = min(end_time, start_time + 0.6)
                text = f"{{\\pos(540,1500)}}{display_text}"
                raw_events.append({'start': start_time, 'end': max(start_time + 0.05, end_time), 'text': text})

        elif animation == 'highlight':
            words = [w['word'] for w in group['words']]
            for i, word_data in enumerate(group['words']):
                start_time = float(word_data['start'])
                if i + 1 < len(group['words']):
                    end_time = float(group['words'][i+1]['start'])
                else:
                    end_time = float(group['end'])
                    if g_idx + 1 < len(groups):
                        next_words: list = groups[g_idx+1].get('words', [])
                        if next_words:
                            end_time = min(end_time, float(next_words[0]['start']))
                    end_time = min(end_time, start_time + 0.6)
                colored_parts: list[str] = []
                for j, w in enumerate(words):
                    if j == i:
                        colored_parts.append(
                            f"{{\\1c{highlight}&\\bord{outline_w+1}}}{w}"
                            f"{{\\1c{primary}&\\bord{outline_w}}}"
                        )
                    else:
                        colored_parts.append(w)
                display_text = " ".join(colored_parts)
                text = f"{{\\pos(540,1500)}}{display_text}"
                raw_events.append({'start': start_time, 'end': max(start_time + 0.05, end_time), 'text': text})

        elif animation == 'one_word':
            for i, word_data in enumerate(group['words']):
                word_text = word_data['word'].upper()
                start_time = float(word_data['start'])
                if i + 1 < len(group['words']):
                    end_time = float(group['words'][i + 1]['start'])
                else:
                    end_time = float(group['end'])
                    if g_idx + 1 < len(groups):
                        next_words: list = groups[g_idx + 1].get('words', [])
                        if next_words:
                            end_time = min(end_time, float(next_words[0]['start']))
                    end_time = min(end_time, start_time + 0.6)
                text = f"{{\\pos(540,1500)\\fscx105\\fscy105}}{word_text}"
                raw_events.append({'start': start_time, 'end': max(start_time + 0.05, end_time), 'text': text})

    # Sort and strictly de-conflict so no two subtitles ever overlap
    raw_events.sort(key=lambda e: e['start'])
    for k in range(len(raw_events) - 1):
        if raw_events[k]['end'] > raw_events[k + 1]['start']:
            raw_events[k]['end'] = raw_events[k + 1]['start']
        if raw_events[k]['end'] <= raw_events[k]['start']:
            raw_events[k]['end'] = raw_events[k]['start'] + 0.05

    for ev in raw_events:
        start_ts = seconds_to_ass(ev['start'])
        end_ts = seconds_to_ass(ev['end'])
        lines.append(
            f"Dialogue: 0,{start_ts},{end_ts},"
            f"Default,,0,0,0,,{ev['text']}\n"
        )

    with open(ass_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)

async def _burn_ass_to_video(input_path: str, ass_path: str, output_path: str) -> None:
    # Use backward slash since windows? But ffmpeg filters often require forward slashes for paths on Windows
    # to avoid escaping issues. Or we can use relative paths if we set cwd.
    # Let's fix the path for ffmpeg filter: replace \ with / and escape : as \:
    safe_ass_path = ass_path.replace("\\", "/").replace(":", "\\:")
    ffmpeg_path = ffmpeg_utils.get_ffmpeg_exe()
    cmd = [
        ffmpeg_path, "-i", input_path,
        "-vf", f"ass='{safe_ass_path}'",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path, "-y"
    ]
    
    def _run_ffmpeg() -> tuple[int, str]:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.returncode, str(res.stderr)
        
    returncode, stderr_output = await asyncio.to_thread(_run_ffmpeg) # type: ignore
    
    if returncode != 0:
        raise RuntimeError(
            f"Caption burn failed: {stderr_output}"
        )

async def burn_captions(video_path: str, full_transcript: List[Dict[str, Any]], clip_start: float, clip_end: float, style_key: str) -> str:
    style = CAPTION_STYLES.get(style_key, CAPTION_STYLES['classic_white'])

    # Step 1 — Extract relevant transcript for this clip
    clip_segments = _extract_clip_segments(full_transcript, clip_start, clip_end)

    if not clip_segments:
        return video_path  # no captions to add

    # Step 2 — Build caption groups
    max_chars = int(style['max_chars_per_line'])
    caption_groups = _build_caption_groups(clip_segments, max_chars)

    # Step 3 — Generate word timing if animation needs it
    if style['animation'] in ['word_by_word', 'highlight', 'one_word']:
        caption_groups = _add_word_timing(caption_groups)

    # Step 4 — Build ASS file
    ass_path = video_path + ".ass"
    _write_ass_file(ass_path, caption_groups, style)

    # Step 5 — Burn with FFmpeg
    output_path = video_path.replace('.mp4', '_captioned.mp4')
    await _burn_ass_to_video(video_path, ass_path, output_path)

    os.remove(ass_path)
    return output_path
