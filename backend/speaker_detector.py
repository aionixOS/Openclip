import subprocess
import os
import numpy as np
from PIL import Image

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

model_path = os.path.join(os.path.dirname(__file__), 'face_landmarker.task')

def _ensure_model_exists():
  if not os.path.exists(model_path):
    import urllib.request
    url = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    urllib.request.urlretrieve(url, model_path)

_ensure_model_exists()
base_options = python.BaseOptions(model_asset_path=model_path)
options = vision.FaceLandmarkerOptions(base_options=base_options, num_faces=6)
face_landmarker = vision.FaceLandmarker.create_from_options(options)

def detect_speakers_per_second(
  video_path: str,
  frames: list[Image.Image],
  face_data: list[list[dict]],
  vid_width: int,
  vid_height: int
) -> list[int]:
  mouth_results = _detect_mouth_movement(
    frames, face_data, vid_width, vid_height
  )
  audio_results = _detect_audio_energy(
    video_path, face_data, vid_width, vid_height
  )

  raw_speakers = []
  for i in range(len(frames)):
    mouth = mouth_results[i] if i < len(mouth_results) else (-1, 0.0)
    audio = audio_results[i] if i < len(audio_results) else (-1, 0.0)
    mouth_conf = mouth[1]

    if mouth_conf > 0.6:
      raw_speakers.append(mouth[0])
    else:
      raw_speakers.append(audio[0])

  return _apply_speaker_hold(raw_speakers, hold_seconds=3)

def _detect_mouth_movement(
  frames: list[Image.Image],
  face_data: list[list[dict]],
  vid_width: int,
  vid_height: int
) -> list[tuple[int, float]]:
  results = []
  for frame, faces in zip(frames, face_data):
    if len(faces) < 2:
      results.append((-1, 0.0))
      continue

    rgb = np.array(frame.convert('RGB'))
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    mesh_result = face_landmarker.detect(mp_image)

    if not mesh_result.face_landmarks:
      results.append((-1, 0.0))
      continue

    mouth_ratios = []
    for landmarks in mesh_result.face_landmarks[:2]:
      upper = landmarks[13]
      lower = landmarks[14]
      dist = abs(upper.y - lower.y)
      mouth_ratios.append(dist)

    if len(mouth_ratios) < 2:
      results.append((-1, 0.0))
      continue

    sorted_faces = sorted(
      enumerate(faces[:2]),
      key=lambda x: x[1]['cx']
    )
    left_idx = sorted_faces[0][0]
    right_idx = sorted_faces[1][0]

    ratio_diff = abs(mouth_ratios[0] - mouth_ratios[1])
    if mouth_ratios[0] > mouth_ratios[1]:
      speaker = left_idx
    else:
      speaker = right_idx

    confidence = min(ratio_diff * 20, 1.0)
    results.append((speaker, float(confidence)))

  return results

def _detect_audio_energy(
  video_path: str,
  face_data: list[list[dict]],
  vid_width: int,
  vid_height: int
) -> list[tuple[int, float]]:
  ffmpeg_path = os.path.expandvars(
      r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
  )
  cmd = [
    ffmpeg_path, "-i", video_path,
    "-af", (
      "astats=metadata=1:reset=1,"
      "ametadata=print:key=lavfi.astats.Overall.RMS_level"
    ),
    "-f", "null", "-"
  ]
  result = subprocess.run(cmd, capture_output=True, text=True)
  lines = result.stderr.split('\n')

  rms_values = []
  for line in lines:
    if 'RMS_level' in line:
      try:
        val = float(line.split('=')[-1])
        rms_values.append(val)
      except ValueError:
        rms_values.append(-91.0)

  if not rms_values:
    return [(-1, 0.0)] * len(face_data)

  max_rms = max(rms_values) if rms_values else -91
  min_rms = min(rms_values) if rms_values else -91
  rms_range = max_rms - min_rms or 1

  speaker_results = []
  current_speaker = 0
  last_switch = 0

  for i, rms in enumerate(rms_values[:len(face_data)]):
    energy = (rms - min_rms) / rms_range
    if energy > 0.3 and i - last_switch > 3:
      current_speaker = 1 - current_speaker
      last_switch = i
    speaker_results.append((int(current_speaker), float(energy)))

  while len(speaker_results) < len(face_data):
    speaker_results.append((int(current_speaker), 0.5))

  return speaker_results

def _apply_speaker_hold(
  raw_speakers: list[int],
  hold_seconds: int = 3
) -> list[int]:
  if not raw_speakers:
    return []

  smoothed = [raw_speakers[0]]
  current = raw_speakers[0]
  candidate = current
  candidate_count = 0

  for i in range(1, len(raw_speakers)):
    s = raw_speakers[i]
    if s == current:
      candidate_count = 0
      smoothed.append(current)
    else:
      if s == candidate:
        candidate_count += 1
      else:
        candidate = s
        candidate_count = 1

      if candidate_count >= hold_seconds:
        current = candidate
        candidate_count = 0

      smoothed.append(current)

  return smoothed
