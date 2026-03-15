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
import time
from typing import Callable, Optional

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
    
    # Clean up any leftover temp files from previous failed downloads
    patterns_to_clean = ["*.temp.*", "*.part", "*.f*.mp4", "*.f*.m4a", "*.ytdl"]
    for pattern in patterns_to_clean:
        for f in glob.glob(os.path.join(output_dir, pattern)):
            try:
                os.remove(f)
                logger.debug("Cleaned up: %s", f)
            except:
                pass

    # Output template — save as MP4 with sanitised title
    output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    # Path to ffmpeg (winget install location)
    ffmpeg_dir = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
    )

    cmd = [
        _resolve_ytdlp_exe(),
        "--newline",
        "--js-runtimes", "node",
        "--extractor-args", "youtube:player_client=web,default",
        # Prefer best video+audio up to 1080p, prioritise h264 (avc) codec
        # to avoid AV1/VP9 transcoding which causes Windows file-lock issues
        "-f", "bestvideo[height<=1080][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/137+140/136+140/22/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--no-mtime",
        "--ffmpeg-location", ffmpeg_dir,
        "--retries", "5",
        "--file-access-retries", "10",
        "--restrict-filenames",
        "--force-overwrites",
        "--windows-filenames",
        "-o", output_template,
        "--compat-options", "no-keep-subs,no-live-chat",
        url,
    ]

    logger.info("Running yt-dlp: %s", " ".join(cmd))

    env = os.environ.copy()
    # Add local bin directory to PATH for bundled ffmpeg
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(backend_dir, "bin")
    env["PATH"] = env.get("PATH", "") + os.pathsep + bin_dir
    
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

    # Longer delay to let Windows release file handles after merge
    time.sleep(3)

    if process.returncode != 0:
        # Check if the file was actually created despite the error
        # (common on Windows: merge succeeds but temp file rename fails due to lock)
        # Try waiting a bit more and check for temp files to rename
        for retry in range(3):
            downloaded_files = glob.glob(os.path.join(output_dir, "*.mp4"))
            temp_files = glob.glob(os.path.join(output_dir, "*.temp.mp4"))
            if downloaded_files:
                break
            # Try renaming temp files manually if they exist
            if temp_files:
                for tf in temp_files:
                    final_name = tf.replace(".temp.mp4", ".mp4")
                    try:
                        os.rename(tf, final_name)
                        logger.info("Manually renamed temp file: %s -> %s", tf, final_name)
                    except OSError:
                        pass
                downloaded_files = glob.glob(os.path.join(output_dir, "*.mp4"))
                if downloaded_files:
                    break
            time.sleep(2)

        downloaded_files = glob.glob(os.path.join(output_dir, "*.mp4"))
        if downloaded_files:
            logger.warning("yt-dlp exited with code %d but MP4 file exists, continuing...", process.returncode)
        else:
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
            [_resolve_ytdlp_exe(), "--print", "title", url],
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
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {file_path}: {result.stderr}")

    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
