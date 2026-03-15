"""Transcript extraction pipeline.

Priority order:
1) User-uploaded/manual YouTube captions
2) Auto-generated YouTube captions
3) yt-dlp subtitle extraction fallback
4) Local Whisper fallback
"""

import asyncio
import glob
import json
import logging
import os
import subprocess
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


def _resolve_ytdlp_exe() -> str:
    """Resolve yt-dlp from local virtualenv first, then PATH."""
    backend_dir = os.path.dirname(__file__)
    candidates = [
        os.path.join(backend_dir, ".venv", "Scripts", "yt-dlp.exe"),
        os.path.join(backend_dir, "..", ".venv", "Scripts", "yt-dlp.exe"),
    ]
    for candidate in candidates:
        resolved = os.path.abspath(candidate)
        if os.path.isfile(resolved):
            return resolved
    return "yt-dlp"


def _notify(
    progress_callback: Optional[Callable[[float, str], None]],
    percent: float,
    message: str,
) -> None:
    if progress_callback is not None:
        progress_callback(percent, message)


def _extract_video_id(youtube_url: str) -> str:
    """Extract canonical YouTube video id from common URL formats."""
    parsed = urlparse(youtube_url)
    host = parsed.netloc.lower()

    if "youtu.be" in host:
        return parsed.path.strip("/")

    if "youtube.com" in host or "m.youtube.com" in host:
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [""])[0]
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/shorts/")[-1].split("/")[0]
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/embed/")[-1].split("/")[0]

    return ""


def _normalize_transcript_items(items: list[object]) -> list[dict]:
    segments: list[dict] = []
    for item in items:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            start = float(item.get("start", 0.0))
            duration = float(item.get("duration", 0.0))
        else:
            text = str(getattr(item, "text", "")).strip()
            start = float(getattr(item, "start", 0.0))
            duration = float(getattr(item, "duration", 0.0))

        if not text:
            continue

        end = max(start + duration, start + 0.2)
        segments.append({"start": start, "end": end, "text": text})

    return segments


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def extract_captions(
    youtube_url: str,
    video_path: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
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
    _notify(progress_callback, 5, "Checking user-provided captions...")
    logger.info("Trying transcript API manual captions...")
    result = await _get_transcript_api_captions(youtube_url, generated=False)
    if result:
        logger.info("Found transcript API manual captions (%d segments)", len(result))
        _notify(progress_callback, 25, "Using user-provided captions")
        return result
    logger.info("No transcript API manual captions found")

    _notify(progress_callback, 30, "Checking auto-generated captions...")
    logger.info("Trying transcript API auto captions...")
    result = await _get_transcript_api_captions(youtube_url, generated=True)
    if result:
        logger.info("Found transcript API auto captions (%d segments)", len(result))
        _notify(progress_callback, 55, "Using auto-generated captions")
        return result
    logger.info("No transcript API auto captions found")

    _notify(progress_callback, 60, "Fallback: yt-dlp manual captions...")
    result = await _get_manual_captions(youtube_url)
    if result:
        _notify(progress_callback, 75, "Using yt-dlp manual captions")
        return result

    _notify(progress_callback, 80, "Fallback: yt-dlp auto captions...")
    result = await _get_auto_captions(youtube_url)
    if result:
        _notify(progress_callback, 90, "Using yt-dlp auto captions")
        return result

    _notify(progress_callback, 92, "No YouTube captions found. Running Whisper...")
    logger.info("Falling back to Whisper transcription...")
    segments = await _get_whisper_transcript(video_path)
    if segments:
        _notify(progress_callback, 100, "Whisper transcription complete")
    return segments


async def _get_transcript_api_captions(youtube_url: str, generated: bool) -> list[dict]:
    """Fetch captions via YouTube Transcript API (fast path)."""

    def _fetch() -> list[dict]:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
        except Exception:
            logger.info("youtube-transcript-api not installed")
            return []

        video_id = _extract_video_id(youtube_url)
        if not video_id:
            logger.warning("Could not parse YouTube video id from URL: %s", youtube_url)
            return []

        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        except Exception as exc:
            logger.info("Transcript API list failed: %s", exc)
            return []

        language_candidates = ["en", "en-US", "en-GB"]

        try:
            if generated:
                transcript = transcript_list.find_generated_transcript(language_candidates)
            else:
                transcript = transcript_list.find_manually_created_transcript(language_candidates)
            return _normalize_transcript_items(list(transcript.fetch()))
        except Exception:
            pass

        # Fallback: use any transcript matching generated/manual mode.
        try:
            for transcript in transcript_list:
                is_generated = bool(getattr(transcript, "is_generated", False))
                if is_generated == generated:
                    return _normalize_transcript_items(list(transcript.fetch()))
        except Exception:
            return []

        return []

    return await asyncio.to_thread(_fetch)


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
        _resolve_ytdlp_exe(),
        "--no-playlist",
        "--ignore-config",
        "--no-warnings",
        "--write-sub",
        "--skip-download",
        "--js-runtimes", "node",
        "--extractor-args", "youtube:player_client=web,default",
        "--sub-format", "json3",
        "--sub-langs", "en.*,en",
        "--socket-timeout", "30",
        "-o", output_template,
        youtube_url,
    ]

    env = os.environ.copy()
    # Add local bin directory to PATH for bundled ffmpeg
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(backend_dir, "bin")
    env["PATH"] = env.get("PATH", "") + os.pathsep + bin_dir

    try:
        logger.info("Running yt-dlp for manual captions...")
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=60,  # type: ignore
            encoding="utf-8", errors="replace", env=env
        )
        logger.info("yt-dlp manual captions exited with code %d", result.returncode)
        if result.returncode != 0:
            return []
        json_files = glob.glob(os.path.join(work_dir, "*.json3"))
        if not json_files:
            logger.info("No manual caption files found")
            return []
        return _parse_json3(json_files[0])
    except subprocess.TimeoutExpired:
        logger.warning("YouTube manual caption extraction timed out")
        return []
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
        _resolve_ytdlp_exe(),
        "--no-playlist",
        "--ignore-config",
        "--no-warnings",
        "--write-auto-sub",
        "--skip-download",
        "--js-runtimes", "node",
        "--extractor-args", "youtube:player_client=web,default",
        "--sub-format", "json3",
        "--sub-langs", "en.*,en",
        "--socket-timeout", "30",
        "-o", output_template,
        youtube_url,
    ]

    env = os.environ.copy()
    # Add local bin directory to PATH for bundled ffmpeg
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(backend_dir, "bin")
    env["PATH"] = env.get("PATH", "") + os.pathsep + bin_dir

    try:
        logger.info("Running yt-dlp for auto-captions: %s", " ".join(cmd))
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=90,  # type: ignore
            encoding="utf-8", errors="replace", env=env,
        )
        logger.info("yt-dlp auto-captions exited with code %d", result.returncode)
        if result.returncode != 0:
            logger.warning("yt-dlp stderr: %s", result.stderr[:500] if result.stderr else "none")
            return []
        json_files = glob.glob(os.path.join(work_dir, "*.json3"))
        if not json_files:
            logger.warning("No JSON3 subtitle files found in %s", work_dir)
            return []
        return _parse_json3(json_files[0])
    except subprocess.TimeoutExpired:
        logger.warning("YouTube auto caption extraction timed out after 90s")
        return []
    except Exception as exc:
        logger.warning("YouTube auto caption extraction failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# JSON3 parser
# ---------------------------------------------------------------------------

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
