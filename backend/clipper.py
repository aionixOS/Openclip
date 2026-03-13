"""
clipper.py — Video clipping engine using FFmpeg.

Provides functions to probe video duration, cut individual clips,
and split a full video into equal-length segments.

How it works:
    1. ``get_video_duration`` shells out to ``ffprobe`` and parses the
       JSON output to retrieve the container duration.
    2. ``cut_clip`` runs ``ffmpeg -ss … -i … -t … -c copy …`` which
       uses stream-copy (no re-encoding) for near-instant cuts.
    3. ``generate_clips`` divides the video length by the requested
       segment duration, loops over each segment calling ``cut_clip``,
       and returns a list of clip metadata dicts.
"""

import os
import subprocess
import json
import math
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_video_duration(file_path: str) -> float:
    """
    Get the duration of a video file in seconds using ffprobe.

    Runs ``ffprobe -print_format json -show_format`` and extracts the
    ``duration`` field from the container-level metadata.

    Args:
        file_path: Absolute path to the video file.

    Returns:
        Duration in seconds as a float.

    Raises:
        RuntimeError: If ffprobe fails or cannot parse the duration.
    """
    ffprobe_path = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffprobe.exe"
    )
    cmd = [
        ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        file_path,
    ]

    logger.debug("Running ffprobe: %s", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed (code {result.returncode}): {result.stderr}"
        )

    try:
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise RuntimeError(
            f"Could not parse ffprobe output for {file_path}: {exc}"
        ) from exc

    logger.debug("Detected duration: %.2fs for %s", duration, file_path)
    return duration


# ---------------------------------------------------------------------------
# Core clipping
# ---------------------------------------------------------------------------

def cut_clip(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
) -> str:
    """
    Cut a single clip from a video file using FFmpeg stream-copy.

    Uses ``-c copy`` to avoid re-encoding, making the operation almost
    instant.  The output directory is created automatically if needed.

    Args:
        input_path:  Path to the source video.
        output_path: Path to write the output clip.
        start:       Start time in seconds.
        end:         End time in seconds.

    Returns:
        The ``output_path`` on success.

    Raises:
        RuntimeError: If FFmpeg exits with a non-zero return code.
    """
    duration = end - start
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    ffmpeg_path = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
    )
    cmd = [
        ffmpeg_path,
        "-y",                  # overwrite without asking
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-c", "copy",
        output_path,
    ]

    logger.info("Cutting clip: %.1f–%.1fs → %s", start, end, output_path)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed (code {result.returncode}) cutting "
            f"{start}–{end}s: {result.stderr}"
        )

    return output_path


def generate_clips(
    input_path: str,
    output_dir: str,
    segment_duration: float = 60.0,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> list[dict]:
    """
    Split a video into equal-length segments.

    The total number of clips is ``floor(total_duration / segment_duration)``.
    Each clip is cut with ``cut_clip`` and its metadata is appended to the
    return list.  An optional ``progress_callback`` is called after each
    clip so callers (e.g. WebSocket handlers) can stream progress.

    Args:
        input_path:        Absolute path to the source video.
        output_dir:        Directory where clips will be written.
        segment_duration:  Duration of each clip in seconds (default 60).
        progress_callback: Optional callback invoked with (percentage, message).

    Returns:
        A list of dicts, each with keys:
        - file_path  (str)
        - start_time (float)
        - end_time   (float)
        - duration   (float)

    Raises:
        RuntimeError: On FFmpeg / ffprobe failure.
    """
    os.makedirs(output_dir, exist_ok=True)

    total_duration = get_video_duration(input_path)
    total_clips = math.floor(total_duration / segment_duration)

    # If the video is shorter than one segment, create a single clip
    if total_clips == 0:
        total_clips = 1

    clips: list[dict] = []

    for i in range(total_clips):
        start_time = i * segment_duration
        # For the last clip, take whatever is left
        end_time = min(start_time + segment_duration, total_duration)
        actual_duration = end_time - start_time

        clip_filename = f"clip_{i + 1:03d}.mp4"
        clip_path = os.path.join(output_dir, clip_filename)

        cut_clip(input_path, clip_path, start_time, end_time)

        clips.append({
            "file_path": os.path.abspath(clip_path),
            "start_time": start_time,
            "end_time": end_time,
            "duration": actual_duration,
        })

        logger.info(
            "Generated clip %d/%d: %.1f–%.1fs",
            i + 1, total_clips, start_time, end_time,
        )

        if progress_callback:
            percent = ((i + 1) / total_clips) * 100.0
            progress_callback(
                percent,
                f"Clipping: {i + 1}/{total_clips} done",
            )

    return clips


def generate_clips_from_suggestions(
    video_path: str,
    suggestions: list[dict],
    output_dir: str,
) -> list[dict]:
    """
    Cut clips using LLM-provided timestamp suggestions.

    Each suggestion is expected to have ``start``, ``end``, ``title``,
    and ``reason`` keys.  Clips are cut with ``-c copy`` (stream-copy,
    no re-encoding) for speed.

    Args:
        video_path:  Absolute path to the source video.
        suggestions: List of LLM suggestion dicts.
        output_dir:  Directory where clip files will be written.

    Returns:
        A list of dicts, each with keys:
        ``file_path``, ``start_time``, ``end_time``, ``duration``,
        ``title``, ``reason``.

    Raises:
        RuntimeError: On FFmpeg failure.
    """
    os.makedirs(output_dir, exist_ok=True)
    clips: list[dict] = []

    for i, suggestion in enumerate(suggestions):
        start = float(suggestion["start"])
        end = float(suggestion["end"])
        duration = end - start
        title = suggestion.get("title", "")
        reason = suggestion.get("reason", "")

        clip_filename = f"clip_{i + 1:03d}.mp4"
        clip_path = os.path.join(output_dir, clip_filename)

        cut_clip(video_path, clip_path, start, end)

        clips.append({
            "file_path": os.path.abspath(clip_path),
            "start_time": start,
            "end_time": end,
            "duration": duration,
            "title": title,
            "reason": reason,
        })

        logger.info(
            "Cut suggestion clip %d/%d: %.1f–%.1fs '%s'",
            i + 1, len(suggestions), start, end, title,
        )

    return clips

