"""
downloader.py — YouTube video downloader using yt-dlp.

Handles downloading a video from a YouTube URL to a local directory,
with real-time progress parsing and callbacks.

How it works:
    1. Spawns ``yt-dlp`` as a subprocess with ``--newline`` so each
       progress tick prints on its own line.
    2. Reads stdout line-by-line and applies a regex to extract the
       download percentage, feeding it to the caller's progress_callback.
    3. After a successful download it runs ``yt-dlp --print title`` to
       obtain the video title and ``ffprobe`` to obtain the duration.
    4. Returns a dict with ``file_path``, ``title``, and
       ``duration_seconds``.
"""

import os
import subprocess
import re
import json
import glob
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def download_video(
    url: str,
    output_dir: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> dict:
    """
    Download a YouTube video using yt-dlp.

    Args:
        url:               The YouTube video URL.
        output_dir:        Directory to save the downloaded video.
        progress_callback: Optional callback invoked with (percentage, message)
                           during the download for real-time progress updates.

    Returns:
        A dict with keys:
          - file_path (str): absolute path to the downloaded file
          - title (str): video title
          - duration_seconds (float): video duration in seconds

    Raises:
        RuntimeError: If yt-dlp or ffprobe exits with a non-zero return code,
                      or if the download produces no output file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Output template — save as MP4 with sanitised title
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    cmd = [
        r"C:\Users\Prajjwal\Downloads\Openclip\backend\.venv\Scripts\yt-dlp.exe",
        "--newline",
        "--js-runtimes", "node",
        "--extractor-args", "youtube:player_client=web,default",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
        "--merge-output-format", "mp4",
        "--no-part",
        "-o", output_template,
        "--compat-options", "no-keep-subs,no-live-chat",
        url,
    ]

    logger.info("Running yt-dlp: %s", " ".join(cmd))

    env = os.environ.copy()
    # Ensure standard Windows paths are present
    env["PATH"] = env.get("PATH", "") + r";C:\Program Files\nodejs;C:\Users\Prajjwal\Downloads\Openclip\backend\bin"
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    # Regex to match lines like:  [download]  45.2% of ~50.00MiB …
    progress_re = re.compile(r"\[download\]\s+([\d.]+)%")

    stdout = process.stdout
    output_lines = []
    if stdout is not None:
        for line in stdout:
            output_lines.append(line)
            line = line.strip()
            if not line:
                continue

            logger.debug("yt-dlp: %s", line)

            match = progress_re.search(line)
            if match:
                percent = float(match.group(1))
                cb = progress_callback
                if cb is not None:
                    cb(percent, f"Downloading: {percent:.1f}%")

    process.wait()

    if process.returncode != 0:
        with open("ytdlp_error.txt", "w") as f:
            f.writelines(output_lines)
        raise RuntimeError(
            f"yt-dlp exited with code {process.returncode} for URL: {url}"
        )

    # Locate the downloaded file
    downloaded_files = glob.glob(os.path.join(output_dir, "*.mp4"))
    if not downloaded_files:
        raise RuntimeError("yt-dlp completed but no MP4 file was produced")

    # Pick the most recently modified file (in case of prior downloads)
    file_path = max(downloaded_files, key=os.path.getmtime)
    file_path = os.path.abspath(file_path)

    # Fetch the video title
    title = _get_video_title(url) or os.path.splitext(os.path.basename(file_path))[0]

    # Fetch the duration via ffprobe
    duration = _get_duration(file_path)

    logger.info("Download complete: %s (%.1fs)", file_path, duration)

    if progress_callback is not None:
        progress_callback(100.0, "Download complete")

    return {
        "file_path": file_path,
        "title": title,
        "duration_seconds": duration,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_video_title(url: str) -> Optional[str]:
    """
    Fetch the title of a YouTube video without downloading it.

    Uses ``yt-dlp --print title`` which is very fast and does not
    download any media data.

    Args:
        url: The YouTube video URL.

    Returns:
        The video title as a string, or None on failure.
    """
    try:
        result = subprocess.run(
            [r"C:\Users\Prajjwal\Downloads\Openclip\backend\.venv\Scripts\yt-dlp.exe", "--print", "title", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except Exception:
        logger.warning("Failed to fetch video title for %s", url)
        return None


def _get_duration(file_path: str) -> float:
    """
    Get the duration of a media file in seconds via ffprobe.

    Args:
        file_path: Absolute path to the video file.

    Returns:
        Duration in seconds as a float.

    Raises:
        RuntimeError: If ffprobe fails.
    """
    cmd = [
        r"C:\Users\Prajjwal\Downloads\Openclip\backend\bin\ffprobe.exe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        file_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {file_path}: {result.stderr}")

    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
