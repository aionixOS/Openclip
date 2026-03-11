"""
tracker.py — Face/subject detection using MediaPipe + OpenCV.

Analyses a video to detect and track faces or subjects, returning
bounding-box data that can be consumed by the reframer.
"""

from typing import Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

# Each track entry is a dict with:
#   frame (int), x (float), y (float), w (float), h (float), confidence (float)

TrackEntry = dict
TrackingData = list[TrackEntry]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_subjects(video_path: str) -> TrackingData:
    """
    Detect and track faces/subjects throughout a video.

    Uses MediaPipe Face Detection combined with OpenCV to produce
    per-frame bounding-box data.

    Args:
        video_path: Absolute path to the video file.

    Returns:
        A list of TrackEntry dicts, one per detected subject per frame.

    Note:
        This is a scaffold stub — not yet implemented.
    """
    # TODO: implement — scaffold only
    raise NotImplementedError("detect_subjects is not yet implemented")
