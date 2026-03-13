import subprocess
import json
import os
import math
import sys
import types
from PIL import Image # type: ignore

# mediapipe internally imports cv2 only for its drawing utilities (drawing_styles.py ->
# drawing_utils.py). Our code never calls any drawing functions. We pre-stub cv2 in
# sys.modules so the native OpenCV binary (and its libGL dependency) is never loaded.
if 'cv2' not in sys.modules:
    _cv2_stub = types.ModuleType('cv2')
    sys.modules['cv2'] = _cv2_stub

import mediapipe as mp # type: ignore
from mediapipe.tasks import python # type: ignore
from mediapipe.tasks.python import vision # type: ignore
import io
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)

model_path = os.path.join(os.path.dirname(__file__), 'blaze_face_short_range.tflite')

def _ensure_model_exists():
  if not os.path.exists(model_path):
    import urllib.request
    url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
    urllib.request.urlretrieve(url, model_path)

_ensure_model_exists()
base_options = python.BaseOptions(model_asset_path=model_path)
options = vision.FaceDetectorOptions(base_options=base_options)
face_detector = vision.FaceDetector.create_from_options(options)

async def process_clip(
  video_path: str,
  suggestion: dict[str, Any],
  output_dir: str,
  project_id: str,
  forced_layout_mode: Optional[str] = None
) -> dict[str, Any]:
  """
  Full pipeline for one clip:
  1. Cut raw clip at suggestion timestamps
  2. Sample frames using FFmpeg
  3. Detect faces in sampled frames (with deduplication)
  4. Generate keyframes & apply dynamic face-reactive zoom using sendcmd
  5. Return clip metadata
  """

  raw_clip = os.path.join(
    output_dir,
    f"raw_{project_id}_{suggestion['start']}.mp4"
  )
  await _cut_raw_clip(
    video_path, suggestion['start'],
    suggestion['end'], raw_clip
  )

  width, height = _get_video_dimensions(raw_clip)
  duration = suggestion['end'] - suggestion['start']
  
  frames = _extract_sample_frames(raw_clip)
  face_data = _detect_faces_all_frames(frames, width, height)

  output_clip = os.path.join(
    output_dir,
    f"clip_{project_id}_{suggestion['start']}.mp4"
  )

  success, face_count = await _reframe_dynamic_zoom(raw_clip, output_clip, width, height, face_data, duration)
  if not success:
    await _reframe_static_fallback(raw_clip, output_clip, width, height, face_data)

  if os.path.exists(raw_clip):
    os.remove(raw_clip)

  return {
    "file_path": output_clip,
    "start_time": suggestion['start'],
    "end_time": suggestion['end'],
    "duration": duration,
    "title": suggestion.get('title', ''),
    "reason": suggestion.get('reason', ''),
    "viral_score": suggestion.get('viral_score', 0),
    "face_count": face_count,
    "layout_mode": "dynamic_zoom",
    "needs_user_confirm": False,
    "reframed": True
  }


def _extract_sample_frames(video_path: str) -> list[Image.Image]:
  """
  Extract 1 frame per second as raw bytes using FFmpeg.
  No temp files — pipe directly to memory.
  """
  ffmpeg_path = os.path.expandvars(
      r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
  )
  result = subprocess.run([
    ffmpeg_path, "-i", video_path,
    "-vf", "fps=1",
    "-f", "image2pipe",
    "-vcodec", "mjpeg",
    "pipe:1"
  ], capture_output=True)

  raw = result.stdout
  frames = []
  start = 0
  while True:
    start = raw.find(b'\xff\xd8', start)
    if start == -1:
      break
    end = raw.find(b'\xff\xd9', start)
    if end == -1:
      break
    jpeg_bytes = bytes(raw[start:end + 2])
    try:
      img = Image.open(io.BytesIO(jpeg_bytes))
      frames.append(img)
    except Exception:
      pass
    start = end + 2

  return frames


def _detect_faces_all_frames(
  frames: list[Image.Image],
  vid_width: int,
  vid_height: int
) -> list[list[dict]]:
  """
  Run MediaPipe face detection on each PIL frame.
  Applies deduplication tracking rules.
  """
  import numpy as np # type: ignore

  all_faces = []
  for frame in frames:
    rgb = np.array(frame.convert('RGB'))
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    results = face_detector.detect(mp_image)
    faces = []
    if results.detections:
      for det in results.detections:
        bb = det.bounding_box
        cx = bb.origin_x + bb.width / 2
        cy = bb.origin_y + bb.height / 2
        fw = bb.width
        fh = bb.height
        size = bb.height / vid_height
        
        # Deduplication Rule: Remove size < 0.05
        if size < 0.05:
            continue
            
        faces.append({
          "cx": cx, "cy": cy,
          "w": fw, "h": fh,
          "size": size
        })
    
    # Deduplication Rule: Remove detections within 50px of another
    valid_faces = []
    for f in faces:
        is_dup = False
        for vf in valid_faces:
            if math.hypot(f['cx'] - vf['cx'], f['cy'] - vf['cy']) < 50:
                is_dup = True
                break
        if not is_dup:
            valid_faces.append(f)
            
    all_faces.append(valid_faces)
  return all_faces


def _ease_in_out(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - math.pow(-2 * t + 2, 2) / 2


async def _reframe_dynamic_zoom(
  input_path: str,
  output_path: str,
  vid_width: int,
  vid_height: int,
  face_data: list[list[dict]],
  duration: float
) -> tuple[bool, int]:
    fps = 30
    total_frames = int(duration * fps)
    
    # Majority vote for face count
    face_counts = [len(f) for f in face_data]
    overall_face_count = max(set(face_counts), key=face_counts.count) if face_counts else 0

    # Step 3: Build per-second keyframes list
    sec_targets = []
    total_secs = math.ceil(duration)
    for sec_data in face_data:
        if sec_data:
            # Pick the largest face to track
            face = max(sec_data, key=lambda f: f['size'])
            size = face['size']
            if size < 0.10: zoom_target = 2.8
            elif size < 0.20: zoom_target = 2.2
            elif size < 0.35: zoom_target = 1.7
            else: zoom_target = 1.3
            sec_targets.append({
                "has_face": True, 
                "zoom": zoom_target,
                "cx": face['cx'],
                "cy": face['cy']
            })
        else:
            sec_targets.append({
                "has_face": False,
                "zoom": 1.0,
                "cx": vid_width / 2.0,
                "cy": vid_height / 2.0
            })
    
    # Pad sec_targets to fill entire duration if frames were missed
    while len(sec_targets) < total_secs:
        sec_targets.append(sec_targets[-1] if sec_targets else {"has_face": False, "zoom": 1.0, "cx": vid_width / 2.0, "cy": vid_height / 2.0})

    frame_crops = []
    last_face_zoom = 1.0
    last_face_cx = vid_width / 2.0
    last_face_cy = vid_height / 2.0
    
    frames_since_face_lost = 0
    ZOOM_OUT_HOLD = 8
    ZOOM_OUT_DUR = 45

    # Step 4 & 5: Interpolate keyframes and convert to crop parameters
    for f_idx in range(total_frames):
        sec = min(int(f_idx / fps), total_secs - 1)
        target = sec_targets[sec]
        
        current_zoom = 1.0
        current_cx = vid_width / 2.0
        current_cy = vid_height / 2.0
        
        if target["has_face"]:
            frames_since_face_lost = 0
            current_zoom = target["zoom"]
            current_cx = target["cx"]
            current_cy = target["cy"]
            
            # Save for zoom out
            last_face_zoom = current_zoom
            last_face_cx = current_cx
            last_face_cy = current_cy
        else:
            frames_since_face_lost += 1
            if frames_since_face_lost > ZOOM_OUT_HOLD:
                progress = min(1.0, (frames_since_face_lost - ZOOM_OUT_HOLD) / float(ZOOM_OUT_DUR))
                eased = _ease_in_out(progress)
                current_zoom = last_face_zoom + (1.0 - last_face_zoom) * eased
                current_cx = last_face_cx + (vid_width / 2.0 - last_face_cx) * eased
                current_cy = last_face_cy + (vid_height / 2.0 - last_face_cy) * eased
            else:
                # Hold before zooming out
                current_zoom = last_face_zoom
                current_cx = last_face_cx
                current_cy = last_face_cy

        crop_h = float(vid_height) / current_zoom
        crop_w = crop_h * 9.0 / 16.0
        
        # Ensure we don't request a width larger than the original video horizontally
        if crop_w > vid_width:
            crop_w = vid_width
            crop_h = crop_w * 16.0 / 9.0
            if crop_h > vid_height:
                crop_h = vid_height
                crop_w = crop_h * 9.0 / 16.0

        crop_x = current_cx - crop_w / 2.0
        crop_y = current_cy - crop_h / 2.0
        
        crop_x = max(0.0, min(crop_x, float(vid_width) - crop_w))
        crop_y = max(0.0, min(crop_y, float(vid_height) - crop_h))

        frame_crops.append({
            "ts": f_idx / float(fps),
            "w": int(crop_w), "h": int(crop_h),
            "x": int(crop_x), "y": int(crop_y)
        })

    # Step 6: Write sendcmd file
    cmd_file = input_path + ".sendcmd"
    lines = []
    for c in frame_crops:
        ts_str = f"{c['ts']:.3f}"
        lines.append(f"{ts_str} crop w {c['w']}, crop h {c['h']}, crop x {c['x']}, crop y {c['y']};")

    with open(cmd_file, 'w') as f:
        f.write('\n'.join(lines))
        
    filter_cmd_file = cmd_file.replace('\\', '/')

    # Step 7: Apply sendcmd with FFmpeg padding output logic to 1080x1920
    filter_cx = (
      f"sendcmd=f='{filter_cmd_file}',"
      f"crop={int(vid_height*9/16)}:{vid_height}:0:0,"
      f"scale=1080:1920:force_original_aspect_ratio=decrease,"
      f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    )

    ffmpeg_path = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
    )
    cmd = [
      ffmpeg_path,
      "-i", input_path,
      "-vf", filter_cx,
      "-c:a", "copy",
      output_path, "-y"
    ]
    
    result = subprocess.run(cmd, capture_output=True)
    
    if os.path.exists(cmd_file):
        os.remove(cmd_file)

    if result.returncode != 0:
        logger.error(f"FFmpeg dynamic sendcmd reframe failed: {result.stderr.decode()}")
        return False, overall_face_count
        
    return True, overall_face_count


async def _reframe_static_fallback(
  input_path: str,
  output_path: str,
  vid_width: int,
  vid_height: int,
  face_data: list[list[dict]]
) -> None:
  """
  Fallback static crop in case dynamic sendcmd fails.
  """
  all_faces = [f for sec_data in face_data for f in sec_data]
  
  if not all_faces:
      avg_cx = vid_width / 2.0
  else:
      avg_cx = sum(f['cx'] for f in all_faces) / len(all_faces)
      
  crop_h = vid_height
  crop_w = crop_h * 9.0 / 16.0
  
  if crop_w > vid_width:
      crop_w = vid_width
      crop_h = crop_w * 16.0 / 9.0

  crop_x = avg_cx - crop_w / 2.0
  crop_x = max(0.0, min(crop_x, float(vid_width) - crop_w))
  crop_y = (vid_height - crop_h) / 2.0

  filter_cx = (
      f"crop={int(crop_w)}:{int(crop_h)}:{int(crop_x)}:{int(crop_y)},"
      f"scale=1080:1920:force_original_aspect_ratio=decrease,"
      f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
  )

  ffmpeg_path = os.path.expandvars(
      r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
  )
  cmd = [
    ffmpeg_path, "-i", input_path,
    "-vf", filter_cx,
    "-c:a", "copy", output_path, "-y"
  ]
  result = subprocess.run(cmd, capture_output=True)
  if result.returncode != 0:
    raise RuntimeError(
      f"FFmpeg static fallback reframe failed: {result.stderr.decode()}"
    )


def _get_video_dimensions(video_path: str) -> tuple[int, int]:
  """
  Use ffprobe to get width and height.
  """
  ffprobe_path = os.path.expandvars(
      r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffprobe.exe"
  )
  cmd = [
      ffprobe_path, 
      "-v", "error", "-select_streams", "v:0", 
      "-show_entries", "stream=width,height", "-of", "json", video_path
  ]
  result = subprocess.run(cmd, capture_output=True, text=True)
  if result.returncode != 0:
      raise RuntimeError(f"FFprobe failed: {result.stderr}")
  data = json.loads(result.stdout)
  stream = data["streams"][0]
  return stream["width"], stream["height"]

async def _cut_raw_clip(
  video_path: str,
  start: float,
  end: float,
  output_path: str
) -> None:
  """
  ffmpeg -ss {start} -i {video_path} ...
  """
  duration = end - start
  ffmpeg_path = os.path.expandvars(
      r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
  )
  cmd = [
      ffmpeg_path, "-y", "-ss", str(start), "-i", video_path,
      "-t", str(duration), "-c", "copy", output_path
  ]
  result = subprocess.run(cmd, capture_output=True, text=True)
  if result.returncode != 0:
      raise RuntimeError(f"FFmpeg failed cutting raw clip: {result.stderr}")
