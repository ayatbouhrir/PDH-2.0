from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sqlalchemy import bindparam, create_engine, text

from sklearn.cluster import DBSCAN, KMeans
from sklearn.metrics import (
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

try:
    import hdbscan as hdbscan_lib
except ImportError:
    hdbscan_lib = None

try:
    from sklearn.cluster import HDBSCAN as sklearn_hdbscan_cls
except Exception:
    sklearn_hdbscan_cls = None


# ============================================================
# CONFIGURATION
# ============================================================

RANDOM_STATE = 42

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parents[1]
FRONTEND_DIR = PROJECT_DIR / "frontend"

SAINT_PARQUET_PATH = (
    PROJECT_DIR / "artifacts/embeddings/saint" / "saint_pfas_latent_mean.parquet"
)

OUTPUT_DIR = PROJECT_DIR / "artifacts/experiments/saint-tabpfn-comparison"
EMBEDDING_DIR = OUTPUT_DIR / "embeddings"
LABEL_DIR = OUTPUT_DIR / "labels"
METRIC_DIR = OUTPUT_DIR / "metrics"

FULL_OUTPUT_DIR = PROJECT_DIR / "artifacts/experiments/full-embeddings"
FULL_EMBEDDING_DIR = FULL_OUTPUT_DIR / "embeddings"

PROPOS_CACHE_DIR = PROJECT_DIR / ".local/cache/research/propos"
PROPOS_MASTER_DIR = PROJECT_DIR / "vendor/propos"
PROPOS_TABULAR_ADAPTER_PATH = PROPOS_MASTER_DIR / "tabular_adapter.py"

for d in [
    OUTPUT_DIR,
    EMBEDDING_DIR,
    LABEL_DIR,
    METRIC_DIR,
    FULL_OUTPUT_DIR,
    FULL_EMBEDDING_DIR,
    PROPOS_CACHE_DIR,
]:
    d.mkdir(parents=True, exist_ok=True)


TARGET_SAMPLE_SIZE = int(os.getenv("TARGET_SAMPLE_SIZE", "87281"))
TARGET_K = int(os.getenv("TARGET_K", "5"))

TABPFN_DEVICE = os.getenv("TABPFN_DEVICE", "cpu")
TABPFN_N_ESTIMATORS = int(os.getenv("TABPFN_N_ESTIMATORS", "1"))
TABPFN_N_FOLD = int(os.getenv("TABPFN_N_FOLD", "2"))
FORCE_REGENERATE_TABPFN = os.getenv("FORCE_REGENERATE_TABPFN", "0") == "1"

RUN_KMEANS = os.getenv("RUN_KMEANS", "1") == "1"
RUN_DBSCAN = os.getenv("RUN_DBSCAN", "1") == "1"
RUN_HDBSCAN = os.getenv("RUN_HDBSCAN", "1") == "1"
RUN_PROPOS = os.getenv("RUN_PROPOS", "1") == "1"

DBSCAN_MIN_SAMPLES = int(os.getenv("DBSCAN_MIN_SAMPLES", "10"))
DBSCAN_EPS_QUANTILE = float(os.getenv("DBSCAN_EPS_QUANTILE", "0.90"))
DBSCAN_EPS_SAMPLE_SIZE = int(os.getenv("DBSCAN_EPS_SAMPLE_SIZE", "20000"))

HDBSCAN_MIN_CLUSTER_SIZE = int(os.getenv("HDBSCAN_MIN_CLUSTER_SIZE", "50"))
HDBSCAN_MIN_SAMPLES = int(os.getenv("HDBSCAN_MIN_SAMPLES", "10"))

PROPOS_EPOCHS = int(os.getenv("PROPOS_EPOCHS", "80"))


# ============================================================
# OUTILS GÉNÉRAUX
# ============================================================

def safe_to_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def clean_point_id(df: pd.DataFrame) -> pd.DataFrame:
    if "point_id" not in df.columns:
        raise RuntimeError("Colonne point_id absente.")

    df = df.copy()
    df["point_id"] = pd.to_numeric(df["point_id"], errors="coerce")
    df = df.dropna(subset=["point_id"])
    df["point_id"] = df["point_id"].astype(np.int64)
    df = df.drop_duplicates(subset=["point_id"], keep="first")
    return df.reset_index(drop=True)


def align_by_point_id(df: pd.DataFrame, point_ids: list[int]) -> pd.DataFrame:
    df = clean_point_id(df)
    indexed = df.set_index("point_id", drop=False)

    missing = [pid for pid in point_ids if pid not in indexed.index]
    if missing:
        raise RuntimeError(f"{len(missing)} point_id absents pendant alignement.")

    return indexed.loc[point_ids].reset_index(drop=True)


def get_x(df: pd.DataFrame, scale: bool = True) -> np.ndarray:
    feature_cols = [c for c in df.columns if c != "point_id"]
    x = df[feature_cols].to_numpy(dtype=np.float32)
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)

    if scale:
        x = StandardScaler().fit_transform(x).astype(np.float32)

    return x


def save_json(obj: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# DATABASE
# ============================================================

def load_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    if not env_path.exists():
        return values

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def build_db_config() -> dict[str, Any]:
    env_values = load_env_file(PROJECT_DIR / ".local/project.env" if (PROJECT_DIR / ".local/project.env").exists() else FRONTEND_DIR / ".env")

    return {
        "host": os.getenv("DB_HOST") or env_values.get("DB_HOST") or "localhost",
        "port": int(os.getenv("DB_PORT") or env_values.get("DB_PORT") or "5432"),
        "database": os.getenv("DB_NAME") or env_values.get("DB_NAME") or "DAE-PFAS",
        "user": os.getenv("DB_USER") or env_values.get("DB_USER") or "postgres",
        "password": os.getenv("DB_PASSWORD") or env_values.get("DB_PASSWORD") or "",
    }


def make_engine():
    db = build_db_config()

    return create_engine(
        "postgresql+pg8000://",
        connect_args={
            "host": db["host"],
            "port": db["port"],
            "database": db["database"],
            "user": db["user"],
            "password": db["password"],
        },
        pool_pre_ping=True,
    )


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def fetch_pfas_columns(engine) -> list[str]:
    sql = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'point'
          AND column_name LIKE 'pfas_%'
        ORDER BY
          CASE
            WHEN split_part(column_name, '_', 2) ~ '^[0-9]+$'
            THEN split_part(column_name, '_', 2)::int
            ELSE 999999
          END
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql).fetchall()

    cols = [str(r[0]) for r in rows]

    if not cols:
        raise RuntimeError("Aucune colonne pfas_* trouvée dans public.point.")

    return cols


def load_pfas_matrix_for_ids(point_ids: list[int]) -> pd.DataFrame:
    engine = make_engine()

    try:
        pfas_cols = fetch_pfas_columns(engine)

        select_cols = ["p.point_id"]
        select_cols += [f"p.{quote_ident(c)}" for c in pfas_cols]
        select_cols += ["m.pfas_sum"]

        sql = text(
            f"""
            SELECT {", ".join(select_cols)}
            FROM public.point p
            LEFT JOIN public.metadonnee m
              ON m.point_id = p.point_id
            WHERE p.point_id IN :ids
            """
        ).bindparams(bindparam("ids", expanding=True))

        chunks: list[pd.DataFrame] = []
        chunk_size = 5000

        for i in range(0, len(point_ids), chunk_size):
            chunk_ids = [int(v) for v in point_ids[i:i + chunk_size]]
            part = pd.read_sql(sql, engine, params={"ids": chunk_ids})
            chunks.append(part)
            print(f"[DB] loaded {min(i + chunk_size, len(point_ids))}/{len(point_ids)}")

        df = pd.concat(chunks, ignore_index=True)

        df = clean_point_id(df)
        df = align_by_point_id(df, point_ids)

        return df

    finally:
        engine.dispose()


# ============================================================
# CHARGEMENT SAINT
# ============================================================

def load_saint_embeddings() -> pd.DataFrame:
    if not SAINT_PARQUET_PATH.exists():
        raise FileNotFoundError(f"Fichier SAINT introuvable: {SAINT_PARQUET_PATH}")

    df = pd.read_parquet(SAINT_PARQUET_PATH)
    df = clean_point_id(df)

    feature_cols = [c for c in df.columns if c != "point_id"]

    if not feature_cols:
        raise RuntimeError("SAINT ne contient aucune feature.")

    for c in feature_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df[feature_cols] = (
        df[feature_cols]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )

    print(f"[OK] SAINT original: {df.shape}, point_id uniques = {df['point_id'].nunique()}")
    return df[["point_id", *feature_cols]].copy()


def select_app_point_ids(saint_df: pd.DataFrame) -> list[int]:
    saint_df = saint_df.sort_values("point_id").reset_index(drop=True)
    all_ids = saint_df["point_id"].astype(int).tolist()

    if TARGET_SAMPLE_SIZE >= len(all_ids):
        print(f"[INFO] Utilisation de tous les points SAINT/app: {len(all_ids)}")
        return all_ids

    rng = np.random.default_rng(RANDOM_STATE)
    selected = sorted(
        rng.choice(np.array(all_ids), size=TARGET_SAMPLE_SIZE, replace=False).tolist()
    )

    print(f"[INFO] Sous-échantillon: {len(selected)} points")
    return [int(v) for v in selected]


# ============================================================
# PRÉTRAITEMENT PFAS POUR TABPFN
# ============================================================

def preprocess_pfas_for_tabpfn(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, dict[str, Any]]:
    df = raw_df.copy()

    pfas_cols = [
        c for c in df.columns
        if c.startswith("pfas_")
        and c != "pfas_sum"
    ]

    if not pfas_cols:
        raise RuntimeError("Aucune colonne pfas_* disponible pour TabPFN.")

    for c in pfas_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df[pfas_cols] = (
        df[pfas_cols]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
        .clip(lower=0.0)
    )

    if "pfas_sum" not in df.columns:
        df["pfas_sum"] = df[pfas_cols].sum(axis=1)
    else:
        df["pfas_sum"] = pd.to_numeric(df["pfas_sum"], errors="coerce")
        df["pfas_sum"] = df["pfas_sum"].fillna(df[pfas_cols].sum(axis=1))
        df["pfas_sum"] = df["pfas_sum"].clip(lower=0.0)

    x_df = df[["point_id", *pfas_cols]].copy()
    x_df[pfas_cols] = np.log1p(x_df[pfas_cols].to_numpy(dtype=np.float64))

    scaler = StandardScaler()
    x_df[pfas_cols] = scaler.fit_transform(x_df[pfas_cols].to_numpy(dtype=np.float64))
    x_df[pfas_cols] = np.nan_to_num(
        x_df[pfas_cols].to_numpy(dtype=np.float64),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    signal = df["pfas_sum"].to_numpy(dtype=np.float64)

    try:
        pseudo_y = pd.qcut(
            signal,
            q=min(TARGET_K, max(2, len(np.unique(signal)))),
            labels=False,
            duplicates="drop",
        )
        pseudo_y = np.asarray(pseudo_y, dtype=np.int64)

        if len(np.unique(pseudo_y)) < 2:
            raise RuntimeError("pseudo_y quantiles contient moins de 2 classes.")

        pseudo_info = {
            "strategy": "quantiles_pfas_sum",
            "n_classes": int(len(np.unique(pseudo_y))),
        }

    except Exception:
        x_small = x_df[pfas_cols].to_numpy(dtype=np.float32)
        pseudo_y = KMeans(
            n_clusters=TARGET_K,
            random_state=RANDOM_STATE,
            n_init="auto",
        ).fit_predict(x_small)

        pseudo_info = {
            "strategy": "kmeans_fallback",
            "n_classes": int(len(np.unique(pseudo_y))),
        }

    return x_df, pseudo_y, pseudo_info


# ============================================================
# TABPFN EMBEDDINGS
# ============================================================

def load_existing_tabpfn(point_ids: list[int]) -> pd.DataFrame | None:
    candidates = [
        EMBEDDING_DIR / "tabpfn_87281.parquet",
        FULL_EMBEDDING_DIR / "tabpfn_full.parquet",
        PROJECT_DIR / "artifacts/experiments/tabpfn" / "tabpfn_embeddings.parquet",
    ]

    expected_set = set(int(v) for v in point_ids)

    for path in candidates:
        if not path.exists():
            continue

        try:
            df = pd.read_parquet(path)
            df = clean_point_id(df)
            current_set = set(df["point_id"].astype(int).tolist())

            if current_set == expected_set:
                print(f"[OK] TabPFN existant réutilisé: {path}")
                return align_by_point_id(df, point_ids)

            print(f"[SKIP] TabPFN existant non aligné: {path} ({len(current_set)} points)")

        except Exception as exc:
            print(f"[WARN] lecture TabPFN existant impossible {path}: {exc}")

    return None


def compute_tabpfn_embeddings(x_df: pd.DataFrame, pseudo_y: np.ndarray) -> pd.DataFrame:
    if not FORCE_REGENERATE_TABPFN:
        existing = load_existing_tabpfn(x_df["point_id"].astype(int).tolist())
        if existing is not None:
            return existing

    if importlib.util.find_spec("tabpfn") is None:
        raise RuntimeError("Package tabpfn absent. Installe: pip install tabpfn")

    if importlib.util.find_spec("tabpfn_extensions") is None:
        raise RuntimeError("Package tabpfn_extensions absent. Installe: pip install tabpfn-extensions")

    from tabpfn import TabPFNClassifier
    from tabpfn_extensions.embedding import TabPFNEmbedding

    feature_cols = [c for c in x_df.columns if c != "point_id"]
    x = x_df[feature_cols].to_numpy(dtype=np.float32)

    print("[INFO] TabPFN génération embeddings")
    print(f"[INFO] X shape = {x.shape}")
    print(f"[INFO] device = {TABPFN_DEVICE}")
    print(f"[INFO] n_estimators = {TABPFN_N_ESTIMATORS}")
    print(f"[INFO] n_fold = {TABPFN_N_FOLD}")

    try:
        model = TabPFNClassifier(
            n_estimators=TABPFN_N_ESTIMATORS,
            random_state=RANDOM_STATE,
            device=TABPFN_DEVICE,
        )
    except TypeError:
        model = TabPFNClassifier(
            n_estimators=TABPFN_N_ESTIMATORS,
            random_state=RANDOM_STATE,
        )

    try:
        transformer = TabPFNEmbedding(n_fold=TABPFN_N_FOLD, model=model)
    except TypeError:
        try:
            transformer = TabPFNEmbedding(model=model, n_fold=TABPFN_N_FOLD)
        except TypeError:
            transformer = TabPFNEmbedding(model=model)

    started = time.perf_counter()
    embeddings = transformer.fit_transform(x, pseudo_y)
    duration = time.perf_counter() - started

    embeddings = np.asarray(embeddings, dtype=np.float32)

    if embeddings.ndim == 3:
        if embeddings.shape[1] == x.shape[0]:
            embeddings = embeddings.mean(axis=0)
        elif embeddings.shape[0] == x.shape[0]:
            embeddings = embeddings.mean(axis=1)
        else:
            raise RuntimeError(f"Shape TabPFN 3D inattendue: {embeddings.shape}")

    if embeddings.ndim != 2:
        raise RuntimeError(f"Shape TabPFN invalide: {embeddings.shape}")

    cols = [f"tabpfn_z{i + 1}" for i in range(embeddings.shape[1])]

    out = pd.DataFrame(embeddings, columns=cols)
    out.insert(0, "point_id", x_df["point_id"].to_numpy(dtype=np.int64))

    print(f"[OK] TabPFN embeddings: {out.shape}")
    print(f"[OK] durée secondes: {duration:.2f}")

    return out


# ============================================================
# CLUSTERING
# ============================================================

def run_kmeans(embedding_df: pd.DataFrame) -> np.ndarray:
    x = get_x(embedding_df, scale=True)
    k = min(TARGET_K, x.shape[0])

    model = KMeans(
        n_clusters=k,
        random_state=RANDOM_STATE,
        n_init="auto",
    )

    return model.fit_predict(x).astype(int)


def estimate_dbscan_eps(x: np.ndarray) -> float:
    if len(x) > DBSCAN_EPS_SAMPLE_SIZE:
        rng = np.random.default_rng(RANDOM_STATE)
        idx = rng.choice(len(x), size=DBSCAN_EPS_SAMPLE_SIZE, replace=False)
        x_sample = x[idx]
    else:
        x_sample = x

    k = min(DBSCAN_MIN_SAMPLES, len(x_sample))

    nn = NearestNeighbors(n_neighbors=k, n_jobs=-1)
    nn.fit(x_sample)

    distances, _ = nn.kneighbors(x_sample)
    kth_distances = np.sort(distances[:, -1])

    eps = float(np.quantile(kth_distances, DBSCAN_EPS_QUANTILE))

    if eps <= 0 or not np.isfinite(eps):
        eps = float(np.mean(kth_distances) + np.std(kth_distances))

    return eps


def run_dbscan(embedding_df: pd.DataFrame) -> tuple[np.ndarray, dict[str, Any]]:
    x = get_x(embedding_df, scale=True)

    eps = estimate_dbscan_eps(x)

    print(f"[INFO] DBSCAN eps estimé = {eps:.6f}")

    model = DBSCAN(
        eps=eps,
        min_samples=DBSCAN_MIN_SAMPLES,
        n_jobs=-1,
    )

    labels = model.fit_predict(x).astype(int)

    return labels, {
        "eps": eps,
        "min_samples": DBSCAN_MIN_SAMPLES,
        "eps_quantile": DBSCAN_EPS_QUANTILE,
    }


def run_hdbscan(embedding_df: pd.DataFrame) -> np.ndarray | None:
    x = get_x(embedding_df, scale=True)

    if hdbscan_lib is not None:
        model = hdbscan_lib.HDBSCAN(
            min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
            min_samples=HDBSCAN_MIN_SAMPLES,
            core_dist_n_jobs=-1,
        )
        return model.fit_predict(x).astype(int)

    if sklearn_hdbscan_cls is not None:
        model = sklearn_hdbscan_cls(
            min_cluster_size=HDBSCAN_MIN_CLUSTER_SIZE,
            min_samples=HDBSCAN_MIN_SAMPLES,
        )
        return model.fit_predict(x).astype(int)

    print("[SKIP] HDBSCAN absent. Installe: pip install hdbscan")
    return None


# ============================================================
# PROPOS
# ============================================================

def pick_torch_device() -> str:
    forced = os.getenv("PROPOS_DEVICE")
    if forced:
        return forced

    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"

        return "cpu"

    except Exception:
        return "cpu"


def load_propos_adapter():
    if not PROPOS_TABULAR_ADAPTER_PATH.exists():
        raise FileNotFoundError(f"Adaptateur ProPos introuvable: {PROPOS_TABULAR_ADAPTER_PATH}")

    master_dir = str(PROPOS_MASTER_DIR)
    if master_dir not in sys.path:
        sys.path.insert(0, master_dir)

    spec = importlib.util.spec_from_file_location(
        "propos_master_tabular_adapter",
        PROPOS_TABULAR_ADAPTER_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError("Impossible de charger ProPos-master/tabular_adapter.py")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "train_tabular_propos"):
        raise RuntimeError("tabular_adapter.py ne contient pas train_tabular_propos.")

    return module


def run_propos(embedding_df: pd.DataFrame, representation: str) -> np.ndarray:
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

    x = get_x(embedding_df, scale=True)
    adapter = load_propos_adapter()
    fn = adapter.train_tabular_propos

    device = pick_torch_device()
    devices = [device]

    if device != "cpu":
        devices.append("cpu")

    attempts = [
        lambda d: fn(
            x,
            num_clusters=TARGET_K,
            epochs=PROPOS_EPOCHS,
            device=d,
            seed=RANDOM_STATE,
        ),
        lambda d: fn(
            x,
            k=TARGET_K,
            epochs=PROPOS_EPOCHS,
            device=d,
            seed=RANDOM_STATE,
        ),
    ]

    result = None
    last_error = None

    started = time.perf_counter()

    for d in devices:
        for attempt in attempts:
            try:
                print(f"[INFO] ProPos {representation} avec device={d}")
                result = attempt(d)
                break
            except TypeError as exc:
                last_error = exc
                continue
            except Exception as exc:
                last_error = exc
                print(f"[WARN] ProPos échec device={d}: {exc}")
                break

        if result is not None:
            break

    if result is None:
        raise RuntimeError(f"ProPos impossible pour {representation}: {last_error}")

    if "labels" not in result:
        raise RuntimeError("Résultat ProPos invalide: clé labels absente.")

    duration = time.perf_counter() - started
    labels = np.asarray(result["labels"], dtype=int)

    model_path = PROPOS_CACHE_DIR / (
        f"propos_{representation}_same_app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pt"
    )

    try:
        import torch

        torch.save(
            {
                "modelState": result.get("modelState"),
                "modelConfig": result.get("modelConfig"),
                "centroids": result.get("centroids"),
                "trainingLoss": result.get("trainingLoss"),
                "epochs": result.get("epochs"),
                "representation": representation,
                "inputShape": list(x.shape),
                "createdAt": datetime.now().isoformat(),
            },
            model_path,
        )
    except Exception as exc:
        print(f"[WARN] modèle ProPos non sauvegardé: {exc}")

    print(f"[OK] ProPos {representation}: labels={labels.shape}, durée={duration:.2f}s")

    return labels


# ============================================================
# MÉTRIQUES ET SAUVEGARDE
# ============================================================

def compute_metrics(
    representation: str,
    clustering: str,
    embedding_df: pd.DataFrame,
    labels: np.ndarray,
) -> dict[str, Any]:
    x = get_x(embedding_df, scale=True)
    labels = np.asarray(labels, dtype=int)

    noise_mask = labels == -1
    valid_mask = ~noise_mask

    valid_x = x[valid_mask]
    valid_labels = labels[valid_mask]

    unique_clusters = sorted(set(int(v) for v in valid_labels.tolist()))
    n_clusters = len(unique_clusters)

    row: dict[str, Any] = {
        "method": f"{representation.upper()} + {clustering.upper()}",
        "representation": representation,
        "clustering": clustering,
        "n_points": int(len(labels)),
        "n_features": int(x.shape[1]),
        "n_clusters": int(n_clusters),
        "noise_points": int(np.sum(noise_mask)),
        "noise_ratio": float(np.mean(noise_mask)) if len(labels) else 0.0,
        "silhouette": None,
        "davies_bouldin": None,
        "calinski_harabasz": None,
    }

    if n_clusters < 2 or len(valid_x) <= n_clusters:
        return row

    row["silhouette"] = float(
        silhouette_score(
            valid_x,
            valid_labels,
            sample_size=min(5000, len(valid_x)),
            random_state=RANDOM_STATE,
        )
    )

    row["davies_bouldin"] = float(davies_bouldin_score(valid_x, valid_labels))
    row["calinski_harabasz"] = float(calinski_harabasz_score(valid_x, valid_labels))

    return row


def save_labels(
    representation: str,
    clustering: str,
    point_ids: np.ndarray,
    labels: np.ndarray,
) -> Path:
    df = pd.DataFrame(
        {
            "point_id": point_ids.astype(np.int64),
            "cluster_id": labels.astype(int),
        }
    )

    path = LABEL_DIR / f"{representation}_{clustering}_labels.parquet"
    safe_to_parquet(df, path)

    return path


def build_cluster_sizes(assignments_long_df: pd.DataFrame) -> pd.DataFrame:
    if assignments_long_df.empty:
        return pd.DataFrame(
            columns=[
                "representation",
                "clustering",
                "cluster_id",
                "cluster_size",
            ]
        )

    return (
        assignments_long_df
        .groupby(["representation", "clustering", "cluster_id"], dropna=False)
        .size()
        .reset_index(name="cluster_size")
        .sort_values(["representation", "clustering", "cluster_id"])
    )


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    started_all = time.perf_counter()

    print("\n=== STEP 1: LOAD SAINT ===")
    saint_original = load_saint_embeddings()

    selected_point_ids = select_app_point_ids(saint_original)
    saint_df = align_by_point_id(saint_original, selected_point_ids)

    safe_to_parquet(saint_df, EMBEDDING_DIR / "saint_87281.parquet")
    safe_to_parquet(saint_df, FULL_EMBEDDING_DIR / "saint_full.parquet")

    print(f"[OK] SAINT sélectionné: {saint_df.shape}")

    print("\n=== STEP 2: LOAD PFAS MATRIX FOR SAME IDS ===")
    raw_pfas_df = load_pfas_matrix_for_ids(selected_point_ids)
    print(f"[OK] raw PFAS: {raw_pfas_df.shape}")

    print("\n=== STEP 3: PREPROCESS PFAS FOR TABPFN ===")
    x_tabpfn_df, pseudo_y, pseudo_info = preprocess_pfas_for_tabpfn(raw_pfas_df)
    print(f"[OK] X TabPFN: {x_tabpfn_df.shape}")
    print(f"[OK] pseudo_y: {pseudo_info}")

    print("\n=== STEP 4: COMPUTE / LOAD TABPFN EMBEDDINGS ===")
    tabpfn_df = compute_tabpfn_embeddings(x_tabpfn_df, pseudo_y)
    tabpfn_df = align_by_point_id(tabpfn_df, selected_point_ids)

    safe_to_parquet(tabpfn_df, EMBEDDING_DIR / "tabpfn_87281.parquet")
    safe_to_parquet(tabpfn_df, FULL_EMBEDDING_DIR / "tabpfn_full.parquet")

    print(f"[OK] TabPFN sélectionné: {tabpfn_df.shape}")

    print("\n=== STEP 5: SAINT VS TABPFN CLUSTERING ===")

    representations = {
        "saint": saint_df,
        "tabpfn": tabpfn_df,
    }

    metrics_rows: list[dict[str, Any]] = []
    assignment_long_rows: list[dict[str, Any]] = []

    assignments_wide = pd.DataFrame({"point_id": np.asarray(selected_point_ids, dtype=np.int64)})

    for representation, embedding_df in representations.items():
        point_ids = embedding_df["point_id"].to_numpy(dtype=np.int64)

        print(f"\n--- {representation.upper()} ---")

        if RUN_KMEANS:
            print("[RUN] KMeans")
            labels = run_kmeans(embedding_df)
            save_labels(representation, "kmeans", point_ids, labels)
            assignments_wide[f"{representation}_kmeans"] = labels
            metrics_rows.append(compute_metrics(representation, "kmeans", embedding_df, labels))

            assignment_long_rows.extend(
                {
                    "point_id": int(pid),
                    "representation": representation,
                    "clustering": "kmeans",
                    "cluster_id": int(label),
                }
                for pid, label in zip(point_ids, labels, strict=True)
            )

        if RUN_DBSCAN:
            print("[RUN] DBSCAN")
            labels, dbscan_info = run_dbscan(embedding_df)
            save_labels(representation, "dbscan", point_ids, labels)
            assignments_wide[f"{representation}_dbscan"] = labels
            row = compute_metrics(representation, "dbscan", embedding_df, labels)
            row.update({f"dbscan_{k}": v for k, v in dbscan_info.items()})
            metrics_rows.append(row)

            assignment_long_rows.extend(
                {
                    "point_id": int(pid),
                    "representation": representation,
                    "clustering": "dbscan",
                    "cluster_id": int(label),
                }
                for pid, label in zip(point_ids, labels, strict=True)
            )

        if RUN_HDBSCAN:
            print("[RUN] HDBSCAN")
            labels = run_hdbscan(embedding_df)

            if labels is not None:
                save_labels(representation, "hdbscan", point_ids, labels)
                assignments_wide[f"{representation}_hdbscan"] = labels
                metrics_rows.append(compute_metrics(representation, "hdbscan", embedding_df, labels))

                assignment_long_rows.extend(
                    {
                        "point_id": int(pid),
                        "representation": representation,
                        "clustering": "hdbscan",
                        "cluster_id": int(label),
                    }
                    for pid, label in zip(point_ids, labels, strict=True)
                )

        if RUN_PROPOS:
            print("[RUN] ProPos")
            try:
                labels = run_propos(embedding_df, representation)
                save_labels(representation, "propos", point_ids, labels)
                assignments_wide[f"{representation}_propos"] = labels
                metrics_rows.append(compute_metrics(representation, "propos", embedding_df, labels))

                assignment_long_rows.extend(
                    {
                        "point_id": int(pid),
                        "representation": representation,
                        "clustering": "propos",
                        "cluster_id": int(label),
                    }
                    for pid, label in zip(point_ids, labels, strict=True)
                )

            except Exception as exc:
                print(f"[WARN] ProPos ignoré pour {representation}: {exc}")

    metrics_df = pd.DataFrame(metrics_rows)
    assignments_long_df = pd.DataFrame(assignment_long_rows)
    cluster_sizes_df = build_cluster_sizes(assignments_long_df)

    metrics_path = METRIC_DIR / "saint_tabpfn_metrics.csv"
    assignments_wide_path = OUTPUT_DIR / "saint_tabpfn_assignments_wide.csv"
    assignments_long_path = OUTPUT_DIR / "saint_tabpfn_assignments_long.csv"
    cluster_sizes_path = METRIC_DIR / "saint_tabpfn_cluster_sizes.csv"

    metrics_df.to_csv(metrics_path, index=False)
    assignments_wide.to_csv(assignments_wide_path, index=False)
    assignments_long_df.to_csv(assignments_long_path, index=False)
    cluster_sizes_df.to_csv(cluster_sizes_path, index=False)

    summary = {
        "created_at": datetime.now().isoformat(),
        "target_sample_size": TARGET_SAMPLE_SIZE,
        "n_selected_points": int(len(selected_point_ids)),
        "saint_shape": list(saint_df.shape),
        "tabpfn_shape": list(tabpfn_df.shape),
        "pseudo_y": pseudo_info,
        "config": {
            "target_k": TARGET_K,
            "tabpfn_device": TABPFN_DEVICE,
            "tabpfn_n_estimators": TABPFN_N_ESTIMATORS,
            "tabpfn_n_fold": TABPFN_N_FOLD,
            "dbscan_min_samples": DBSCAN_MIN_SAMPLES,
            "dbscan_eps_quantile": DBSCAN_EPS_QUANTILE,
            "hdbscan_min_cluster_size": HDBSCAN_MIN_CLUSTER_SIZE,
            "hdbscan_min_samples": HDBSCAN_MIN_SAMPLES,
            "propos_epochs": PROPOS_EPOCHS,
        },
        "outputs": {
            "metrics": str(metrics_path),
            "assignments_wide": str(assignments_wide_path),
            "assignments_long": str(assignments_long_path),
            "cluster_sizes": str(cluster_sizes_path),
            "saint_embedding": str(EMBEDDING_DIR / "saint_87281.parquet"),
            "tabpfn_embedding": str(EMBEDDING_DIR / "tabpfn_87281.parquet"),
            "full_saint_embedding": str(FULL_EMBEDDING_DIR / "saint_full.parquet"),
            "full_tabpfn_embedding": str(FULL_EMBEDDING_DIR / "tabpfn_full.parquet"),
        },
        "duration_seconds": float(time.perf_counter() - started_all),
    }

    save_json(summary, OUTPUT_DIR / "summary_saint_tabpfn.json")

    print("\n=== FINAL METRICS ===")
    if metrics_df.empty:
        print("Aucune métrique.")
    else:
        print(metrics_df.to_string(index=False))

    print("\n=== OUTPUTS ===")
    print(metrics_path)
    print(assignments_wide_path)
    print(assignments_long_path)
    print(cluster_sizes_path)
    print(OUTPUT_DIR / "summary_saint_tabpfn.json")

    print("\n[OK] Comparaison SAINT vs TabPFN terminée.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())