from pathlib import Path
import os
from functools import lru_cache
import json
import pandas as pd
import numpy as np

SAINT_PARQUET_PATH = Path(os.getenv(
    "SAINT_PARQUET_PATH",
    str(Path(__file__).resolve().parents[1] / "artifacts/embeddings/saint" / "saint_pfas_latent_mean.parquet"),
))
SAINT_METADATA_PATH = SAINT_PARQUET_PATH.with_suffix(".json")
SAINT_MODEL_PATH = SAINT_PARQUET_PATH.with_suffix(".pt")


@lru_cache(maxsize=1)
def load_saint_embeddings_df() -> pd.DataFrame:
    if not SAINT_PARQUET_PATH.exists():
        raise RuntimeError(f"Fichier SAINT introuvable: {SAINT_PARQUET_PATH}")

    df = pd.read_parquet(SAINT_PARQUET_PATH)

    if "point_id" not in df.columns:
        raise RuntimeError("Le parquet SAINT doit contenir point_id")

    z_cols = [c for c in df.columns if c.startswith("z")]
    if not z_cols:
        raise RuntimeError("Le parquet SAINT ne contient aucune colonne z*")

    return df[["point_id", *z_cols]].copy()


def load_saint_embeddings_for_point_ids(point_ids: list[int]) -> tuple[np.ndarray, list[str]]:
    saint_df = load_saint_embeddings_df()
    z_cols = [c for c in saint_df.columns if c.startswith("z")]

    wanted = pd.DataFrame({"point_id": point_ids})
    merged = wanted.merge(saint_df, on="point_id", how="left")

    missing_mask = merged[z_cols].isna().all(axis=1)
    if missing_mask.any():
        raise RuntimeError(
            f"{int(missing_mask.sum())} points n'ont pas d'embeddings SAINT pré-calculés."
        )

    x = merged[z_cols].to_numpy(dtype=np.float32)
    return x, z_cols


@lru_cache(maxsize=1)
def load_saint_artifact_metadata() -> dict:
    if not SAINT_METADATA_PATH.exists():
        return {
            "metadataStatus": "missing",
            "metadataPath": str(SAINT_METADATA_PATH),
        }

    try:
        raw = json.loads(SAINT_METADATA_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "metadataStatus": "unreadable",
            "metadataPath": str(SAINT_METADATA_PATH),
            "error": str(exc),
        }

    raw["metadataStatus"] = "loaded"
    raw["metadataPath"] = str(SAINT_METADATA_PATH)
    return raw


def get_saint_embedding_artifact_metadata() -> dict:
    metadata = dict(load_saint_artifact_metadata())
    input_columns = metadata.get("input_columns") or []

    return {
        "source": "precomputed_saint",
        "runName": metadata.get("run_name"),
        "dbName": metadata.get("db_name"),
        "categoryFilter": metadata.get("category_filter"),
        "sqlLimit": metadata.get("sql_limit"),
        "nRowsExported": metadata.get("n_rows_exported"),
        "nPointIdsExported": metadata.get("n_point_ids_exported"),
        "nFeaturesInput": metadata.get("n_features_input"),
        "inputColumns": input_columns,
        "inputColumnCount": len(input_columns),
        "pooling": metadata.get("pooling"),
        "embeddingDim": metadata.get("embedding_dim"),
        "preprocessing": metadata.get("preprocessing"),
        "saintConfig": metadata.get("saint_config"),
        "exportFiles": metadata.get("export_files"),
        "parquetPath": str(SAINT_PARQUET_PATH),
        "metadataPath": str(SAINT_METADATA_PATH),
        "modelPath": str(SAINT_MODEL_PATH),
        "parquetExists": SAINT_PARQUET_PATH.exists(),
        "metadataExists": SAINT_METADATA_PATH.exists(),
        "modelExists": SAINT_MODEL_PATH.exists(),
        "metadataStatus": metadata.get("metadataStatus"),
        "metadataError": metadata.get("error"),
    }
