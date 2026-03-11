import numpy as np # type: ignore
from PIL import Image # type: ignore
from typing import Any, cast

def detect_layout(
  frames: list[Image.Image],
  face_data: list[list[dict[str, Any]]],
  vid_width: int,
  vid_height: int
) -> dict:
  """
  Analyze sampled frames and return layout decision.
  """
  face_data = _deduplicate_faces(face_data)
  face_data = _filter_false_positives(face_data)
  majority_faces = _majority_face_count(face_data)

  has_screen = _detect_screen_region(
    frames, face_data, vid_width, vid_height
  )

  if majority_faces == 0:
    mode = "none"
    confidence = 1.0

  elif majority_faces == 1:
    # Single face — check if tutorial
    if has_screen:
      mode = "tutorial"
      confidence = 0.85
    else:
      mode = "single"
      confidence = 1.0

  elif majority_faces == 2:
    # Verify both faces are consistently different people
    # Check: are the two faces always on opposite sides?
    consistent_sides = _check_consistent_face_sides(face_data)
    if consistent_sides:
      mode = "podcast"
      confidence = 0.9
    else:
      # Inconsistent = probably same face being double-detected
      mode = "single"
      confidence = 0.75

  else:
    mode = "panel"
    confidence = 0.85

  return {
    "mode": mode,
    "confidence": confidence,
    "face_count": majority_faces,
    "has_screen_region": has_screen,
    "needs_user_confirm": confidence < 0.8
  }


def _detect_screen_region(
  frames: list[Image.Image],
  face_data: list[list[dict[str, Any]]],
  vid_width: int,
  vid_height: int
) -> bool:
  screen_count: float = 0.0
  step = max(1, len(frames) // 5)
  sample_frames = [frames[x] for x in range(0, len(frames), step)]
  sample_faces = [face_data[x] for x in range(0, len(face_data), step)]

  for i, (frame, faces) in enumerate(
    zip(sample_frames, sample_faces)
  ):
    gray = np.array(frame.convert('L'), dtype=float)
    h, w = gray.shape
    cell_h = h // 4
    cell_w = w // 4

    # Build face mask — regions occupied by faces
    face_mask = np.zeros((4, 4), dtype=bool) # type: ignore
    for face in faces:
      col = int(face['cx'] / w * 4)
      row = int(face['cy'] / h * 4)
      col = max(0, min(col, 3)) # type: ignore
      row = max(0, min(row, 3)) # type: ignore
      face_mask[row][col] = True

    # Check variance in non-face regions
    high_variance_cells: float = 0.0
    for row in range(4):
      for col in range(4):
        if face_mask[row][col]: # type: ignore
          continue
        cell = gray[ # type: ignore
          row*cell_h:(row+1)*cell_h, # type: ignore
          col*cell_w:(col+1)*cell_w # type: ignore
        ] # type: ignore
        variance = float(np.var(cell)) # type: ignore
        if variance > 800:  # threshold for screen content
          high_variance_cells += 1.0 # type: ignore

    # Screen detected if 3+ high-variance non-face cells
    if float(high_variance_cells) >= 3.0: # type: ignore
      screen_count += 1.0 # type: ignore

  return float(screen_count) / max(len(sample_frames), 1) > 0.4 # type: ignore


def _majority_face_count(face_data: list[list[dict[str, Any]]]) -> int:
  from collections import Counter
  counts: Any = Counter([len(f) for f in face_data]) # type: ignore
  total = len(face_data)
  if total == 0:
    return 0

  for count, freq in counts.most_common():
    if freq / total > 0.5:
      return int(count)

  # No majority — use median
  all_counts: list[int] = sorted([len(f) for f in face_data])
  return all_counts[len(all_counts) // 2]


def _filter_false_positives(face_data: list[list[dict[str, Any]]]) -> list[list[dict[str, Any]]]:
  cleaned = []
  for frame_faces in face_data:
    real_faces = [f for f in frame_faces if f['size'] > 0.05]
    cleaned.append(real_faces)
  return cleaned


def _deduplicate_faces(face_data: list[list[dict[str, Any]]]) -> list[list[dict[str, Any]]]:
  cleaned = []
  for frame_faces in face_data:
    unique: list[dict[str, Any]] = []
    for face in frame_faces:
      is_duplicate = False
      for existing in unique:
        dist = ((face['cx']-existing['cx'])**2 +
                (face['cy']-existing['cy'])**2) ** 0.5
        if dist < 50:
          is_duplicate = True
          break
      if not is_duplicate:
        unique.append(face)
    cleaned.append(unique)
  return cleaned


def _check_consistent_face_sides(
  face_data: list[list[dict[str, Any]]]
) -> bool:
  """
  For two-face frames, check that face positions
  are consistently on opposite sides of the frame.
  """
  two_face_frames: list[list[dict[str, Any]]] = [f for f in face_data if len(f) >= 2]

  if len(two_face_frames) < 3:
    return False

  opposite_count: float = 0.0
  for frame in two_face_frames:
    typed_frame: list[dict[str, Any]] = list(frame)
    sorted_f: Any = sorted(typed_frame[:2], key=lambda f: float(f['cx'])) # type: ignore
    left_cx = float(sorted_f[0]['cx'])
    right_cx = float(sorted_f[1]['cx'])
    gap = right_cx - left_cx
    if gap > 0.15: 
      opposite_count += 1.0 # type: ignore

  return float(opposite_count) / len(two_face_frames) > 0.6 # type: ignore
