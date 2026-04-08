"""
Lip2Speech inference pipeline.

Usage:
    pipeline = Lip2SpeechPipeline.load(weights_path="path/to/model.pt")
    audio_bytes, meta = pipeline.run(video_path="path/to/video.mp4")

The pipeline:
  1. Extracts face + lip frames (preprocessing.py)
  2. Runs the Lip2Speech neural network (nn/model.py)
  3. Converts the predicted mel spectrogram → raw audio via Griffin-Lim
  4. Returns WAV bytes + inference metadata dict

Pre-trained weights are available at:
  https://github.com/Chris10M/Lip2Speech
"""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Audio parameters (must match training config)
SAMPLE_RATE = 16_000
N_FFT = 1024
HOP_LENGTH = 256
WIN_LENGTH = 1024
N_MELS = 80
FMIN = 0
FMAX = 8000
GRIFFIN_LIM_ITERS = 60


def _mel_to_audio(mel: np.ndarray) -> np.ndarray:
    """
    Convert a mel spectrogram (T, n_mels) to a raw waveform via Griffin-Lim.

    mel values are assumed to be in log-scale (natural log or log10 × 20 dB).
    """
    import librosa

    # Invert log-mel → linear mel
    mel_linear = np.exp(mel.T)  # (n_mels, T)

    # Build mel filter bank and invert to linear spectrogram
    mel_basis = librosa.filters.mel(
        sr=SAMPLE_RATE, n_fft=N_FFT, n_mels=N_MELS, fmin=FMIN, fmax=FMAX
    )
    # Pseudo-inverse mel-to-linear
    lin_spec = np.maximum(1e-8, np.dot(np.linalg.pinv(mel_basis), mel_linear))

    # Griffin-Lim phase reconstruction
    audio = librosa.griffinlim(
        lin_spec,
        n_iter=GRIFFIN_LIM_ITERS,
        hop_length=HOP_LENGTH,
        win_length=WIN_LENGTH,
        n_fft=N_FFT,
    )
    return audio.astype(np.float32)


def _audio_to_wav_bytes(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Encode a float32 waveform as 16-bit PCM WAV bytes."""
    import wave, struct

    # Clip and convert to int16
    audio_int16 = np.clip(audio, -1.0, 1.0)
    audio_int16 = (audio_int16 * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


class Lip2SpeechPipeline:
    """
    End-to-end inference pipeline.

    Attributes:
        model: The Lip2Speech neural network (nn.Module).
        device: torch.device the model is on.
    """

    def __init__(self, model, device=None):
        import torch
        self.model = model
        self.device = device or torch.device("cpu")
        self.model.to(self.device)
        self.model.eval()

    # ------------------------------------------------------------------
    @classmethod
    def load(
        cls,
        weights_path: str | Path | None = None,
        device=None,
        **model_kwargs,
    ) -> "Lip2SpeechPipeline":
        """
        Instantiate the pipeline, optionally loading pre-trained weights.

        If `weights_path` is None the model runs with random weights
        (useful for testing the pipeline end-to-end before training).

        Args:
            weights_path: Path to a .pt checkpoint saved with torch.save(model.state_dict(), …).
            device: 'cpu', 'cuda', 'mps', or a torch.device.  Auto-detected if None.
            **model_kwargs: Passed through to Lip2Speech.__init__.
        """
        import torch
        from .nn.model import Lip2Speech

        if device is None:
            if torch.cuda.is_available():
                device = torch.device("cuda")
            elif torch.backends.mps.is_available():
                device = torch.device("mps")
            else:
                device = torch.device("cpu")

        model = Lip2Speech(**model_kwargs)

        if weights_path is not None:
            weights_path = Path(weights_path)
            if not weights_path.exists():
                logger.warning("Weights file not found at %s — running with random weights.", weights_path)
            else:
                state = torch.load(str(weights_path), map_location=device)
                model.load_state_dict(state)
                logger.info("Loaded Lip2Speech weights from %s", weights_path)
        else:
            logger.warning(
                "No weights_path provided — model has random weights. "
                "Download pre-trained weights from https://github.com/Chris10M/Lip2Speech"
            )

        return cls(model, device=device)

    # ------------------------------------------------------------------
    def run(
        self,
        video_path: str | Path,
        max_frames: int = 150,
    ) -> tuple[bytes, dict]:
        """
        Run full inference on a video file.

        Args:
            video_path: Path to the input video (mp4, avi, mov, …).
            max_frames: Maximum frames to extract from the video.

        Returns:
            wav_bytes: Raw WAV file as bytes (ready to write to disk or serve over HTTP).
            meta: Dict with inference metadata:
                  {num_frames, mel_frames, duration_seconds, processing_time_ms, device}
        """
        import torch

        t0 = time.perf_counter()

        # 1. Preprocess
        from .preprocessing import extract_from_video
        face_np, lips_np = extract_from_video(video_path, max_frames=max_frames)

        # face_np: (96, 96, 3)  → tensor (1, 3, 96, 96)
        face_t = torch.from_numpy(face_np).permute(2, 0, 1).unsqueeze(0).to(self.device)

        # lips_np: (T, 48, 96) → tensor (1, T, 48, 96)
        lips_t = torch.from_numpy(lips_np).unsqueeze(0).to(self.device)

        # 2. Forward pass
        with torch.no_grad():
            mel_pred, _ = self.model.synthesise(face_t, lips_t)

        # mel_pred: (1, T_mel, 80) → numpy (T_mel, 80)
        mel_np = mel_pred.squeeze(0).cpu().numpy()

        # 3. Griffin-Lim → waveform → WAV bytes
        audio = _mel_to_audio(mel_np)
        wav_bytes = _audio_to_wav_bytes(audio)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        duration_s = len(audio) / SAMPLE_RATE

        meta = {
            "num_frames": int(lips_np.shape[0]),
            "mel_frames": int(mel_np.shape[0]),
            "duration_seconds": round(duration_s, 3),
            "processing_time_ms": round(elapsed_ms, 1),
            "device": str(self.device),
        }
        logger.info("Lip2Speech inference complete: %s", meta)
        return wav_bytes, meta
