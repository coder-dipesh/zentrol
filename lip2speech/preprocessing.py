"""
Video preprocessing for Lip2Speech inference.

Responsibilities:
  1. Read video frames with OpenCV.
  2. Detect faces with OpenCV Haar cascade (no extra model downloads needed).
  3. Estimate lip ROI as the lower 40% of the face bounding box.
  4. Return:
       - face_frame : np.ndarray (96, 96, 3) — first face crop (RGB, float32 [0,1])
       - lip_sequence: np.ndarray (T, 48, 96) — grayscale lip crops per frame
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Output sizes
FACE_SIZE = (96, 96)
LIP_H, LIP_W = 48, 96


def _face_detector():
    """Return OpenCV's built-in frontal-face Haar cascade."""
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        raise RuntimeError(
            "Could not load haarcascade_frontalface_default.xml from OpenCV data directory."
        )
    return cascade


def _detect_face(gray: np.ndarray, cascade):
    """Return (x, y, w, h) of the largest detected face, or None."""
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )
    if len(faces) == 0:
        return None
    # Pick the largest face
    return max(faces, key=lambda f: f[2] * f[3])


def _crop_face(frame_rgb: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """Return a square RGB face crop resized to FACE_SIZE."""
    fh, fw = frame_rgb.shape[:2]
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(fw, x + w)
    y2 = min(fh, y + h)
    crop = frame_rgb[y1:y2, x1:x2]
    return cv2.resize(crop, FACE_SIZE)


def _crop_lip(frame_bgr: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """
    Estimate the lip ROI as the lower ~40% of the face bounding box.
    Returns a grayscale crop resized to (LIP_H, LIP_W).
    """
    fh, fw = frame_bgr.shape[:2]
    lip_y = max(0, y + int(h * 0.60))
    lip_y2 = min(fh, y + h)
    lip_x1 = max(0, x + int(w * 0.10))
    lip_x2 = min(fw, x + w - int(w * 0.10))

    lip_crop = frame_bgr[lip_y:lip_y2, lip_x1:lip_x2]
    if lip_crop.size == 0:
        return None
    lip_gray = cv2.cvtColor(lip_crop, cv2.COLOR_BGR2GRAY)
    return cv2.resize(lip_gray, (LIP_W, LIP_H))


def extract_from_video(
    video_path: str | Path,
    max_frames: int = 150,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract face frame and lip sequence from a video file.

    Args:
        video_path: Path to the input video.
        max_frames: Maximum number of frames to process.

    Returns:
        face_frame:   np.ndarray (96, 96, 3)  float32, values in [0, 1]
        lip_sequence: np.ndarray (T, 48, 96)  float32, values in [0, 1]

    Raises:
        ValueError: If no face can be detected in the video.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    cascade = _face_detector()
    face_frame_rgb: np.ndarray | None = None
    lip_frames: list[np.ndarray] = []
    last_bbox = None  # reuse last known bbox when detection fails

    try:
        for _ in range(max_frames):
            ret, frame = cap.read()
            if not ret:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            bbox = _detect_face(gray, cascade)

            if bbox is not None:
                last_bbox = bbox

            if last_bbox is None:
                continue

            x, y, w, h = last_bbox
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if face_frame_rgb is None:
                face_frame_rgb = _crop_face(frame_rgb, x, y, w, h)

            lip = _crop_lip(frame, x, y, w, h)
            if lip is not None:
                lip_frames.append(lip)

    finally:
        cap.release()

    if face_frame_rgb is None:
        raise ValueError("No face detected in the video. Make sure your face is visible to the camera.")
    if len(lip_frames) == 0:
        raise ValueError("Could not extract lip region from the video.")

    face_out = face_frame_rgb.astype(np.float32) / 255.0       # (96, 96, 3)
    lip_out  = np.stack(lip_frames).astype(np.float32) / 255.0 # (T, 48, 96)

    logger.info("Extracted %d lip frames from %s", len(lip_frames), Path(video_path).name)
    return face_out, lip_out
