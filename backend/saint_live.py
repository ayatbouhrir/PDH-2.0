from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, StandardScaler

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
except ImportError as exc:
    raise RuntimeError(
        "PyTorch est requis pour saint_live.py. Installe torch avant d'utiliser SAINT live."
    ) from exc


PreprocessingType = Literal["none", "standardize", "normalize"]


@dataclass
class SaintLiveConfig:
    embedding_dim: int = 8
    depth: int = 2
    heads: int = 2
    ff_mult: int = 4
    dropout: float = 0.1
    hidden_dim: int = 64
    batch_size: int = 512
    epochs: int = 8
    learning_rate: float = 1e-3
    weight_decay: float = 1e-5
    mask_prob: float = 0.15
    log1p_transform: bool = True
    clip_negative_to_zero: bool = True
    use_cache: bool = True
    cache_dir: str = str(Path(__file__).resolve().parents[1] / ".local/cache/saint")
    seed: int = 42
    pooling: Literal["cls", "mean"] = "mean"
    verbose: bool = True


class ContinuousFeatureTokenizer(nn.Module):
    """
    Tokenisation continue-only :
    une petite MLP par feature scalaire.
    """

    def __init__(self, num_features: int, dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.num_features = num_features
        self.dim = dim
        self.mlps = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Linear(1, hidden_dim),
                    nn.ReLU(),
                    nn.Linear(hidden_dim, dim),
                )
                for _ in range(num_features)
            ]
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, F]
        tokens = []
        for i in range(self.num_features):
            xi = x[:, i : i + 1]  # [B, 1]
            ti = self.mlps[i](xi)  # [B, dim]
            tokens.append(ti.unsqueeze(1))  # [B, 1, dim]
        return torch.cat(tokens, dim=1)  # [B, F, dim]


class ContinuousSaintEncoder(nn.Module):
    """
    SAINT-like encoder pour données continues uniquement.
    Pré-entraînement par masked reconstruction.
    """

    def __init__(
        self,
        num_features: int,
        dim: int = 8,
        depth: int = 2,
        heads: int = 2,
        ff_mult: int = 4,
        dropout: float = 0.1,
        hidden_dim: int = 64,
    ) -> None:
        super().__init__()

        self.num_features = num_features
        self.dim = dim

        self.tokenizer = ContinuousFeatureTokenizer(
            num_features=num_features,
            dim=dim,
            hidden_dim=hidden_dim,
        )

        self.cls_token = nn.Parameter(torch.zeros(1, 1, dim))
        self.pos_embedding = nn.Parameter(torch.zeros(1, num_features + 1, dim))
        self.input_dropout = nn.Dropout(dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=dim,
            nhead=heads,
            dim_feedforward=dim * ff_mult,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=depth)

        self.reconstruction_heads = nn.ModuleList(
            [nn.Linear(dim, 1) for _ in range(num_features)]
        )

        self._reset_parameters()

    def _reset_parameters(self) -> None:
        nn.init.normal_(self.cls_token, mean=0.0, std=0.02)
        nn.init.normal_(self.pos_embedding, mean=0.0, std=0.02)

        for head in self.reconstruction_heads:
            nn.init.xavier_uniform_(head.weight)
            if head.bias is not None:
                nn.init.zeros_(head.bias)

    def encode_tokens(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, F]
        feat_tokens = self.tokenizer(x)  # [B, F, dim]
        batch_size = feat_tokens.size(0)

        cls = self.cls_token.expand(batch_size, -1, -1)  # [B, 1, dim]
        tokens = torch.cat([cls, feat_tokens], dim=1)  # [B, F+1, dim]
        tokens = tokens + self.pos_embedding[:, : tokens.size(1), :]
        tokens = self.input_dropout(tokens)

        encoded = self.transformer(tokens)  # [B, F+1, dim]
        return encoded

    def reconstruct(self, x_masked: torch.Tensor) -> torch.Tensor:
        encoded = self.encode_tokens(x_masked)
        feat_encoded = encoded[:, 1:, :]  # [B, F, dim]

        preds = []
        for i, head in enumerate(self.reconstruction_heads):
            pi = head(feat_encoded[:, i, :])  # [B, 1]
            preds.append(pi)
        return torch.cat(preds, dim=1)  # [B, F]

    def embed(self, x: torch.Tensor, pooling: Literal["cls", "mean"] = "mean") -> torch.Tensor:
        encoded = self.encode_tokens(x)
        if pooling == "cls":
            return encoded[:, 0, :]  # [B, dim]
        return encoded[:, 1:, :].mean(dim=1)  # [B, dim]


def _set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _sanitize_matrix(
    df: pd.DataFrame,
    selected_pfas_cols: list[str],
    preprocessing: PreprocessingType,
    config: SaintLiveConfig,
) -> tuple[np.ndarray, dict]:
    missing = [c for c in selected_pfas_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes PFAS absentes du DataFrame: {missing[:10]}")

    x_df = df[selected_pfas_cols].copy()

    for col in selected_pfas_cols:
        x_df[col] = pd.to_numeric(x_df[col], errors="coerce")

    x_df = x_df.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    if config.clip_negative_to_zero:
        x_df = x_df.clip(lower=0.0)

    x = x_df.to_numpy(dtype=np.float32)

    if config.log1p_transform:
        x = np.log1p(x)

    scaler_info: dict = {"type": preprocessing}

    if preprocessing == "standardize":
        scaler = StandardScaler()
        x = scaler.fit_transform(x).astype(np.float32)
        scaler_info["mean"] = scaler.mean_.tolist()
        scaler_info["scale"] = scaler.scale_.tolist()

    elif preprocessing == "normalize":
        scaler = MinMaxScaler()
        x = scaler.fit_transform(x).astype(np.float32)
        scaler_info["min"] = scaler.min_.tolist()
        scaler_info["scale"] = scaler.scale_.tolist()

    elif preprocessing == "none":
        x = x.astype(np.float32)

    else:
        raise ValueError(f"Prétraitement non supporté: {preprocessing}")

    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
    return x, scaler_info


def _masked_reconstruction_loss(
    model: ContinuousSaintEncoder,
    batch_x: torch.Tensor,
    mask_prob: float,
) -> torch.Tensor:
    mask = (torch.rand_like(batch_x) < mask_prob)
    x_masked = batch_x.clone()
    x_masked[mask] = 0.0

    preds = model.reconstruct(x_masked)

    if mask.any():
        loss = ((preds[mask] - batch_x[mask]) ** 2).mean()
    else:
        loss = ((preds - batch_x) ** 2).mean()

    return loss


def _train_saint_live(
    x: np.ndarray,
    config: SaintLiveConfig,
    device: torch.device,
) -> tuple[ContinuousSaintEncoder, list[dict]]:
    num_rows, num_features = x.shape

    model = ContinuousSaintEncoder(
        num_features=num_features,
        dim=config.embedding_dim,
        depth=config.depth,
        heads=config.heads,
        ff_mult=config.ff_mult,
        dropout=config.dropout,
        hidden_dim=config.hidden_dim,
    ).to(device)

    dataset = TensorDataset(torch.from_numpy(x))
    batch_size = min(config.batch_size, max(32, num_rows))
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        drop_last=False,
    )

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )

    model.train()

    training_history: list[dict] = []

    for epoch in range(config.epochs):
        epoch_losses: list[float] = []

        for (batch_x,) in loader:
            batch_x = batch_x.to(device)

            optimizer.zero_grad(set_to_none=True)
            loss = _masked_reconstruction_loss(
                model=model,
                batch_x=batch_x,
                mask_prob=config.mask_prob,
            )
            loss.backward()
            optimizer.step()

            epoch_losses.append(float(loss.detach().cpu().item()))

        mean_loss = float(np.mean(epoch_losses)) if epoch_losses else 0.0
        training_history.append({
            "epoch": int(epoch + 1),
            "loss": mean_loss,
        })

        if config.verbose:
            print(f"[SAINT live] epoch {epoch + 1}/{config.epochs} - loss: {mean_loss:.6f}")

    return model, training_history


def _infer_embeddings(
    model: ContinuousSaintEncoder,
    x: np.ndarray,
    pooling: Literal["cls", "mean"],
    batch_size: int,
    device: torch.device,
) -> np.ndarray:
    model.eval()

    dataset = TensorDataset(torch.from_numpy(x))
    loader = DataLoader(
        dataset,
        batch_size=min(batch_size, max(32, len(x))),
        shuffle=False,
        drop_last=False,
    )

    outputs: list[np.ndarray] = []

    with torch.no_grad():
        for (batch_x,) in loader:
            batch_x = batch_x.to(device)
            emb = model.embed(batch_x, pooling=pooling)
            outputs.append(emb.detach().cpu().numpy())

    return np.vstack(outputs).astype(np.float32)


def _build_cache_key(
    point_ids: list[int] | None,
    selected_pfas_cols: list[str],
    preprocessing: str,
    config: SaintLiveConfig,
    n_rows: int,
) -> str:
    payload = {
        "point_ids": point_ids if point_ids is not None else f"n={n_rows}",
        "selected_pfas_cols": selected_pfas_cols,
        "preprocessing": preprocessing,
        "config": asdict(config),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _save_cache(
    cache_dir: Path,
    cache_key: str,
    point_ids: np.ndarray | None,
    embeddings: np.ndarray,
    z_cols: list[str],
    meta: dict,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)

    np.savez_compressed(
        cache_dir / f"{cache_key}.npz",
        embeddings=embeddings,
        point_ids=point_ids if point_ids is not None else np.array([], dtype=np.int64),
        z_cols=np.array(z_cols, dtype=object),
    )

    with open(cache_dir / f"{cache_key}.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _load_cache(
    cache_dir: Path,
    cache_key: str,
) -> tuple[np.ndarray, list[str], dict] | None:
    npz_path = cache_dir / f"{cache_key}.npz"
    if not npz_path.exists():
        return None

    data = np.load(npz_path, allow_pickle=True)
    embeddings = data["embeddings"].astype(np.float32)
    z_cols = [str(x) for x in data["z_cols"].tolist()]

    meta_path = cache_dir / f"{cache_key}.json"
    meta: dict = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            meta = {
                "metadataStatus": "unreadable",
                "metadataError": str(exc),
            }

    meta.update({
        "cache_key": cache_key,
        "cache_hit": True,
        "embedding_shape": [int(embeddings.shape[0]), int(embeddings.shape[1])],
        "cache_files": {
            "npz": str(npz_path),
            "json": str(meta_path),
            "npzExists": npz_path.exists(),
            "jsonExists": meta_path.exists(),
        },
    })
    return embeddings, z_cols, meta


def compute_saint_embeddings_live(
    df: pd.DataFrame,
    selected_pfas_cols: list[str],
    preprocessing: PreprocessingType = "standardize",
    point_id_col: str = "point_id",
    config: SaintLiveConfig | None = None,
    return_metadata: bool = False,
) -> tuple[np.ndarray, list[str]] | tuple[np.ndarray, list[str], dict]:
    """
    Entrée:
        - df : DataFrame déjà filtré par l'application
        - selected_pfas_cols : colonnes PFAS réellement choisies
        - preprocessing : none / standardize / normalize

    Sortie:
        - embeddings numpy [n_samples, embedding_dim]
        - noms des colonnes embeddings ["z1", ..., "zN"]
    """
    if df.empty:
        raise ValueError("Le DataFrame filtré est vide.")

    if not selected_pfas_cols:
        raise ValueError("Aucune colonne PFAS fournie à SAINT live.")

    cfg = config or SaintLiveConfig()
    _set_seed(cfg.seed)
    device = _pick_device()

    started = time.perf_counter()

    point_ids_list: list[int] | None = None
    if point_id_col in df.columns:
        point_ids_list = df[point_id_col].astype(int).tolist()

    cache_dir = Path(cfg.cache_dir)
    cache_key = _build_cache_key(
        point_ids=point_ids_list,
        selected_pfas_cols=selected_pfas_cols,
        preprocessing=preprocessing,
        config=cfg,
        n_rows=len(df),
    )

    if cfg.use_cache:
        cached = _load_cache(cache_dir, cache_key)
        if cached is not None:
            if cfg.verbose:
                print(f"[SAINT live] cache hit: {cache_key[:12]}")
            embeddings, z_cols, meta = cached
            meta["cache_lookup_seconds"] = round(time.perf_counter() - started, 6)
            if return_metadata:
                return embeddings, z_cols, meta
            return embeddings, z_cols

    x, scaler_info = _sanitize_matrix(
        df=df,
        selected_pfas_cols=selected_pfas_cols,
        preprocessing=preprocessing,
        config=cfg,
    )

    if x.shape[1] < 1:
        raise ValueError("SAINT live a besoin d'au moins une feature.")

    model, training_history = _train_saint_live(
        x=x,
        config=cfg,
        device=device,
    )

    embeddings = _infer_embeddings(
        model=model,
        x=x,
        pooling=cfg.pooling,
        batch_size=cfg.batch_size,
        device=device,
    )

    z_cols = [f"z{i+1}" for i in range(embeddings.shape[1])]

    duration_s = time.perf_counter() - started
    meta = {
        "mode": "saint_live",
        "n_rows": int(len(df)),
        "n_features": int(len(selected_pfas_cols)),
        "selected_pfas_cols": selected_pfas_cols,
        "preprocessing": preprocessing,
        "scaler_info": scaler_info,
        "embedding_dim": int(embeddings.shape[1]),
        "embedding_shape": [int(embeddings.shape[0]), int(embeddings.shape[1])],
        "device": str(device),
        "duration_seconds": round(duration_s, 3),
        "training_history": training_history,
        "config": asdict(cfg),
        "cache_key": cache_key,
        "cache_hit": False,
        "cache_files": {
            "npz": str(cache_dir / f"{cache_key}.npz"),
            "json": str(cache_dir / f"{cache_key}.json"),
            "npzExists": bool(cfg.use_cache),
            "jsonExists": bool(cfg.use_cache),
        },
    }

    if cfg.use_cache:
        point_ids_arr = (
            df[point_id_col].astype(np.int64).to_numpy()
            if point_id_col in df.columns
            else None
        )
        _save_cache(
            cache_dir=cache_dir,
            cache_key=cache_key,
            point_ids=point_ids_arr,
            embeddings=embeddings,
            z_cols=z_cols,
            meta=meta,
        )

    if cfg.verbose:
        print(
            f"[SAINT live] done - rows={len(df)}, features={len(selected_pfas_cols)}, "
            f"embedding_dim={embeddings.shape[1]}, duration={duration_s:.2f}s"
        )

    if return_metadata:
        return embeddings, z_cols, meta
    return embeddings, z_cols
