"""Transformer baseline trainers for financial time-series classification.

This module provides practical baseline implementations for:
- PatchTST-like encoder
- MTST-like multi-resolution encoder
- TFT-like temporal fusion encoder

The goal is reproducible benchmarking for roadmap tasks, not full research
parity with original papers.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

ID_COLUMNS = {"symbol", "t_index", "future_return"}
MULTIMODAL_KEYWORDS = (
    "sentiment",
    "finbert",
    "news",
    "cot",
    "commitment",
    "foreign",
    "horizon",
    "macro",
)


@dataclass
class SequenceSplit:
    """Prepared sequence split used by transformer baseline trainers."""

    x_train: np.ndarray
    y_train: np.ndarray
    x_val: np.ndarray
    y_val: np.ndarray
    x_test: np.ndarray
    y_test: np.ndarray
    feature_columns: List[str]
    label_to_index: Dict[int, int]
    index_to_label: Dict[int, int]
    normalization_mean: np.ndarray
    normalization_std: np.ndarray


class TimeSeriesTensorDataset:  # Lazy import torch-compatible dataset
    """Simple dataset that yields (sequence, label) tensors."""

    def __init__(self, x: np.ndarray, y: np.ndarray) -> None:
        import torch

        self._x = torch.tensor(x, dtype=torch.float32)
        self._y = torch.tensor(y, dtype=torch.long)

    def __len__(self) -> int:
        return int(self._x.shape[0])

    def __getitem__(self, idx: int):
        return self._x[idx], self._y[idx]


def set_global_seed(seed: int) -> None:
    """Set deterministic seeds for python, numpy, and torch (if available)."""

    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def _prepare_feature_frame(
    df: pd.DataFrame,
    target_col: str,
) -> pd.DataFrame:
    drop_cols = set(ID_COLUMNS)
    drop_cols.add(target_col)
    feature_df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore").copy()

    for col in feature_df.columns:
        if pd.api.types.is_bool_dtype(feature_df[col]):
            feature_df[col] = feature_df[col].astype(int)
        elif not pd.api.types.is_numeric_dtype(feature_df[col]):
            feature_df[col] = feature_df[col].astype("category").cat.codes.astype(float)

    feature_df = (
        feature_df
        .replace([np.inf, -np.inf], np.nan)
        .ffill()
        .bfill()
        .fillna(0.0)
        .astype(np.float32)
    )
    return feature_df


def prepare_sequence_data(
    df: pd.DataFrame,
    target_col: str = "label",
    group_col: str = "symbol",
    time_col: str = "t_index",
    seq_len: int = 32,
    test_size: float = 0.2,
    purge_gap: int = 5,
    val_size: float = 0.1,
) -> SequenceSplit:
    """Convert tabular labelled rows into chronological sequence tensors."""

    if target_col not in df.columns:
        raise RuntimeError(f"{target_col} not found in dataset")
    if seq_len < 2:
        raise RuntimeError("seq_len must be >= 2")

    work = df.copy()
    if group_col not in work.columns:
        work[group_col] = "__single__"
    if time_col not in work.columns:
        work[time_col] = np.arange(len(work), dtype=int)

    work["_global_position"] = np.arange(len(work), dtype=int)
    work = work.sort_values([group_col, time_col, "_global_position"], kind="mergesort").reset_index(drop=True)

    feature_df = _prepare_feature_frame(work, target_col=target_col)
    raw_labels = work[target_col].to_numpy()

    unique_labels = sorted(int(v) for v in np.unique(raw_labels))
    label_to_index = {label: idx for idx, label in enumerate(unique_labels)}
    index_to_label = {idx: label for label, idx in label_to_index.items()}
    encoded_labels = np.array([label_to_index[int(v)] for v in raw_labels], dtype=np.int64)

    sequences: List[np.ndarray] = []
    targets: List[int] = []
    positions: List[int] = []

    for _, g in work.groupby(group_col, sort=False):
        g_idx = g.index.to_numpy()
        if len(g_idx) < seq_len:
            continue

        g_features = feature_df.iloc[g_idx].to_numpy(dtype=np.float32)
        g_labels = encoded_labels[g_idx]
        g_positions = g["_global_position"].to_numpy(dtype=np.int64)

        for end in range(seq_len - 1, len(g_idx)):
            start = end - seq_len + 1
            sequences.append(g_features[start : end + 1])
            targets.append(int(g_labels[end]))
            positions.append(int(g_positions[end]))

    if not sequences:
        raise RuntimeError(
            "No sequence samples generated. Increase dataset size or reduce seq_len."
        )

    x_all = np.stack(sequences).astype(np.float32)
    y_all = np.array(targets, dtype=np.int64)
    pos_all = np.array(positions, dtype=np.int64)

    order = np.argsort(pos_all)
    x_all = x_all[order]
    y_all = y_all[order]

    n_samples = int(x_all.shape[0])
    split_idx = int(n_samples * (1.0 - float(test_size)))
    if split_idx <= 1 or split_idx >= n_samples:
        raise RuntimeError("Invalid split boundary for sequence dataset")

    test_start = min(n_samples, split_idx + max(0, int(purge_gap)))
    if test_start >= n_samples:
        test_start = split_idx

    x_train_all = x_all[:split_idx]
    y_train_all = y_all[:split_idx]
    x_test = x_all[test_start:]
    y_test = y_all[test_start:]

    if len(x_test) == 0:
        x_test = x_all[split_idx:]
        y_test = y_all[split_idx:]

    val_count = int(len(x_train_all) * float(val_size))
    if val_count < 1 and len(x_train_all) >= 20:
        val_count = 1

    if val_count > 0 and (len(x_train_all) - val_count) >= 1:
        x_train = x_train_all[:-val_count]
        y_train = y_train_all[:-val_count]
        x_val = x_train_all[-val_count:]
        y_val = y_train_all[-val_count:]
    else:
        x_train = x_train_all
        y_train = y_train_all
        x_val = x_test
        y_val = y_test

    mean = x_train.mean(axis=(0, 1), keepdims=True)
    std = x_train.std(axis=(0, 1), keepdims=True)
    std = np.where(std < 1e-6, 1.0, std)

    x_train = ((x_train - mean) / std).astype(np.float32)
    x_val = ((x_val - mean) / std).astype(np.float32)
    x_test = ((x_test - mean) / std).astype(np.float32)

    return SequenceSplit(
        x_train=x_train,
        y_train=y_train,
        x_val=x_val,
        y_val=y_val,
        x_test=x_test,
        y_test=y_test,
        feature_columns=list(feature_df.columns),
        label_to_index=label_to_index,
        index_to_label=index_to_label,
        normalization_mean=mean.astype(np.float32),
        normalization_std=std.astype(np.float32),
    )


def _extract_patches(x, patch_size: int, stride: int):
    """Extract flattened patch tokens from [B, T, F] tensor."""

    import torch

    batch_size, time_steps, feat_dim = x.shape
    if time_steps < patch_size:
        pad_len = patch_size - time_steps
        pad = x[:, :1, :].repeat(1, pad_len, 1)
        x = torch.cat([pad, x], dim=1)
        time_steps = x.shape[1]

    patches = []
    for start in range(0, time_steps - patch_size + 1, stride):
        window = x[:, start : start + patch_size, :]
        patches.append(window.reshape(batch_size, patch_size * feat_dim))

    if not patches:
        window = x[:, -patch_size:, :]
        patches.append(window.reshape(batch_size, patch_size * feat_dim))

    return torch.stack(patches, dim=1)


def infer_feature_partitions(feature_columns: Sequence[str]) -> Dict[str, List[int]]:
    """Infer technical vs context feature partitions for fusion models."""

    context_indices: List[int] = []
    for idx, name in enumerate(feature_columns):
        col = str(name).lower()
        if any(token in col for token in MULTIMODAL_KEYWORDS):
            context_indices.append(idx)

    technical_indices = [idx for idx in range(len(feature_columns)) if idx not in context_indices]
    if not technical_indices:
        technical_indices = list(range(len(feature_columns)))
        context_indices = []

    return {
        "technical_indices": technical_indices,
        "context_indices": context_indices,
    }


class _PatchEncoderBranch:
    """Shared branch logic for patch-based transformer encoders."""

    def __init__(
        self,
        input_dim: int,
        patch_size: int,
        patch_stride: int,
        d_model: int,
        n_heads: int,
        n_layers: int,
        dropout: float,
    ) -> None:
        import torch.nn as nn

        self.patch_size = patch_size
        self.patch_stride = patch_stride
        self.input_projection = nn.Linear(patch_size * input_dim, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_model * 4,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        self.norm = nn.LayerNorm(d_model)

    def modules(self):
        return [self.input_projection, self.encoder, self.norm]

    def forward(self, x):
        patches = _extract_patches(x, patch_size=self.patch_size, stride=self.patch_stride)
        tokens = self.input_projection(patches)
        encoded = self.encoder(tokens)
        pooled = self.norm(encoded.mean(dim=1))
        return pooled


class PatchTSTBaseline:
    """PatchTST-inspired baseline classifier."""

    def __init__(
        self,
        input_dim: int,
        num_classes: int,
        patch_size: int = 8,
        patch_stride: int = 4,
        d_model: int = 128,
        n_heads: int = 4,
        n_layers: int = 2,
        dropout: float = 0.1,
    ) -> None:
        import torch.nn as nn

        super().__init__()
        self.branch = _PatchEncoderBranch(
            input_dim=input_dim,
            patch_size=patch_size,
            patch_stride=patch_stride,
            d_model=d_model,
            n_heads=n_heads,
            n_layers=n_layers,
            dropout=dropout,
        )
        self.classifier = nn.Linear(d_model, num_classes)

    def parameters(self):
        modules = self.branch.modules() + [self.classifier]
        for module in modules:
            for param in module.parameters():
                yield param

    def to(self, device):
        for module in self.branch.modules() + [self.classifier]:
            module.to(device)
        return self

    def train(self):
        for module in self.branch.modules() + [self.classifier]:
            module.train()

    def eval(self):
        for module in self.branch.modules() + [self.classifier]:
            module.eval()

    def state_dict(self):
        state = {}
        for i, module in enumerate(self.branch.modules() + [self.classifier]):
            state[f"module_{i}"] = module.state_dict()
        return state

    def load_state_dict(self, state):
        for i, module in enumerate(self.branch.modules() + [self.classifier]):
            module.load_state_dict(state[f"module_{i}"])

    def __call__(self, x):
        pooled = self.branch.forward(x)
        return self.classifier(pooled)


class MTSTBaseline:
    """MTST-inspired baseline with multi-resolution patch branches."""

    def __init__(
        self,
        input_dim: int,
        num_classes: int,
        patch_sizes: Sequence[int],
        patch_stride: int = 4,
        d_model: int = 96,
        n_heads: int = 4,
        n_layers: int = 2,
        dropout: float = 0.1,
    ) -> None:
        import torch.nn as nn

        super().__init__()
        safe_patch_sizes = [int(p) for p in patch_sizes if int(p) >= 2]
        if not safe_patch_sizes:
            safe_patch_sizes = [4, 8, 16]

        self.branches = [
            _PatchEncoderBranch(
                input_dim=input_dim,
                patch_size=patch,
                patch_stride=patch_stride,
                d_model=d_model,
                n_heads=n_heads,
                n_layers=n_layers,
                dropout=dropout,
            )
            for patch in safe_patch_sizes
        ]
        self.fusion_norm = nn.LayerNorm(d_model * len(self.branches))
        self.classifier = nn.Linear(d_model * len(self.branches), num_classes)

    def parameters(self):
        modules = [self.fusion_norm, self.classifier]
        for branch in self.branches:
            modules.extend(branch.modules())
        for module in modules:
            for param in module.parameters():
                yield param

    def to(self, device):
        for branch in self.branches:
            for module in branch.modules():
                module.to(device)
        self.fusion_norm.to(device)
        self.classifier.to(device)
        return self

    def train(self):
        for branch in self.branches:
            for module in branch.modules():
                module.train()
        self.fusion_norm.train()
        self.classifier.train()

    def eval(self):
        for branch in self.branches:
            for module in branch.modules():
                module.eval()
        self.fusion_norm.eval()
        self.classifier.eval()

    def state_dict(self):
        state = {
            "fusion_norm": self.fusion_norm.state_dict(),
            "classifier": self.classifier.state_dict(),
        }
        for i, branch in enumerate(self.branches):
            for j, module in enumerate(branch.modules()):
                state[f"branch_{i}_module_{j}"] = module.state_dict()
        return state

    def load_state_dict(self, state):
        self.fusion_norm.load_state_dict(state["fusion_norm"])
        self.classifier.load_state_dict(state["classifier"])
        for i, branch in enumerate(self.branches):
            for j, module in enumerate(branch.modules()):
                module.load_state_dict(state[f"branch_{i}_module_{j}"])

    def __call__(self, x):
        import torch

        pooled = [branch.forward(x) for branch in self.branches]
        fused = torch.cat(pooled, dim=1)
        fused = self.fusion_norm(fused)
        return self.classifier(fused)


class TFTBaseline:
    """TFT-inspired baseline with variable gating, LSTM, and attention."""

    def __init__(
        self,
        input_dim: int,
        num_classes: int,
        hidden_dim: int = 128,
        n_heads: int = 4,
        dropout: float = 0.1,
    ) -> None:
        import torch.nn as nn

        super().__init__()
        self.variable_selector = nn.Sequential(
            nn.Linear(input_dim, input_dim),
            nn.Sigmoid(),
        )
        self.input_projection = nn.Linear(input_dim, hidden_dim)
        self.temporal_encoder = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            dropout=0.0,
            batch_first=True,
        )
        self.temporal_attention = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=n_heads,
            dropout=dropout,
            batch_first=True,
        )
        self.grn = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.gate = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.Sigmoid(),
        )
        self.norm = nn.LayerNorm(hidden_dim)
        self.classifier = nn.Linear(hidden_dim, num_classes)

    def parameters(self):
        modules = [
            self.variable_selector,
            self.input_projection,
            self.temporal_encoder,
            self.temporal_attention,
            self.grn,
            self.gate,
            self.norm,
            self.classifier,
        ]
        for module in modules:
            for param in module.parameters():
                yield param

    def to(self, device):
        for module in [
            self.variable_selector,
            self.input_projection,
            self.temporal_encoder,
            self.temporal_attention,
            self.grn,
            self.gate,
            self.norm,
            self.classifier,
        ]:
            module.to(device)
        return self

    def train(self):
        for module in [
            self.variable_selector,
            self.input_projection,
            self.temporal_encoder,
            self.temporal_attention,
            self.grn,
            self.gate,
            self.norm,
            self.classifier,
        ]:
            module.train()

    def eval(self):
        for module in [
            self.variable_selector,
            self.input_projection,
            self.temporal_encoder,
            self.temporal_attention,
            self.grn,
            self.gate,
            self.norm,
            self.classifier,
        ]:
            module.eval()

    def state_dict(self):
        return {
            "variable_selector": self.variable_selector.state_dict(),
            "input_projection": self.input_projection.state_dict(),
            "temporal_encoder": self.temporal_encoder.state_dict(),
            "temporal_attention": self.temporal_attention.state_dict(),
            "grn": self.grn.state_dict(),
            "gate": self.gate.state_dict(),
            "norm": self.norm.state_dict(),
            "classifier": self.classifier.state_dict(),
        }

    def load_state_dict(self, state):
        self.variable_selector.load_state_dict(state["variable_selector"])
        self.input_projection.load_state_dict(state["input_projection"])
        self.temporal_encoder.load_state_dict(state["temporal_encoder"])
        self.temporal_attention.load_state_dict(state["temporal_attention"])
        self.grn.load_state_dict(state["grn"])
        self.gate.load_state_dict(state["gate"])
        self.norm.load_state_dict(state["norm"])
        self.classifier.load_state_dict(state["classifier"])

    def __call__(self, x):
        weights = self.variable_selector(x)
        selected = x * weights
        projected = self.input_projection(selected)
        encoded, _ = self.temporal_encoder(projected)
        attended, _ = self.temporal_attention(encoded, encoded, encoded, need_weights=False)
        pooled = attended.mean(dim=1)
        transformed = self.grn(pooled)
        gate = self.gate(pooled)
        fused = gate * transformed + (1.0 - gate) * pooled
        fused = self.norm(fused)
        return self.classifier(fused)


class CrossModalFusionBaseline:
    """Cross-modal attention fusion baseline for technical + contextual signals."""

    def __init__(
        self,
        input_dim: int,
        num_classes: int,
        technical_indices: Optional[Sequence[int]] = None,
        context_indices: Optional[Sequence[int]] = None,
        d_model: int = 128,
        n_heads: int = 4,
        n_layers: int = 2,
        dropout: float = 0.1,
    ) -> None:
        import torch.nn as nn

        super().__init__()
        technical = list(technical_indices or list(range(input_dim)))
        context = list(context_indices or [])
        if not technical:
            technical = list(range(input_dim))
            context = []

        self.technical_indices = technical
        self.context_indices = context
        self.use_context = len(self.context_indices) > 0

        self.tech_projection = nn.Linear(len(self.technical_indices), d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_model * 4,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
        )
        self.tech_encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        self.tech_norm = nn.LayerNorm(d_model)

        if self.use_context:
            self.context_projection = nn.Sequential(
                nn.Linear(len(self.context_indices), d_model),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(d_model, d_model),
            )
            self.cross_attention = nn.MultiheadAttention(
                embed_dim=d_model,
                num_heads=n_heads,
                dropout=dropout,
                batch_first=True,
            )
            self.fusion_gate = nn.Sequential(
                nn.Linear(d_model * 2, d_model),
                nn.GELU(),
                nn.Linear(d_model, d_model),
                nn.Sigmoid(),
            )
        else:
            self.context_projection = nn.Sequential(nn.Identity())
            self.cross_attention = nn.MultiheadAttention(
                embed_dim=d_model,
                num_heads=n_heads,
                dropout=dropout,
                batch_first=True,
            )
            self.fusion_gate = nn.Sequential(nn.Identity())

        self.output_norm = nn.LayerNorm(d_model)
        self.classifier = nn.Linear(d_model, num_classes)

    def _modules(self):
        modules = [self.tech_projection, self.tech_encoder, self.tech_norm]
        if self.use_context:
            modules.extend([
                self.context_projection,
                self.cross_attention,
                self.fusion_gate,
            ])
        modules.extend([self.output_norm, self.classifier])
        return modules

    def parameters(self):
        for module in self._modules():
            for param in module.parameters():
                yield param

    def to(self, device):
        for module in self._modules():
            module.to(device)
        return self

    def train(self):
        for module in self._modules():
            module.train()

    def eval(self):
        for module in self._modules():
            module.eval()

    def state_dict(self):
        state = {
            "technical_indices": list(self.technical_indices),
            "context_indices": list(self.context_indices),
            "tech_projection": self.tech_projection.state_dict(),
            "tech_encoder": self.tech_encoder.state_dict(),
            "tech_norm": self.tech_norm.state_dict(),
            "output_norm": self.output_norm.state_dict(),
            "classifier": self.classifier.state_dict(),
        }
        if self.use_context:
            state.update(
                {
                    "context_projection": self.context_projection.state_dict(),
                    "cross_attention": self.cross_attention.state_dict(),
                    "fusion_gate": self.fusion_gate.state_dict(),
                }
            )
        return state

    def load_state_dict(self, state):
        self.technical_indices = list(state.get("technical_indices", self.technical_indices))
        self.context_indices = list(state.get("context_indices", self.context_indices))
        self.tech_projection.load_state_dict(state["tech_projection"])
        self.tech_encoder.load_state_dict(state["tech_encoder"])
        self.tech_norm.load_state_dict(state["tech_norm"])
        self.output_norm.load_state_dict(state["output_norm"])
        self.classifier.load_state_dict(state["classifier"])

        if self.use_context and "context_projection" in state:
            self.context_projection.load_state_dict(state["context_projection"])
            self.cross_attention.load_state_dict(state["cross_attention"])
            self.fusion_gate.load_state_dict(state["fusion_gate"])

    def __call__(self, x):
        import torch

        technical_x = x[:, :, self.technical_indices]
        technical_tokens = self.tech_projection(technical_x)
        technical_encoded = self.tech_encoder(technical_tokens)
        technical_repr = self.tech_norm(technical_encoded.mean(dim=1))

        fused = technical_repr
        if self.use_context:
            context_x = x[:, :, self.context_indices]
            context_summary = context_x.mean(dim=1)
            context_token = self.context_projection(context_summary).unsqueeze(1)

            query = technical_repr.unsqueeze(1)
            attended, _ = self.cross_attention(
                query,
                context_token,
                context_token,
                need_weights=False,
            )
            attended_repr = attended.squeeze(1)
            gate_input = torch.cat([technical_repr, attended_repr], dim=1)
            gate = self.fusion_gate(gate_input)
            fused = gate * attended_repr + (1.0 - gate) * technical_repr

        fused = self.output_norm(fused)
        return self.classifier(fused)


def build_baseline_model(
    architecture: str,
    input_dim: int,
    num_classes: int,
    feature_columns: Optional[Sequence[str]] = None,
    technical_indices: Optional[Sequence[int]] = None,
    context_indices: Optional[Sequence[int]] = None,
    patch_sizes: Optional[Sequence[int]] = None,
    patch_stride: int = 4,
    d_model: int = 128,
    n_heads: int = 4,
    n_layers: int = 2,
    dropout: float = 0.1,
):
    arch = architecture.strip().lower()
    if arch == "patchtst":
        return PatchTSTBaseline(
            input_dim=input_dim,
            num_classes=num_classes,
            patch_size=(patch_sizes or [8])[0],
            patch_stride=patch_stride,
            d_model=d_model,
            n_heads=n_heads,
            n_layers=n_layers,
            dropout=dropout,
        )
    if arch == "mtst":
        return MTSTBaseline(
            input_dim=input_dim,
            num_classes=num_classes,
            patch_sizes=patch_sizes or [4, 8, 16],
            patch_stride=patch_stride,
            d_model=max(64, d_model // 2),
            n_heads=n_heads,
            n_layers=n_layers,
            dropout=dropout,
        )
    if arch == "tft":
        return TFTBaseline(
            input_dim=input_dim,
            num_classes=num_classes,
            hidden_dim=d_model,
            n_heads=n_heads,
            dropout=dropout,
        )
    if arch in {"fusion", "cross_modal_fusion", "crossmodal", "cmf"}:
        tech_idx = list(technical_indices or [])
        ctx_idx = list(context_indices or [])

        if (not tech_idx) and feature_columns:
            parts = infer_feature_partitions(feature_columns)
            tech_idx = parts["technical_indices"]
            ctx_idx = parts["context_indices"]

        return CrossModalFusionBaseline(
            input_dim=input_dim,
            num_classes=num_classes,
            technical_indices=tech_idx,
            context_indices=ctx_idx,
            d_model=d_model,
            n_heads=n_heads,
            n_layers=n_layers,
            dropout=dropout,
        )
    raise RuntimeError(f"Unsupported architecture: {architecture}")


def _train_one_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0.0
    total_batches = 0
    for xb, yb in loader:
        xb = xb.to(device)
        yb = yb.to(device)

        optimizer.zero_grad(set_to_none=True)
        logits = model(xb)
        loss = criterion(logits, yb)
        loss.backward()
        optimizer.step()

        total_loss += float(loss.item())
        total_batches += 1

    if total_batches == 0:
        return 0.0
    return total_loss / total_batches


def _evaluate(model, loader, criterion, device):
    import torch

    model.eval()
    total_loss = 0.0
    total_batches = 0
    logits_list: List[np.ndarray] = []
    labels_list: List[np.ndarray] = []

    with torch.no_grad():
        for xb, yb in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            logits = model(xb)
            loss = criterion(logits, yb)

            total_loss += float(loss.item())
            total_batches += 1
            logits_list.append(logits.cpu().numpy())
            labels_list.append(yb.cpu().numpy())

    mean_loss = (total_loss / total_batches) if total_batches else 0.0
    if logits_list:
        logits_np = np.concatenate(logits_list, axis=0)
        labels_np = np.concatenate(labels_list, axis=0)
    else:
        logits_np = np.empty((0, 0), dtype=np.float32)
        labels_np = np.empty((0,), dtype=np.int64)

    return mean_loss, logits_np, labels_np


def _classification_metrics(y_true: np.ndarray, logits: np.ndarray) -> Dict:
    from sklearn.metrics import accuracy_score, classification_report, f1_score, roc_auc_score

    if len(y_true) == 0 or logits.size == 0:
        return {
            "accuracy": 0.0,
            "f1_macro": 0.0,
            "f1_weighted": 0.0,
            "roc_auc_ovr_weighted": None,
            "classification_report": {},
        }

    logits = np.asarray(logits)
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp_scores = np.exp(shifted)
    probs = exp_scores / np.clip(exp_scores.sum(axis=1, keepdims=True), a_min=1e-8, a_max=None)
    y_pred = probs.argmax(axis=1)

    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "classification_report": classification_report(y_true, y_pred, output_dict=True, zero_division=0),
    }

    try:
        if probs.shape[1] > 2:
            auc_value = roc_auc_score(
                y_true,
                probs,
                multi_class="ovr",
                average="weighted",
            )
        else:
            auc_value = roc_auc_score(y_true, probs[:, 1])
        metrics["roc_auc_ovr_weighted"] = float(auc_value)
    except Exception:
        metrics["roc_auc_ovr_weighted"] = None

    return metrics


def train_transformer_baseline(
    dataset_csv: str,
    architecture: str,
    model_out: str,
    target_col: str = "label",
    seq_len: int = 32,
    epochs: int = 10,
    batch_size: int = 64,
    learning_rate: float = 1e-3,
    test_size: float = 0.2,
    purge_gap: int = 5,
    patch_sizes: Optional[Sequence[int]] = None,
    patch_stride: int = 4,
    d_model: int = 128,
    n_heads: int = 4,
    n_layers: int = 2,
    dropout: float = 0.1,
    random_state: int = 42,
    device: Optional[str] = None,
    patience: int = 3,
) -> Dict:
    """Train one transformer baseline and persist checkpoint + metrics."""

    import torch

    if not os.path.exists(dataset_csv):
        raise RuntimeError(f"Dataset not found: {dataset_csv}")

    set_global_seed(random_state)

    df = pd.read_csv(dataset_csv)
    split = prepare_sequence_data(
        df,
        target_col=target_col,
        seq_len=seq_len,
        test_size=test_size,
        purge_gap=purge_gap,
    )

    input_dim = int(split.x_train.shape[-1])
    num_classes = int(len(split.label_to_index))
    if num_classes < 2:
        raise RuntimeError("Need at least 2 classes for baseline classification")

    resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    device_obj = torch.device(resolved_device)

    model = build_baseline_model(
        architecture=architecture,
        input_dim=input_dim,
        num_classes=num_classes,
        feature_columns=split.feature_columns,
        patch_sizes=patch_sizes,
        patch_stride=patch_stride,
        d_model=d_model,
        n_heads=n_heads,
        n_layers=n_layers,
        dropout=dropout,
    ).to(device_obj)

    train_dataset = TimeSeriesTensorDataset(split.x_train, split.y_train)
    val_dataset = TimeSeriesTensorDataset(split.x_val, split.y_val)
    test_dataset = TimeSeriesTensorDataset(split.x_test, split.y_test)

    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    class_counts = np.bincount(split.y_train, minlength=num_classes)
    class_weights = len(split.y_train) / np.maximum(class_counts, 1)
    class_weights = class_weights / class_weights.sum() * num_classes

    criterion = torch.nn.CrossEntropyLoss(
        weight=torch.tensor(class_weights, dtype=torch.float32, device=device_obj)
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)

    best_state = None
    best_val_loss = float("inf")
    epochs_without_improvement = 0
    history: List[Dict] = []

    for epoch in range(1, max(1, int(epochs)) + 1):
        train_loss = _train_one_epoch(model, train_loader, optimizer, criterion, device_obj)
        val_loss, _, _ = _evaluate(model, val_loader, criterion, device_obj)

        history.append({
            "epoch": epoch,
            "train_loss": float(train_loss),
            "val_loss": float(val_loss),
        })

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = model.state_dict()
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= max(1, int(patience)):
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    test_loss, test_logits, test_labels = _evaluate(model, test_loader, criterion, device_obj)
    metrics = _classification_metrics(test_labels, test_logits)

    os.makedirs(os.path.dirname(model_out) or ".", exist_ok=True)
    checkpoint = {
        "architecture": architecture.lower(),
        "input_dim": input_dim,
        "num_classes": num_classes,
        "feature_columns": split.feature_columns,
        "label_to_index": split.label_to_index,
        "index_to_label": split.index_to_label,
        "state_dict": model.state_dict(),
        "normalization_mean": split.normalization_mean.squeeze(0).squeeze(0).tolist(),
        "normalization_std": split.normalization_std.squeeze(0).squeeze(0).tolist(),
        "train_config": {
            "seq_len": int(seq_len),
            "epochs": int(epochs),
            "batch_size": int(batch_size),
            "learning_rate": float(learning_rate),
            "test_size": float(test_size),
            "purge_gap": int(purge_gap),
            "patch_sizes": list(patch_sizes or []),
            "patch_stride": int(patch_stride),
            "d_model": int(d_model),
            "n_heads": int(n_heads),
            "n_layers": int(n_layers),
            "dropout": float(dropout),
            "random_state": int(random_state),
            "device": resolved_device,
        },
        "history": history,
        "metrics": {
            **metrics,
            "test_loss": float(test_loss),
            "best_val_loss": float(best_val_loss),
        },
    }
    torch.save(checkpoint, model_out)

    return {
        "architecture": architecture.lower(),
        "model_path": model_out,
        "metrics": checkpoint["metrics"],
        "history": history,
        "num_samples": {
            "train": int(len(split.x_train)),
            "val": int(len(split.x_val)),
            "test": int(len(split.x_test)),
        },
        "feature_count": int(input_dim),
        "num_classes": int(num_classes),
    }


def train_transformer_baselines(
    dataset_csv: str,
    architectures: Optional[Sequence[str]] = None,
    model_dir: str = "models/transformers",
    report_out: Optional[str] = "models/transformers/baseline_report.json",
    continue_on_error: bool = True,
    **train_kwargs,
) -> Dict:
    """Train multiple transformer baselines and write a summary report."""

    architecture_list = list(architectures or ["patchtst", "mtst", "tft"])
    os.makedirs(model_dir, exist_ok=True)

    results: Dict[str, Dict] = {}
    for architecture in architecture_list:
        model_path = os.path.join(model_dir, f"{architecture.lower()}_baseline.pt")
        try:
            result = train_transformer_baseline(
                dataset_csv=dataset_csv,
                architecture=architecture,
                model_out=model_path,
                **train_kwargs,
            )
            results[architecture.lower()] = result
        except Exception as exc:
            if not continue_on_error:
                raise
            results[architecture.lower()] = {
                "architecture": architecture.lower(),
                "model_path": model_path,
                "error": str(exc),
            }

    summary = {
        "dataset_csv": dataset_csv,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "architectures": architecture_list,
        "results": results,
    }

    if report_out:
        os.makedirs(os.path.dirname(report_out) or ".", exist_ok=True)
        with open(report_out, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)

    return summary


__all__ = [
    "infer_feature_partitions",
    "prepare_sequence_data",
    "train_transformer_baseline",
    "train_transformer_baselines",
    "build_baseline_model",
]
