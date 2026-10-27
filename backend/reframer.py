import subprocess
import json
import os
import ffmpeg_utils
import math
import sys
import types
from PIL import Image # type: ignore
import numpy as np # type: ignore

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
options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.18)
face_detector = vision.FaceDetector.create_from_options(options)

async def process_clip(
  video_path: str,
  suggestion: dict[str, Any],
  output_dir: str,
  project_id: str,
  forced_layout_mode: Optional[str] = None,
  transcript_segments: Optional[list[dict]] = None
) -> dict[str, Any]:
  """
  Full Smart Director 2.0 pipeline for one clip:
  1. Cut raw clip at suggestion timestamps
  2. Sample frames using FFmpeg
  3. Extract speech onsets and viral climax timestamps
  4. Detect faces with gaze lead-room & biometric color signatures
  5. Apply dynamic audio-synced multicam cuts and kinetic zoom
  6. Return clip metadata
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
  
  # Extract sub-second speech onsets & emotional climax timestamp from Whisper
  clip_start = suggestion['start']
  clip_end = suggestion['end']
  speech_onsets = []
  climax_ts = None

  if transcript_segments:
      clip_segs = [s for s in transcript_segments if s.get('end', 0) >= clip_start and s.get('start', 0) <= clip_end]
      for s in clip_segs:
          rel_start = max(0.0, min(duration, s.get('start', clip_start) - clip_start))
          speech_onsets.append(rel_start)
          text = s.get('text', '')
          if climax_ts is None and ('!' in text or any(k in text.lower() for k in ['gila', 'kaget', 'rahasia', 'shock', 'wow', 'gokil', 'parah', 'kacau', 'ternyata', 'never'])):
              climax_ts = rel_start

  frames = _extract_sample_frames(raw_clip)
  face_data = _detect_faces_all_frames(frames, width, height)

  output_clip = os.path.join(
    output_dir,
    f"clip_{project_id}_{suggestion['start']}.mp4"
  )

  success, face_count = await _reframe_dynamic_zoom(
      raw_clip, output_clip, width, height, face_data, duration,
      frames=frames, speech_onsets=speech_onsets, climax_ts=climax_ts
  )
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
  ffmpeg_path = ffmpeg_utils.get_ffmpeg_exe()
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
  Applies strict anatomical & spatial filtering to reject hands, microphones,
  clothing patterns, and stray false positives.
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
        score = det.categories[0].score if det.categories else 0
        bb = det.bounding_box
        cx = bb.origin_x + bb.width / 2.0
        cy = bb.origin_y + bb.height / 2.0
        fw = bb.width
        fh = bb.height
        size = fh / vid_height
        
        # 1. Size Filter: Ignore tiny noise or background specks
        if size < 0.05 or fw / vid_width < 0.035:
            continue
            
        # 2. Aspect Ratio: Human face bounding boxes have ratio 0.50 - 1.40
        # Hands, arms, or fingers frequently form extreme ratios (<0.45 or >1.50)
        ar = fw / max(fh, 1.0)
        if ar < 0.50 or ar > 1.40:
            continue

        # 3. Hand / Lap Zone Filter: In horizontal video, faces sit in upper/mid area.
        # Bottom 24% of frame is the desk/lap/keyboard area where gesturing hands rest.
        if cy > vid_height * 0.76:
            continue

        # 4. Anatomical Keypoints Check: Validate facial geometry & compute Gaze Yaw
        yaw_bias = 0.0
        if det.keypoints and len(det.keypoints) >= 4:
            re = det.keypoints[0]
            le = det.keypoints[1]
            nose = det.keypoints[2]
            mouth = det.keypoints[3]
            eye_y = (re.y + le.y) / 2.0 * vid_height
            mouth_y = mouth.y * vid_height
            eye_dist = math.hypot((re.x - le.x) * vid_width, (re.y - le.y) * vid_height)

            # Eyes must be strictly above mouth in upright footage (rejects knuckles/hands)
            if eye_y >= mouth_y - (fh * 0.04):
                continue

            # Eyes must have plausible spacing (preserves profiles, rejects collapsed points)
            if eye_dist < fw * 0.05 or eye_dist > fw * 0.95:
                continue

            # Cinematographic Gaze Vector (Lead-Room)
            d_left = abs(nose.x - le.x) * vid_width
            d_right = abs(nose.x - re.x) * vid_width
            yaw_bias = float((d_right - d_left) / (d_left + d_right + 1e-5))

        # 5. Confidence Threshold
        if score < 0.28:
            continue

        # 6. Biometric Torso/Shirt Color Signature (for 100% Anti-Hand verification)
        torso_rgb = None
        try:
            tx1 = int(max(0, cx - fw * 0.25))
            tx2 = int(min(vid_width, cx + fw * 0.25))
            ty1 = int(min(vid_height - 1, cy + fh * 0.65))
            ty2 = int(min(vid_height, cy + fh * 1.25))
            if tx2 > tx1 and ty2 > ty1:
                torso_crop = rgb[ty1:ty2, tx1:tx2]
                torso_rgb = np.mean(torso_crop, axis=(0, 1)).tolist()
        except Exception:
            pass

        faces.append({
          "cx": cx, "cy": cy,
          "w": fw, "h": fh,
          "size": size,
          "score": score,
          "yaw_bias": max(-1.0, min(1.0, yaw_bias)),
          "torso_rgb": torso_rgb
        })
    
    # Deduplication Rule: Remove detections within 50px of each other
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



def _extract_mouth_roi(frame: Image.Image, face: dict) -> Optional[np.ndarray]:
    """Extract and normalize mouth region of interest for speech motion detection."""
    cx, cy = face['cx'], face['cy']
    fw, fh = face['w'], face['h']
    x1 = int(max(0, cx - fw * 0.28))
    x2 = int(min(frame.width, cx + fw * 0.28))
    y1 = int(max(0, cy + fh * 0.12))
    y2 = int(min(frame.height, cy + fh * 0.44))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = frame.crop((x1, y1, x2, y2)).convert('L').resize((32, 32))
    return np.array(crop, dtype=np.float32)

def _compute_mouth_diff(roi1: Optional[np.ndarray], roi2: Optional[np.ndarray]) -> float:
    """Compute frame-to-frame mouth movement difference."""
    if roi1 is None or roi2 is None:
        return 0.0
    return float(np.mean(np.abs(roi1 - roi2)))

def _ease_in_out(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - math.pow(-2 * t + 2, 2) / 2


def _is_scene_cut(img1: Image.Image, img2: Image.Image) -> bool:
    """Detect visual shot cut/scene change using fast luminance difference."""
    try:
        arr1 = np.array(img1.convert("L").resize((64, 36)), dtype=np.float32)
        arr2 = np.array(img2.convert("L").resize((64, 36)), dtype=np.float32)
        return float(np.mean(np.abs(arr1 - arr2))) > 34.0
    except Exception:
        return False


def _cluster_speaker_anchors(face_data: list[list[dict]], min_count: int = 2) -> list[dict]:
    """Find persistent horizontal speaker anchor positions and median torso colors across the video."""
    all_faces = [f for sec in face_data for f in sec if f.get("cx") is not None]
    if not all_faces:
        return []
    clusters: list[list[dict]] = []
    for f in sorted(all_faces, key=lambda x: x["cx"]):
        matched = False
        for c in clusters:
            cxs = [cf["cx"] for cf in c]
            if abs(float(np.mean(cxs)) - f["cx"]) < 180:
                c.append(f)
                matched = True
                break
        if not matched:
            clusters.append([f])

    anchors = []
    for c in clusters:
        if len(c) >= min_count:
            cxs = [cf["cx"] for cf in c]
            colors = [cf["torso_rgb"] for cf in c if cf.get("torso_rgb") is not None]
            median_color = np.median(colors, axis=0).tolist() if colors else None
            anchors.append({
                "cx": float(np.mean(cxs)),
                "torso_rgb": median_color,
                "count": len(c)
            })
    return sorted(anchors, key=lambda a: a["cx"])


async def _reframe_dynamic_zoom(
  input_path: str,
  output_path: str,
  vid_width: int,
  vid_height: int,
  face_data: list[list[dict]],
  duration: float,
  frames: Optional[list[Image.Image]] = None,
  speech_onsets: Optional[list[float]] = None,
  climax_ts: Optional[float] = None
) -> tuple[bool, int]:
    fps = 30
    total_frames = int(duration * fps)
    total_secs = math.ceil(duration)

    # 1. Majority vote for overall face count
    face_counts = [len(f) for f in face_data]
    overall_face_count = max(set(face_counts), key=face_counts.count) if face_counts else 0

    # 2. Scene cut detection across sampled frames
    scene_cuts = [False] * total_secs
    if frames and len(frames) > 1:
        for s in range(1, min(len(frames), total_secs)):
            if _is_scene_cut(frames[s - 1], frames[s]):
                scene_cuts[s] = True

    # 3. Speaker anchors & transient false-positive rejection
    speaker_anchors = _cluster_speaker_anchors(face_data, min_count=2)
    cleaned_face_data = []
    for sec_faces in face_data:
        if not speaker_anchors or len(sec_faces) <= 1:
            cleaned_face_data.append(sec_faces)
        else:
            # If multiple detections, filter out any stray detection far from all known anchors or with mismatched torso color
            v_faces = []
            for f in sec_faces:
                matched_anchor = None
                for anchor in speaker_anchors:
                    if abs(f["cx"] - anchor["cx"]) < 220:
                        matched_anchor = anchor
                        break
                
                if matched_anchor:
                    f_rgb = f.get("torso_rgb")
                    a_rgb = matched_anchor.get("torso_rgb")
                    if f_rgb is not None and a_rgb is not None:
                        color_diff = math.sqrt(sum((a - b) ** 2 for a, b in zip(f_rgb, a_rgb)))
                        if color_diff > 95.0 and f.get("score", 1.0) < 0.60:
                            continue
                    v_faces.append(f)
                elif f.get("score", 1.0) >= 0.58:
                    v_faces.append(f)
            cleaned_face_data.append(v_faces if v_faces else sec_faces)

    # 4. Adaptive Base Zoom
    all_sizes = [f['size'] for sec in cleaned_face_data for f in sec if f.get('size')]
    if all_sizes:
        all_sizes.sort()
        median_size = all_sizes[len(all_sizes) // 2]
        base_zoom = max(1.20, min(0.24 / max(median_size, 0.08), 1.70))
    else:
        median_size = 0.25
        base_zoom = 1.35

    anchor_positions = [round(a["cx"], 1) for a in speaker_anchors]
    logger.info(f"[Director] Dynamic Decision Engine: base_zoom={base_zoom:.2f}, anchors={anchor_positions}")

    # 5. Build per-second targets with Dynamic Active Speaker Tracking & Pacing
    sec_targets = []
    last_known_cx = vid_width / 2.0
    last_known_cy = vid_height / 2.0
    active_speaker_history = []
    crop_w_nominal = (float(vid_height) / base_zoom) * 9.0 / 16.0

    for s in range(len(cleaned_face_data)):
        sec_faces = cleaned_face_data[s]

        if not sec_faces:
            # Hold last known framing position
            sec_targets.append({
                "has_face": False,
                "cx": last_known_cx,
                "cy": last_known_cy,
                "zoom": base_zoom,
                "yaw_bias": 0.0,
                "is_cut": scene_cuts[s] if s < len(scene_cuts) else False,
                "mode": "hold"
            })
            continue

        if len(sec_faces) == 1:
            f = sec_faces[0]
            last_known_cx = f['cx']
            last_known_cy = f['cy']
            active_speaker_history.append("single")
            sec_targets.append({
                "has_face": True,
                "cx": f['cx'],
                "cy": f['cy'],
                "zoom": base_zoom,
                "yaw_bias": f.get('yaw_bias', 0.0),
                "is_cut": scene_cuts[s] if s < len(scene_cuts) else False,
                "mode": "single"
            })
        else:
            sorted_faces = sorted(sec_faces, key=lambda x: x['cx'])
            f1, f2 = sorted_faces[0], sorted_faces[-1]
            face_dist = abs(f1['cx'] - f2['cx'])

            # If both fit in standard vertical framing:
            if face_dist < (crop_w_nominal * 0.72):
                c_x = (f1['cx'] + f2['cx']) / 2.0
                c_y = (f1['cy'] + f2['cy']) / 2.0
                last_known_cx = c_x
                last_known_cy = c_y
                active_speaker_history.append("two_shot")
                sec_targets.append({
                    "has_face": True,
                    "cx": c_x,
                    "cy": c_y,
                    "zoom": max(1.15, min(base_zoom, 1.30)),
                    "yaw_bias": 0.0,
                    "is_cut": scene_cuts[s] if s < len(scene_cuts) else False,
                    "mode": "two_shot"
                })
            else:
                # Two separated speakers (e.g. Left vs Right podcast setup)
                # Compute lip movement
                m1_diff, m2_diff = 0.0, 0.0
                if frames and s > 0 and s < len(frames):
                    prev_f = frames[s - 1]
                    curr_f = frames[s]
                    r1_prev = _extract_mouth_roi(prev_f, f1)
                    r1_curr = _extract_mouth_roi(curr_f, f1)
                    r2_prev = _extract_mouth_roi(prev_f, f2)
                    r2_curr = _extract_mouth_roi(curr_f, f2)
                    m1_diff = _compute_mouth_diff(r1_prev, r1_curr)
                    m2_diff = _compute_mouth_diff(r2_prev, r2_curr)

                if m2_diff > m1_diff * 1.30 and m2_diff > 5.5:
                    speaker = "right"
                    dominant_face = f2
                elif m1_diff > m2_diff * 1.30 and m1_diff > 5.5:
                    speaker = "left"
                    dominant_face = f1
                else:
                    speaker = "hold"
                    dominant_face = min(sorted_faces, key=lambda f: abs(f['cx'] - last_known_cx))

                # Conversational Velocity Index:
                # Count speaker changes in rolling 8-second window
                recent_history = active_speaker_history[-8:] if len(active_speaker_history) >= 2 else []
                switches = sum(
                    1 for i in range(1, len(recent_history))
                    if recent_history[i] != recent_history[i-1] and "two_shot" not in str(recent_history[i]) and "hold" not in str(recent_history[i])
                )

                is_rapid_banter = (switches >= 3) or (
                    len(recent_history) >= 2 and 
                    recent_history[-2] != recent_history[-1] and 
                    speaker != "hold" and 
                    speaker != recent_history[-1]
                )

                if is_rapid_banter:
                    # Dynamic Two-Shot during quick back-and-forth banter!
                    c_x = (f1['cx'] + f2['cx']) / 2.0
                    c_y = (f1['cy'] + f2['cy']) / 2.0
                    last_known_cx = c_x
                    last_known_cy = c_y
                    active_speaker_history.append("banter_two_shot")
                    sec_targets.append({
                        "has_face": True,
                        "cx": c_x,
                        "cy": c_y,
                        "zoom": max(1.12, min(base_zoom * 0.88, 1.25)),
                        "yaw_bias": 0.0,
                        "is_cut": scene_cuts[s] if s < len(scene_cuts) else False,
                        "mode": "banter_two_shot"
                    })
                else:
                    last_known_cx = dominant_face['cx']
                    last_known_cy = dominant_face['cy']
                    active_speaker_history.append(speaker)
                    sec_targets.append({
                        "has_face": True,
                        "cx": dominant_face['cx'],
                        "cy": dominant_face['cy'],
                        "zoom": base_zoom,
                        "yaw_bias": dominant_face.get('yaw_bias', 0.0),
                        "is_cut": scene_cuts[s] if s < len(scene_cuts) else False,
                        "mode": "speaker"
                    })

    while len(sec_targets) < total_secs:
        sec_targets.append(sec_targets[-1] if sec_targets else {
            "has_face": False, "cx": last_known_cx, "cy": last_known_cy, "zoom": base_zoom, "yaw_bias": 0.0, "is_cut": False, "mode": "hold"
        })

    # 6. Autonomous Dynamic Framing Engine (Sub-second Audio Snapped Cuts vs Organic Follow)
    DEADBAND_X = 40.0       # Stable tolerance zone (px) - locks on natural gestures
    DEADBAND_Y = 30.0
    ALPHA_POS = 0.12        # Snappy responsive follow for same speaker
    ALPHA_ZOOM = 0.04       # Smooth zoom transition
    MAX_PAN_SPEED = 22.0    # Responsive pan speed limit (px/frame)
    SNAP_CUT_DIST = 210.0   # Distance threshold (px) to trigger an instant multicam cut instead of slow pan

    # Pre-calculate audio-synced cut trigger frames
    cut_trigger_frames = set()
    for s in range(1, total_secs):
        prev_st = sec_targets[s - 1]
        curr_st = sec_targets[s]
        is_scene_cut = curr_st.get("is_cut", False)
        dist_to_prev = abs(curr_st["cx"] - prev_st["cx"])
        is_speaker_switch = (dist_to_prev > SNAP_CUT_DIST)

        if is_scene_cut or is_speaker_switch:
            nominal_sec = float(s)
            snapped_frame = int(round(nominal_sec * fps))

            # Snap to Whisper speech onset within +/- 0.55s
            if speech_onsets:
                valid_onsets = [t for t in speech_onsets if abs(t - nominal_sec) <= 0.55]
                if valid_onsets:
                    closest_onset = min(valid_onsets, key=lambda t: abs(t - nominal_sec))
                    snapped_frame = int(round(closest_onset * fps))

            snapped_frame = max(0, min(snapped_frame, total_frames - 1))
            cut_trigger_frames.add(snapped_frame)

    curr_cx = sec_targets[0]["cx"] if sec_targets[0]["has_face"] else vid_width / 2.0
    curr_cy = sec_targets[0]["cy"] if sec_targets[0]["has_face"] else vid_height / 2.0
    curr_zoom = base_zoom if sec_targets[0]["has_face"] else 1.0
    curr_yaw = sec_targets[0].get("yaw_bias", 0.0)

    target_cx = curr_cx
    target_cy = curr_cy
    target_zoom = curr_zoom
    target_yaw = curr_yaw

    monologue_frames = 0
    frame_crops = []

    for f_idx in range(total_frames):
        sec = min(int(f_idx / fps), total_secs - 1)
        st = sec_targets[sec]

        if st["has_face"]:
            raw_target_x = st["cx"]
            raw_target_y = st["cy"]
            raw_target_zoom = st["zoom"]
            raw_target_yaw = st.get("yaw_bias", 0.0)
        else:
            raw_target_x = last_known_cx
            raw_target_y = last_known_cy
            raw_target_zoom = base_zoom
            raw_target_yaw = 0.0

        is_cut_frame = (f_idx in cut_trigger_frames)

        if is_cut_frame:
            # DIRECT MULTICAM CUT: Instant snap on speech onset or scene cut!
            curr_cx = raw_target_x
            curr_cy = raw_target_y
            curr_zoom = raw_target_zoom
            curr_yaw = raw_target_yaw
            target_cx = raw_target_x
            target_cy = raw_target_y
            target_zoom = raw_target_zoom
            target_yaw = raw_target_yaw
            monologue_frames = 0
        else:
            monologue_frames += 1
            dx = abs(raw_target_x - target_cx)
            dy = abs(raw_target_y - target_cy)
            if dx > DEADBAND_X:
                target_cx = raw_target_x
            if dy > DEADBAND_Y:
                target_cy = raw_target_y
            target_zoom = raw_target_zoom
            target_yaw = raw_target_yaw

            step_x = (target_cx - curr_cx) * ALPHA_POS
            step_x = max(-MAX_PAN_SPEED, min(step_x, MAX_PAN_SPEED))
            curr_cx += step_x

            step_y = (target_cy - curr_cy) * ALPHA_POS
            step_y = max(-MAX_PAN_SPEED, min(step_y, MAX_PAN_SPEED))
            curr_cy += step_y

            curr_zoom += (target_zoom - curr_zoom) * ALPHA_ZOOM
            curr_yaw += (target_yaw - curr_yaw) * 0.08

        # Kinetic Zoom Suite: Hook Zoom + Climax Punch + Subconscious Monologue Dolly-in
        # 1. Dynamic Hook Punch (First 2.5s)
        hook_frames = int(2.5 * fps)
        if f_idx < hook_frames:
            hook_progress = float(f_idx) / float(hook_frames)
            hook_boost = 0.10 * (1.0 - _ease_in_out(hook_progress))
        else:
            hook_boost = 0.0

        # 2. Climax Punch (+12% punch-in at emotional exclamation timestamps)
        climax_boost = 0.0
        if climax_ts is not None:
            climax_frame = int(climax_ts * fps)
            df = f_idx - climax_frame
            if -int(0.2 * fps) <= df <= int(1.6 * fps):
                if df < 0:
                    climax_prog = (df + int(0.2 * fps)) / (0.2 * fps)
                    climax_boost = 0.12 * climax_prog
                else:
                    climax_prog = df / (1.6 * fps)
                    climax_boost = 0.12 * (1.0 - _ease_in_out(climax_prog))

        # 3. Subconscious Monologue Dolly-in (+3.5% over 8s of uninterrupted speech)
        dolly_boost = 0.0
        if monologue_frames > int(3.5 * fps):
            dolly_prog = min(1.0, (monologue_frames - int(3.5 * fps)) / float(8.0 * fps))
            dolly_boost = 0.035 * _ease_in_out(dolly_prog)

        effective_zoom = curr_zoom * (1.0 + hook_boost + climax_boost + dolly_boost)

        # Calculate 9:16 vertical crop
        crop_h = float(vid_height) / effective_zoom
        crop_w = crop_h * 9.0 / 16.0

        if crop_w > vid_width:
            crop_w = float(vid_width)
            crop_h = crop_w * 16.0 / 9.0
            if crop_h > vid_height:
                crop_h = float(vid_height)
                crop_w = crop_h * 9.0 / 16.0

        # Cinematographic Lead-Room offset:
        # Looking right (yaw_bias > 0) -> shift crop right so subject is placed on the left third with room in front
        lead_room_px = curr_yaw * (crop_w * 0.075)
        effective_cx = curr_cx + lead_room_px

        crop_x = effective_cx - crop_w / 2.0
        crop_x = max(0.0, min(crop_x, float(vid_width) - crop_w))

        # Golden Ratio Eye-Level composition (38% from top)
        crop_y = curr_cy - crop_h * 0.38
        crop_y = max(0.0, min(crop_y, float(vid_height) - crop_h))

        frame_crops.append({
            "ts": f_idx / float(fps),
            "w": int(crop_w), "h": int(crop_h),
            "x": int(crop_x), "y": int(crop_y)
        })

    # 7. Write sendcmd commands
    cmd_file = input_path + ".sendcmd"
    lines = []
    for c in frame_crops:
        ts_str = f"{c['ts']:.3f}"
        lines.append(f"{ts_str} crop w {c['w']}, crop h {c['h']}, crop x {c['x']}, crop y {c['y']};")

    with open(cmd_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    filter_cmd_file = cmd_file.replace('\\', '/').replace(':', '\\:')

    # 8. Apply sendcmd with FFmpeg scaling to 1080x1920
    filter_cx = (
      f"sendcmd=f='{filter_cmd_file}',"
      f"crop={int(vid_height*9/16)}:{vid_height}:0:0,"
      f"scale=1080:1920:force_original_aspect_ratio=decrease,"
      f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    )

    ffmpeg_path = ffmpeg_utils.get_ffmpeg_exe()
    cmd = [
      ffmpeg_path,
      "-i", input_path,
      "-vf", filter_cx,
      "-c:v", "libx264",
      "-preset", "veryfast",
      "-crf", "22",
      "-c:a", "copy",
      "-movflags", "+faststart",
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
  Fallback static crop with cinematic eye-level composition.
  """
  all_faces = [f for sec_data in face_data for f in sec_data]

  if not all_faces:
      avg_cx = vid_width / 2.0
      avg_cy = vid_height / 2.0
  else:
      avg_cx = sum(f['cx'] for f in all_faces) / len(all_faces)
      avg_cy = sum(f['cy'] for f in all_faces) / len(all_faces)

  crop_h = float(vid_height)
  crop_w = crop_h * 9.0 / 16.0

  if crop_w > vid_width:
      crop_w = float(vid_width)
      crop_h = crop_w * 16.0 / 9.0

  crop_x = avg_cx - crop_w / 2.0
  crop_x = max(0.0, min(crop_x, float(vid_width) - crop_w))

  # Cinematic Eye-Level vertical framing
  crop_y = avg_cy - crop_h * 0.38
  crop_y = max(0.0, min(crop_y, float(vid_height) - crop_h))

  filter_cx = (
      f"crop={int(crop_w)}:{int(crop_h)}:{int(crop_x)}:{int(crop_y)},"
      f"scale=1080:1920:force_original_aspect_ratio=decrease,"
      f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
  )

  ffmpeg_path = ffmpeg_utils.get_ffmpeg_exe()
  cmd = [
    ffmpeg_path, "-i", input_path,
    "-vf", filter_cx,
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-crf", "22",
    "-c:a", "copy",
    "-movflags", "+faststart",
    output_path, "-y"
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
  ffprobe_path = ffmpeg_utils.get_ffprobe_exe()
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
  ffmpeg_path = ffmpeg_utils.get_ffmpeg_exe()
  cmd = [
      ffmpeg_path, "-y", "-ss", str(start), "-i", video_path,
      "-t", str(duration), "-c", "copy", output_path
  ]
  result = subprocess.run(cmd, capture_output=True, text=True)
  if result.returncode != 0:
      raise RuntimeError(f"FFmpeg failed cutting raw clip: {result.stderr}")
