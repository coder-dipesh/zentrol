"""
Video preprocessing for Lip2Speech inference.

Produces tensors matching the original Lip2Speech model's expected format:
  - video_frames: (1, 3, T, 96, 96)  RGB lip-ROI crops, ImageNet-normalised
  - face_frames:  (1, 1, 3, 160, 160) face crop, normalised as (x-127.5)/128
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import torch

logger = logging.getLogger(__name__)

# ImageNet normalisation for lip-ROI frames (VideoExtractor / ShuffleNetV2)
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)

LIP_SIZE  = 96   # expected by VideoExtractor
FACE_SIZE = 160  # expected by FaceRecognizer (InceptionResnetV1)


def _face_detector():
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        raise RuntimeError("Could not load haarcascade_frontalface_default.xml")
    return cascade


def _detect_face(gray: np.ndarray, cascade):
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def _crop_lip_roi(frame_rgb: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """Lower-centre of face bbox → 96×96 RGB, ImageNet-normalised float32."""
    fh, fw = frame_rgb.shape[:2]
    # Mouth is roughly in the bottom 40 % of the face box
    y1 = max(0, y + int(h * 0.60))
    y2 = min(fh, y + h)
    x1 = max(0, x + int(w * 0.10))
    x2 = min(fw, x + w - int(w * 0.10))

    crop = frame_rgb[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    crop = cv2.resize(crop, (LIP_SIZE, LIP_SIZE)).astype(np.float32) / 255.0
    crop = (crop - _IMAGENET_MEAN) / _IMAGENET_STD
    return crop  # (96, 96, 3)


def _crop_face(frame_rgb: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """Face bbox → 160×160 RGB, normalised as (x-127.5)/128 for FaceNet."""
    fh, fw = frame_rgb.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(fw, x + w), min(fh, y + h)

    crop = frame_rgb[y1:y2, x1:x2]
    crop = cv2.resize(crop, (FACE_SIZE, FACE_SIZE)).astype(np.float32)
    crop = (crop - 127.5) / 128.0
    return crop  # (160, 160, 3)


def extract_from_video(
    video_path: str | Path,
    max_frames: int = 150,
) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Extract lip-ROI video tensor and face tensor from a video file.

    Returns:
        video_frames: (1, 3, T, 96, 96)   float32 CPU tensor
        face_frames:  (1, 1, 3, 160, 160) float32 CPU tensor

    Raises:
        ValueError: if no face is detected.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    cascade   = _face_detector()
    lip_frames: list[np.ndarray] = []
    face_crop: np.ndarray | None = None
    last_bbox = None

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

            lip = _crop_lip_roi(frame_rgb, x, y, w, h)
            if lip is not None:
                lip_frames.append(lip)

            if face_crop is None:
                face_crop = _crop_face(frame_rgb, x, y, w, h)

    finally:
        cap.release()

    if face_crop is None or len(lip_frames) == 0:
        raise ValueError(
            "No face detected in the video. Make sure your face is visible."
        )

    # Stack lip frames: (T, 96, 96, 3) → (3, T, 96, 96) → (1, 3, T, 96, 96)
    lip_arr = np.stack(lip_frames)                        # (T, 96, 96, 3)
    lip_t   = torch.from_numpy(lip_arr).permute(3, 0, 1, 2).unsqueeze(0)  # (1,3,T,96,96)

    # Face: (160, 160, 3) → (3, 160, 160) → (1, 1, 3, 160, 160)
    face_t = torch.from_numpy(face_crop).permute(2, 0, 1).unsqueeze(0).unsqueeze(0)  # (1,1,3,160,160)

    logger.info("Extracted %d lip frames from %s", len(lip_frames), Path(video_path).name)
    return lip_t, face_t
