"""
3-D Lower-Face Encoder — "Show Me Your Face, And I'll Tell You How You Speak".

Processes a temporal sequence of grayscale lip-ROI crops with 3-D convolutions
to capture spatio-temporal articulation features, then projects each frame to a
fixed-size feature vector.

Architecture mirrors the paper's description:
  3-D Conv → BN → ReLU → MaxPool  (repeated)  → temporal FC projection.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class LipEncoder(nn.Module):
    """
    Encodes a sequence of lip crops into per-frame feature vectors.

    Input:  (B, T, H, W)  — grayscale lip ROI sequence, values in [0, 1]
    Output: (B, T, feature_dim)
    """

    def __init__(self, feature_dim: int = 256):
        super().__init__()

        # 3-D convolutions treat the temporal axis as depth.
        # Input channel = 1 (grayscale).
        self.conv3d = nn.Sequential(
            # Stage 1 — large spatial kernel to capture lip shape
            nn.Conv3d(1, 32, kernel_size=(3, 5, 5), padding=(1, 2, 2), bias=False),
            nn.BatchNorm3d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool3d(kernel_size=(1, 2, 2)),  # spatial ÷2, time unchanged

            # Stage 2
            nn.Conv3d(32, 64, kernel_size=(3, 3, 3), padding=(1, 1, 1), bias=False),
            nn.BatchNorm3d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool3d(kernel_size=(1, 2, 2)),

            # Stage 3
            nn.Conv3d(64, 128, kernel_size=(3, 3, 3), padding=(1, 1, 1), bias=False),
            nn.BatchNorm3d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool3d(kernel_size=(1, 2, 2)),

            # Stage 4 — reduce to 256 channels
            nn.Conv3d(128, 256, kernel_size=(3, 3, 3), padding=(1, 1, 1), bias=False),
            nn.BatchNorm3d(256),
            nn.ReLU(inplace=True),

            # Pool spatial dims away; keep temporal dimension.
            nn.AdaptiveAvgPool3d((None, 1, 1)),
        )

        self.temporal_fc = nn.Linear(256, feature_dim)
        self.feature_dim = feature_dim

    def forward(self, lips: torch.Tensor) -> torch.Tensor:
        """
        Args:
            lips: (B, T, H, W) grayscale lip crops.
        Returns:
            (B, T, feature_dim) per-frame features.
        """
        B, T, H, W = lips.shape
        x = lips.unsqueeze(1)                 # (B, 1, T, H, W)
        x = self.conv3d(x)                    # (B, 256, T, 1, 1)
        x = x.squeeze(-1).squeeze(-1)         # (B, 256, T)
        x = x.permute(0, 2, 1)               # (B, T, 256)
        return self.temporal_fc(x)            # (B, T, feature_dim)
