from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

CORE_IMPORT_ERRORS: dict[str, str] = {}

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - handled at runtime
    np = None  # type: ignore[assignment]
    CORE_IMPORT_ERRORS["numpy"] = str(exc)

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover - handled at runtime
    pd = None  # type: ignore[assignment]
    CORE_IMPORT_ERRORS["pandas"] = str(exc)

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as exc:  # pragma: no cover - handled at runtime
    matplotlib = None  # type: ignore[assignment]
    plt = None  # type: ignore[assignment]
    CORE_IMPORT_ERRORS["matplotlib"] = str(exc)

try:
    from sqlalchemy import bindparam, create_engine, text
except ImportError as exc:  # pragma: no cover - handled at runtime
    bindparam = None  # type: ignore[assignment]
    create_engine = None  # type: ignore[assignment]
    text = None  # type: ignore[assignment]
    CORE_IMPORT_ERRORS["sqlalchemy"] = str(exc)

try:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.metrics import (
        calinski_harabasz_score,
        davies_bouldin_score,
        silhouette_score,
    )
    from sklearn.preprocessing import StandardScaler
except ImportError as exc:  # pragma: no cover - handled at runtime
    KMeans = None  # type: ignore[assignment]
    PCA = None  # type: ignore[assignment]
    StandardScaler = None  # type: ignore[assignment]
    silhouette_score = None  # type: ignore[assignment]
    davies_bouldin_score = None  # type: ignore[assignment]
    calinski_harabasz_score = None  # type: ignore[assignment]
    CORE_IMPORT_ERRORS["scikit-learn"] = str(exc)

try:
    import hdbscan as hdbscan_lib
except ImportError:
    hdbscan_lib = None

try:
    from sklearn.cluster import HDBSCAN as sklearn_hdbscan_cls
except Exception:
    sklearn_hdbscan_cls = None


RANDOM_STATE = 42
TARGET_SAMPLE_SIZE = 10_000_000
TARGET_KMEANS_CLUSTERS = 5
DEFAULT_HDBSCAN_MIN_CLUSTER_SIZE = 50
DEFAULT_HDBSCAN_MIN_SAMPLES = 10

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parents[1]
FRONTEND_DIR = PROJECT_DIR / "frontend"
OUTPUT_DIR = PROJECT_DIR / "artifacts/experiments/tabpfn"

SAINT_PARQUET_PATH = PROJECT_DIR / "artifacts/embeddings/saint" / "saint_pfas_latent_mean.parquet"
SAINT_METADATA_PATH = SAINT_PARQUET_PATH.with_suffix(".json")
SAINT_NOTEBOOK_PATH = PROJECT_DIR / "research/notebooks/saint_pfas.ipynb"
SAINT_DATASET_SCRIPT_PATH = PROJECT_DIR / "research/saint/pfas_saint_dataset.py"
MAIN_PIPELINE_PATH = PROJECT_DIR / "backend/main.py"

POINT_CSV_CANDIDATES = [
    PROJECT_DIR / ".local/research-data/point.csv",
    FRONTEND_DIR / "point.csv",
    SCRIPT_DIR / "point.csv",
]
METADONNEE_CSV_CANDIDATES = [
    PROJECT_DIR / ".local/research-data/metadonnee.csv",
    FRONTEND_DIR / "metadonnee.csv",
    SCRIPT_DIR / "metadonnee.csv",
]
SUBSTANCE_REF_CSV_CANDIDATES = [
    PROJECT_DIR / ".local/research-data/substance_ref.csv",
    FRONTEND_DIR / "substance_ref.csv",
    SCRIPT_DIR / "substance_ref.csv",
]


def find_file(candidates: list[Path | str]) -> Path | None:
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def load_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def require_core_dependencies() -> None:
    missing: list[str] = []
    for name in ("numpy", "pandas", "matplotlib", "sqlalchemy", "scikit-learn"):
        if name in CORE_IMPORT_ERRORS:
            missing.append(name)

    if importlib.util.find_spec("pg8000") is None:
        missing.append("pg8000")

    if importlib.util.find_spec("pyarrow") is None and importlib.util.find_spec("fastparquet") is None:
        missing.append("pyarrow or fastparquet")

    if missing:
        details = "\n".join(f"- {name}" for name in missing)
        raise RuntimeError(
            "Dependances Python manquantes pour cette experience.\n"
            "Installe au minimum:\n"
            f"{details}\n"
            "Exemple: pip install pandas numpy scikit-learn sqlalchemy pg8000 pyarrow matplotlib"
        )


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _fetch_table_columns(engine: Any, table_name: str, schema: str = "public") -> list[str]:
    query = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = :schema
          AND table_name = :table_name
        ORDER BY ordinal_position
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"schema": schema, "table_name": table_name}).fetchall()
    return [str(row[0]) for row in rows]


def _build_db_config() -> tuple[dict[str, Any], Path]:
    env_path = PROJECT_DIR / ".local/project.env" if (PROJECT_DIR / ".local/project.env").exists() else FRONTEND_DIR / ".env"
    env_values = load_env_file(env_path)
    db_config = {
        "host": os.getenv("DB_HOST") or env_values.get("DB_HOST") or "localhost",
        "port": int(os.getenv("DB_PORT") or env_values.get("DB_PORT") or "5432"),
        "database": os.getenv("DB_NAME") or env_values.get("DB_NAME") or "DAE-PFAS",
        "user": os.getenv("DB_USER") or env_values.get("DB_USER") or "postgres",
        "password": os.getenv("DB_PASSWORD") or env_values.get("DB_PASSWORD") or "",
    }
    return db_config, env_path


def _make_engine(db_config: dict[str, Any]) -> Any:
    if create_engine is None:
        raise RuntimeError("SQLAlchemy est requis pour lire PostgreSQL.")

    return create_engine(
        "postgresql+pg8000://",
        connect_args={
            "host": db_config["host"],
            "port": db_config["port"],
            "database": db_config["database"],
            "user": db_config["user"],
            "password": db_config["password"],
        },
        pool_pre_ping=True,
    )


def _load_csv_header(path: Path) -> list[str]:
    return list(pd.read_csv(path, nrows=0).columns)


def _first_existing_column(columns: list[str], candidates: list[str]) -> str | None:
    lower_map = {col.lower(): col for col in columns}
    for candidate in candidates:
        found = lower_map.get(candidate.lower())
        if found:
            return found
    return None


def _deduplicate_on_point_id(df: Any, label: str) -> tuple[Any, list[str]]:
    warnings_list: list[str] = []
    if "point_id" not in df.columns:
        raise RuntimeError(f"{label}: colonne point_id absente.")

    duplicated = int(df["point_id"].duplicated().sum())
    if duplicated:
        warnings_list.append(
            f"{label}: {duplicated} point_id dupliques detectes, conservation de la premiere occurrence."
        )
        df = df.drop_duplicates(subset=["point_id"], keep="first").copy()
    return df, warnings_list


def _align_by_point_id(df: Any, point_ids: list[int]) -> Any:
    indexed = df.set_index("point_id", drop=False)
    missing = [point_id for point_id in point_ids if point_id not in indexed.index]
    if missing:
        raise RuntimeError(f"{len(missing)} point_id sont absents lors de l'alignement.")
    aligned = indexed.loc[point_ids].copy()
    return aligned.reset_index(drop=True)


def load_point_matrix_from_postgres(
    db_config: dict[str, Any],
    saint_info: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    warnings_list: list[str] = []
    engine = _make_engine(db_config)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        point_columns = _fetch_table_columns(engine, "point")
        pfas_points_columns = _fetch_table_columns(engine, "pfas_points")

        saint_input_columns = list(saint_info.get("input_columns") or [])
        requested_point_columns = [col for col in saint_input_columns if col != "pfas_sum"]
        available_point_columns = [col for col in requested_point_columns if col in point_columns]
        missing_point_columns = [col for col in requested_point_columns if col not in point_columns]
        if missing_point_columns:
            warnings_list.append(
                "PostgreSQL: certaines colonnes SAINT sont absentes de public.point: "
                + ", ".join(missing_point_columns[:10])
                + (" ..." if len(missing_point_columns) > 10 else "")
            )

        exact_source_columns = [
            "id",
            "category",
        ]
        can_use_exact_source = all(col in pfas_points_columns for col in exact_source_columns) and "point_id" in point_columns

        if can_use_exact_source:
            select_parts = ["p.id AS point_id"]
            for metadata_col in ["lat", "lon", "year", "category", "matrix", "dataset_id", "pfas_sum"]:
                if metadata_col in pfas_points_columns:
                    select_parts.append(f"p.{_quote_ident(metadata_col)}")
            for col in available_point_columns:
                select_parts.append(f"v.{_quote_ident(col)}")

            query_sql = (
                "SELECT\n    "
                + ",\n    ".join(select_parts)
                + "\nFROM public.pfas_points p\nJOIN public.point v\n  ON v.point_id = p.id"
            )
            params: dict[str, Any] = {}
            category_filter = saint_info.get("category_filter")
            if category_filter and "category" in pfas_points_columns:
                query_sql += "\nWHERE p.category = :category_filter"
                params["category_filter"] = category_filter

            df = pd.read_sql(text(query_sql), engine, params=params)
            source_label = "postgresql public.pfas_points JOIN public.point"
            source_mode = "exact_saint_source"
        else:
            if "point_id" not in point_columns:
                raise RuntimeError("La table public.point ne contient pas point_id.")
            select_parts = [f"{_quote_ident('point_id')} AS point_id"] + [_quote_ident(col) for col in available_point_columns]
            query_sql = "SELECT\n    " + ",\n    ".join(select_parts) + "\nFROM public.point"
            df = pd.read_sql(text(query_sql), engine)
            source_label = "postgresql public.point"
            source_mode = "fallback_point_only"
            warnings_list.append(
                "Source PostgreSQL exacte indisponible, fallback vers public.point uniquement."
            )

        if df.empty:
            raise RuntimeError("La source PostgreSQL renvoie un DataFrame vide.")

        if "point_id" not in df.columns:
            raise RuntimeError("La matrice PostgreSQL doit contenir point_id.")

        df["point_id"] = pd.to_numeric(df["point_id"], errors="coerce")
        df = df.dropna(subset=["point_id"]).copy()
        df["point_id"] = df["point_id"].astype(np.int64)

        for column in df.columns:
            if column == "point_id":
                continue
            if column.startswith("pfas_") or column in {"lat", "lon", "year"}:
                df[column] = pd.to_numeric(df[column], errors="coerce")

        return df, {
            "source_label": source_label,
            "source_mode": source_mode,
            "warnings": warnings_list,
            "files_used": ["PostgreSQL"],
            "available_point_columns": available_point_columns,
            "missing_point_columns": missing_point_columns,
        }
    except Exception as exc:
        raise RuntimeError(
            "Impossible de lire PostgreSQL. Verifier les variables DB_* ou exporter public.point en point.csv."
        ) from exc
    finally:
        engine.dispose()


def load_point_matrix_from_csv(saint_info: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    point_csv_path = find_file(POINT_CSV_CANDIDATES)
    if point_csv_path is None:
        raise RuntimeError("Aucun point.csv n'a ete trouve dans les chemins attendus.")

    header = _load_csv_header(point_csv_path)
    point_id_col = _first_existing_column(header, ["point_id", "id"])
    if point_id_col is None:
        raise RuntimeError(f"{point_csv_path}: aucune colonne point_id/id detectee.")

    saint_input_columns = list(saint_info.get("input_columns") or [])
    requested_columns = [point_id_col] + [col for col in saint_input_columns if col in header]
    usecols = list(dict.fromkeys(requested_columns))
    df = pd.read_csv(point_csv_path, usecols=usecols, low_memory=False)

    if point_id_col != "point_id":
        df = df.rename(columns={point_id_col: "point_id"})

    df["point_id"] = pd.to_numeric(df["point_id"], errors="coerce")
    df = df.dropna(subset=["point_id"]).copy()
    df["point_id"] = df["point_id"].astype(np.int64)

    warnings_list: list[str] = []
    missing_columns = [col for col in saint_input_columns if col not in df.columns]
    if missing_columns:
        warnings_list.append(
            "CSV: certaines colonnes SAINT sont absentes du point.csv: "
            + ", ".join(missing_columns[:10])
            + (" ..." if len(missing_columns) > 10 else "")
        )

    for column in df.columns:
        if column == "point_id":
            continue
        if column.startswith("pfas_"):
            df[column] = pd.to_numeric(df[column], errors="coerce")

    return df, {
        "source_label": f"csv {point_csv_path}",
        "source_mode": "csv_fallback",
        "warnings": warnings_list,
        "files_used": [str(point_csv_path)],
        "missing_point_columns": missing_columns,
        "point_csv_path": str(point_csv_path),
    }


def load_optional_metadata(
    selected_point_ids: list[int],
    db_config: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    warnings_list: list[str] = []
    empty_df = pd.DataFrame({"point_id": pd.Series(dtype="int64")})
    if not selected_point_ids:
        return empty_df, {"warnings": warnings_list, "files_used": []}

    engine: Any | None = None
    try:
        engine = _make_engine(db_config)
        metadata_columns = _fetch_table_columns(engine, "metadonnee")
        if metadata_columns:
            point_id_col = _first_existing_column(metadata_columns, ["point_id", "id_point", "pointid"])
            if point_id_col is not None:
                selected_columns = [
                    point_id_col,
                    *[
                        col
                        for col in [
                            "lat",
                            "lon",
                            "year",
                            "category",
                            "matrix",
                            "dataset_id",
                            "commune",
                            "departement",
                            "region",
                            "country",
                        ]
                        if col in metadata_columns
                    ],
                ]

                query_sql = (
                    "SELECT\n    "
                    + ",\n    ".join(_quote_ident(col) for col in selected_columns)
                    + f"\nFROM public.metadonnee\nWHERE {_quote_ident(point_id_col)} IN :point_ids"
                )
                stmt = text(query_sql).bindparams(bindparam("point_ids", expanding=True))
                df = pd.read_sql(stmt, engine, params={"point_ids": selected_point_ids})
                if point_id_col != "point_id":
                    df = df.rename(columns={point_id_col: "point_id"})
                df["point_id"] = pd.to_numeric(df["point_id"], errors="coerce")
                df = df.dropna(subset=["point_id"]).copy()
                df["point_id"] = df["point_id"].astype(np.int64)
                df, dedup_warnings = _deduplicate_on_point_id(df, "metadonnee PostgreSQL")
                warnings_list.extend(dedup_warnings)
                return df, {
                    "warnings": warnings_list,
                    "files_used": ["PostgreSQL public.metadonnee"],
                }
    except Exception as exc:
        warnings_list.append(f"Metadata PostgreSQL indisponible: {exc}")
    finally:
        if engine is not None:
            engine.dispose()

    metadata_csv_path = find_file(METADONNEE_CSV_CANDIDATES)
    if metadata_csv_path is None:
        warnings_list.append("metadonnee optionnelle absente, poursuite sans enrichissement metadata.")
        return empty_df, {"warnings": warnings_list, "files_used": []}

    header = _load_csv_header(metadata_csv_path)
    point_id_col = _first_existing_column(header, ["point_id", "id_point", "pointid"])
    if point_id_col is None:
        warnings_list.append(f"{metadata_csv_path}: aucune colonne point_id metadata detectee.")
        return empty_df, {"warnings": warnings_list, "files_used": [str(metadata_csv_path)]}

    keep_columns = [point_id_col] + [
        col
        for col in [
            "lat",
            "lon",
            "year",
            "category",
            "matrix",
            "dataset_id",
            "commune",
            "departement",
            "region",
            "country",
        ]
        if col in header
    ]

    wanted_ids = set(int(point_id) for point_id in selected_point_ids)
    chunks: list[Any] = []
    for chunk in pd.read_csv(metadata_csv_path, usecols=keep_columns, chunksize=50000, low_memory=False):
        chunk[point_id_col] = pd.to_numeric(chunk[point_id_col], errors="coerce")
        chunk = chunk.dropna(subset=[point_id_col]).copy()
        chunk[point_id_col] = chunk[point_id_col].astype(np.int64)
        chunk = chunk[chunk[point_id_col].isin(wanted_ids)]
        if not chunk.empty:
            chunks.append(chunk)

    if not chunks:
        warnings_list.append("metadonnee.csv trouve mais aucun point_id selectionne n'a ete retrouve.")
        return empty_df, {"warnings": warnings_list, "files_used": [str(metadata_csv_path)]}

    df = pd.concat(chunks, ignore_index=True)
    if point_id_col != "point_id":
        df = df.rename(columns={point_id_col: "point_id"})
    df, dedup_warnings = _deduplicate_on_point_id(df, "metadonnee CSV")
    warnings_list.extend(dedup_warnings)
    return df, {
        "warnings": warnings_list,
        "files_used": [str(metadata_csv_path)],
    }


def load_substance_ref(db_config: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    warnings_list: list[str] = []
    engine: Any | None = None

    def _normalize_substance_ref(raw_df: Any) -> Any:
        if raw_df.empty:
            return pd.DataFrame(columns=["pfas_index", "substance_name", "column_name"])

        columns = list(raw_df.columns)
        index_col = _first_existing_column(columns, ["pfas_index", "index", "pfas_id", "id"])
        name_col = _first_existing_column(columns, ["substance_name", "name", "substance", "label"])
        if index_col is None or name_col is None:
            raise RuntimeError("Impossible d'identifier les colonnes de substance_ref.")

        out = raw_df.copy()
        out[index_col] = pd.to_numeric(out[index_col], errors="coerce")
        out = out.dropna(subset=[index_col]).copy()
        out[index_col] = out[index_col].astype(int)
        out[name_col] = out[name_col].astype(str)
        out = out.rename(columns={index_col: "pfas_index", name_col: "substance_name"})
        keep_cols = ["pfas_index", "substance_name"]
        for optional_col in ("cas_id", "isomer", "unit_ref", "unit", "units"):
            if optional_col in out.columns and optional_col not in keep_cols:
                keep_cols.append(optional_col)
        out = out[keep_cols].copy()
        out["column_name"] = out["pfas_index"].apply(lambda idx: f"pfas_{int(idx)}")
        return out.drop_duplicates(subset=["column_name"], keep="first").reset_index(drop=True)

    try:
        engine = _make_engine(db_config)
        substance_columns = _fetch_table_columns(engine, "substance_ref")
        if substance_columns:
            df = pd.read_sql(text("SELECT * FROM public.substance_ref"), engine)
            return _normalize_substance_ref(df), {
                "warnings": warnings_list,
                "files_used": ["PostgreSQL public.substance_ref"],
            }
    except Exception as exc:
        warnings_list.append(f"substance_ref PostgreSQL indisponible: {exc}")
    finally:
        if engine is not None:
            engine.dispose()

    substance_csv_path = find_file(SUBSTANCE_REF_CSV_CANDIDATES)
    if substance_csv_path is None:
        warnings_list.append("substance_ref optionnelle absente, poursuite sans traduction des PFAS.")
        return pd.DataFrame(columns=["pfas_index", "substance_name", "column_name"]), {
            "warnings": warnings_list,
            "files_used": [],
        }

    df = pd.read_csv(substance_csv_path, low_memory=False)
    try:
        normalized = _normalize_substance_ref(df)
    except Exception as exc:
        warnings_list.append(f"{substance_csv_path}: lecture substance_ref impossible ({exc}).")
        normalized = pd.DataFrame(columns=["pfas_index", "substance_name", "column_name"])

    return normalized, {
        "warnings": warnings_list,
        "files_used": [str(substance_csv_path)],
    }


def load_saint_embeddings() -> tuple[Any, dict[str, Any]]:
    if not SAINT_PARQUET_PATH.exists():
        raise RuntimeError(
            f"Fichier SAINT introuvable: {SAINT_PARQUET_PATH}. Comparaison SAINT vs TabPFN impossible."
        )

    try:
        saint_df = pd.read_parquet(SAINT_PARQUET_PATH)
    except Exception as exc:
        raise RuntimeError(
            "Lecture du parquet SAINT impossible. Installer pyarrow ou fastparquet si necessaire."
        ) from exc

    if "point_id" not in saint_df.columns:
        raise RuntimeError("Le parquet SAINT doit contenir point_id.")

    z_columns = [col for col in saint_df.columns if col.startswith("z")]
    if not z_columns:
        raise RuntimeError("Le parquet SAINT ne contient aucune colonne z*.")

    saint_df["point_id"] = pd.to_numeric(saint_df["point_id"], errors="coerce")
    saint_df = saint_df.dropna(subset=["point_id"]).copy()
    saint_df["point_id"] = saint_df["point_id"].astype(np.int64)
    saint_df, dedup_warnings = _deduplicate_on_point_id(saint_df, "SAINT parquet")

    metadata = {}
    if SAINT_METADATA_PATH.exists():
        try:
            metadata = json.loads(SAINT_METADATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            metadata = {}

    return saint_df[["point_id", *z_columns]].copy(), {
        "warnings": dedup_warnings,
        "files_used": [str(SAINT_PARQUET_PATH), str(SAINT_METADATA_PATH)],
        "embedding_columns": z_columns,
        "metadata": metadata,
    }


def inspect_saint_source() -> dict[str, Any]:
    warnings_list: list[str] = []
    files_inspected: list[str] = []

    metadata: dict[str, Any] = {}
    if SAINT_METADATA_PATH.exists():
        try:
            metadata = json.loads(SAINT_METADATA_PATH.read_text(encoding="utf-8"))
            files_inspected.append(str(SAINT_METADATA_PATH))
        except Exception as exc:
            warnings_list.append(f"Metadata SAINT illisible: {exc}")

    dataset_script_text = ""
    if SAINT_DATASET_SCRIPT_PATH.exists():
        dataset_script_text = SAINT_DATASET_SCRIPT_PATH.read_text(encoding="utf-8")
        files_inspected.append(str(SAINT_DATASET_SCRIPT_PATH))

    notebook_text = ""
    if SAINT_NOTEBOOK_PATH.exists():
        notebook_text = SAINT_NOTEBOOK_PATH.read_text(encoding="utf-8")
        files_inspected.append(str(SAINT_NOTEBOOK_PATH))

    main_text = ""
    if MAIN_PIPELINE_PATH.exists():
        main_text = MAIN_PIPELINE_PATH.read_text(encoding="utf-8")
        files_inspected.append(str(MAIN_PIPELINE_PATH))

    exact_source_detected = (
        "public.pfas_points" in notebook_text
        and "JOIN public.point" in notebook_text
    ) or (
        "public.pfas_points" in main_text
        and "JOIN public.point" in main_text
    )

    input_columns = list(metadata.get("input_columns") or [])
    preprocessing = dict(metadata.get("preprocessing") or {})
    if not input_columns and "pfas_cols = [c for c in filtered.columns if c.startswith(\"pfas_\")]" in dataset_script_text:
        warnings_list.append(
            "Metadata SAINT incomplete: la liste exacte des colonnes d'entree est absente."
        )

    return {
        "files_inspected": files_inspected,
        "warnings": warnings_list,
        "source_label": "postgresql public.pfas_points JOIN public.point" if exact_source_detected else "source SAINT partiellement detectee",
        "source_mode": "exact_saint_source" if exact_source_detected else "partial_detection",
        "category_filter": metadata.get("category_filter") or "Measurement",
        "db_name": metadata.get("db_name"),
        "input_columns": input_columns,
        "preprocessing": preprocessing,
        "n_rows_exported": metadata.get("n_rows_exported"),
        "n_point_ids_exported": metadata.get("n_point_ids_exported"),
        "embedding_dim": metadata.get("embedding_dim"),
        "pooling": metadata.get("pooling"),
        "sql_limit": metadata.get("sql_limit"),
        "parquet_path": SAINT_PARQUET_PATH,
        "metadata_path": SAINT_METADATA_PATH,
    }


def clean_pfas_matrix(df: Any, saint_info: dict[str, Any]) -> dict[str, Any]:
    warnings_list: list[str] = []
    if "point_id" not in df.columns:
        raise RuntimeError("La matrice PFAS doit contenir point_id.")

    metadata_input_columns = list(saint_info.get("input_columns") or [])
    if metadata_input_columns:
        ordered_feature_columns = [col for col in metadata_input_columns if col in df.columns]
    else:
        ordered_feature_columns = [col for col in df.columns if col.startswith("pfas_")]

    if not ordered_feature_columns:
        raise RuntimeError("Aucune colonne pfas_* utilisable n'a ete trouvee dans la matrice source.")

    raw_df = df[["point_id", *ordered_feature_columns]].copy()
    for column in ordered_feature_columns:
        raw_df[column] = pd.to_numeric(raw_df[column], errors="coerce")

    raw_df = raw_df.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    actual_pfas_columns = [
        col
        for col in ordered_feature_columns
        if col.startswith("pfas_")
        and col != "pfas_sum"
        and len(col.split("_")) == 2
        and col.split("_")[1].isdigit()
    ]

    if "pfas_sum" not in raw_df.columns and actual_pfas_columns:
        raw_df.insert(1, "pfas_sum", raw_df[actual_pfas_columns].sum(axis=1))
        ordered_feature_columns = ["pfas_sum", *ordered_feature_columns]
        warnings_list.append(
            "pfas_sum absent de la source fallback, reconstruction technique a partir des colonnes pfas_*."
        )

    numeric_feature_columns = [col for col in raw_df.columns if col != "point_id"]
    raw_df[numeric_feature_columns] = raw_df[numeric_feature_columns].clip(lower=0.0)

    clean_df = raw_df.copy()
    clean_df[numeric_feature_columns] = np.log1p(clean_df[numeric_feature_columns].to_numpy(dtype=np.float64))

    kept_columns: list[str] = []
    dropped_columns: list[str] = []
    for column in numeric_feature_columns:
        values = clean_df[column].to_numpy(dtype=np.float64)
        if np.allclose(values, 0.0) or np.nanstd(values) == 0.0:
            dropped_columns.append(column)
        else:
            kept_columns.append(column)

    clean_df = clean_df[["point_id", *kept_columns]].copy()
    model_df = clean_df.copy()

    use_standardize = bool((saint_info.get("preprocessing") or {}).get("use_standardize"))
    if use_standardize and kept_columns:
        scaler = StandardScaler()
        model_df[kept_columns] = scaler.fit_transform(model_df[kept_columns].to_numpy(dtype=np.float64))
        model_df[kept_columns] = np.nan_to_num(
            model_df[kept_columns].to_numpy(dtype=np.float64),
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )

    return {
        "clean_df": clean_df,
        "model_df": model_df,
        "kept_feature_columns": kept_columns,
        "dropped_feature_columns": dropped_columns,
        "warnings": warnings_list,
        "used_standardize": use_standardize,
        "actual_pfas_columns": [col for col in kept_columns if col in actual_pfas_columns],
    }


def build_common_sample(
    point_df: Any,
    saint_df: Any,
    sample_size: int = TARGET_SAMPLE_SIZE,
    random_state: int = RANDOM_STATE,
) -> tuple[Any, Any, dict[str, Any]]:
    warnings_list: list[str] = []
    point_df, point_warnings = _deduplicate_on_point_id(point_df, "Matrice PFAS")
    saint_df, saint_warnings = _deduplicate_on_point_id(saint_df, "Embeddings SAINT")
    warnings_list.extend(point_warnings)
    warnings_list.extend(saint_warnings)

    common_point_ids = sorted(set(point_df["point_id"]).intersection(set(saint_df["point_id"])))
    if not common_point_ids:
        raise RuntimeError("Aucun point_id commun entre la matrice PFAS et les embeddings SAINT.")

    if len(common_point_ids) <= sample_size:
        selected_point_ids = common_point_ids
        warnings_list.append(
            f"Seulement {len(common_point_ids)} points communs disponibles, utilisation de tous les points."
        )
    else:
        rng = np.random.default_rng(random_state)
        selected_point_ids = sorted(rng.choice(np.array(common_point_ids), size=sample_size, replace=False).tolist())

    point_sample = _align_by_point_id(point_df, selected_point_ids)
    saint_sample = _align_by_point_id(saint_df, selected_point_ids)

    return point_sample, saint_sample, {
        "selected_point_ids": selected_point_ids,
        "n_common_points": len(common_point_ids),
        "n_selected_points": len(selected_point_ids),
        "warnings": warnings_list,
    }


def compute_pca_embeddings(point_sample_model_df: Any) -> tuple[Any, dict[str, Any]]:
    feature_columns = [col for col in point_sample_model_df.columns if col != "point_id"]
    if not feature_columns:
        raise RuntimeError("Impossible de calculer PCA: aucune feature PFAS disponible.")

    x = point_sample_model_df[feature_columns].to_numpy(dtype=np.float64)
    n_components = min(8, x.shape[0], x.shape[1])
    if n_components < 1:
        raise RuntimeError("Impossible de calculer PCA: n_components < 1.")

    pca = PCA(n_components=n_components)
    z = pca.fit_transform(x)
    columns = [f"pca_z{i + 1}" for i in range(z.shape[1])]
    out_df = pd.DataFrame(z, columns=columns)
    out_df.insert(0, "point_id", point_sample_model_df["point_id"].to_numpy(dtype=np.int64))

    return out_df, {
        "shape": z.shape,
        "columns": columns,
        "explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
    }


def _build_pseudo_y(clean_sample_df: Any) -> tuple[Any, dict[str, Any]]:
    if "pfas_sum" in clean_sample_df.columns:
        pfas_signal = clean_sample_df["pfas_sum"].to_numpy(dtype=np.float64)
        signal_name = "pfas_sum"
    else:
        numeric_pfas_columns = [
            col
            for col in clean_sample_df.columns
            if col.startswith("pfas_")
            and col != "point_id"
            and col != "pfas_sum"
            and len(col.split("_")) == 2
            and col.split("_")[1].isdigit()
        ]
        if not numeric_pfas_columns:
            raise RuntimeError("Impossible de construire pseudo_y: aucune colonne PFAS numerique exploitable.")
        pfas_signal = clean_sample_df[numeric_pfas_columns].sum(axis=1).to_numpy(dtype=np.float64)
        signal_name = "sum(actual_pfas_columns)"

    try:
        pseudo_y = pd.qcut(pfas_signal, q=4, labels=False, duplicates="drop")
        pseudo_y = np.asarray(pseudo_y, dtype=np.int64)
    except Exception:
        pseudo_y = np.array([], dtype=np.int64)

    unique_values = np.unique(pseudo_y) if pseudo_y.size else np.array([], dtype=np.int64)
    if unique_values.size >= 2:
        return pseudo_y, {
            "strategy": "quantiles_of_pfas_sum",
            "signal": signal_name,
            "n_classes": int(unique_values.size),
        }

    numeric_feature_columns = [col for col in clean_sample_df.columns if col != "point_id"]
    x_fallback = clean_sample_df[numeric_feature_columns].to_numpy(dtype=np.float64)
    fallback_pca_components = min(4, x_fallback.shape[0], x_fallback.shape[1])
    if fallback_pca_components < 1:
        raise RuntimeError("Pseudo_y fallback impossible: matrice vide.")

    x_reduced = PCA(n_components=fallback_pca_components).fit_transform(x_fallback)
    fallback_k = min(TARGET_KMEANS_CLUSTERS, max(2, x_reduced.shape[0]))
    pseudo_y = KMeans(n_clusters=fallback_k, random_state=RANDOM_STATE, n_init="auto").fit_predict(x_reduced)
    return pseudo_y.astype(np.int64), {
        "strategy": "kmeans_on_pca_fallback",
        "signal": signal_name,
        "n_classes": int(np.unique(pseudo_y).size),
    }


def compute_tabpfn_embeddings(
    point_sample_model_df: Any,
    clean_sample_df: Any,
) -> tuple[Any | None, dict[str, Any]]:
    warnings_list: list[str] = []
    feature_columns = [col for col in point_sample_model_df.columns if col != "point_id"]
    if not feature_columns:
        return None, {
            "status": "skipped",
            "warnings": ["TabPFN ignore: aucune feature disponible."],
            "error": "Aucune feature PFAS disponible.",
        }

    if importlib.util.find_spec("tabpfn") is None or importlib.util.find_spec("tabpfn_extensions") is None:
        return None, {
            "status": "skipped",
            "warnings": [
                "TabPFN ignore: packages absents. Installer avec: pip install tabpfn tabpfn-extensions"
            ],
            "error": "pip install tabpfn tabpfn-extensions",
        }

    # Ne jamais forcer TABPFN_NO_BROWSER ici.
    # Si un token est fourni dans le terminal, TabPFN doit pouvoir l'utiliser.
    if os.getenv("TABPFN_TOKEN"):
        os.environ.pop("TABPFN_NO_BROWSER", None)

    if not os.getenv("TABPFN_MODEL_CACHE_DIR") and not os.getenv("TABPFN_TOKEN"):
        warnings_list.append(
            "TABPFN local sans TABPFN_MODEL_CACHE_DIR/TABPFN_TOKEN: l'extraction peut echouer si les poids locaux ne sont pas deja disponibles."
        )

    try:
        from tabpfn import TabPFNClassifier
        from tabpfn_extensions.embedding import TabPFNEmbedding
    except Exception as exc:
        return None, {
            "status": "skipped",
            "warnings": warnings_list
            + ["TabPFN ignore: import impossible. Installer avec: pip install tabpfn tabpfn-extensions"],
            "error": str(exc),
        }

    x = point_sample_model_df[feature_columns].to_numpy(dtype=np.float32)
    try:
        pseudo_y, pseudo_info = _build_pseudo_y(clean_sample_df)
    except Exception as exc:
        return None, {
            "status": "skipped",
            "warnings": warnings_list + [f"TabPFN ignore: pseudo_y impossible ({exc})"],
            "error": str(exc),
        }

    # pseudo_y is not ground truth. It is only a weak technical signal to let
    # TabPFN expose dense sample embeddings in this exploratory clustering test.
    try:
        model = TabPFNClassifier(n_estimators=2, random_state=RANDOM_STATE)
        try:
            transformer = TabPFNEmbedding(n_fold=3, model=model)
        except TypeError:
            try:
                transformer = TabPFNEmbedding(model=model, n_fold=3)
            except TypeError:
                transformer = TabPFNEmbedding(model=model)

        embeddings = transformer.fit_transform(x, pseudo_y)
        embeddings = np.asarray(embeddings, dtype=np.float32)

        # TabPFNEmbedding peut retourner :
        # - 2D : (n_samples, embedding_dim)
        # - 3D : (n_estimators, n_samples, embedding_dim)
        # Ici, on moyenne les estimateurs pour obtenir une matrice 2D.
        if embeddings.ndim == 3:
            if embeddings.shape[1] == x.shape[0]:
                embeddings = embeddings.mean(axis=0)  # (n_estimators, n_samples, dim) -> (n_samples, dim)
            elif embeddings.shape[0] == x.shape[0]:
                embeddings = embeddings.mean(axis=1)  # (n_samples, n_estimators, dim) -> (n_samples, dim)
            else:
                raise RuntimeError(f"Shape TabPFN 3D inattendue: {embeddings.shape}")

        if embeddings.ndim != 2:
            raise RuntimeError(f"Shape TabPFN invalide apres conversion: {embeddings.shape}")

        columns = [f"tabpfn_z{i + 1}" for i in range(embeddings.shape[1])]
        out_df = pd.DataFrame(embeddings, columns=columns)
        out_df.insert(0, "point_id", point_sample_model_df["point_id"].to_numpy(dtype=np.int64))

        return out_df, {
            "status": "ok",
            "warnings": warnings_list,
            "error": None,
            "shape": embeddings.shape,
            "columns": columns,
            "pseudo_y": pseudo_info,
        }
    except Exception as exc:
        warnings_list.append(f"TabPFN ignore: extraction impossible ({exc})")
        return None, {
            "status": "skipped",
            "warnings": warnings_list,
            "error": str(exc),
            "pseudo_y": pseudo_info,
        }


def run_kmeans(embedding_df: Any) -> tuple[Any, dict[str, Any]]:
    feature_columns = [col for col in embedding_df.columns if col != "point_id"]
    x = embedding_df[feature_columns].to_numpy(dtype=np.float64)
    n_clusters = min(TARGET_KMEANS_CLUSTERS, x.shape[0])
    if n_clusters < 1:
        raise RuntimeError("KMeans impossible: aucun point disponible.")
    if n_clusters == 1:
        labels = np.zeros(x.shape[0], dtype=int)
    else:
        labels = KMeans(
            n_clusters=n_clusters,
            random_state=RANDOM_STATE,
            n_init="auto",
        ).fit_predict(x)
    return labels, {"n_clusters_requested": TARGET_KMEANS_CLUSTERS, "n_clusters_used": int(n_clusters)}


def run_hdbscan_if_available(embedding_df: Any) -> tuple[Any | None, list[str]]:
    warnings_list: list[str] = []
    feature_columns = [col for col in embedding_df.columns if col != "point_id"]
    x = embedding_df[feature_columns].to_numpy(dtype=np.float64)

    if hdbscan_lib is None and sklearn_hdbscan_cls is None:
        warnings_list.append("HDBSCAN indisponible: package non installe. Continuation avec KMeans uniquement.")
        return None, warnings_list

    try:
        min_cluster_size = min(DEFAULT_HDBSCAN_MIN_CLUSTER_SIZE, max(5, x.shape[0] // 20))
        min_samples = min(DEFAULT_HDBSCAN_MIN_SAMPLES, max(3, x.shape[0] // 50))
        if hdbscan_lib is not None:
            clusterer = hdbscan_lib.HDBSCAN(
                min_cluster_size=min_cluster_size,
                min_samples=min_samples,
                cluster_selection_method="eom",
            )
        else:
            clusterer = sklearn_hdbscan_cls(
                min_cluster_size=min_cluster_size,
                min_samples=min_samples,
                cluster_selection_method="eom",
            )
        labels = clusterer.fit_predict(x)
        return labels, warnings_list
    except Exception as exc:
        warnings_list.append(f"HDBSCAN a echoue et sera ignore: {exc}")
        return None, warnings_list


def compute_metrics(
    method: str,
    representation: str,
    clustering: str,
    embedding_df: Any,
    labels: Any,
) -> tuple[dict[str, Any], list[str]]:
    warnings_list: list[str] = []
    feature_columns = [col for col in embedding_df.columns if col != "point_id"]
    x = embedding_df[feature_columns].to_numpy(dtype=np.float64)
    labels = np.asarray(labels)

    noise_points = int(np.sum(labels == -1))
    valid_mask = labels != -1
    valid_x = x[valid_mask]
    valid_labels = labels[valid_mask]
    valid_clusters = sorted(set(valid_labels.tolist()))
    n_clusters = len(valid_clusters)

    row = {
        "method": method,
        "representation": representation,
        "clustering": clustering,
        "n_points": int(x.shape[0]),
        "n_features": int(x.shape[1]),
        "n_clusters": int(n_clusters),
        "noise_points": noise_points,
        "silhouette": None,
        "davies_bouldin": None,
        "calinski_harabasz": None,
    }

    if n_clusters < 2 or valid_x.shape[0] < 2:
        warnings_list.append(
            f"{method}: un seul cluster valide detecte, metriques de separation non calculees."
        )
        return row, warnings_list

    try:
        row["silhouette"] = float(silhouette_score(valid_x, valid_labels))
    except Exception as exc:
        warnings_list.append(f"{method}: silhouette non calculee ({exc}).")
    try:
        row["davies_bouldin"] = float(davies_bouldin_score(valid_x, valid_labels))
    except Exception as exc:
        warnings_list.append(f"{method}: Davies-Bouldin non calcule ({exc}).")
    try:
        row["calinski_harabasz"] = float(calinski_harabasz_score(valid_x, valid_labels))
    except Exception as exc:
        warnings_list.append(f"{method}: Calinski-Harabasz non calcule ({exc}).")

    if clustering == "hdbscan" and noise_points > int(0.25 * len(labels)):
        warnings_list.append(f"{method}: beaucoup de bruit detecte avec HDBSCAN ({noise_points} points).")

    return row, warnings_list


def compute_cluster_sizes(assignments_long_df: Any) -> Any:
    if assignments_long_df.empty:
        return pd.DataFrame(columns=["method", "representation", "clustering", "cluster_id", "n_points"])

    sizes = (
        assignments_long_df.groupby(["method", "representation", "clustering", "cluster_id"], dropna=False)
        .size()
        .reset_index(name="n_points")
        .sort_values(["representation", "clustering", "cluster_id"])
        .reset_index(drop=True)
    )
    return sizes


def compute_dominant_pfas(
    clean_sample_df: Any,
    assignments_long_df: Any,
    substance_ref_df: Any,
) -> Any:
    candidate_pfas_columns = [
        col
        for col in clean_sample_df.columns
        if col.startswith("pfas_")
        and col != "pfas_sum"
        and len(col.split("_")) == 2
        and col.split("_")[1].isdigit()
    ]
    if not candidate_pfas_columns or assignments_long_df.empty:
        return pd.DataFrame(
            columns=[
                "method",
                "representation",
                "clustering",
                "cluster_id",
                "n_points",
                "dominant_pfas",
                "substance_name",
                "mean_dominant_pfas",
            ]
        )

    merged = assignments_long_df.merge(clean_sample_df, on="point_id", how="left")
    name_map = {}
    if not substance_ref_df.empty and {"column_name", "substance_name"}.issubset(substance_ref_df.columns):
        name_map = substance_ref_df.set_index("column_name")["substance_name"].to_dict()

    rows: list[dict[str, Any]] = []
    group_columns = ["method", "representation", "clustering", "cluster_id"]
    for keys, group in merged.groupby(group_columns, dropna=False):
        means = group[candidate_pfas_columns].mean(numeric_only=True)
        if means.empty:
            continue
        dominant_pfas = str(means.idxmax())
        rows.append(
            {
                "method": keys[0],
                "representation": keys[1],
                "clustering": keys[2],
                "cluster_id": keys[3],
                "n_points": int(len(group)),
                "dominant_pfas": dominant_pfas,
                "substance_name": name_map.get(dominant_pfas),
                "mean_dominant_pfas": float(means.loc[dominant_pfas]),
            }
        )

    return pd.DataFrame(rows).sort_values(["representation", "clustering", "cluster_id"]).reset_index(drop=True)


def _write_parquet(df: Any, path: Path) -> None:
    try:
        df.to_parquet(path, index=False)
    except Exception as exc:
        raise RuntimeError(
            f"Ecriture parquet impossible pour {path}. Installer pyarrow ou fastparquet si necessaire."
        ) from exc


def save_outputs(
    metrics_df: Any,
    assignments_df: Any,
    pca_df: Any,
    saint_sample_df: Any,
    cluster_sizes_df: Any,
    dominant_pfas_df: Any,
    tabpfn_df: Any | None,
) -> dict[str, str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    comparison_metrics_path = OUTPUT_DIR / "comparison_metrics.csv"
    comparison_assignments_path = OUTPUT_DIR / "comparison_assignments.csv"
    pca_used_sample_path = OUTPUT_DIR / "pca_used_sample.parquet"
    saint_used_sample_path = OUTPUT_DIR / "saint_used_sample.parquet"
    cluster_sizes_path = OUTPUT_DIR / "cluster_sizes.csv"
    dominant_pfas_path = OUTPUT_DIR / "dominant_pfas_by_cluster.csv"

    metrics_df.to_csv(comparison_metrics_path, index=False)
    assignments_df.to_csv(comparison_assignments_path, index=False)
    cluster_sizes_df.to_csv(cluster_sizes_path, index=False)
    dominant_pfas_df.to_csv(dominant_pfas_path, index=False)
    _write_parquet(pca_df, pca_used_sample_path)
    _write_parquet(saint_sample_df, saint_used_sample_path)

    paths = {
        "comparison_metrics.csv": str(comparison_metrics_path),
        "comparison_assignments.csv": str(comparison_assignments_path),
        "pca_used_sample.parquet": str(pca_used_sample_path),
        "saint_used_sample.parquet": str(saint_used_sample_path),
        "cluster_sizes.csv": str(cluster_sizes_path),
        "dominant_pfas_by_cluster.csv": str(dominant_pfas_path),
    }

    if tabpfn_df is not None:
        tabpfn_path = OUTPUT_DIR / "tabpfn_embeddings.parquet"
        _write_parquet(tabpfn_df, tabpfn_path)
        paths["tabpfn_embeddings.parquet"] = str(tabpfn_path)

    return paths


def plot_metrics(metrics_df: Any) -> dict[str, str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_paths: dict[str, str] = {}

    configs = [
        ("silhouette", "metrics_silhouette.png", True, "Silhouette score"),
        ("davies_bouldin", "metrics_davies_bouldin.png", False, "Davies-Bouldin score"),
        ("calinski_harabasz", "metrics_calinski_harabasz.png", True, "Calinski-Harabasz score"),
    ]

    for metric_column, filename, higher_is_better, title in configs:
        plot_df = metrics_df[["method", metric_column]].dropna().copy()
        if plot_df.empty:
            continue
        plot_df = plot_df.sort_values(metric_column, ascending=not higher_is_better)

        fig, ax = plt.subplots(figsize=(10, max(4, 0.7 * len(plot_df))))
        ax.barh(plot_df["method"], plot_df[metric_column], color="#3B82F6")
        ax.set_title(title)
        ax.set_xlabel(metric_column)
        ax.invert_yaxis()
        fig.tight_layout()

        path = OUTPUT_DIR / filename
        fig.savefig(path, dpi=160)
        plt.close(fig)
        output_paths[filename] = str(path)

    return output_paths


def plot_cluster_sizes(cluster_sizes_df: Any) -> dict[str, str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_paths: dict[str, str] = {}

    for representation in ["pca", "saint", "tabpfn"]:
        plot_df = cluster_sizes_df[
            (cluster_sizes_df["representation"] == representation)
            & (cluster_sizes_df["clustering"] == "kmeans")
        ].copy()
        if plot_df.empty:
            continue

        plot_df = plot_df.sort_values("cluster_id")
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(plot_df["cluster_id"].astype(str), plot_df["n_points"], color="#10B981")
        ax.set_title(f"Cluster sizes - {representation.upper()} + KMeans")
        ax.set_xlabel("cluster_id")
        ax.set_ylabel("n_points")
        fig.tight_layout()

        filename = f"cluster_sizes_{representation}_kmeans.png"
        path = OUTPUT_DIR / filename
        fig.savefig(path, dpi=160)
        plt.close(fig)
        output_paths[filename] = str(path)

    return output_paths


def plot_embeddings_2d(
    embedding_df: Any,
    labels: Any,
    representation: str,
    clustering: str,
) -> str:
    feature_columns = [col for col in embedding_df.columns if col != "point_id"]
    x = embedding_df[feature_columns].to_numpy(dtype=np.float64)

    if x.shape[1] == 1:
        coords = np.column_stack([x[:, 0], np.zeros(x.shape[0])])
    elif x.shape[1] == 2:
        coords = x[:, :2]
    else:
        coords = PCA(n_components=2).fit_transform(x)

    fig, ax = plt.subplots(figsize=(8, 6))
    labels_array = np.asarray(labels)
    unique_labels = sorted(set(labels_array.tolist()))

    for label in unique_labels:
        mask = labels_array == label
        if label == -1:
            color = "#9CA3AF"
            legend_label = "noise"
        else:
            color = plt.cm.tab10(int(label) % 10)
            legend_label = f"cluster {label}"
        ax.scatter(
            coords[mask, 0],
            coords[mask, 1],
            s=14,
            alpha=0.75,
            c=[color],
            label=legend_label,
        )

    ax.set_title(f"Embedding 2D - {representation.upper()} + {clustering.upper()}")
    ax.set_xlabel("component_1")
    ax.set_ylabel("component_2")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()

    filename = f"embedding_2d_{representation}_{clustering}.png"
    path = OUTPUT_DIR / filename
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return str(path)


def _best_method(metrics_df: Any, metric_column: str, higher_is_better: bool) -> str | None:
    candidate_df = metrics_df.dropna(subset=[metric_column]).copy()
    if candidate_df.empty:
        return None
    candidate_df = candidate_df.sort_values(metric_column, ascending=not higher_is_better)
    return str(candidate_df.iloc[0]["method"])


def _build_interpretation(metrics_df: Any, tabpfn_info: dict[str, Any]) -> str:
    best_silhouette = _best_method(metrics_df, "silhouette", True)
    best_db = _best_method(metrics_df, "davies_bouldin", False)
    best_ch = _best_method(metrics_df, "calinski_harabasz", True)

    if tabpfn_info.get("status") != "ok":
        return (
            "Interpretation automatique: la comparaison exploitable repose sur PCA et SAINT, "
            "car TabPFN a ete ignore pour cette execution."
        )

    if best_silhouette and best_db and best_ch and len({best_silhouette, best_db, best_ch}) == 1:
        return f"Interpretation automatique: {best_silhouette} semble etre la representation la plus convaincante sur les trois metriques principales."

    return (
        "Interpretation automatique: aucune methode ne domine toutes les metriques, "
        "il faut lire silhouette, Davies-Bouldin et Calinski-Harabasz ensemble."
    )


def print_summary(summary: dict[str, Any]) -> None:
    print("\n=== SAINT SOURCE ===")
    print(summary["saint_source_label"])
    print(f"Files inspected: {', '.join(summary['saint_files_inspected'])}")
    print(f"SAINT parquet: {summary['saint_parquet_path']}")
    print(f"SAINT metadata: {summary['saint_metadata_path']}")
    print(f"Input PFAS columns declared by SAINT: {summary['saint_input_column_count']}")
    print(f"SAINT category filter: {summary['saint_category_filter']}")
    print(f"SAINT preprocessing: {summary['saint_preprocessing']}")

    print("\n=== TABPFN / PCA SOURCE ===")
    print(summary["matrix_source_label"])
    print(f"Files used: {', '.join(summary['matrix_files_used'])}")
    if summary["missing_optional_files"]:
        print("Optional missing files:")
        for item in summary["missing_optional_files"]:
            print(f"- {item}")

    print("\n=== SAMPLE ===")
    print(f"Common point_id count: {summary['n_common_points']}")
    print(f"Selected point_id count: {summary['n_selected_points']}")
    print(f"PFAS feature count used: {summary['n_pfas_features']}")
    print(f"X clean shape: {summary['x_shape']}")
    print(f"PCA shape: {summary['pca_shape']}")
    print(f"SAINT shape: {summary['saint_shape']}")
    if summary["tabpfn_shape"] is not None:
        print(f"TabPFN shape: {summary['tabpfn_shape']}")
    else:
        print("TabPFN shape: skipped")

    print("\n=== METRICS ===")
    if summary["metrics_df"].empty:
        print("Aucune metrique calculee.")
    else:
        print(summary["metrics_df"].to_string(index=False))

    print("\n=== BEST METHODS ===")
    print(f"Best silhouette: {summary['best_silhouette']}")
    print(f"Best Davies-Bouldin: {summary['best_davies_bouldin']}")
    print(f"Best Calinski-Harabasz: {summary['best_calinski_harabasz']}")

    print("\n=== OUTPUTS ===")
    for name, path in summary["output_paths"].items():
        print(f"{name}: {path}")
    for name, path in summary["figure_paths"].items():
        print(f"{name}: {path}")

    if summary["warnings"]:
        print("\n=== WARNINGS ===")
        for warning in summary["warnings"]:
            print(f"- {warning}")

    print("\n=== INTERPRETATION ===")
    print(summary["interpretation"])


def main() -> int:
    try:
        require_core_dependencies()
    except Exception as exc:
        print(str(exc))
        return 1

    all_warnings: list[str] = []
    figure_paths: dict[str, str] = {}

    try:
        saint_info = inspect_saint_source()
        all_warnings.extend(saint_info.get("warnings", []))

        saint_df, saint_load_info = load_saint_embeddings()
        all_warnings.extend(saint_load_info.get("warnings", []))

        db_config, env_path = _build_db_config()
        matrix_source_info: dict[str, Any]
        try:
            raw_matrix_df, matrix_source_info = load_point_matrix_from_postgres(db_config, saint_info)
        except Exception as postgres_exc:
            all_warnings.append(str(postgres_exc))
            raw_matrix_df, matrix_source_info = load_point_matrix_from_csv(saint_info)

        all_warnings.extend(matrix_source_info.get("warnings", []))

        clean_info = clean_pfas_matrix(raw_matrix_df, saint_info)
        all_warnings.extend(clean_info.get("warnings", []))

        clean_df = clean_info["clean_df"]
        model_df = clean_info["model_df"]

        clean_sample_df, saint_sample_df, sample_info = build_common_sample(clean_df, saint_df)
        all_warnings.extend(sample_info.get("warnings", []))
        selected_point_ids = list(sample_info["selected_point_ids"])

        model_sample_df = _align_by_point_id(model_df, selected_point_ids)

        context_columns = [
            col
            for col in ["point_id", "lat", "lon", "year", "category", "matrix", "dataset_id"]
            if col in raw_matrix_df.columns
        ]
        context_df = raw_matrix_df[context_columns].copy() if context_columns else pd.DataFrame({"point_id": selected_point_ids})
        context_df = _align_by_point_id(context_df, selected_point_ids)

        metadata_df, metadata_info = load_optional_metadata(selected_point_ids, db_config)
        all_warnings.extend(metadata_info.get("warnings", []))

        substance_ref_df, substance_info = load_substance_ref(db_config)
        all_warnings.extend(substance_info.get("warnings", []))

        pca_df, pca_info = compute_pca_embeddings(model_sample_df)

        tabpfn_df, tabpfn_info = compute_tabpfn_embeddings(model_sample_df, clean_sample_df)
        all_warnings.extend(tabpfn_info.get("warnings", []))

        assignments_df = context_df.copy()
        if not metadata_df.empty:
            metadata_merge_columns = [col for col in metadata_df.columns if col != "point_id" and col not in assignments_df.columns]
            if metadata_merge_columns:
                assignments_df = assignments_df.merge(
                    metadata_df[["point_id", *metadata_merge_columns]],
                    on="point_id",
                    how="left",
                )

        metrics_rows: list[dict[str, Any]] = []
        assignment_long_rows: list[dict[str, Any]] = []
        kmeans_label_store: dict[str, Any] = {}

        representation_frames = [
            ("pca", pca_df),
            ("saint", saint_sample_df),
            ("tabpfn", tabpfn_df),
        ]

        for representation, embedding_df in representation_frames:
            if embedding_df is None:
                continue

            kmeans_labels, _ = run_kmeans(embedding_df)
            assignments_df[f"cluster_{representation}_kmeans"] = kmeans_labels
            kmeans_label_store[representation] = kmeans_labels

            method_name = f"{representation.upper()} + KMeans" if representation != "tabpfn" else "TabPFN + KMeans"
            metric_row, metric_warnings = compute_metrics(
                method=method_name,
                representation=representation,
                clustering="kmeans",
                embedding_df=embedding_df,
                labels=kmeans_labels,
            )
            metrics_rows.append(metric_row)
            all_warnings.extend(metric_warnings)

            assignment_long_rows.extend(
                {
                    "point_id": int(point_id),
                    "method": method_name,
                    "representation": representation,
                    "clustering": "kmeans",
                    "cluster_id": int(cluster_id),
                }
                for point_id, cluster_id in zip(embedding_df["point_id"], kmeans_labels, strict=True)
            )

            hdbscan_labels, hdbscan_warnings = run_hdbscan_if_available(embedding_df)
            all_warnings.extend(hdbscan_warnings)
            if hdbscan_labels is not None:
                method_name = f"{representation.upper()} + HDBSCAN" if representation != "tabpfn" else "TabPFN + HDBSCAN"
                assignments_df[f"cluster_{representation}_hdbscan"] = hdbscan_labels
                metric_row, metric_warnings = compute_metrics(
                    method=method_name,
                    representation=representation,
                    clustering="hdbscan",
                    embedding_df=embedding_df,
                    labels=hdbscan_labels,
                )
                metrics_rows.append(metric_row)
                all_warnings.extend(metric_warnings)
                assignment_long_rows.extend(
                    {
                        "point_id": int(point_id),
                        "method": method_name,
                        "representation": representation,
                        "clustering": "hdbscan",
                        "cluster_id": int(cluster_id),
                    }
                    for point_id, cluster_id in zip(embedding_df["point_id"], hdbscan_labels, strict=True)
                )

        required_assignment_columns = [
            "cluster_pca_kmeans",
            "cluster_saint_kmeans",
            "cluster_tabpfn_kmeans",
        ]
        for column in required_assignment_columns:
            if column not in assignments_df.columns:
                assignments_df[column] = np.nan

        metrics_df = pd.DataFrame(
            metrics_rows,
            columns=[
                "method",
                "representation",
                "clustering",
                "n_points",
                "n_features",
                "n_clusters",
                "noise_points",
                "silhouette",
                "davies_bouldin",
                "calinski_harabasz",
            ],
        )

        assignments_long_df = pd.DataFrame(
            assignment_long_rows,
            columns=["point_id", "method", "representation", "clustering", "cluster_id"],
        )

        cluster_sizes_df = compute_cluster_sizes(assignments_long_df)
        dominant_pfas_df = compute_dominant_pfas(clean_sample_df, assignments_long_df, substance_ref_df)

        output_paths = save_outputs(
            metrics_df=metrics_df,
            assignments_df=assignments_df,
            pca_df=pca_df,
            saint_sample_df=saint_sample_df,
            cluster_sizes_df=cluster_sizes_df,
            dominant_pfas_df=dominant_pfas_df,
            tabpfn_df=tabpfn_df,
        )

        figure_paths.update(plot_metrics(metrics_df))
        figure_paths.update(plot_cluster_sizes(cluster_sizes_df))

        if "pca" in kmeans_label_store:
            figure_paths["embedding_2d_pca_kmeans.png"] = plot_embeddings_2d(
                pca_df, kmeans_label_store["pca"], "pca", "kmeans"
            )
        if "saint" in kmeans_label_store:
            figure_paths["embedding_2d_saint_kmeans.png"] = plot_embeddings_2d(
                saint_sample_df, kmeans_label_store["saint"], "saint", "kmeans"
            )
        if tabpfn_df is not None and "tabpfn" in kmeans_label_store:
            figure_paths["embedding_2d_tabpfn_kmeans.png"] = plot_embeddings_2d(
                tabpfn_df, kmeans_label_store["tabpfn"], "tabpfn", "kmeans"
            )

        summary = {
            "saint_source_label": saint_info["source_label"],
            "saint_files_inspected": saint_info["files_inspected"],
            "saint_parquet_path": str(saint_info["parquet_path"]),
            "saint_metadata_path": str(saint_info["metadata_path"]),
            "saint_input_column_count": len(saint_info.get("input_columns") or []),
            "saint_category_filter": saint_info.get("category_filter"),
            "saint_preprocessing": saint_info.get("preprocessing"),
            "matrix_source_label": matrix_source_info["source_label"],
            "matrix_files_used": matrix_source_info.get("files_used", []) + [str(env_path)],
            "missing_optional_files": [
                warning
                for warning in all_warnings
                if "optionnelle absente" in warning or "absente" in warning
            ],
            "n_common_points": sample_info["n_common_points"],
            "n_selected_points": sample_info["n_selected_points"],
            "n_pfas_features": len(clean_info["kept_feature_columns"]),
            "x_shape": tuple(model_sample_df.drop(columns=["point_id"]).shape),
            "pca_shape": pca_info["shape"],
            "saint_shape": (
                int(saint_sample_df.shape[0]),
                int(len([col for col in saint_sample_df.columns if col != "point_id"])),
            ),
            "tabpfn_shape": tabpfn_info.get("shape"),
            "metrics_df": metrics_df,
            "best_silhouette": _best_method(metrics_df, "silhouette", True),
            "best_davies_bouldin": _best_method(metrics_df, "davies_bouldin", False),
            "best_calinski_harabasz": _best_method(metrics_df, "calinski_harabasz", True),
            "output_paths": output_paths,
            "figure_paths": figure_paths,
            "warnings": all_warnings,
            "interpretation": _build_interpretation(metrics_df, tabpfn_info),
        }
        print_summary(summary)
        return 0
    except Exception as exc:
        print(f"Execution interrompue: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
