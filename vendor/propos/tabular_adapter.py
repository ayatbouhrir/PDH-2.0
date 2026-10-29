from __future__ import annotations

import copy
import random
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.cluster import KMeans, MiniBatchKMeans


MINIBATCH_THRESHOLD = 100_000


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _normalize_rows_np(values: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    norms = np.clip(norms, eps, None)
    return values / norms


def _build_clusterer(
    values: np.ndarray,
    num_clusters: int,
    *,
    max_iter: int,
    seed: int,
):
    if len(values) > MINIBATCH_THRESHOLD:
        return MiniBatchKMeans(
            n_clusters=num_clusters,
            random_state=seed,
            batch_size=min(1024, len(values)),
            n_init=10,
            max_iter=max_iter,
        )
    return KMeans(
        n_clusters=num_clusters,
        random_state=seed,
        n_init=10,
        max_iter=max_iter,
    )


def _augment_latent(
    batch: torch.Tensor,
    *,
    noise_std: float,
    dropout_prob: float,
) -> torch.Tensor:
    augmented = batch
    if noise_std > 0:
        augmented = augmented + torch.randn_like(batch) * noise_std
    if dropout_prob > 0:
        keep_prob = max(1e-6, 1.0 - dropout_prob)
        mask = (torch.rand_like(batch) < keep_prob).float()
        augmented = augmented * mask / keep_prob
    return augmented


def _compute_centers(
    x: torch.Tensor,
    pseudo_labels: torch.Tensor,
    num_clusters: int,
) -> torch.Tensor:
    n_samples = x.size(0)
    weight = torch.zeros(num_clusters, n_samples, device=x.device, dtype=x.dtype)
    weight[pseudo_labels, torch.arange(n_samples, device=x.device)] = 1.0
    weight = F.normalize(weight, p=1, dim=1)
    centers = torch.mm(weight, x)
    return F.normalize(centers, dim=1)


def _compute_cluster_loss(
    q_centers: torch.Tensor,
    k_centers: torch.Tensor,
    temperature: float,
    pseudo_labels: torch.Tensor,
    num_clusters: int,
) -> torch.Tensor:
    if q_centers.numel() == 0:
        return torch.zeros((), device=q_centers.device)

    d_q = q_centers.mm(q_centers.T) / temperature
    d_k = (q_centers * k_centers).sum(dim=1) / temperature
    d_q = d_q.float()
    d_q[torch.arange(num_clusters, device=d_q.device), torch.arange(num_clusters, device=d_q.device)] = d_k

    counts = torch.bincount(pseudo_labels, minlength=num_clusters)
    zero_classes = torch.arange(num_clusters, device=d_q.device)[counts == 0]
    if len(zero_classes) == num_clusters:
        return torch.zeros((), device=d_q.device)

    mask = torch.zeros((num_clusters, num_clusters), dtype=torch.bool, device=d_q.device)
    mask[:, zero_classes] = True
    d_q.masked_fill_(mask, -10.0)

    pos = d_q.diag(0)
    neg_mask = torch.ones((num_clusters, num_clusters), dtype=torch.bool, device=d_q.device)
    neg_mask.fill_diagonal_(False)
    neg = d_q[neg_mask].reshape(num_clusters, num_clusters - 1)

    loss = -pos + torch.logsumexp(torch.cat([pos.reshape(num_clusters, 1), neg], dim=1), dim=1)
    loss[zero_classes] = 0.0
    denom = max(1, num_clusters - len(zero_classes))
    return loss.sum() / denom


class TabularBackbone(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
        )

    def forward(self, batch: torch.Tensor) -> torch.Tensor:
        return self.net(batch)


class ProjectionHead(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, batch: torch.Tensor) -> torch.Tensor:
        return self.net(batch)


class PredictorHead(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, input_dim),
        )

    def forward(self, batch: torch.Tensor) -> torch.Tensor:
        return self.net(batch)


class TabularProPosModel(nn.Module):
    def __init__(
        self,
        *,
        input_dim: int,
        hidden_dim: int,
        feature_dim: int,
    ) -> None:
        super().__init__()
        self.encoder_q = TabularBackbone(input_dim, hidden_dim)
        self.projector_q = ProjectionHead(hidden_dim, hidden_dim, feature_dim)
        self.encoder_k = copy.deepcopy(self.encoder_q)
        self.projector_k = copy.deepcopy(self.projector_q)
        self.predictor = PredictorHead(feature_dim, hidden_dim)

        for param in list(self.encoder_k.parameters()) + list(self.projector_k.parameters()):
            param.requires_grad = False

    def encode_online(self, batch: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.projector_q(self.encoder_q(batch)), dim=1)

    def encode_target(self, batch: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.projector_k(self.encoder_k(batch)), dim=1)

    def predict_online(self, batch: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.predictor(batch), dim=1)

    @torch.no_grad()
    def momentum_update(self, momentum: float) -> None:
        for param_q, param_k in zip(self.encoder_q.parameters(), self.encoder_k.parameters()):
            param_k.data = param_k.data * momentum + param_q.data * (1.0 - momentum)
        for param_q, param_k in zip(self.projector_q.parameters(), self.projector_k.parameters()):
            param_k.data = param_k.data * momentum + param_q.data * (1.0 - momentum)


def train_tabular_propos(
    values: np.ndarray,
    *,
    num_clusters: int,
    epochs: int,
    device: str,
    seed: int = 42,
    batch_size: int | None = None,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-5,
    temperature: float = 0.5,
    momentum: float = 0.996,
    noise_std: float = 0.03,
    dropout_prob: float = 0.05,
    hidden_dim: int | None = None,
    feature_dim: int | None = None,
    refresh_interval: int = 1,
) -> dict[str, Any]:
    if len(values) < 4:
        raise ValueError("ProPos requiert au moins 4 points.")
    if num_clusters < 2:
        raise ValueError("num_clusters doit etre >= 2.")
    if num_clusters >= len(values):
        raise ValueError("num_clusters doit etre strictement inferieur au nombre de points.")

    _set_seed(seed)

    input_x = np.asarray(values, dtype=np.float32)
    input_x = np.nan_to_num(input_x, nan=0.0, posinf=0.0, neginf=0.0)
    input_dim = int(input_x.shape[1])
    hidden_dim = int(hidden_dim or max(64, input_dim * 4))
    feature_dim = int(feature_dim or max(16, min(128, input_dim * 2)))
    batch_size = int(batch_size or min(512, len(input_x)))
    batch_size = max(2, min(batch_size, len(input_x)))
    epochs = int(max(10, min(200, epochs)))
    refresh_interval = max(1, int(refresh_interval))

    train_device = torch.device(device)
    model = TabularProPosModel(
        input_dim=input_dim,
        hidden_dim=hidden_dim,
        feature_dim=feature_dim,
    ).to(train_device)
    optimizer = torch.optim.AdamW(
        list(model.encoder_q.parameters())
        + list(model.projector_q.parameters())
        + list(model.predictor.parameters()),
        lr=learning_rate,
        weight_decay=weight_decay,
    )

    initial_model = _build_clusterer(input_x, num_clusters, max_iter=100, seed=seed)
    pseudo_labels_np = initial_model.fit_predict(input_x)

    x_tensor = torch.tensor(input_x, dtype=torch.float32, device=train_device)
    pseudo_labels = torch.tensor(pseudo_labels_np, dtype=torch.long, device=train_device)
    final_loss = None

    for epoch_idx in range(epochs):
        permutation = torch.randperm(len(input_x), device=train_device)

        for start in range(0, len(input_x), batch_size):
            indices = permutation[start:start + batch_size]
            if len(indices) < 2:
                continue

            batch = x_tensor[indices]
            batch_labels = pseudo_labels[indices]

            view_q = _augment_latent(batch, noise_std=noise_std, dropout_prob=dropout_prob)
            view_k = _augment_latent(batch, noise_std=noise_std, dropout_prob=dropout_prob)

            q = model.encode_online(view_q)
            pred_q = model.predict_online(q)

            with torch.no_grad():
                k = model.encode_target(view_k)

            contrastive_loss = (2.0 - 2.0 * F.cosine_similarity(pred_q, k, dim=1)).mean()
            q_centers = _compute_centers(q, batch_labels, num_clusters)
            k_centers = _compute_centers(k, batch_labels, num_clusters)
            cluster_loss = _compute_cluster_loss(
                q_centers,
                k_centers,
                temperature,
                batch_labels,
                num_clusters,
            )
            loss = contrastive_loss + cluster_loss

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            model.momentum_update(momentum)
            final_loss = float(loss.detach().cpu().item())

        should_refresh = ((epoch_idx + 1) % refresh_interval == 0) or (epoch_idx + 1 == epochs)
        if should_refresh:
            with torch.no_grad():
                refreshed_embedding = model.encode_target(x_tensor).cpu().numpy()
            refreshed_model = _build_clusterer(
                refreshed_embedding,
                num_clusters,
                max_iter=100,
                seed=seed,
            )
            pseudo_labels_np = refreshed_model.fit_predict(refreshed_embedding)
            pseudo_labels = torch.tensor(pseudo_labels_np, dtype=torch.long, device=train_device)

    with torch.no_grad():
        refined_embedding = model.encode_target(x_tensor).cpu().numpy().astype(np.float32)

    final_model = _build_clusterer(refined_embedding, num_clusters, max_iter=200, seed=seed)
    labels = final_model.fit_predict(refined_embedding)
    distances = final_model.transform(refined_embedding)
    min_dist = distances.min(axis=1)
    shifted = distances - min_dist[:, None]
    confidence = np.clip(1.0 / (1.0 + min_dist), 0.0, 1.0)

    return {
        "labels": np.asarray(labels, dtype=int),
        "summaryFeatures": refined_embedding,
        "trainingLoss": final_loss,
        "epochs": epochs,
        "centroids": final_model.cluster_centers_.astype(np.float32),
        "pointConfidence": confidence.astype(np.float32),
        "temperatureAdjustedDistances": shifted.astype(np.float32),
        "modelState": {
            "encoderQ": {key: value.detach().cpu() for key, value in model.encoder_q.state_dict().items()},
            "projectorQ": {key: value.detach().cpu() for key, value in model.projector_q.state_dict().items()},
            "encoderK": {key: value.detach().cpu() for key, value in model.encoder_k.state_dict().items()},
            "projectorK": {key: value.detach().cpu() for key, value in model.projector_k.state_dict().items()},
            "predictor": {key: value.detach().cpu() for key, value in model.predictor.state_dict().items()},
        },
        "modelConfig": {
            "inputDim": input_dim,
            "hiddenDim": hidden_dim,
            "featureDim": feature_dim,
            "temperature": float(temperature),
            "momentum": float(momentum),
            "noiseStd": float(noise_std),
            "dropoutProb": float(dropout_prob),
            "backend": "propos_master_tabular_adapter",
        },
    }


def infer_tabular_propos(
    values: np.ndarray,
    artifact: dict[str, Any],
    *,
    device: str,
) -> dict[str, Any]:
    model_state = artifact.get("modelState")
    model_config = artifact.get("modelConfig") or {}
    centroids = artifact.get("centroids")

    if not isinstance(model_state, dict) or centroids is None:
        raise ValueError("Artefact ProPos invalide pour inference.")

    input_x = np.asarray(values, dtype=np.float32)
    input_x = np.nan_to_num(input_x, nan=0.0, posinf=0.0, neginf=0.0)

    input_dim = int(model_config.get("inputDim") or input_x.shape[1])
    hidden_dim = int(model_config.get("hiddenDim") or max(64, input_dim * 4))
    feature_dim = int(model_config.get("featureDim") or max(16, min(128, input_dim * 2)))

    if input_dim != input_x.shape[1]:
        raise ValueError(
            f"Le modele ProPos attend {input_dim} features latentes, mais {input_x.shape[1]} ont ete fournies."
        )

    model = TabularProPosModel(
        input_dim=input_dim,
        hidden_dim=hidden_dim,
        feature_dim=feature_dim,
    ).to(torch.device(device))
    model.encoder_q.load_state_dict(model_state["encoderQ"])
    model.projector_q.load_state_dict(model_state["projectorQ"])
    model.encoder_k.load_state_dict(model_state["encoderK"])
    model.projector_k.load_state_dict(model_state["projectorK"])
    model.predictor.load_state_dict(model_state["predictor"])
    model.eval()

    centroid_array = np.asarray(centroids, dtype=np.float32)
    x_tensor = torch.tensor(input_x, dtype=torch.float32, device=torch.device(device))
    centroid_tensor = torch.tensor(centroid_array, dtype=torch.float32, device=torch.device(device))

    with torch.no_grad():
        refined_embedding = model.encode_target(x_tensor)
        normalized_centroids = F.normalize(centroid_tensor, dim=1)
        distances = torch.cdist(refined_embedding, normalized_centroids, p=2)
        labels = torch.argmin(distances, dim=1)
        min_dist = distances.gather(1, labels.unsqueeze(1)).squeeze(1)
        shifted = distances - min_dist.unsqueeze(1)
        confidence = torch.clamp(1.0 / (1.0 + min_dist), 0.0, 1.0)

    return {
        "labels": labels.cpu().numpy().astype(int),
        "summaryFeatures": refined_embedding.cpu().numpy().astype(np.float32),
        "trainingLoss": artifact.get("trainingLoss"),
        "epochs": artifact.get("epochs"),
        "centroids": centroid_array,
        "pointConfidence": confidence.cpu().numpy().astype(np.float32),
        "temperatureAdjustedDistances": shifted.cpu().numpy().astype(np.float32),
        "modelState": model_state,
        "modelConfig": model_config,
    }
