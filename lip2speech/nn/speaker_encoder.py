"""
Speaker Encoder — "Show Me Your Face, And I'll Tell You How You Speak" (Lip2Speech).

Takes a face image and produces a 256-dim L2-normalised speaker embedding that
encodes vocal identity (age, gender, ethnicity) without needing an audio sample.

Architecture: CNN backbone → GlobalAvgPool → FC(256) → L2-normalise.
Trained with GE2E / contrastive loss on (face-image, audio) pairs from AVSpeech.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class _ConvBlock(nn.Module):
    def __init__(self, in_ch, out_ch, stride=1):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, stride=stride, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )
        self.downsample = (
            nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 1, stride=stride, bias=False),
                nn.BatchNorm2d(out_ch),
            )
            if in_ch != out_ch or stride != 1
            else nn.Identity()
        )

    def forward(self, x):
        return F.relu(self.block(x) + self.downsample(x), inplace=True)


class SpeakerEncoder(nn.Module):
    """
    Encodes a face frame (3 × H × W) into a 256-dim speaker embedding.

    Input:  (B, 3, 96, 96)  — normalised face crop
    Output: (B, embedding_dim) — L2-normalised embedding
    """

    def __init__(self, embedding_dim: int = 256):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(3, 32, 3, padding=1, bias=False),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
        )
        self.backbone = nn.Sequential(
            _ConvBlock(32, 64, stride=2),   # 96→48
            _ConvBlock(64, 128, stride=2),  # 48→24
            _ConvBlock(128, 256, stride=2), # 24→12
            _ConvBlock(256, 256, stride=2), # 12→6
            nn.AdaptiveAvgPool2d(1),
        )
        self.projector = nn.Sequential(
            nn.Flatten(),
            nn.Linear(256, embedding_dim),
        )
        self.embedding_dim = embedding_dim

    def forward(self, face: torch.Tensor) -> torch.Tensor:
        """
        Args:
            face: (B, 3, H, W) face image, values in [0, 1] or normalised.
        Returns:
            (B, embedding_dim) L2-normalised speaker embedding.
        """
        x = self.stem(face)
        x = self.backbone(x)
        emb = self.projector(x)
        return F.normalize(emb, p=2, dim=1)
