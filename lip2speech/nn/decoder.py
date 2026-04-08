"""
LSTM Mel-Spectrogram Decoder — "Show Me Your Face, And I'll Tell You How You Speak".

Tacotron-style auto-regressive decoder that generates mel frames one step at a
time conditioned on visual features (speaker embedding ⊕ lip features).

Pipeline per step:
  prev-mel → PreNet → att-LSTM → dec-LSTM → mel-projection + stop-token
"""

import random
import torch
import torch.nn as nn
import torch.nn.functional as F


class _PreNet(nn.Module):
    """Two FC-ReLU-Dropout layers applied to the previous mel frame."""

    def __init__(self, mel_dim: int, hidden: int = 256, dropout: float = 0.5):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(mel_dim, hidden),
            nn.ReLU(inplace=True),
            nn.Dropout(p=dropout),
            nn.Linear(hidden, hidden),
            nn.ReLU(inplace=True),
            nn.Dropout(p=dropout),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class Decoder(nn.Module):
    """
    Auto-regressive LSTM decoder that maps visual features to a mel spectrogram.

    Args:
        visual_dim:   Dimensionality of each visual feature vector (speaker + lip).
        mel_dim:      Number of mel filter banks (default 80).
        lstm_hidden:  Hidden size of both LSTM cells.
        prenet_hidden: Hidden size of the PreNet FC layers.

    Forward inputs:
        visual_features: (B, T_vis, visual_dim)  — encoder output
        mel_targets:     (B, T_mel, mel_dim) or None (for inference)
        teacher_forcing_ratio: float in [0, 1]

    Forward outputs:
        mel_outputs:  (B, T_mel, mel_dim)
        stop_outputs: (B, T_mel, 1)  — logits; sigmoid > 0.5 means "stop"
    """

    # During inference, generate at most this many times the visual-sequence length.
    MAX_DECODE_RATIO = 8
    STOP_THRESHOLD = 0.5

    def __init__(
        self,
        visual_dim: int,
        mel_dim: int = 80,
        lstm_hidden: int = 512,
        prenet_hidden: int = 256,
    ):
        super().__init__()
        self.mel_dim = mel_dim
        self.lstm_hidden = lstm_hidden

        self.prenet = _PreNet(mel_dim, hidden=prenet_hidden)

        # Attention LSTM: takes (prenet_out ⊕ context) as input
        self.att_rnn = nn.LSTMCell(prenet_hidden + visual_dim, lstm_hidden)

        # Decoder LSTM: takes (att_hidden ⊕ context) as input
        self.dec_rnn = nn.LSTMCell(lstm_hidden + visual_dim, lstm_hidden)

        self.mel_proj = nn.Linear(lstm_hidden, mel_dim)
        self.stop_proj = nn.Linear(lstm_hidden, 1)

    # ------------------------------------------------------------------
    def _init_states(self, B: int, device: torch.device):
        z = lambda: torch.zeros(B, self.lstm_hidden, device=device)
        return z(), z(), z(), z()  # h_att, c_att, h_dec, c_dec

    # ------------------------------------------------------------------
    def forward(
        self,
        visual_features: torch.Tensor,
        mel_targets: torch.Tensor | None = None,
        teacher_forcing_ratio: float = 1.0,
    ):
        B, T_vis, _ = visual_features.shape
        device = visual_features.device

        # Simple context: mean of visual features across time.
        # (A full attention mechanism would dynamically weight each frame.)
        context = visual_features.mean(dim=1)  # (B, visual_dim)

        h_att, c_att, h_dec, c_dec = self._init_states(B, device)
        prev_mel = torch.zeros(B, self.mel_dim, device=device)

        mel_outputs, stop_outputs = [], []
        max_steps = (
            mel_targets.shape[1]
            if mel_targets is not None
            else T_vis * self.MAX_DECODE_RATIO
        )

        for step in range(max_steps):
            # Teacher forcing: use ground-truth frame or last prediction
            if (
                mel_targets is not None
                and step > 0
                and random.random() < teacher_forcing_ratio
            ):
                prev_mel = mel_targets[:, step - 1, :]

            prenet_out = self.prenet(prev_mel)                          # (B, 256)
            att_in = torch.cat([prenet_out, context], dim=-1)          # (B, 256+visual_dim)
            h_att, c_att = self.att_rnn(att_in, (h_att, c_att))

            dec_in = torch.cat([h_att, context], dim=-1)               # (B, 512+visual_dim)
            h_dec, c_dec = self.dec_rnn(dec_in, (h_dec, c_dec))

            mel_frame = self.mel_proj(h_dec)    # (B, mel_dim)
            stop_logit = self.stop_proj(h_dec)  # (B, 1)

            mel_outputs.append(mel_frame.unsqueeze(1))
            stop_outputs.append(stop_logit.unsqueeze(1))

            prev_mel = mel_frame

            # Early-stop during inference
            if mel_targets is None and torch.sigmoid(stop_logit).mean().item() > self.STOP_THRESHOLD:
                break

        mel_out = torch.cat(mel_outputs, dim=1)   # (B, T_mel, mel_dim)
        stop_out = torch.cat(stop_outputs, dim=1)  # (B, T_mel, 1)
        return mel_out, stop_out
