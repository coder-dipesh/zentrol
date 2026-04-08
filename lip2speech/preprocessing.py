"""
Video preprocessing for Lip2Speech inference.

Responsibilities:
  1. Read video frames with OpenCV.
  2. Detect face + extract lip ROI with MediaPipe FaceMesh.
  3. Return:
       - face_frame : np.ndarray (96, 96, 3) — first face crop for the speaker encoder
       - lip_sequence: np.ndarray (T, 48, 96) — grayscale lip crops per frame
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# MediaPipe FaceMesh landmark indices for the lip region (outer contour).
# Reference: https://github.com/google/mediapipe/blob/master/mediapipe/python/solutions/face_mesh_connections.py
_UPPER_LIP = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291]
_LOWER_LIP = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291]
_LIP_LANDMARKS = list(set(_UPPER_LIP + _LOWER_LIP))

# Output sizes
FACE_SIZE = (96, 96)
LIP_H, LIP_W = 48, 96
# Padding around the tight lip bounding box (fraction of bbox side)
LIP_PAD = 0.3


def _get_face_mesh():
    """Lazy-import MediaPipe FaceMesh to avoid import cost at module load."""
    try:
        import mediapipe as mp
        return mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
    except ImportError:
        raise ImportError(
            "mediapipe is required for preprocessing. "
            "Install it with: pip install mediapipe"
        )


def _crop_face(frame: np.ndarray, landmarks, h: int, w: int) -> np.ndarray | None:
    """Return a square face crop centred on the detected face."""
    xs = [lm.x * w for lm in landmarks.landmark]
    ys = [lm.y * h for lm in landmarks.landmark]
    x1, x2 = int(min(xs)), int(max(xs))
    y1, y2 = int(min(ys)), int(max(ys))

    # Add padding
    pw = int((x2 - x1) * 0.2)
    ph = int((y2 - y1) * 0.2)
    x1, y1 = max(0, x1 - pw), max(0, y1 - ph)
    x2, y2 = min(w, x2 + pw), min(h, y2 + ph)

    if x2 <= x1 or y2 <= y1:
        return None

    crop = frame[y1:y2, x1:x2]
    return cv2.resize(crop, FACE_SIZE)


def _crop_lip(frame: np.ndarray, landmarks, h: int, w: int) -> np.ndarray | None:
    """Return a grayscale lip ROI crop."""
    xs = [landmarks.landmark[i].x * w for i in _LIP_LANDMARKS]
    ys = [landmarks.landmark[i].y * h for i in _LIP_LANDMARKS]

    x1, x2 = int(min(xs)), int(max(xs))
    y1, y2 = int(min(ys)), int(max(ys))

    pw = int((x2 - x1) * LIP_PAD)
    ph = int((y2 - y1) * LIP_PAD)
    x1, y1 = max(0, x1 - pw), max(0, y1 - ph)
    x2, y2 = min(w, x2 + pw), min(h, y2 + ph)

    if x2 <= x1 or y2 <= y1:
        return None

    lip = frame[y1:y2, x1:x2]
    lip_gray = cv2.cvtColor(lip, cv2.COLOR_BGR2GRAY)
    return cv2.resize(lip_gray, (LIP_W, LIP_H))


def extract_from_video(
    video_path: str | Path,
    max_frames: int = 150,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract face frame and lip sequence from a video file.

    Args:
        video_path: Path to the input video.
        max_frames: Maximum number of frames to process (keeps inference fast).

    Returns:
        face_frame:   np.ndarray (96, 96, 3)  float32, values in [0, 1]
        lip_sequence: np.ndarray (T, 48, 96)  float32, values in [0, 1]

    Raises:
        ValueError: If no face or lips can be detected in the video.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    face_frame_rgb: np.ndarray | None = None
    lip_frames: list[np.ndarray] = []

    face_mesh = _get_face_mesh()

    try:
        frame_idx = 0
        while cap.isOpened() and frame_idx < max_frames:
            ret, frame = cap.read()
            if not ret:
                break

            h, w = frame.shape[:2]
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = face_mesh.process(frame_rgb)

            if result.multi_face_landmarks:
                lms = result.multi_face_landmarks[0]

                if face_frame_rgb is None:
                    face_frame_rgb = _crop_face(frame_rgb, lms, h, w)

                lip = _crop_lip(frame, lms, h, w)
                if lip is not None:
                    lip_frames.append(lip)

            frame_idx += 1
    finally:
        cap.release()
        face_mesh.close()

    if face_frame_rgb is None:
        raise ValueError("No face detected in the video.")
    if len(lip_frames) == 0:
        raise ValueError("No lip region detected in the video.")

    face_out = face_frame_rgb.astype(np.float32) / 255.0          # (96, 96, 3)
    lip_out = np.stack(lip_frames).astype(np.float32) / 255.0     # (T, 48, 96)

    logger.info(
        "Extracted %d lip frames from %s", len(lip_frames), Path(video_path).name
    )
    return face_out, lip_out
