"""
transcriber.py — Transcript extraction for OpenClip.

Provides two strategies for obtaining a transcript:

1. **YouTube captions** (fast, free) — downloads the auto-generated or
   manual subtitle track via ``yt-dlp --write-auto-sub`` and parses the
   resulting ``.vtt`` file.
2. **Local Whisper** (slow, accurate) — runs OpenAI's open-source Whisper
   model on the audio to produce word-level timestamps.

The public entry-point ``extract_transcript`` tries YouTube captions
first and falls back to Whisper if none are available.
"""

import os
import re
import glob
import asyncio
import subprocess
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def extract_captions(
    youtube_url: str,
    video_path: str,
) -> list[dict]:
    """
    Extract a transcript for the given video.

    Strategy: try YouTube manual captions first, then auto captions,
    fall back to local Whisper transcription if captions are unavailable.

    Args:
        youtube_url:       Original YouTube URL (used to fetch captions).
        video_path:        Absolute path to the downloaded video file (used for Whisper fallback).

    Returns:
        A list of segment dicts::

            [{"start": 0.0, "end": 5.2, "text": "Hey welcome back..."}, ...]
    """
    # Priority 1: Creator captions
    result = await _get_manual_captions(youtube_url)
    if result:
        return result

    # Priority 2: Auto-generated captions
    result = await _get_auto_captions(youtube_url)
    if result:
        return result

    # Priority 3: Whisper fallback
    logger.info("Falling back to Whisper transcription...")
    return await _get_whisper_transcript(video_path)


# ---------------------------------------------------------------------------
# Strategy 1: YouTube captions via yt-dlp
# ---------------------------------------------------------------------------

async def _get_manual_captions(youtube_url: str) -> list[dict]:
    """
    Use yt-dlp to download manual creator captions as a ``.vtt`` file.
    """
    import tempfile
    work_dir = tempfile.mkdtemp(prefix="openclip_subs_")
    output_template = os.path.join(work_dir, "%(id)s")

    cmd = [
        r"C:\Users\Prajjwal\Downloads\Openclip\backend\.venv\Scripts\yt-dlp.exe",
        "--write-sub",
        "--skip-download",
        "--sub-format", "json3",
        "--sub-langs", "en.*,en",
        "-o", output_template,
        youtube_url,
    ]

    try:
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=60,  # type: ignore
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            return []
        json_files = glob.glob(os.path.join(work_dir, "*.json3"))
        if not json_files:
            return []
        return _parse_json3(json_files[0])
    except Exception as exc:
        logger.warning("YouTube manual caption extraction failed: %s", exc)
        return []

async def _get_auto_captions(youtube_url: str) -> list[dict]:
    """
    Use yt-dlp to download auto-generated captions as a ``.vtt`` file.
    """
    import tempfile
    work_dir = tempfile.mkdtemp(prefix="openclip_subs_")
    output_template = os.path.join(work_dir, "%(id)s")

    cmd = [
        r"C:\Users\Prajjwal\Downloads\Openclip\backend\.venv\Scripts\yt-dlp.exe",
        "--write-auto-sub",
        "--skip-download",
        "--js-runtimes", "node",
        "--extractor-args", "youtube:player_client=web,default",
        "--sub-format", "json3",
        "--sub-langs", "en.*,en",
        "-o", output_template,
        youtube_url,
    ]

    env = os.environ.copy()
    env["PATH"] = env.get("PATH", "") + r";C:\Program Files\nodejs;C:\Users\Prajjwal\Downloads\Openclip\backend\bin"

    try:
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=60,  # type: ignore
            encoding="utf-8", errors="replace", env=env,
        )
        if result.returncode != 0:
            return []
        json_files = glob.glob(os.path.join(work_dir, "*.json3"))
        if not json_files:
            return []
        return _parse_json3(json_files[0])
    except Exception as exc:
        logger.warning("YouTube auto caption extraction failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# JSON3 parser
# ---------------------------------------------------------------------------

import json

def _parse_json3(json_path: str) -> list[dict]:
    """
    Parse a YouTube JSON3 subtitle file into transcript segments with word timings.
    """
    segments: list[dict] = []

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data.get("events", [])
    
    for event in events:
        if "segs" not in event:
            continue
            
        t_start_ms = event.get("tStartMs", 0)
        d_duration_ms = event.get("dDurationMs", 0)
        
        # Build segment text and word array
        seg_text = ""
        words = []
        
        segs = event["segs"]
        for i, s in enumerate(segs):
            raw_word = str(s.get("utf8", ""))
            if not raw_word.strip() or raw_word == "\n":
                continue
                
            offset_ms = float(s.get("tOffsetMs", 0))
            word_start = (t_start_ms + offset_ms) / 1000.0
            
            # Estimate word end: If next word exists, use its start. Else, use event end.
            if i + 1 < len(segs) and "tOffsetMs" in segs[i+1]:
                word_end = (float(t_start_ms) + float(segs[i+1]["tOffsetMs"])) / 1000.0
            else:
                # Provide a minimum padding if duration is missing
                fallback_dur = max(float(d_duration_ms), offset_ms + 300.0)
                word_end = (float(t_start_ms) + fallback_dur) / 1000.0
                
            words.append({
                "word": str(raw_word).strip(),
                "start": word_start,
                "end": word_end
            })
            seg_text += raw_word
            
        seg_text = str(seg_text).strip()
        if not seg_text or not words:
            continue
            
        start_sec = words[0]["start"]
        end_sec = words[-1]["end"]
        
        # Merge if very close to previous segment
        if segments and start_sec - segments[-1]["end"] < 0.5:
            last_seg = segments[-1]
            last_seg["end"] = max(last_seg["end"], end_sec)
            last_seg["text"] += " " + seg_text
            last_seg["words"].extend(words) # type: ignore
        else:
            segments.append({
                "start": start_sec,
                "end": end_sec,
                "text": seg_text,
                "words": words
            })

    logger.info("Parsed %d segments from JSON3 file", len(segments))
    return segments


# ---------------------------------------------------------------------------
# Strategy 2: Local Whisper transcription
# ---------------------------------------------------------------------------

async def _get_whisper_transcript(
    video_path: str,
) -> list[dict]:
    """
    Transcribe a video locally using OpenAI's open-source Whisper model.
    """
    def _do_transcribe() -> list[dict]:
        try:
            import whisper  # type: ignore[import-untyped]
        except ImportError:
            logger.error("openai-whisper is not installed — cannot transcribe")
            return []
            
        model = whisper.load_model("base")
        result = model.transcribe(video_path)

        segments: list[dict] = []
        for seg in result.get("segments", []):
            segments.append({
                "start": float(seg["start"]),
                "end": float(seg["end"]),
                "text": seg["text"].strip(),
            })

        return segments

    segments: list[dict] = await asyncio.to_thread(_do_transcribe)  # type: ignore
    logger.info("Whisper produced %d segments", len(segments))
    return segments
