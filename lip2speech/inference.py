"""
Lip2Speech inference pipeline using the original pre-trained model.

Reference: "Show Me Your Face, And I'll Tell You How You Speak"
Weights:   lip2speech/weights/lip2speech_final.pth  (265 MB)
"""

from __future__ import annotations

import io
import logging
import sys
import time
import wave
from pathlib import Path

import numpy as np
import torch

logger = logging.getLogger(__name__)

# Audio parameters (must match training config in hparams.py)
SAMPLE_RATE   = 16_000
N_FFT         = 1024
HOP_LENGTH    = 256
WIN_LENGTH    = 1024
N_MELS        = 80
FMIN          = 0
FMAX          = 8000
GRIFFIN_LIM_ITERS = 60

# Default weights path (overridden via settings.LIP2SPEECH_WEIGHTS_PATH)
_DEFAULT_WEIGHTS = Path(__file__).parent / 'weights' / 'lip2speech_final.pth'


def _add_original_model_to_path():
    """Add the original model directory to sys.path so its imports resolve."""
    orig = str(Path(__file__).parent / 'original_model')
    if orig not in sys.path:
        sys.path.insert(0, orig)


def _mel_to_audio(mel: np.ndarray) -> np.ndarray:
    """
    mel: (T, n_mels) float32  →  raw waveform float32.
    Returns silence if the spectrogram is too short for Griffin-Lim.
    """
    import librosa

    min_frames = N_FFT // HOP_LENGTH + 1
    if mel.shape[0] < min_frames:
        return np.zeros(N_FFT, dtype=np.float32)

    mel_linear = np.exp(mel.T)  # (n_mels, T)
    mel_basis  = librosa.filters.mel(
        sr=SAMPLE_RATE, n_fft=N_FFT, n_mels=N_MELS, fmin=FMIN, fmax=FMAX
    )
    lin_spec = np.maximum(1e-8, np.dot(np.linalg.pinv(mel_basis), mel_linear))
    audio = librosa.griffinlim(
        lin_spec,
        n_iter=GRIFFIN_LIM_ITERS,
        hop_length=HOP_LENGTH,
        win_length=WIN_LENGTH,
        n_fft=N_FFT,
    )
    return audio.astype(np.float32)


def _audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    audio_i16 = np.clip(audio, -1.0, 1.0)
    audio_i16  = (audio_i16 * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_i16.tobytes())
    return buf.getvalue()


class Lip2SpeechPipeline:

    def __init__(self, model, device: torch.device):
        self.model  = model
        self.device = device

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, weights_path=None, device=None, **_) -> 'Lip2SpeechPipeline':
        _add_original_model_to_path()
        from model.model import get_network  # original repo code

        if device is None:
            # MPS excluded: adaptive_avg_pool3d not supported on MPS
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        net = get_network('test')

        # Resolve weights path
        wpath = Path(weights_path) if weights_path else _DEFAULT_WEIGHTS
        if not wpath.exists():
            logger.warning(
                "Weights not found at %s — running with random weights. "
                "Download from https://github.com/Chris10M/Lip2Speech", wpath
            )
        else:
            state = torch.load(str(wpath), map_location=device)
            if 'state_dict' in state:
                state = state['state_dict']
            # Strip speaker_encoder prefix (it's a separate module in the checkpoint)
            state = {k: v for k, v in state.items() if not k.startswith('speaker_encoder.')}
            net.load_state_dict(state, strict=True)
            logger.info("Loaded Lip2Speech weights from %s", wpath)

        net = net.to(device).eval()
        return cls(net, device)

    # ------------------------------------------------------------------
    def run(self, video_path: str | Path, max_frames: int = 150):
        from .preprocessing import extract_from_video

        t0 = time.perf_counter()

        video_t, face_t = extract_from_video(video_path, max_frames=max_frames)
        video_t = video_t.to(self.device)  # (1, 3, T, 96, 96)
        face_t  = face_t.to(self.device)   # (1, 1, 3, 160, 160)

        with torch.no_grad():
            # inference() returns (mel_outputs, stop_tokens, attention_matrix)
            # mel_outputs shape: (1, n_mels, T_mel)
            outputs = self.model.inference(video_t, face_t, return_attention_map=True)
            mel_pred, stop_tokens = outputs[0], outputs[1]

        # Trim at stop token
        stop_idx = int(stop_tokens[0].item()) if stop_tokens.numel() > 0 else mel_pred.shape[2]
        mel_np = mel_pred[0, :, :stop_idx].cpu().numpy().T  # (T_mel, n_mels)

        audio    = _mel_to_audio(mel_np)
        wav_bytes = _audio_to_wav_bytes(audio)

        elapsed_ms  = (time.perf_counter() - t0) * 1000
        duration_s  = len(audio) / SAMPLE_RATE

        meta = {
            'num_frames':        int(video_t.shape[2]),
            'mel_frames':        mel_np.shape[0],
            'duration_seconds':  round(duration_s, 3),
            'processing_time_ms': round(elapsed_ms, 1),
            'device':            str(self.device),
        }
        logger.info("Lip2Speech inference complete: %s", meta)
        return wav_bytes, meta
