"""
Lip2Speech — end-to-end model.

"Show Me Your Face, And I'll Tell You How You Speak"
Christen Millerdurai, Lotfy Abdel Khaliq, Timon Ulrich — Saarland University.

Architecture overview (Figure 2 from the paper):
  1. Speaker Encoder  : first frame  → 256-dim speaker embedding
  2. Lip Encoder      : lip-ROI seq  → (T, 256) per-frame lip features
  3. Tile + concat    : speaker_emb tiled T times, then cat with lip features → (T, 512)
  4. LSTM Decoder     : visual features → mel spectrogram (auto-regressive)
  5. (Offline)        : Griffin-Lim / neural vocoder → raw waveform
"""

import torch
import torch.nn as nn

from .speaker_encoder import SpeakerEncoder
from .lip_encoder import LipEncoder
from .decoder import Decoder


class Lip2Speech(nn.Module):
    """
    End-to-end Lip-to-Speech synthesis model.

    Args:
        speaker_dim: Dimension of the speaker embedding (default 256).
        lip_dim:     Dimension of per-frame lip features (default 256).
        mel_dim:     Number of mel filter banks (default 80).
        lstm_hidden: Hidden size of the LSTM decoder cells (default 512).

    Forward:
        face:     (B, 3, H, W)  — first video frame (face crop, RGB, [0,1])
        lips:     (B, T, H, W)  — grayscale lip-ROI sequence, [0,1]
        mel_gt:   (B, T_mel, mel_dim) or None  — ground-truth mel for teacher forcing
        tf_ratio: float in [0, 1]  — teacher-forcing ratio (1 = always use GT)

    Returns:
        mel_pred:    (B, T_mel, mel_dim)
        stop_logits: (B, T_mel, 1)
        speaker_emb: (B, speaker_dim)  — for auxiliary losses / visualisation
    """

    def __init__(
        self,
        speaker_dim: int = 256,
        lip_dim: int = 256,
        mel_dim: int = 80,
        lstm_hidden: int = 512,
    ):
        super().__init__()
        self.speaker_encoder = SpeakerEncoder(embedding_dim=speaker_dim)
        self.lip_encoder = LipEncoder(feature_dim=lip_dim)
        self.decoder = Decoder(
            visual_dim=speaker_dim + lip_dim,
            mel_dim=mel_dim,
            lstm_hidden=lstm_hidden,
        )
        self.mel_dim = mel_dim

    # ------------------------------------------------------------------
    def forward(
        self,
        face: torch.Tensor,
        lips: torch.Tensor,
        mel_gt: torch.Tensor | None = None,
        tf_ratio: float = 1.0,
    ):
        # 1. Speaker identity from the first face frame
        speaker_emb = self.speaker_encoder(face)          # (B, speaker_dim)

        # 2. Temporal lip features
        lip_features = self.lip_encoder(lips)             # (B, T, lip_dim)

        # 3. Tile speaker embedding and concatenate
        T = lip_features.shape[1]
        spk_tiled = speaker_emb.unsqueeze(1).expand(-1, T, -1)  # (B, T, speaker_dim)
        visual = torch.cat([spk_tiled, lip_features], dim=-1)   # (B, T, speaker_dim+lip_dim)

        # 4. Auto-regressive mel decoding
        mel_pred, stop_logits = self.decoder(visual, mel_gt, tf_ratio)

        return mel_pred, stop_logits, speaker_emb

    # ------------------------------------------------------------------
    @torch.no_grad()
    def synthesise(
        self,
        face: torch.Tensor,
        lips: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Convenience wrapper for inference (no teacher forcing, no grad).

        Returns:
            mel_pred:    (B, T_mel, mel_dim)
            speaker_emb: (B, speaker_dim)
        """
        self.eval()
        mel_pred, _, speaker_emb = self.forward(face, lips, mel_gt=None, tf_ratio=0.0)
        return mel_pred, speaker_emb
