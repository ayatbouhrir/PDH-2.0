import os
import sys
import time
from datetime import datetime, timezone
from functools import lru_cache
import importlib.util
from multiprocessing import Pool
from typing import Any, Literal
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fastapi.responses import JSONResponse
import json as _json
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import create_engine, text, bindparam
from sklearn.cluster import DBSCAN, KMeans, MiniBatchKMeans, Birch
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.ensemble import RandomForestClassifier
from visualization import build_substance_maps
from saint_loader import (
    get_saint_embedding_artifact_metadata,
    load_saint_embeddings_for_point_ids,
)
from saint_live import compute_saint_embeddings_live, SaintLiveConfig
from clamp.clamp_service import compute_clamp_explanation, ClampServiceError
from fastapi import FastAPI, HTTPException, Body, Request

try:
    import hdbscan as hdbscan_lib
except ImportError:
    hdbscan_lib = None

try:
    from sklearn.cluster import HDBSCAN as SklearnHDBSCAN
except Exception:
    SklearnHDBSCAN = None


MSSP_MAX_POINTS = 2000
MSSP_KNN = 12
MSSP_THETA = 0.85
MSSP_MAX_K = 12

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
from visualization import (
    build_temporal_visualization,
    build_radar_visualization,
)


app = FastAPI(title="PFAS Clustering API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("PFAS_FRONTEND_URL", "http://127.0.0.1:5173"),
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request
from fastapi.responses import JSONResponse
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    print(f"[UNHANDLED EXCEPTION] {exc}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Erreur interne du serveur Python : {str(exc)}"},
    )

#..........CONFIG.................#
MINIBATCH_THRESHOLD = 1_00_000
DBSCAN_SAMPLE_THRESHOLD = 1_0_000
DBSCAN_TIMEOUT_SECONDS = 120
TSNE_FALLBACK_THRESHOLD = 50_000

load_dotenv()

PG_PARAMS = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "dbname": os.getenv("DB_NAME", "DAE-PFAS"),
}
PFAS_SOURCE_TABLE = os.getenv("PFAS_SOURCE_TABLE", "point")
CACHE_DIR = Path(os.getenv("ANALYSIS_CACHE_DIR", str(Path(__file__).resolve().parents[1] / ".local/cache/analysis")))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
PROPOS_CACHE_DIR = Path(os.getenv("PROPOS_CACHE_DIR", str(Path(__file__).resolve().parents[1] / ".local/cache/propos")))
PROPOS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
PROPOS_REFERENCE_ARTIFACT = PROPOS_CACHE_DIR / "propos_simple_reference.pt"
PROPOS_LIVE_DIR = PROPOS_CACHE_DIR / "live"
PROPOS_LIVE_DIR.mkdir(parents=True, exist_ok=True)
PRESERVED_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[1] / "artifacts/reference-runs/2026-06-29"
PRESERVED_DEFAULT_ANALYSIS_DIR = PRESERVED_DEFAULT_CACHE_DIR / "analysis_cache"
PRESERVED_DEFAULT_FILTERS = {
    "category": "Measurement",
    "datasetId": [],
    "matrix": [],
    "yearRange": [2003, 2025],
    "lassoRegion": [],
    "substances": [],
    "viewport": None,
}
PRESERVED_DEFAULT_CASES = {
    "kmeans": {
        "path": PRESERVED_DEFAULT_ANALYSIS_DIR
        / "kmeans"
        / "8bc105f76184639020d6044ad88823be96e0fc5ab0cb7f473d9412effb9efd9a.json",
        "params": {
            "k": 5,
            "maxIterations": 100,
            "preprocessing": "none",
            "reduction": "saint",
        },
    },
    "dbscan": {
        "path": PRESERVED_DEFAULT_ANALYSIS_DIR
        / "dbscan"
        / "073752ae9f3f28caa65db7cd402fffaff00161a44c0197fd73b256101cd4aa08.json",
        "params": {
            "eps": 0.008,
            "minPts": 10,
            "preprocessing": "none",
            "reduction": "saint",
        },
    },
    "hdbscan": {
        "path": PRESERVED_DEFAULT_ANALYSIS_DIR
        / "hdbscan"
        / "6be9d2dcaa41c5ac0a619c4a2128d2f3818b10629f64bea9a201c8c43c6bb608.json",
        "params": {
            "minClusterSize": 30,
            "minSamples": 10,
            "clusterSelectionMethod": "eom",
            "preprocessing": "none",
            "reduction": "saint",
        },
    },
    "propos": {
        "path": PRESERVED_DEFAULT_ANALYSIS_DIR
        / "propos"
        / "640467088adb3cec8460cf9925912dfdcb05e95c3516d562ab8e731c0513b829.json",
        "params": {
            "k": 5,
            "maxIterations": 100,
            "preprocessing": "none",
            "reduction": "saint",
        },
    },
}
PROPOS_MASTER_DIR = Path(__file__).resolve().parents[1] / "vendor/propos"
PROPOS_TABULAR_ADAPTER_PATH = PROPOS_MASTER_DIR / "tabular_adapter.py"
PIPELINE_VERSION = os.getenv("ANALYSIS_CACHE_VERSION", "v3")
ANALYSIS_HISTORY_LIMIT = 10
ANALYSIS_SESSION_TABLE = "analysis_cache_sessions"


engine = create_engine(
    "postgresql+pg8000://",
    connect_args={
        "host": PG_PARAMS["host"],
        "port": PG_PARAMS["port"],
        "user": PG_PARAMS["user"],
        "password": PG_PARAMS["password"],
        "database": PG_PARAMS["dbname"],
    },
    pool_pre_ping=True,
)

with engine.connect() as conn:
    conn.execute(text("SELECT 1"))
print("Connexion PostgreSQL OK")


#............MODELS...............#



class Viewport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    south: float
    west: float
    north: float
    east: float


class LassoPoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lat: float
    lon: float


class SubstanceFilter(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    unit: str
    rangeMode: str | None = None
    filteredRange: list[float] | None = None
    rawRange: list[float] | None = None


class Filters(BaseModel):
   
    model_config = ConfigDict(extra="ignore")

    category: str | None = None
    datasetId: list[str] = Field(default_factory=list)
    matrix: list[str] = Field(default_factory=list)
    yearRange: list[int] | None = None
    lassoRegion: list[LassoPoint] = Field(default_factory=list)
    substances: list[SubstanceFilter] = Field(default_factory=list)

class AnalysisParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    k: int = 5
    maxIterations: int = 100
    eps: float = 0.008
    minPts: int = 10
    minClusterSize: int = 30
    minSamples: int = 10
    clusterSelectionMethod: Literal["eom", "leaf"] = "eom"
    preprocessing: Literal["none", "standardize", "normalize"] = "none"
    reduction: Literal["none", "pca", "tsne", "autoencoder", "saint"] = "saint"
    birchThreshold: float = 25.0
    birchBranchingFactor: int = 50

class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    selectedModelPfas: list[str] = Field(default_factory=lambda: ["All"])

    algorithm: Literal["kmeans", "dbscan", "hdbscan", "propos"]
    filters: Filters = Field(default_factory=Filters)
    viewport: Viewport | None = None
    params: AnalysisParams = Field(default_factory=AnalysisParams)
    mode: Literal["simple", "expert"] = "expert"


class BirchCondenseRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    filters: Filters = Field(default_factory=Filters)
    viewport: Viewport | None = None
    selectedModelPfas: list[str] = Field(default_factory=lambda: ["All"])
    preprocessing: Literal["none", "standardize", "normalize"] = "none"

    birchThreshold: float = 0.7
    birchBranchingFactor: int = 50

    assignments: dict[str, int] = Field(default_factory=dict)


class AssignmentItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pointId: str | int
    cluster: int
#............HELPERS...............#


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def normalize_assignments_payload(assignments: Any) -> dict[str, int]:
    if isinstance(assignments, dict):
        normalized: dict[str, int] = {}
        for point_id, cluster_id in assignments.items():
            try:
                normalized[str(point_id)] = int(cluster_id)
            except (TypeError, ValueError):
                continue
        return normalized

    normalized = {}
    if isinstance(assignments, list):
        for item in assignments:
            if isinstance(item, BaseModel):
                point_id = getattr(item, "pointId", None)
                cluster_id = getattr(item, "cluster", None)
            elif isinstance(item, dict):
                point_id = item.get("pointId")
                cluster_id = item.get("cluster")
            else:
                continue

            if point_id is None or cluster_id is None:
                continue

            try:
                normalized[str(point_id)] = int(cluster_id)
            except (TypeError, ValueError):
                continue
    return normalized

def stable_json_dumps(value: Any) -> str:
    return _json.dumps(
        json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

def build_analysis_params_hash(payload: dict) -> str:
    return hashlib.sha256(
        stable_json_dumps(payload).encode("utf-8")
    ).hexdigest()

def get_analysis_cache_path(cache_key: str) -> Path:
    return CACHE_DIR / f"{cache_key}.json"

def load_cached_analysis(cache_key: str) -> dict | None:
    path = get_analysis_cache_path(cache_key)
    if not path.exists():
        return None

    return _json.loads(path.read_text(encoding="utf-8"))

def save_cached_analysis(cache_key: str, payload: dict) -> None:
    path = get_analysis_cache_path(cache_key)
    path.write_text(
        _json.dumps(json_safe(payload), ensure_ascii=False),
        encoding="utf-8",
    )


def normalize_string_list(values: list[Any] | None, *, treat_all_as_single=False) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()

    for raw in values or []:
        value = str(raw).strip()
        if not value:
            continue

        if treat_all_as_single and value == "All":
            return ["All"]

        if value in seen:
            continue

        seen.add(value)
        items.append(value)

    return sorted(items)


def normalize_filters_for_cache(filters: Filters | dict[str, Any]) -> dict[str, Any]:
    payload = filters.model_dump() if isinstance(filters, BaseModel) else dict(filters)

    year_range = payload.get("yearRange")
    normalized_year_range: list[int] | None = None
    if isinstance(year_range, list) and len(year_range) >= 2:
        try:
            start = int(year_range[0])
            end = int(year_range[1])
            normalized_year_range = [min(start, end), max(start, end)]
        except Exception:
            normalized_year_range = json_safe(year_range)

    normalized_substances: list[dict[str, Any]] = []
    for substance in payload.get("substances") or []:
        item = dict(substance or {})
        normalized_substances.append(
            {
                "name": str(item.get("name") or "").strip(),
                "unit": str(item.get("unit") or "").strip(),
                "rangeMode": item.get("rangeMode"),
                "filteredRange": json_safe(item.get("filteredRange")),
                "rawRange": json_safe(item.get("rawRange")),
            }
        )

    normalized_substances.sort(
        key=lambda item: (
            item.get("name") or "",
            item.get("unit") or "",
            item.get("rangeMode") or "",
            stable_json_dumps(item.get("filteredRange")),
            stable_json_dumps(item.get("rawRange")),
        )
    )

    return {
        "category": payload.get("category"),
        "datasetId": normalize_string_list(payload.get("datasetId")),
        "matrix": normalize_string_list(payload.get("matrix")),
        "yearRange": normalized_year_range,
        "lassoRegion": json_safe(payload.get("lassoRegion") or []),
        "substances": normalized_substances,
    }


def normalize_viewport_for_cache(viewport: Viewport | dict[str, Any] | None) -> dict[str, float] | None:
    if viewport is None:
        return None

    payload = viewport.model_dump() if isinstance(viewport, BaseModel) else dict(viewport)

    try:
        return {
            "south": float(payload["south"]),
            "west": float(payload["west"]),
            "north": float(payload["north"]),
            "east": float(payload["east"]),
        }
    except Exception:
        return json_safe(payload)


def build_cache_session_payload(
    req: AnalysisRequest,
    effective_reduction: str,
    birch_preprocessing: str,
    birch_threshold: float,
    birch_branching_factor: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    filters_payload = normalize_filters_for_cache(req.filters)
    filters_payload["viewport"] = normalize_viewport_for_cache(req.viewport)

    params_payload = req.params.model_dump()
    params_payload["reduction"] = effective_reduction

    parameters_payload = {
        "schemaVersion": "analysis_trace_v1",
        "algorithm": req.algorithm,
        "mode": req.mode,
        "selectedModelPfas": normalize_string_list(
            req.selectedModelPfas,
            treat_all_as_single=True,
        )
        or ["All"],
        "params": json_safe(params_payload),
        "birch": {
            "enabled": True,
            "preprocessing": birch_preprocessing,
            "threshold": birch_threshold,
            "branchingFactor": birch_branching_factor,
        },
    }

    return parameters_payload, filters_payload


def db_json_param(value: Any) -> str | None:
    if value is None:
        return None
    return stable_json_dumps(value)


def decode_json_column(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return _json.loads(value)
    return value


def datetime_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def datetime_to_epoch_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp() * 1000)
    return None


def ensure_analysis_sessions_table() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS public.{ANALYSIS_SESSION_TABLE} (
                    cache_key TEXT PRIMARY KEY,
                    analysis_type TEXT NOT NULL,
                    parameters_json JSONB NOT NULL,
                    filters_json JSONB NOT NULL,
                    results_json JSONB,
                    map_state_json JSONB,
                    panel_state_json JSONB,
                    version TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ready',
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    name TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    last_opened_at TIMESTAMPTZ,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                ALTER TABLE public.{ANALYSIS_SESSION_TABLE}
                ADD COLUMN IF NOT EXISTS name TEXT
                """
            )
        )
        conn.execute(
            text(
                f"""
                ALTER TABLE public.{ANALYSIS_SESSION_TABLE}
                ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{ANALYSIS_SESSION_TABLE}_status_last_opened
                ON public.{ANALYSIS_SESSION_TABLE} (status, last_opened_at DESC, created_at DESC)
                """
            )
        )


def fetch_analysis_session(cache_key: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    f"""
                    SELECT
                        cache_key,
                        analysis_type,
                        parameters_json,
                        filters_json,
                        results_json,
                        map_state_json,
                        panel_state_json,
                        version,
                        status,
                        hit_count,
                        name,
                        created_at,
                        last_opened_at
                    FROM public.{ANALYSIS_SESSION_TABLE}
                    WHERE cache_key = :cache_key
                    """
                ),
                {"cache_key": cache_key},
            )
            .mappings()
            .first()
        )

    if row is None:
        return None

    return dict(row)


def upsert_analysis_session(
    *,
    cache_key: str,
    analysis_type: str,
    parameters_json: dict[str, Any],
    filters_json: dict[str, Any],
    results_json: dict[str, Any] | None,
    version: str,
    status: str,
    map_state_json: dict[str, Any] | None = None,
    panel_state_json: dict[str, Any] | None = None,
    name: str | None = None,
    last_opened: bool = False,
) -> dict[str, Any]:
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    f"""
                    INSERT INTO public.{ANALYSIS_SESSION_TABLE} (
                        cache_key,
                        analysis_type,
                        parameters_json,
                        filters_json,
                        results_json,
                        map_state_json,
                        panel_state_json,
                        version,
                        status,
                        hit_count,
                        name,
                        last_opened_at,
                        updated_at
                    )
                    VALUES (
                        :cache_key,
                        :analysis_type,
                        CAST(:parameters_json AS JSONB),
                        CAST(:filters_json AS JSONB),
                        CAST(:results_json AS JSONB),
                        CAST(:map_state_json AS JSONB),
                        CAST(:panel_state_json AS JSONB),
                        :version,
                        :status,
                        :hit_count,
                        :name,
                        CASE WHEN :last_opened THEN NOW() ELSE NULL END,
                        NOW()
                    )
                    ON CONFLICT (cache_key) DO UPDATE SET
                        analysis_type = EXCLUDED.analysis_type,
                        parameters_json = EXCLUDED.parameters_json,
                        filters_json = EXCLUDED.filters_json,
                        results_json = COALESCE(EXCLUDED.results_json, public.{ANALYSIS_SESSION_TABLE}.results_json),
                        map_state_json = COALESCE(EXCLUDED.map_state_json, public.{ANALYSIS_SESSION_TABLE}.map_state_json),
                        panel_state_json = COALESCE(EXCLUDED.panel_state_json, public.{ANALYSIS_SESSION_TABLE}.panel_state_json),
                        version = EXCLUDED.version,
                        status = EXCLUDED.status,
                        hit_count = GREATEST(public.{ANALYSIS_SESSION_TABLE}.hit_count, EXCLUDED.hit_count),
                        name = COALESCE(EXCLUDED.name, public.{ANALYSIS_SESSION_TABLE}.name),
                        last_opened_at = CASE
                            WHEN :last_opened THEN NOW()
                            ELSE public.{ANALYSIS_SESSION_TABLE}.last_opened_at
                        END,
                        updated_at = NOW()
                    RETURNING
                        cache_key,
                        analysis_type,
                        parameters_json,
                        filters_json,
                        results_json,
                        map_state_json,
                        panel_state_json,
                        version,
                        status,
                        hit_count,
                        name,
                        created_at,
                        last_opened_at
                    """
                ),
                {
                    "cache_key": cache_key,
                    "analysis_type": analysis_type,
                    "parameters_json": db_json_param(parameters_json),
                    "filters_json": db_json_param(filters_json),
                    "results_json": db_json_param(results_json),
                    "map_state_json": db_json_param(map_state_json),
                    "panel_state_json": db_json_param(panel_state_json),
                    "version": version,
                    "status": status,
                    "hit_count": 0,
                    "name": name,
                    "last_opened": last_opened,
                },
            )
            .mappings()
            .first()
        )

    return dict(row)


def mark_analysis_session_failed(
    cache_key: str,
    *,
    error_message: str,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                UPDATE public.{ANALYSIS_SESSION_TABLE}
                SET
                    status = 'failed',
                    results_json = CAST(:results_json AS JSONB),
                    updated_at = NOW()
                WHERE cache_key = :cache_key
                """
            ),
            {
                "cache_key": cache_key,
                "results_json": db_json_param({"error": error_message}),
            },
        )


def touch_analysis_session(cache_key: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    f"""
                    UPDATE public.{ANALYSIS_SESSION_TABLE}
                    SET
                        hit_count = hit_count + 1,
                        last_opened_at = NOW(),
                        updated_at = NOW()
                    WHERE cache_key = :cache_key
                    RETURNING
                        cache_key,
                        analysis_type,
                        parameters_json,
                        filters_json,
                        results_json,
                        map_state_json,
                        panel_state_json,
                        version,
                        status,
                        hit_count,
                        name,
                        created_at,
                        last_opened_at
                    """
                ),
                {"cache_key": cache_key},
            )
            .mappings()
            .first()
        )

    if row is None:
        return None

    return dict(row)


def update_analysis_session_state(
    cache_key: str,
    *,
    map_state_json: dict[str, Any] | None,
    panel_state_json: dict[str, Any] | None,
) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    f"""
                    UPDATE public.{ANALYSIS_SESSION_TABLE}
                    SET
                        map_state_json = COALESCE(CAST(:map_state_json AS JSONB), map_state_json),
                        panel_state_json = COALESCE(CAST(:panel_state_json AS JSONB), panel_state_json),
                        last_opened_at = COALESCE(last_opened_at, NOW()),
                        updated_at = NOW()
                    WHERE cache_key = :cache_key
                    RETURNING
                        cache_key,
                        analysis_type,
                        parameters_json,
                        filters_json,
                        results_json,
                        map_state_json,
                        panel_state_json,
                        version,
                        status,
                        hit_count,
                        name,
                        created_at,
                        last_opened_at
                    """
                ),
                {
                    "cache_key": cache_key,
                    "map_state_json": db_json_param(map_state_json),
                    "panel_state_json": db_json_param(panel_state_json),
                },
            )
            .mappings()
            .first()
        )

    if row is None:
        return None

    return dict(row)


def rename_analysis_session(cache_key: str, name: str | None) -> dict[str, Any] | None:
    clean_name = (name or "").strip() or None

    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    f"""
                    UPDATE public.{ANALYSIS_SESSION_TABLE}
                    SET
                        name = :name,
                        updated_at = NOW()
                    WHERE cache_key = :cache_key
                    RETURNING
                        cache_key,
                        analysis_type,
                        parameters_json,
                        filters_json,
                        results_json,
                        map_state_json,
                        panel_state_json,
                        version,
                        status,
                        hit_count,
                        name,
                        created_at,
                        last_opened_at
                    """
                ),
                {
                    "cache_key": cache_key,
                    "name": clean_name,
                },
            )
            .mappings()
            .first()
        )

    if row is None:
        return None

    return dict(row)


def delete_analysis_session(cache_key: str) -> bool:
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                DELETE FROM public.{ANALYSIS_SESSION_TABLE}
                WHERE cache_key = :cache_key
                """
            ),
            {"cache_key": cache_key},
        )

    return (result.rowcount or 0) > 0


def clear_analysis_sessions() -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text(
                f"""
                DELETE FROM public.{ANALYSIS_SESSION_TABLE}
                """
            )
        )

    return int(result.rowcount or 0)


def list_analysis_sessions(limit: int = ANALYSIS_HISTORY_LIMIT) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))

    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    f"""
                    SELECT
                        cache_key,
                        analysis_type,
                        parameters_json,
                        filters_json,
                        results_json,
                        map_state_json,
                        panel_state_json,
                        version,
                        status,
                        hit_count,
                        name,
                        created_at,
                        last_opened_at
                    FROM public.{ANALYSIS_SESSION_TABLE}
                    WHERE status = 'ready'
                      AND results_json IS NOT NULL
                    ORDER BY COALESCE(last_opened_at, created_at) DESC, created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
            .mappings()
            .all()
        )

    return [dict(row) for row in rows]


def build_history_snapshot_from_session(
    row: dict[str, Any],
    *,
    include_result: bool = False,
) -> dict[str, Any]:
    parameters = decode_json_column(row.get("parameters_json")) or {}
    filters = decode_json_column(row.get("filters_json")) or {}
    results = decode_json_column(row.get("results_json")) or {}
    map_state = decode_json_column(row.get("map_state_json")) or {}
    filters_for_snapshot = dict(filters)
    viewport_from_filters = filters_for_snapshot.pop("viewport", None)

    params = parameters.get("params") or {}
    birch = parameters.get("birch") or {}

    return {
        "filters": json_safe(filters_for_snapshot),
        "viewport": json_safe(map_state.get("viewport") or viewport_from_filters),
        "params": {
            "k": params.get("k"),
            "maxIterations": params.get("maxIterations"),
            "eps": params.get("eps"),
            "minPts": params.get("minPts"),
            "minClusterSize": params.get("minClusterSize"),
            "minSamples": params.get("minSamples"),
            "clusterSelectionMethod": params.get("clusterSelectionMethod"),
            "preprocessing": params.get("preprocessing", "none"),
            "reduction": params.get("reduction", "none"),
            "birchThreshold": params.get("birchThreshold") or birch.get("threshold"),
            "birchBranchingFactor": params.get("birchBranchingFactor") or birch.get("branchingFactor"),
        },
        "selectedModelPfas": json_safe(parameters.get("selectedModelPfas") or ["All"]),
        "mode": parameters.get("mode", "expert"),
        "algorithm": row.get("analysis_type"),
        "displayMode": map_state.get("displayMode") or results.get("displayMode") or "points",
        "result": json_safe(results) if include_result else None,
    }


def serialize_history_entry(
    row: dict[str, Any],
    *,
    include_result: bool = False,
) -> dict[str, Any]:
    results = decode_json_column(row.get("results_json")) or {}
    summary = results.get("summary") or {}

    created_at_ms = datetime_to_epoch_ms(row.get("created_at"))
    last_opened_at_ms = datetime_to_epoch_ms(row.get("last_opened_at"))

    return {
        "id": row.get("cache_key"),
        "name": row.get("name"),
        "timestamp": created_at_ms or int(time.time() * 1000),
        "createdAt": datetime_to_iso(row.get("created_at")),
        "lastOpenedAt": last_opened_at_ms,
        "lastOpenedAtIso": datetime_to_iso(row.get("last_opened_at")),
        "algorithm": row.get("analysis_type"),
        "params": build_history_snapshot_from_session(row)["params"],
        "pfasSelected": build_history_snapshot_from_session(row)["selectedModelPfas"],
        "pointCount": int(summary.get("analyzedPoints") or 0),
        "clusterCount": int(summary.get("clusterCount") or 0),
        "noiseCount": int(summary.get("noiseCount") or 0),
        "durationMs": int(summary.get("durationMs") or 0),
        "globalMetrics": json_safe(results.get("globalMetrics")),
        "metricsSummary": json_safe(results.get("metricsSummary")),
        "requestSnapshot": json_safe(results.get("requestSnapshot")),
        "runMetadata": json_safe(results.get("runMetadata")),
        "reductionMeta": json_safe(results.get("reductionMeta")),
        "clusteringMeta": json_safe(results.get("clusteringMeta")),
        "condensationMeta": json_safe(results.get("condensationMeta")),
        "analysisId": row.get("cache_key"),
        "cacheKey": row.get("cache_key"),
        "paramsHash": row.get("cache_key"),
        "cached": int(row.get("hit_count") or 0) > 0,
        "status": row.get("status"),
        "version": row.get("version"),
        "hitCount": int(row.get("hit_count") or 0),
        "mapState": json_safe(decode_json_column(row.get("map_state_json"))),
        "panelState": json_safe(decode_json_column(row.get("panel_state_json"))),
        "snapshot": build_history_snapshot_from_session(row, include_result=include_result),
    }


def build_cached_response_from_session(
    row: dict[str, Any],
    *,
    cached: bool,
) -> dict[str, Any]:
    results = decode_json_column(row.get("results_json")) or {}
    payload = dict(results)
    cache_key = row.get("cache_key")

    payload["analysisId"] = cache_key
    payload["cacheKey"] = cache_key
    payload["paramsHash"] = cache_key
    payload["cached"] = cached
    payload["status"] = row.get("status")
    payload["version"] = row.get("version")
    payload["hitCount"] = int(row.get("hit_count") or 0)
    payload["createdAt"] = datetime_to_iso(row.get("created_at"))
    payload["lastOpenedAt"] = datetime_to_iso(row.get("last_opened_at"))
    payload["mapState"] = json_safe(decode_json_column(row.get("map_state_json")))
    payload["panelState"] = json_safe(decode_json_column(row.get("panel_state_json")))
    payload["historyEntry"] = serialize_history_entry(row, include_result=False)
    return payload


def hydrate_analysis_session_from_file_cache(
    *,
    cache_key: str,
    analysis_type: str,
    parameters_json: dict[str, Any],
    filters_json: dict[str, Any],
) -> dict[str, Any] | None:
    cached_payload = load_cached_analysis(cache_key)
    if cached_payload is None:
        return None

    return upsert_analysis_session(
        cache_key=cache_key,
        analysis_type=analysis_type,
        parameters_json=parameters_json,
        filters_json=filters_json,
        results_json=json_safe(cached_payload),
        version=PIPELINE_VERSION,
        status="ready",
        last_opened=False,
    )


def _matches_preserved_default_case(
    *,
    req: AnalysisRequest,
    filters_json: dict[str, Any],
    effective_reduction: str,
) -> dict[str, Any] | None:
    if os.getenv("PFAS_PRESERVED_CACHE", "true").lower() == "false":
        return None
    case = PRESERVED_DEFAULT_CASES.get(req.algorithm)
    if case is None:
        return None

    if not _is_all_selected_model_pfas(req.selectedModelPfas):
        return None

    if stable_json_dumps(filters_json) != stable_json_dumps(PRESERVED_DEFAULT_FILTERS):
        return None

    for key, expected in case["params"].items():
        actual = effective_reduction if key == "reduction" else getattr(req.params, key, None)
        if actual != expected:
            return None

    return case


def hydrate_analysis_session_from_preserved_default_cache(
    *,
    req: AnalysisRequest,
    cache_key: str,
    params_hash: str,
    effective_reduction: str,
    parameters_json: dict[str, Any],
    filters_json: dict[str, Any],
) -> dict[str, Any] | None:
    case = _matches_preserved_default_case(
        req=req,
        filters_json=filters_json,
        effective_reduction=effective_reduction,
    )
    if case is None:
        return None

    preserved_path = case["path"]
    if not preserved_path.exists():
        return None

    preserved_payload = _json.loads(preserved_path.read_text(encoding="utf-8"))
    adapted_payload = dict(preserved_payload)

    effective_params_payload = req.params.model_dump()
    effective_params_payload["reduction"] = effective_reduction

    adapted_payload["analysisId"] = cache_key
    adapted_payload["cacheKey"] = cache_key
    adapted_payload["paramsHash"] = params_hash
    adapted_payload["cached"] = True
    adapted_payload["effectiveParams"] = json_safe(effective_params_payload)
    adapted_payload["requestSnapshot"] = {
        "schemaVersion": "analysis_trace_v1",
        "pipelineVersion": PIPELINE_VERSION,
        "cacheKey": cache_key,
        "paramsHash": params_hash,
        "analysisType": req.algorithm,
        "parameters": json_safe(parameters_json),
        "filters": json_safe(filters_json),
    }

    run_metadata = dict(adapted_payload.get("runMetadata") or {})
    run_metadata["schemaVersion"] = "analysis_trace_v1"
    run_metadata["pipelineVersion"] = PIPELINE_VERSION
    run_metadata["cacheKey"] = cache_key
    run_metadata["paramsHash"] = params_hash
    run_metadata["analysisType"] = req.algorithm
    run_metadata["request"] = {
        "schemaVersion": "analysis_trace_v1",
        "pipelineVersion": PIPELINE_VERSION,
        "cacheKey": cache_key,
        "paramsHash": params_hash,
        "analysisType": req.algorithm,
        "parameters": json_safe(parameters_json),
        "filters": json_safe(filters_json),
    }
    adapted_payload["runMetadata"] = run_metadata

    save_cached_analysis(cache_key, adapted_payload)
    return upsert_analysis_session(
        cache_key=cache_key,
        analysis_type=req.algorithm,
        parameters_json=parameters_json,
        filters_json=filters_json,
        results_json=json_safe(adapted_payload),
        version=PIPELINE_VERSION,
        status="ready",
        last_opened=False,
    )


def find_first_existing(columns: list[str], candidates: list[str]) -> str | None:
    lower_map = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None

def get_point_pfas_columns() -> list[str]:
    query = text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'point'
          AND column_name ILIKE 'pfas_%'
        ORDER BY ordinal_position
    """)

    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    cols = [
        row[0]
        for row in rows
        if row[0].startswith("pfas_")
        and len(row[0].split("_")) == 2
        and row[0].split("_")[1].isdigit()
    ]

    cols = sorted(cols, key=lambda c: int(c.split("_")[1]))
    return cols


def compute_selected_pfas_sum(
    df: pd.DataFrame,
    pfas_cols: list[str],
) -> pd.Series:
    if not pfas_cols:
        return pd.Series(np.zeros(len(df), dtype=float), index=df.index)

    values = (
        df[pfas_cols]
        .copy()
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
    )

    values = values.clip(lower=0.0)
    return values.sum(axis=1)


ensure_analysis_sessions_table()

#............DATA LOADING FROM POSTGRESQL...............#

@lru_cache(maxsize=1)
def load_dataframe() -> pd.DataFrame:
    pfas_col_names = get_point_pfas_columns()
    if not pfas_col_names:
        raise RuntimeError("Aucune colonne PFAS trouvée dans la table public.point.")

    pfas_cols = ", ".join([f'v.{col}' for col in pfas_col_names])
    query = text(f"""
        SELECT
            p.id AS point_id,
            p.lat,
            p.lon,
            p.year,
            p.category,
            p.matrix,
            p.dataset_id,
            p.pfas_sum,
            {pfas_cols}
        FROM public.pfas_points p
        JOIN public.point v
          ON v.point_id = p.id
    """)

    df = pd.read_sql(query, engine)

    if df.empty:
        raise RuntimeError("La jointure pfas_points + point est vide.")

    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["pfas_sum"] = pd.to_numeric(df["pfas_sum"], errors="coerce").fillna(0.0)

    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce")

    if "dataset_id" in df.columns:
        df["dataset_id"] = df["dataset_id"].astype(str)

    if "matrix" in df.columns:
        df["matrix"] = df["matrix"].astype(str)

    if "category" in df.columns:
        df["category"] = df["category"].astype(str)

    for col in df.columns:
        if col.startswith("pfas_"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["lat", "lon"]).copy()
    return df

@lru_cache(maxsize=1)
def load_substance_ref() -> pd.DataFrame:
    query = """
        SELECT
            pfas_index,
            substance_name,
            cas_id,
            isomer,
            unit_ref
        FROM substance_ref
        ORDER BY pfas_index
    """
    return pd.read_sql(text(query), engine)


def get_pfas_column_mapping() -> list[dict]:
    ref = load_substance_ref().copy()
    ref["column"] = ref["pfas_index"].apply(lambda i: f"pfas_{int(i)}")

    return [
        {
            "column": row["column"],
            "name": row["substance_name"],
            "cas_id": row["cas_id"],
            "unit": row["unit_ref"],
            "isomer": row["isomer"],
        }
        for _, row in ref.iterrows()
    ]

@app.get("/pfas-list")
def get_pfas_list():
    return get_pfas_column_mapping()



#............FILTERING...............#

def point_in_polygon(lat: float, lon: float, polygon: list[LassoPoint]) -> bool:
    inside = False
    n = len(polygon)
    if n < 3:
        return True

    j = n - 1
    for i in range(n):
        yi = polygon[i].lat
        xi = polygon[i].lon
        yj = polygon[j].lat
        xj = polygon[j].lon

        intersect = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) + 1e-12) + xi
        )
        if intersect:
            inside = not inside
        j = i

    return inside


def apply_filters(df: pd.DataFrame, req: AnalysisRequest) -> pd.DataFrame:
    out = df.copy()
    vp = req.viewport

    if vp is not None:
        out = out[
            (out["lat"] >= vp.south)
            & (out["lat"] <= vp.north)
            & (out["lon"] >= vp.west)
            & (out["lon"] <= vp.east)
        ]

    filters = req.filters

    if filters.datasetId and "dataset_id" in out.columns:
        out = out[out["dataset_id"].isin(set(filters.datasetId))]

    if filters.matrix and "matrix" in out.columns:
        out = out[out["matrix"].isin(set(filters.matrix))]

    if filters.category and "category" in out.columns:
        out = out[out["category"] == filters.category]

    if filters.yearRange and len(filters.yearRange) >= 2 and "year" in out.columns:
        year_min = min(filters.yearRange[0], filters.yearRange[1])
        year_max = max(filters.yearRange[0], filters.yearRange[1])
        out = out[(out["year"] >= year_min) & (out["year"] <= year_max)]

    if len(filters.lassoRegion) >= 3:
        mask = out.apply(
            lambda row: point_in_polygon(float(row["lat"]), float(row["lon"]), filters.lassoRegion),
            axis=1,
        )
        out = out[mask]

    if filters.substances:
        for substance in filters.substances:
            if not substance.name:
                continue

            target_col = None
            if substance.name in out.columns:
                target_col = substance.name
            else:
                lower_map = {str(c).lower(): c for c in out.columns}
                target_col = lower_map.get(str(substance.name).lower())

            if not target_col:
                continue

            out[target_col] = pd.to_numeric(out[target_col], errors="coerce")

            range_mode = (substance.rangeMode or "raw").lower()
            range_values = (
                substance.filteredRange if range_mode == "filtered" else substance.rawRange
            )

            if range_values and len(range_values) >= 2:
                lo = float(min(range_values[0], range_values[1]))
                hi = float(max(range_values[0], range_values[1]))
                out = out[(out[target_col] >= lo) & (out[target_col] <= hi)]

    return out.reset_index(drop=True)
#...def apply_filters(df: pd.DataFrame, req: AnalysisRequest) -> pd.DataFrame:   return df.reset_index(drop=True)



#............FEATURE MATRIX...............#
def resolve_selected_pfas_columns(
    df: pd.DataFrame,
    selected_model_pfas: list[str],
    substance_ref: pd.DataFrame,
) -> list[str]:
    all_pfas_cols = [
        c for c in df.columns
        if c.startswith("pfas_")
        and len(c.split("_")) == 2
        and c.split("_")[1].isdigit()
    ]
    all_pfas_cols = sorted(all_pfas_cols, key=lambda c: int(c.split("_")[1]))

    if not all_pfas_cols:
        raise ValueError("Aucune colonne PFAS trouvée.")

    if not selected_model_pfas or "All" in selected_model_pfas:
        return all_pfas_cols

    name_to_col, _ = build_substance_maps(substance_ref)

    selected_cols: list[str] = []
    lower_df = {c.lower(): c for c in all_pfas_cols}

    for item in selected_model_pfas:
        if not item:
            continue

        if item in all_pfas_cols:
            selected_cols.append(item)
            continue

        mapped = name_to_col.get(item)
        if mapped and mapped in df.columns:
            selected_cols.append(mapped)
            continue

        direct = lower_df.get(str(item).lower())
        if direct:
            selected_cols.append(direct)

    selected_cols = list(dict.fromkeys(selected_cols))

    if not selected_cols:
        raise ValueError("Aucune colonne PFAS ne correspond à selectedModelPfas.")

    return selected_cols

def build_birch_pfas_matrix(
    cluster_df: pd.DataFrame,
    selected_model_pfas: list[str],
    substance_ref: pd.DataFrame,
    preprocessing: str,
) -> tuple[np.ndarray, list[str]]:
    pfas_cols = resolve_selected_pfas_columns(
        df=cluster_df,
        selected_model_pfas=selected_model_pfas,
        substance_ref=substance_ref,
    )

    if not pfas_cols:
        raise ValueError("Aucune colonne PFAS trouvée pour BIRCH.")

    x = (
        cluster_df[pfas_cols]
        .copy()
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .to_numpy(dtype=float)
    )

    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    x = np.maximum(x, 0.0)

    if preprocessing == "standardize":
        x = StandardScaler().fit_transform(x)
    elif preprocessing == "normalize":
        x = MinMaxScaler().fit_transform(x)

    return x, pfas_cols


def resolve_display_pfas_info(
    cluster_df: pd.DataFrame,
    selected_model_pfas: list[str],
    substance_ref: pd.DataFrame,
) -> tuple[str | None, str, list[str]]:
    pfas_cols = resolve_selected_pfas_columns(
        df=cluster_df,
        selected_model_pfas=selected_model_pfas,
        substance_ref=substance_ref,
    )

    if len(pfas_cols) == 1:
        _, col_to_name = build_substance_maps(substance_ref)
        col = pfas_cols[0]
        return col, col_to_name.get(col, col), pfas_cols

    return None, "Somme des PFAS sélectionnés", pfas_cols

def build_run_cache_hash(
    req: AnalysisRequest,
    effective_reduction: str,
    birch_preprocessing: str,
    birch_threshold: float,
    birch_branching_factor: int,
) -> str:
    parameters_payload, filters_payload = build_cache_session_payload(
        req=req,
        effective_reduction=effective_reduction,
        birch_preprocessing=birch_preprocessing,
        birch_threshold=birch_threshold,
        birch_branching_factor=birch_branching_factor,
    )

    cache_payload_for_hash = {
        "pipelineVersion": PIPELINE_VERSION,
        "analysisType": req.algorithm,
        "filters": filters_payload,
        "parameters": parameters_payload,
    }
    return build_analysis_params_hash(cache_payload_for_hash)


def _substance_labels_for_columns(
    pfas_cols: list[str],
    substance_ref: pd.DataFrame,
) -> list[dict[str, Any]]:
    _, col_to_name = build_substance_maps(substance_ref)

    labels: list[dict[str, Any]] = []
    ref_by_index: dict[int, dict[str, Any]] = {}
    for _, row in substance_ref.iterrows():
        try:
            ref_by_index[int(row["pfas_index"])] = row.to_dict()
        except Exception:
            continue

    for col in pfas_cols:
        idx = None
        if col.startswith("pfas_"):
            suffix = col.split("_", 1)[1]
            if suffix.isdigit():
                idx = int(suffix)

        ref_row = ref_by_index.get(idx) if idx is not None else None
        labels.append({
            "column": col,
            "pfasIndex": idx,
            "name": col_to_name.get(col, col),
            "casId": ref_row.get("cas_id") if ref_row else None,
            "unit": ref_row.get("unit_ref") if ref_row else None,
        })

    return labels


def _build_feature_metadata_base(
    *,
    df: pd.DataFrame,
    params: AnalysisParams,
    selected_model_pfas: list[str],
    resolved_pfas_cols: list[str],
    substance_ref: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "stage": "reduction",
        "requestedReduction": params.reduction,
        "preprocessing": params.preprocessing,
        "inputRows": int(len(df)),
        "selectedModelPfas": normalize_string_list(
            selected_model_pfas,
            treat_all_as_single=True,
        ) or ["All"],
        "resolvedPfasColumns": resolved_pfas_cols,
        "resolvedPfasColumnCount": int(len(resolved_pfas_cols)),
        "resolvedPfasLabels": _substance_labels_for_columns(
            resolved_pfas_cols,
            substance_ref,
        ),
    }


def build_feature_matrix_with_metadata(
    df: pd.DataFrame,
    params: AnalysisParams,
    selected_model_pfas: list[str],
    substance_ref: pd.DataFrame,
) -> tuple[np.ndarray, list[str], dict[str, Any]]:

    if params.reduction == "saint":
        is_all = _is_all_selected_model_pfas(selected_model_pfas)
        resolved_pfas_cols = resolve_selected_pfas_columns(
            df=df,
            selected_model_pfas=selected_model_pfas,
            substance_ref=substance_ref,
        )
        metadata = _build_feature_metadata_base(
            df=df,
            params=params,
            selected_model_pfas=selected_model_pfas,
            resolved_pfas_cols=resolved_pfas_cols,
            substance_ref=substance_ref,
        )
        metadata["method"] = "saint"

        if is_all and os.getenv("PFAS_PRECOMPUTED_SAINT", "true").lower() != "false":
            point_ids = df["point_id"].astype(int).tolist()
            x, z_cols = load_saint_embeddings_for_point_ids(point_ids)
            saint_artifact = get_saint_embedding_artifact_metadata()
            metadata.update({
                "effectiveReduction": "saint",
                "embeddingSource": "precomputed",
                "outputFeatureNames": z_cols,
                "outputFeatureCount": int(len(z_cols)),
                "outputShape": [int(x.shape[0]), int(x.shape[1])],
                "inputFeatureCount": int(
                    saint_artifact.get("nFeaturesInput")
                    or saint_artifact.get("inputColumnCount")
                    or len(resolved_pfas_cols)
                ),
                "saintArtifact": saint_artifact,
            })
            return x, z_cols, metadata

        saint_cfg = SaintLiveConfig(
            embedding_dim=8,
            depth=2,
            heads=2,
            ff_mult=4,
            dropout=0.1,
            hidden_dim=64,
            batch_size=512,
            epochs=8,
            learning_rate=1e-3,
            weight_decay=1e-5,
            mask_prob=0.15,
            log1p_transform=True,
            clip_negative_to_zero=True,
            use_cache=True,
            cache_dir=os.getenv("SAINT_LIVE_CACHE_DIR", ".saint_live_cache"),
            seed=42,
            pooling="mean",
            verbose=True,
        )

        x_live, z_cols, saint_live_meta = compute_saint_embeddings_live(
            df=df,
            selected_pfas_cols=resolved_pfas_cols,
            preprocessing=params.preprocessing,
            point_id_col="point_id",
            config=saint_cfg,
            return_metadata=True,
        )
        metadata.update({
            "effectiveReduction": "saint",
            "embeddingSource": "saint_live_cache",
            "outputFeatureNames": z_cols,
            "outputFeatureCount": int(len(z_cols)),
            "outputShape": [int(x_live.shape[0]), int(x_live.shape[1])],
            "inputFeatureCount": int(len(resolved_pfas_cols)),
            "saintLive": json_safe(saint_live_meta),
            "saintLiveCacheKey": saint_live_meta.get("cache_key"),
            "saintLiveCacheHit": bool(saint_live_meta.get("cache_hit")),
        })
        return x_live, z_cols, metadata

    pfas_cols = resolve_selected_pfas_columns(
        df=df,
        selected_model_pfas=selected_model_pfas,
        substance_ref=substance_ref,
    )

    if not pfas_cols:
        raise ValueError("Aucune colonne PFAS trouvée après résolution de selectedModelPfas.")

    metadata = _build_feature_metadata_base(
        df=df,
        params=params,
        selected_model_pfas=selected_model_pfas,
        resolved_pfas_cols=pfas_cols,
        substance_ref=substance_ref,
    )
    metadata["method"] = params.reduction

    x = (
        df[pfas_cols]
        .copy()
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .to_numpy(dtype=float)
    )

    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)

    if params.preprocessing == "standardize":
        x = StandardScaler().fit_transform(x)
    elif params.preprocessing == "normalize":
        x = MinMaxScaler().fit_transform(x)

    if params.reduction == "none":
        metadata.update({
            "effectiveReduction": "none",
            "inputFeatureCount": int(len(pfas_cols)),
            "outputFeatureNames": pfas_cols,
            "outputFeatureCount": int(len(pfas_cols)),
            "outputShape": [int(x.shape[0]), int(x.shape[1])],
        })
        return x, pfas_cols, metadata

    if params.reduction == "pca":
        if len(df) < 2:
            metadata.update({
                "effectiveReduction": "pca",
                "reductionSkipped": True,
                "skipReason": "too_few_rows",
                "inputFeatureCount": int(len(pfas_cols)),
                "outputFeatureNames": pfas_cols,
                "outputFeatureCount": int(len(pfas_cols)),
                "outputShape": [int(x.shape[0]), int(x.shape[1])],
            })
            return x, pfas_cols, metadata

        x_pca = PCA(
            n_components=min(2, x.shape[1]),
            random_state=42,
        ).fit_transform(x)

        feature_names = [f"pc{i+1}" for i in range(x_pca.shape[1])]
        metadata.update({
            "effectiveReduction": "pca",
            "inputFeatureCount": int(len(pfas_cols)),
            "outputFeatureNames": feature_names,
            "outputFeatureCount": int(len(feature_names)),
            "outputShape": [int(x_pca.shape[0]), int(x_pca.shape[1])],
            "modelParameters": {
                "nComponents": int(x_pca.shape[1]),
                "randomState": 42,
            },
        })
        return x_pca, feature_names, metadata

    if params.reduction == "tsne":
        if len(df) < 4:
            metadata.update({
                "effectiveReduction": "tsne",
                "reductionSkipped": True,
                "skipReason": "too_few_rows",
                "inputFeatureCount": int(len(pfas_cols)),
                "outputFeatureNames": pfas_cols,
                "outputFeatureCount": int(len(pfas_cols)),
                "outputShape": [int(x.shape[0]), int(x.shape[1])],
            })
            return x, pfas_cols, metadata

        if len(df) > TSNE_FALLBACK_THRESHOLD:
            x_pca = PCA(
                n_components=min(2, x.shape[1]),
                random_state=42,
            ).fit_transform(x)
            feature_names = [f"pca_fallback_{i+1}" for i in range(x_pca.shape[1])]
            metadata.update({
                "effectiveReduction": "pca",
                "requestedReduction": "tsne",
                "fallback": {
                    "from": "tsne",
                    "to": "pca",
                    "reason": "row_count_above_tsne_threshold",
                    "threshold": TSNE_FALLBACK_THRESHOLD,
                },
                "inputFeatureCount": int(len(pfas_cols)),
                "outputFeatureNames": feature_names,
                "outputFeatureCount": int(len(feature_names)),
                "outputShape": [int(x_pca.shape[0]), int(x_pca.shape[1])],
                "modelParameters": {
                    "nComponents": int(x_pca.shape[1]),
                    "randomState": 42,
                },
            })
            return x_pca, feature_names, metadata

        perplexity = max(2, min(30, len(df) - 1))
        x_tsne = TSNE(
            n_components=2,
            perplexity=perplexity,
            random_state=42,
            init="random",
            learning_rate="auto",
        ).fit_transform(x)

        feature_names = [f"tsne_{i+1}" for i in range(x_tsne.shape[1])]
        metadata.update({
            "effectiveReduction": "tsne",
            "inputFeatureCount": int(len(pfas_cols)),
            "outputFeatureNames": feature_names,
            "outputFeatureCount": int(len(feature_names)),
            "outputShape": [int(x_tsne.shape[0]), int(x_tsne.shape[1])],
            "modelParameters": {
                "nComponents": 2,
                "perplexity": float(perplexity),
                "randomState": 42,
                "init": "random",
                "learningRate": "auto",
            },
        })
        return x_tsne, feature_names, metadata

    if params.reduction == "autoencoder":
        x_ae = _autoencoder_reduce(x, n_components=min(2, x.shape[1]))
        feature_names = [f"ae_{i+1}" for i in range(x_ae.shape[1])]
        metadata.update({
            "effectiveReduction": "autoencoder",
            "inputFeatureCount": int(len(pfas_cols)),
            "outputFeatureNames": feature_names,
            "outputFeatureCount": int(len(feature_names)),
            "outputShape": [int(x_ae.shape[0]), int(x_ae.shape[1])],
            "modelParameters": {
                "nComponents": int(x_ae.shape[1]),
            },
        })
        return x_ae, feature_names, metadata

    metadata.update({
        "effectiveReduction": params.reduction,
        "inputFeatureCount": int(len(pfas_cols)),
        "outputFeatureNames": pfas_cols,
        "outputFeatureCount": int(len(pfas_cols)),
        "outputShape": [int(x.shape[0]), int(x.shape[1])],
    })
    return x, pfas_cols, metadata


def build_feature_matrix(
    df: pd.DataFrame,
    params: AnalysisParams,
    selected_model_pfas: list[str],
    substance_ref: pd.DataFrame,
) -> tuple[np.ndarray, list[str]]:
    x, feature_names, _ = build_feature_matrix_with_metadata(
        df=df,
        params=params,
        selected_model_pfas=selected_model_pfas,
        substance_ref=substance_ref,
    )
    return x, feature_names






def _compute_geo_dispersion(cluster_df: pd.DataFrame) -> float:
    if len(cluster_df) <= 1:
        return 0.0

    lat = pd.to_numeric(cluster_df["lat"], errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(cluster_df["lon"], errors="coerce").to_numpy(dtype=float)

    center_lat = np.nanmean(lat)
    center_lon = np.nanmean(lon)

    # approximation simple en degrés
    distances = np.sqrt((lat - center_lat) ** 2 + (lon - center_lon) ** 2)
    return float(np.nanmean(distances))


def _build_birch_group_id(parent_cluster_id: int, subgroup_id: int) -> str:
    return f"{parent_cluster_id}::birch::{subgroup_id}"


def compute_birch_condensed_groups(
    df: pd.DataFrame,
    global_labels: np.ndarray,
    selected_model_pfas: list[str],
    substance_ref: pd.DataFrame,
    preprocessing: str,
    birch_threshold: float,
    birch_branching_factor: int,
) -> list[dict]:
    work = df.copy()
    work["clusterId"] = np.asarray(global_labels).astype(int)

    bubbles: list[dict] = []
    unique_clusters = sorted({int(v) for v in work["clusterId"].tolist()})

    for cluster_id in unique_clusters:
        cluster_df = work[work["clusterId"] == cluster_id].copy()
        if cluster_df.empty:
            continue

        display_col, display_name, display_pfas_cols = resolve_display_pfas_info(
            cluster_df=cluster_df,
            selected_model_pfas=selected_model_pfas,
            substance_ref=substance_ref,
        )

        if len(cluster_df) == 1:
            row = cluster_df.iloc[0]

            if display_col and display_col in cluster_df.columns:
                display_value = float(
                    pd.to_numeric(cluster_df[display_col], errors="coerce").fillna(0.0).iloc[0]
                )
            else:
                selected_sum = compute_selected_pfas_sum(cluster_df, display_pfas_cols)
                display_value = float(selected_sum.iloc[0]) if len(selected_sum) > 0 else 0.0

            bubbles.append({
                "groupId": _build_birch_group_id(cluster_id, 0),
                "parentClusterId": int(cluster_id),
                "subgroupId": 0,
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "count": 1,
                "producerCount": 0,
                "userCount": 0,
                "presumedCount": 0,
                "pointIds": [json_safe(row["point_id"])],
                "groupType": "noise" if cluster_id == -1 else "cluster",
                "avgPfasSum": float(row["pfas_sum"]) if pd.notna(row["pfas_sum"]) else 0.0,
                "avgDisplayPfasValue": display_value,
                "displayPfasName": display_name,
                "dominantPfas": _dominant_pfas(cluster_df),
                "spatialDispersion": 0.0,
            })
            continue

        # BIRCH SUR PFAS, PAS SUR LAT/LON
        x_local, _ = build_birch_pfas_matrix(
            cluster_df=cluster_df,
            selected_model_pfas=selected_model_pfas,
            substance_ref=substance_ref,
            preprocessing=preprocessing,
        )

        if x_local.shape[0] < 2:
            subgroup_labels = np.zeros(len(cluster_df), dtype=int)
        else:
            birch = Birch(
                threshold=float(birch_threshold),
                branching_factor=max(10, int(birch_branching_factor)),
                n_clusters=None,
            )
            subgroup_labels = birch.fit_predict(x_local)

        cluster_df["subgroupId"] = subgroup_labels

        for subgroup_id in sorted(set(int(v) for v in subgroup_labels)):
            sub_df = cluster_df[cluster_df["subgroupId"] == subgroup_id].copy()
            if sub_df.empty:
                continue

            mean_lat = pd.to_numeric(sub_df["lat"], errors="coerce").mean()
            mean_lon = pd.to_numeric(sub_df["lon"], errors="coerce").mean()
            mean_pfas_sum = pd.to_numeric(sub_df["pfas_sum"], errors="coerce").fillna(0.0).mean()

            if display_col and display_col in sub_df.columns:
                mean_display_value = float(
                    pd.to_numeric(sub_df[display_col], errors="coerce").fillna(0.0).mean()
                )
            else:
                selected_sum = compute_selected_pfas_sum(sub_df, display_pfas_cols)
                mean_display_value = float(selected_sum.mean()) if len(selected_sum) > 0 else 0.0

            bubbles.append({
                "groupId": _build_birch_group_id(cluster_id, subgroup_id),
                "parentClusterId": int(cluster_id),
                "subgroupId": int(subgroup_id),
                "lat": float(mean_lat),
                "lon": float(mean_lon),
                "count": int(len(sub_df)),
                "producerCount": 0,
                "userCount": 0,
                "presumedCount": 0,
                "pointIds": [json_safe(v) for v in sub_df["point_id"].tolist()],
                "groupType": "noise" if cluster_id == -1 else "cluster",
                "avgPfasSum": float(mean_pfas_sum),
                "avgDisplayPfasValue": float(mean_display_value),
                "displayPfasName": display_name,
                "dominantPfas": _dominant_pfas(sub_df),
                "spatialDispersion": _compute_geo_dispersion(sub_df),
            })

    return bubbles

def pfas_columns_to_display_names(
    pfas_cols: list[str],
    substance_ref: pd.DataFrame,
) -> list[str]:
    idx_to_name: dict[str, str] = {}

    for _, row in substance_ref.iterrows():
        col = f"pfas_{int(row['pfas_index'])}"

        substance_name = (
            str(row["substance_name"])
            if row["substance_name"] is not None
            else col
        )

        cas_id = (
            str(row["cas_id"]).strip()
            if row["cas_id"] is not None and str(row["cas_id"]).strip() not in ("", "nan", "None")
            else None
        )

        isomer = (
            str(row["isomer"]).strip()
            if row["isomer"] is not None and str(row["isomer"]).strip() not in ("", "nan", "None")
            else None
        )

        extras = []
        if cas_id:
            extras.append(f"CAS {cas_id}")
        if isomer:
            extras.append(isomer)

        if extras:
            label = f"{substance_name} [{' | '.join(extras)}]"
        else:
            label = f"{substance_name} [{col}]"

        idx_to_name[col] = label

    return [idx_to_name.get(col, col) for col in pfas_cols]


def build_shap_matrix_from_raw_pfas(
    df: pd.DataFrame,
    params: AnalysisParams,
    selected_model_pfas: list[str],
    substance_ref: pd.DataFrame,
) -> tuple[np.ndarray, list[str], list[str]]:
    """
    Matrice utilisée uniquement pour SHAP :
    - PFAS bruts sélectionnés
    - même prétraitement éventuel
    - aucune réduction de dimension
    """
    pfas_cols = resolve_selected_pfas_columns(
        df=df,
        selected_model_pfas=selected_model_pfas,
        substance_ref=substance_ref,
    )

    if not pfas_cols:
        raise ValueError("Aucune colonne PFAS trouvée pour SHAP.")

    x = (
        df[pfas_cols]
        .copy()
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
        .to_numpy(dtype=float)
    )

    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)

    if params.preprocessing == "standardize":
        x = StandardScaler().fit_transform(x)
    elif params.preprocessing == "normalize":
        x = MinMaxScaler().fit_transform(x)

    feature_keys = pfas_cols
    feature_labels = pfas_columns_to_display_names(pfas_cols, substance_ref)
    return x, feature_keys, feature_labels





def _autoencoder_reduce(x: np.ndarray, n_components: int = 2, epochs: int = 50) -> np.ndarray:
    if len(x) < 4:
        return x

    try:
        import torch
        import torch.nn as nn

        input_dim = x.shape[1]
        hidden_dim = max(input_dim * 2, 8)

        class Autoencoder(nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder = nn.Sequential(
                    nn.Linear(input_dim, hidden_dim),
                    nn.ReLU(),
                    nn.Linear(hidden_dim, n_components),
                )
                self.decoder = nn.Sequential(
                    nn.Linear(n_components, hidden_dim),
                    nn.ReLU(),
                    nn.Linear(hidden_dim, input_dim),
                )

            def forward(self, data):
                encoded = self.encoder(data)
                decoded = self.decoder(encoded)
                return decoded

            def encode(self, data):
                return self.encoder(data)

        torch.manual_seed(42)
        model = Autoencoder()
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.MSELoss()

        tensor_x = torch.FloatTensor(x)

        batch_size = min(256, len(x))
        dataset = torch.utils.data.TensorDataset(tensor_x, tensor_x)
        loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

        model.train()
        for _ in range(epochs):
            for batch_input, batch_target in loader:
                optimizer.zero_grad()
                output = model(batch_input)
                loss = criterion(output, batch_target)
                loss.backward()
                optimizer.step()

        model.eval()
        with torch.no_grad():
            encoded = model.encode(tensor_x).numpy()

        return encoded

    except ImportError:
        pca = PCA(n_components=min(n_components, x.shape[1]), random_state=42)
        return pca.fit_transform(x)


def _pick_local_torch_device():
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


@lru_cache(maxsize=1)
def _load_propos_master_tabular_adapter():
    if not PROPOS_TABULAR_ADAPTER_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="Adaptateur tabulaire ProPos-master introuvable.",
        )

    master_dir = str(PROPOS_MASTER_DIR)
    if master_dir not in sys.path:
        sys.path.insert(0, master_dir)

    spec = importlib.util.spec_from_file_location(
        "propos_master_tabular_adapter",
        PROPOS_TABULAR_ADAPTER_PATH,
    )
    if spec is None or spec.loader is None:
        raise HTTPException(
            status_code=500,
            detail="Impossible de charger l'adaptateur ProPos-master.",
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize_rows_np(values: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    norms = np.clip(norms, eps, None)
    return values / norms


def _run_propos_on_latent(
    x: np.ndarray,
    req: AnalysisRequest,
) -> dict[str, Any]:
    if len(x) < 4:
        raise HTTPException(
            status_code=400,
            detail="ProPos requiert au moins 4 points.",
        )

    if req.params.k < 2:
        raise HTTPException(status_code=400, detail="K doit être >= 2.")

    if req.params.k >= len(x):
        raise HTTPException(
            status_code=400,
            detail=f"K ({req.params.k}) doit être strictement inférieur au nombre de points ({len(x)}).",
        )

    try:
        adapter = _load_propos_master_tabular_adapter()
        result = adapter.train_tabular_propos(
            np.asarray(x, dtype=np.float32),
            num_clusters=int(req.params.k),
            epochs=int(req.params.maxIterations),
            device=str(_pick_local_torch_device()),
            seed=42,
        )
    except HTTPException:
        raise
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="PyTorch est requis pour ProPos.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur ProPos-master tabulaire: {exc}",
        ) from exc

    return {
        "labels": np.asarray(result["labels"], dtype=int),
        "summaryFeatures": np.asarray(result["summaryFeatures"], dtype=np.float32),
        "trainingLoss": result.get("trainingLoss"),
        "epochs": int(result.get("epochs") or req.params.maxIterations),
        "centroids": np.asarray(result["centroids"], dtype=np.float32),
        "pointConfidence": np.asarray(result["pointConfidence"], dtype=np.float32),
        "temperatureAdjustedDistances": np.asarray(
            result["temperatureAdjustedDistances"],
            dtype=np.float32,
        ),
        "modelState": result.get("modelState"),
        "modelConfig": result.get("modelConfig"),
    }


def _load_propos_artifact(
    artifact_path: Path,
) -> dict[str, Any] | None:
    if not artifact_path.exists():
        return None

    try:
        import torch
    except ImportError:
        return None

    payload = torch.load(artifact_path, map_location="cpu", weights_only=False)
    if not isinstance(payload, dict):
        return None
    return payload


def _run_saved_propos_inference(
    x: np.ndarray,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    try:
        adapter = _load_propos_master_tabular_adapter()
        result = adapter.infer_tabular_propos(
            np.asarray(x, dtype=np.float32),
            artifact,
            device=str(_pick_local_torch_device()),
        )
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="PyTorch est requis pour recharger ProPos.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur inférence ProPos-master tabulaire: {exc}",
        ) from exc

    return {
        "labels": np.asarray(result["labels"], dtype=int),
        "summaryFeatures": np.asarray(result["summaryFeatures"], dtype=np.float32),
        "trainingLoss": result.get("trainingLoss"),
        "epochs": result.get("epochs"),
        "centroids": np.asarray(result["centroids"], dtype=np.float32),
        "pointConfidence": np.asarray(result["pointConfidence"], dtype=np.float32),
        "temperatureAdjustedDistances": np.asarray(
            result["temperatureAdjustedDistances"],
            dtype=np.float32,
        ),
        "modelState": result.get("modelState"),
        "modelConfig": result.get("modelConfig"),
        "sourceModelPath": str(
            Path(str(artifact.get("artifactPath") or PROPOS_REFERENCE_ARTIFACT)).resolve()
        ),
    }


def _save_propos_artifact(
    artifact_path: Path,
    clustering_artifacts: dict[str, Any] | None,
    *,
    feature_metadata: dict[str, Any] | None = None,
    source_model_path: str | None = None,
    purpose: str = "reference",
) -> str | None:
    if not clustering_artifacts:
        return None

    model_state = clustering_artifacts.get("modelState")
    model_config = clustering_artifacts.get("modelConfig")
    centroids = clustering_artifacts.get("centroids")

    if model_state is None or model_config is None or centroids is None:
        return None

    try:
        import torch
    except ImportError:
        return None

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "modelState": model_state,
            "modelConfig": json_safe(model_config),
            "centroids": centroids,
            "trainingLoss": clustering_artifacts.get("trainingLoss"),
            "epochs": clustering_artifacts.get("epochs"),
            "featureMetadata": json_safe(feature_metadata or {}),
            "sourceModelPath": source_model_path,
            "purpose": purpose,
            "artifactPath": str(artifact_path.resolve()),
            "savedAt": datetime.now(timezone.utc).isoformat(),
        },
        artifact_path,
    )
    return str(artifact_path.resolve())

#............CLUSTERING...............#


def _fit_dbscan_worker(args: tuple) -> np.ndarray:
    """Worker function for multiprocessing — runs DBSCAN fit_predict.
    Must be a top-level function to be picklable.
    """
    x_sample, eps, min_samples = args
    algo = "ball_tree" if len(x_sample) >= 5_000 else "auto"
    dbscan = DBSCAN(
        eps=eps,
        min_samples=min_samples,
        metric="euclidean",
        algorithm=algo,
        n_jobs=-1,
    )
    return dbscan.fit_predict(x_sample)


def _run_dbscan_with_timeout(
    x: np.ndarray, eps: float, min_pts: int, timeout: int,
) -> np.ndarray:
    """Run DBSCAN in a subprocess with a hard timeout.
    If it exceeds the timeout, the subprocess is killed and an error is raised.
    """
    with Pool(processes=1) as pool:
        result = pool.apply_async(_fit_dbscan_worker, ((x, eps, min_pts),))
        try:
            return result.get(timeout=timeout)
        except Exception as exc:
            pool.terminate()
            pool.join()
            if "TimeoutError" in type(exc).__name__ or isinstance(exc, TimeoutError):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"DBSCAN timeout ({timeout}s) sur {len(x):,} points. "
                        f"Essayez de réduire eps (actuellement {eps}) "
                        f"ou d'augmenter minPts (actuellement {min_pts})."
                    ),
                )
            raise


def _dbscan_with_sampling(
    x: np.ndarray,
    req: AnalysisRequest,
    sample_size: int = DBSCAN_SAMPLE_THRESHOLD,
) -> np.ndarray:
    """Run DBSCAN on a random sample, then propagate cluster labels to ALL
    points using a k-NN lookup on the labelled (non-noise) sample points.

    This keeps DBSCAN tractable for very large datasets while still assigning
    every point a cluster label.
    """
    n = len(x)
    rng = np.random.RandomState(42)
    retry_sizes: list[int] = []
    current_size = min(sample_size, n)
    while current_size >= 2_500:
        retry_sizes.append(current_size)
        if current_size <= 2_500:
            break
        current_size = max(2_500, current_size // 2)

    sample_idx = None
    x_sample = None
    sample_labels = None
    last_timeout: HTTPException | None = None

    for candidate_size in retry_sizes:
        sample_idx = rng.choice(n, size=candidate_size, replace=False)
        x_sample = x[sample_idx]
        print(f"[DBSCAN sampling] {n:,} points → sampled {len(x_sample):,}")

        try:
            sample_labels = _run_dbscan_with_timeout(
                x_sample, req.params.eps, req.params.minPts, DBSCAN_TIMEOUT_SECONDS,
            )
            if candidate_size != retry_sizes[0]:
                print(
                    f"[DBSCAN sampling] Timeout fallback succeeded with {candidate_size:,} sampled points"
                )
            break
        except HTTPException as exc:
            if exc.status_code == 400 and "DBSCAN timeout" in str(exc.detail):
                last_timeout = exc
                print(
                    f"[DBSCAN sampling] Timeout with {candidate_size:,} sampled points, retrying with a smaller sample"
                )
                continue
            raise

    if sample_labels is None or sample_idx is None or x_sample is None:
        if last_timeout is not None:
            raise last_timeout
        raise HTTPException(status_code=500, detail="DBSCAN sampling a échoué sans résultat.")

    labeled_mask = sample_labels != -1
    if not np.any(labeled_mask):
        # Every sample point is noise → all points are noise
        print("[DBSCAN sampling] All sample points are noise")
        return np.full(n, -1, dtype=int)

    # Build k-NN index from the labelled sample points
    x_labeled = x_sample[labeled_mask]
    labels_labeled = sample_labels[labeled_mask]

    nn = NearestNeighbors(n_neighbors=1, algorithm="ball_tree", n_jobs=-1)
    nn.fit(x_labeled)

    # Assign every point by nearest labelled neighbour
    distances, indices = nn.kneighbors(x)
    all_labels = labels_labeled[indices.ravel()].copy()

    # Points farther than 3× eps from any labelled neighbour stay noise
    all_labels[distances.ravel() > req.params.eps * 3] = -1

    n_clusters = len(set(int(v) for v in all_labels if v != -1))
    n_noise = int(np.sum(all_labels == -1))
    print(f"[DBSCAN sampling] Propagated → {n_clusters} clusters, {n_noise} noise")
    return all_labels


def _auto_k_silhouette(x: np.ndarray, k_range: range = range(2, 11)) -> int:
    """Find best k via silhouette score."""
    from sklearn.metrics import silhouette_score as _sil

    best_k, best_score = 3, -1.0
    n = len(x)
    if n < 3:
        return 2

    for k in k_range:
        if k >= n:
            break
        try:
            if n > MINIBATCH_THRESHOLD:
                labels = MiniBatchKMeans(n_clusters=k, n_init=2, random_state=42, batch_size=min(1024, n)).fit_predict(x)
            else:
                labels = KMeans(n_clusters=k, n_init=5, random_state=42, max_iter=50).fit_predict(x)
            unique = set(labels)
            if len(unique) < 2:
                continue
            score = _sil(x, labels, sample_size=min(5000, n), random_state=42)
            if score > best_score:
                best_score = score
                best_k = k
        except Exception:
            continue
    return best_k

def _auto_k_mssp_chn(
    x: np.ndarray,
    similarity: str = "cosine",
    theta: float = MSSP_THETA,
    max_iter: int = 500,
) -> tuple[int, np.ndarray | None, dict]:
    """
    Retourne:
      k,
      seeds éventuels pour KMeans,
      méta-infos autoParams
    """
    n = len(x)
    if n < 3:
        return 2, None, {
            "method": "mssp_chn_fallback",
            "reason": "too_few_points",
        }

    if similarity != "cosine":
        raise ValueError("Cette adaptation MSSP/CHN supporte seulement similarity='cosine'.")

    x_sample, sample_idx = _sample_for_mssp(x, MSSP_MAX_POINTS)
    x_mssp = _prepare_mssp_matrix(x_sample)

    conflict = _build_conflict_matrix(
        x=x_mssp,
        knn=min(MSSP_KNN, max(1, len(x_mssp) - 1)),
        theta=theta,
    )

    if len(x_mssp) < 3 or not np.any(conflict):
        k = _auto_k_silhouette(x_mssp, range(2, min(MSSP_MAX_K, len(x_mssp) - 1) + 1))
        return int(k), None, {
            "method": "mssp_chn_fallback",
            "reason": "empty_conflict_graph",
            "sampleSize": int(len(x_sample)),
        }

    scores = _chn_relaxation(conflict=conflict, max_iter=max_iter)
    selected_local = _repair_to_stable_set(conflict=conflict, scores=scores)

    if len(selected_local) == 0:
        k = _auto_k_silhouette(x_mssp, range(2, min(MSSP_MAX_K, len(x_mssp) - 1) + 1))
        return int(k), None, {
            "method": "mssp_chn_fallback",
            "reason": "empty_stable_set",
            "sampleSize": int(len(x_sample)),
        }

    # borne pratique pour éviter des K absurdes
    selected_scores = scores[selected_local]
    order = np.argsort(selected_scores)[::-1]
    selected_local = selected_local[order]

    k = int(len(selected_local))
    k = max(2, min(k, min(MSSP_MAX_K, len(x) - 1)))

    selected_local = selected_local[:k]
    selected_global = sample_idx[selected_local]
    seeds = x[selected_global]

    if len(seeds) != k:
        return _auto_k_silhouette(x), None, {
            "method": "mssp_chn_fallback",
            "reason": "seed_shape_mismatch",
            "sampleSize": int(len(x_sample)),
        }

    avg_degree = float(conflict.sum(axis=1).mean()) if len(conflict) else 0.0

    return k, seeds, {
        "method": "mssp_chn",
        "sampleSize": int(len(x_sample)),
        "theta": float(theta),
        "knn": int(min(MSSP_KNN, max(1, len(x_mssp) - 1))),
        "avgConflictDegree": avg_degree,
    }

def _auto_eps(x: np.ndarray, min_pts: int = 5) -> float:
    """Estimate eps via k-distance knee detection."""
    sample_size = min(5000, len(x))
    if sample_size < len(x):
        rng = np.random.RandomState(42)
        idx = rng.choice(len(x), sample_size, replace=False)
        x_sample = x[idx]
    else:
        x_sample = x

    nn = NearestNeighbors(n_neighbors=min_pts, n_jobs=-1)
    nn.fit(x_sample)
    distances, _ = nn.kneighbors(x_sample)
    k_dists = np.sort(distances[:, -1])

    # Simple knee: max second derivative
    if len(k_dists) < 4:
        return float(np.median(k_dists))
    diffs = np.diff(k_dists)
    diffs2 = np.diff(diffs)
    knee_idx = int(np.argmax(diffs2)) + 2
    return float(k_dists[min(knee_idx, len(k_dists) - 1)])

def _build_simple_hdbscan_params(x: np.ndarray) -> dict[str, Any]:
    point_count = max(2, int(len(x)))
    min_cluster_size = int(max(10, min(60, round(np.sqrt(point_count)))))
    min_samples = int(max(5, min(20, round(min_cluster_size / 2))))

    return {
        "minClusterSize": min_cluster_size,
        "minSamples": min_samples,
        "clusterSelectionMethod": "eom",
        "method": "simple_auto",
    }


def _build_hdbscan_model(req: AnalysisRequest):
    model_kwargs = {
        "min_cluster_size": int(req.params.minClusterSize),
        "min_samples": int(req.params.minSamples),
        "cluster_selection_method": req.params.clusterSelectionMethod,
    }

    if hdbscan_lib is not None:
        return (
            hdbscan_lib.HDBSCAN(
                metric="euclidean",
                gen_min_span_tree=True,
                **model_kwargs,
            ),
            "hdbscan",
        )

    if SklearnHDBSCAN is not None:
        return (
            SklearnHDBSCAN(
                metric="euclidean",
                allow_single_cluster=False,
                **model_kwargs,
            ),
            "sklearn",
        )

    raise HTTPException(
        status_code=500,
        detail=(
            "HDBSCAN n'est pas disponible dans l'environnement Python. "
            "Installez le package `hdbscan` (recommandé) ou une version "
            "de scikit-learn fournissant HDBSCAN."
        ),
    )


def run_clustering(
    x: np.ndarray,
    req: AnalysisRequest,
) -> tuple[np.ndarray, np.ndarray | None, dict | None, dict | None]:
    """Returns (labels, core_sample_indices_or_None, auto_params_or_None, clustering_artifacts_or_None)."""
    auto_params = None
    init_centers = None
    if req.mode == "simple":
        if req.algorithm == "kmeans":
            auto_k, init_centers, auto_info = _auto_k_mssp_chn(x)
            req.params.k = auto_k
            auto_params = {"k": auto_k, **auto_info}
        elif req.algorithm == "dbscan":
            req.params.eps = 0.008
            req.params.minPts = 10
            auto_params = {
                "eps": 0.008,
                "minPts": 10,
                "method": "simple_preset",
            }
        elif req.algorithm == "hdbscan":
            auto_params = _build_simple_hdbscan_params(x)
            req.params.minClusterSize = int(auto_params["minClusterSize"])
            req.params.minSamples = int(auto_params["minSamples"])
            req.params.clusterSelectionMethod = (
                "leaf" if auto_params["clusterSelectionMethod"] == "leaf" else "eom"
            )
        elif req.algorithm == "propos":
            saved_artifact = _load_propos_artifact(PROPOS_REFERENCE_ARTIFACT)
            saved_centroids = (
                np.asarray(saved_artifact.get("centroids"), dtype=np.float32)
                if saved_artifact and saved_artifact.get("centroids") is not None
                else None
            )
            saved_model_state = (
                saved_artifact.get("modelState")
                if isinstance(saved_artifact, dict)
                else None
            )
            saved_model_config = (
                saved_artifact.get("modelConfig")
                if isinstance(saved_artifact, dict)
                else None
            )
            if (
                saved_artifact is not None
                and saved_centroids is not None
                and saved_model_state is not None
                and saved_model_config is not None
                and saved_centroids.ndim == 2
                and saved_centroids.shape[1] == x.shape[1]
            ):
                req.params.k = int(saved_centroids.shape[0])
                req.params.maxIterations = int(saved_artifact.get("epochs") or 80)
                auto_params = {
                    "k": int(saved_centroids.shape[0]),
                    "epochs": int(saved_artifact.get("epochs") or 80),
                    "latentReduction": "saint",
                    "method": "saved_reference",
                    "savedModelPath": str(PROPOS_REFERENCE_ARTIFACT.resolve()),
                }
            else:
                auto_k, _, auto_info = _auto_k_mssp_chn(x)
                req.params.k = auto_k
                req.params.maxIterations = 80
                auto_params = {
                    "k": auto_k,
                    "epochs": 80,
                    "latentReduction": "saint",
                    "method": "simple_train_and_save",
                    **auto_info,
                }

        #   auto_eps = _auto_eps(x, min_pts=req.params.minPts)
        #   req.params.eps = auto_eps
        #  auto_params = {"eps": round(auto_eps, 4)}

    if req.algorithm == "kmeans":
        if req.params.k < 2:
            raise HTTPException(status_code=400, detail="K doit être >= 2.")
        if req.params.k >= len(x):
            raise HTTPException(
                status_code=400,
                detail=f"K ({req.params.k}) doit être strictement inférieur au nombre de points ({len(x)}).",
            )

        init_value: str | np.ndarray = "k-means++"
        n_init_value = 10

        if init_centers is not None and len(init_centers) == req.params.k:
            init_value = init_centers
            n_init_value = 1

        if len(x) > MINIBATCH_THRESHOLD:
            model = MiniBatchKMeans(
                n_clusters=req.params.k,
                max_iter=req.params.maxIterations,
                n_init=n_init_value,
                init=init_value,
                random_state=42,
                batch_size=min(1024, len(x)),
            )
        else:
            model = KMeans(
                n_clusters=req.params.k,
                max_iter=req.params.maxIterations,
                n_init=n_init_value,
                init=init_value,
                random_state=42,
            )
        return model.fit_predict(x), None, auto_params, None

    if req.algorithm == "dbscan":
        if req.params.eps <= 0:
            raise HTTPException(status_code=400, detail="eps doit être > 0.")
        if req.params.minPts < 2:
            raise HTTPException(status_code=400, detail="minPts doit être >= 2.")

        if len(x) >= DBSCAN_SAMPLE_THRESHOLD:
            return _dbscan_with_sampling(x, req), None, auto_params, None

        labels = _run_dbscan_with_timeout(
            x, req.params.eps, req.params.minPts, DBSCAN_TIMEOUT_SECONDS,
        )
        try:
            dbscan_model = DBSCAN(
                eps=req.params.eps,
                min_samples=req.params.minPts,
                metric="euclidean",
                n_jobs=-1,
            )
            dbscan_model.fit(x)
            return labels, dbscan_model.core_sample_indices_, auto_params, None
        except Exception:
            return labels, None, auto_params, None

    if req.algorithm == "hdbscan":
        if req.params.minClusterSize < 2:
            raise HTTPException(status_code=400, detail="minClusterSize doit être >= 2.")
        if req.params.minSamples < 1:
            raise HTTPException(status_code=400, detail="minSamples doit être >= 1.")
        if req.params.clusterSelectionMethod not in {"eom", "leaf"}:
            raise HTTPException(
                status_code=400,
                detail="clusterSelectionMethod doit être `eom` ou `leaf`.",
            )

        model, backend = _build_hdbscan_model(req)
        model.fit(x)
        labels = np.asarray(model.labels_, dtype=int)
        cluster_persistence = getattr(model, "cluster_persistence_", None)
        probabilities = getattr(model, "probabilities_", None)

        try:
            outlier_scores = getattr(model, "outlier_scores_", None)
        except Exception:
            outlier_scores = None

        try:
            relative_validity = getattr(model, "relative_validity_", None)
        except Exception:
            relative_validity = None

        return labels, None, auto_params, {
            "backend": backend,
            "model": model,
            "clusterPersistence": np.asarray(cluster_persistence, dtype=float)
            if cluster_persistence is not None
            else None,
            "probabilities": np.asarray(probabilities, dtype=float)
            if probabilities is not None
            else None,
            "outlierScores": np.asarray(outlier_scores, dtype=float)
            if outlier_scores is not None
            else None,
            "relativeValidity": float(relative_validity)
            if relative_validity is not None and np.isfinite(relative_validity)
            else None,
        }

    if req.algorithm == "propos":
        use_saved_reference = (
            req.mode == "simple"
            and auto_params is not None
            and auto_params.get("method") == "saved_reference"
        )
        if use_saved_reference:
            saved_artifact = _load_propos_artifact(PROPOS_REFERENCE_ARTIFACT)
            if saved_artifact is None:
                raise HTTPException(
                    status_code=500,
                    detail="Le modèle ProPos simple enregistré est introuvable.",
                )
            saved_artifact = {
                **saved_artifact,
                "artifactPath": str(PROPOS_REFERENCE_ARTIFACT.resolve()),
            }
            propos_result = _run_saved_propos_inference(x, saved_artifact)
        else:
            propos_result = _run_propos_on_latent(x, req)
        return (
            propos_result["labels"],
            None,
            auto_params,
            {
                "backend": "propos_master_tabular",
                "summaryFeatures": propos_result["summaryFeatures"],
                "trainingLoss": propos_result["trainingLoss"],
                "epochs": propos_result["epochs"],
                "centroids": propos_result["centroids"],
                "pointConfidence": propos_result["pointConfidence"],
                "modelState": propos_result.get("modelState"),
                "modelConfig": propos_result.get("modelConfig"),
                "latentReduction": "saint",
                "sourceModelPath": propos_result.get("sourceModelPath"),
                "usedSavedReference": use_saved_reference,
            },
        )

    raise HTTPException(status_code=400, detail="Algorithme non supporté.")
#............SUMMARIES...............#



def _euclidean_distances_to_center(cluster_x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    center = np.mean(cluster_x, axis=0)
    distances = np.linalg.norm(cluster_x - center, axis=1)
    return center, distances


def compute_cluster_summaries(
    df: pd.DataFrame,
    labels: np.ndarray,
    x: np.ndarray,
    algorithm: str,
    core_sample_indices: np.ndarray | None = None,
    clustering_artifacts: dict[str, Any] | None = None,
) -> list[dict]:
    summaries = []
    unique_labels = sorted(set(int(v) for v in labels))
    total_count = len(df)
    persistence_values = clustering_artifacts.get("clusterPersistence") if clustering_artifacts else None
    persistence_by_cluster: dict[int, float | None] = {}

    if persistence_values is not None:
        real_labels = sorted(int(v) for v in unique_labels if int(v) != -1)
        persistence_array = np.asarray(persistence_values, dtype=float)
        for idx, cluster_id in enumerate(real_labels):
            persistence_by_cluster[cluster_id] = (
                float(persistence_array[idx])
                if idx < len(persistence_array) and np.isfinite(persistence_array[idx])
                else None
            )

    for cluster_id in unique_labels:
        mask = labels == cluster_id
        cluster_df = df[mask]
        cluster_x = x[mask]
        pfas_values = cluster_df["pfas_sum"].to_numpy(dtype=float)

        _, distances = _euclidean_distances_to_center(cluster_x)

        summary = {
            "clusterId": cluster_id,
            "count": int(mask.sum()),
            "relativeSize": float(mask.sum() / total_count) if total_count > 0 else 0.0,
            "avgPfasSum": float(np.nanmean(pfas_values)) if len(pfas_values) > 0 else 0.0,
            "minPfasSum": float(np.nanmin(pfas_values)) if len(pfas_values) > 0 else 0.0,
            "maxPfasSum": float(np.nanmax(pfas_values)) if len(pfas_values) > 0 else 0.0,
            "centerLat": float(cluster_df["lat"].mean()),
            "centerLon": float(cluster_df["lon"].mean()),
            "distanceAvg": float(np.mean(distances)) if len(distances) > 0 else 0.0,
            "distanceMin": float(np.min(distances)) if len(distances) > 0 else 0.0,
            "distanceMax": float(np.max(distances)) if len(distances) > 0 else 0.0,
            "dispersion": float(np.var(distances)) if len(distances) > 0 else 0.0,
            "dominantPfas": _dominant_pfas(cluster_df),
        }

        if algorithm == "kmeans":
            summary["inertia"] = float(np.sum(distances ** 2)) if len(distances) > 0 else 0.0

        if algorithm == "dbscan":
            if cluster_id == -1:
                summary["clusterType"] = "noise"
                summary["corePoints"] = 0
                summary["borderPoints"] = int(mask.sum())
            else:
                summary["clusterType"] = "density"
                if core_sample_indices is not None:
                    # Real core points from DBSCAN model
                    cluster_indices = np.where(mask)[0]
                    core_set = set(core_sample_indices.tolist())
                    n_core = sum(1 for idx in cluster_indices if idx in core_set)
                    summary["corePoints"] = n_core
                    summary["borderPoints"] = int(mask.sum()) - n_core
                else:
                    # Sampling mode — cannot compute real core points
                    summary["corePoints"] = None
                    summary["borderPoints"] = None

        if algorithm == "hdbscan":
            summary["clusterType"] = "noise" if cluster_id == -1 else "density_hierarchy"
            summary["clusterPersistence"] = (
                None if cluster_id == -1 else persistence_by_cluster.get(cluster_id)
            )

        # Merge geometry info (centroid, min/max point coords)
        geo = _cluster_geometry_info(cluster_df, cluster_x)
        summary.update(geo)

        summaries.append(summary)

    return summaries

def _cluster_geometry_info(cluster_df: pd.DataFrame, cluster_x: np.ndarray) -> dict:
    if len(cluster_df) == 0 or len(cluster_x) == 0:
        return {
            "centroidLat": None,
            "centroidLon": None,
            "minPointId": None,
            "minPointLat": None,
            "minPointLon": None,
            "maxPointId": None,
            "maxPointLat": None,
            "maxPointLon": None,
            "geoDistanceAvg": 0.0,
            "geoDistanceMin": 0.0,
            "geoDistanceMax": 0.0,
            "geoDispersion": 0.0,
        }

    # Centroïde logique dans l’espace des concentrations
    _, distances = _euclidean_distances_to_center(cluster_x)

    point_id_col = "point_id" if "point_id" in cluster_df.columns else "id"

    # Point réel le plus proche du centroïde logique
    center_idx = int(np.argmin(distances)) if len(distances) > 0 else 0

    # Extrêmes réels par rapport au centroïde logique
    min_idx = int(np.argmin(distances)) if len(distances) > 0 else 0
    max_idx = int(np.argmax(distances)) if len(distances) > 0 else 0

    center_row = cluster_df.iloc[center_idx]
    min_row = cluster_df.iloc[min_idx]
    max_row = cluster_df.iloc[max_idx]

    def safe_float(value):
        return float(value) if pd.notna(value) else None

    def safe_id(row):
        return json_safe(row[point_id_col]) if point_id_col in cluster_df.columns else None

    return {
        # IMPORTANT :
        # centroidLat/Lon = centre visible sur carte
        # = point réel le plus proche du centroïde logique
        "centroidLat": safe_float(center_row["lat"]),
        "centroidLon": safe_float(center_row["lon"]),

        "minPointId": safe_id(min_row),
        "minPointLat": safe_float(min_row["lat"]),
        "minPointLon": safe_float(min_row["lon"]),

        "maxPointId": safe_id(max_row),
        "maxPointLat": safe_float(max_row["lat"]),
        "maxPointLon": safe_float(max_row["lon"]),

        # On garde ces champs pour compatibilité frontend.
        # Ici, ils représentent toujours les distances au centroïde logique.
        "geoDistanceAvg": float(np.mean(distances)) if len(distances) > 0 else 0.0,
        "geoDistanceMin": float(np.min(distances)) if len(distances) > 0 else 0.0,
        "geoDistanceMax": float(np.max(distances)) if len(distances) > 0 else 0.0,
        "geoDispersion": float(np.var(distances)) if len(distances) > 0 else 0.0,
    }

def _dominant_pfas(cluster_df: pd.DataFrame) -> str | None:
    pfas_cols = []

    for c in cluster_df.columns:
        cl = c.lower()
        if cl.startswith("pfas_"):
            suffix = c.split("_", 1)[1]
            if suffix.isdigit():
                pfas_cols.append(c)

    if not pfas_cols:
        return None

    values = cluster_df[pfas_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    means = values.mean()

    if means.empty:
        return None

    dominant_col = str(means.idxmax())

    suffix = dominant_col.split("_", 1)[1]
    if not suffix.isdigit():
        return dominant_col

    idx = int(suffix)

    ref = load_substance_ref()
    match = ref.loc[ref["pfas_index"] == idx]

    if match.empty:
        return dominant_col

    return str(match.iloc[0]["substance_name"])




#............GLOBAL METRICS...............#


def _compute_global_metrics(
    x: np.ndarray,
    labels: np.ndarray,
    algorithm: str,
    clustering_artifacts: dict[str, Any] | None = None,
) -> dict:
    """Compute global clustering quality metrics."""
    from sklearn.metrics import silhouette_score, davies_bouldin_score, calinski_harabasz_score

    unique_real = sorted({int(v) for v in labels if int(v) != -1})
    n_clusters = len(unique_real)
    metrics: dict = {"algorithm": algorithm}

    # Need at least 2 clusters and some non-noise points for most metrics
    non_noise_mask = labels != -1
    n_non_noise = int(non_noise_mask.sum())

    if algorithm in {"kmeans", "propos"}:
        # WCSS / Inertia
        wcss = 0.0
        for cid in unique_real:
            mask = labels == cid
            cluster_x = x[mask]
            center = np.mean(cluster_x, axis=0)
            wcss += float(np.sum(np.linalg.norm(cluster_x - center, axis=1) ** 2))
        metrics["wcss"] = wcss

        if n_clusters >= 2 and n_non_noise >= n_clusters:
            try:
                metrics["silhouetteScore"] = float(silhouette_score(x, labels, sample_size=min(5000, len(x)), random_state=42))
            except Exception:
                metrics["silhouetteScore"] = None
            try:
                metrics["daviesBouldinIndex"] = float(davies_bouldin_score(x, labels))
            except Exception:
                metrics["daviesBouldinIndex"] = None
            try:
                metrics["calinskiHarabaszScore"] = float(calinski_harabasz_score(x, labels))
            except Exception:
                metrics["calinskiHarabaszScore"] = None
        else:
            metrics["silhouetteScore"] = None
            metrics["daviesBouldinIndex"] = None
            metrics["calinskiHarabaszScore"] = None

        if algorithm == "propos":
            training_loss = (
                clustering_artifacts.get("trainingLoss")
                if clustering_artifacts
                else None
            )
            metrics["proposTrainingLoss"] = (
                float(training_loss)
                if training_loss is not None and np.isfinite(training_loss)
                else None
            )

    elif algorithm in {"dbscan", "hdbscan"}:
        noise_count = int(np.sum(labels == -1))
        total = len(labels)
        metrics["noiseCount"] = noise_count
        metrics["noiseRatio"] = float(noise_count / total) if total > 0 else 0.0

        cluster_sizes = [int(np.sum(labels == cid)) for cid in unique_real]
        metrics["clusterSizes"] = cluster_sizes
        metrics["avgClusterSize"] = float(np.mean(cluster_sizes)) if cluster_sizes else None
        metrics["minClusterSize"] = int(np.min(cluster_sizes)) if cluster_sizes else None
        metrics["maxClusterSize"] = int(np.max(cluster_sizes)) if cluster_sizes else None

        if algorithm == "hdbscan":
            relative_validity = (
                clustering_artifacts.get("relativeValidity")
                if clustering_artifacts
                else None
            )
            persistence_values = (
                clustering_artifacts.get("clusterPersistence")
                if clustering_artifacts
                else None
            )
            metrics["relativeValidity"] = (
                float(relative_validity)
                if relative_validity is not None and np.isfinite(relative_validity)
                else None
            )
            if persistence_values is not None:
                persistence_array = np.asarray(persistence_values, dtype=float)
                finite_values = persistence_array[np.isfinite(persistence_array)]
                metrics["clusterPersistenceMean"] = (
                    float(np.mean(finite_values)) if len(finite_values) > 0 else None
                )
            else:
                metrics["clusterPersistenceMean"] = None

        # Silhouette & Davies-Bouldin only on non-noise points
        if n_clusters >= 2 and n_non_noise >= n_clusters:
            x_nn = x[non_noise_mask]
            labels_nn = labels[non_noise_mask]
            try:
                metrics["silhouetteScore"] = float(silhouette_score(x_nn, labels_nn, sample_size=min(5000, len(x_nn)), random_state=42))
            except Exception:
                metrics["silhouetteScore"] = None
            try:
                metrics["daviesBouldinIndex"] = float(davies_bouldin_score(x_nn, labels_nn))
            except Exception:
                metrics["daviesBouldinIndex"] = None
        else:
            metrics["silhouetteScore"] = None
            metrics["daviesBouldinIndex"] = None

        if algorithm == "dbscan":
            metrics["relativeValidity"] = None
            metrics["clusterPersistenceMean"] = None

    return metrics


def _label_distribution(labels: np.ndarray) -> dict[str, int]:
    values, counts = np.unique(labels.astype(int), return_counts=True)
    return {str(int(label)): int(count) for label, count in zip(values, counts)}


def _build_point_annotations(
    point_ids: np.ndarray,
    clustering_artifacts: dict[str, Any] | None,
) -> dict[str, dict[str, float | None]]:
    if not clustering_artifacts:
        return {}

    probabilities = clustering_artifacts.get("probabilities")
    outlier_scores = clustering_artifacts.get("outlierScores")
    point_confidence = clustering_artifacts.get("pointConfidence")

    if probabilities is None and outlier_scores is None and point_confidence is None:
        return {}

    annotations: dict[str, dict[str, float | None]] = {}
    total = len(point_ids)

    for idx in range(total):
        item: dict[str, float | None] = {}

        if probabilities is not None and idx < len(probabilities):
            probability = probabilities[idx]
            item["membershipProbability"] = (
                float(probability) if np.isfinite(probability) else None
            )

        if outlier_scores is not None and idx < len(outlier_scores):
            outlier_score = outlier_scores[idx]
            item["outlierScore"] = (
                float(outlier_score) if np.isfinite(outlier_score) else None
            )

        if point_confidence is not None and idx < len(point_confidence):
            confidence = point_confidence[idx]
            item["assignmentConfidence"] = (
                float(confidence) if np.isfinite(confidence) else None
            )

        if item:
            annotations[str(json_safe(point_ids[idx]))] = item

    return annotations


def build_metrics_summary(
    *,
    global_metrics: dict | None,
    labels: np.ndarray,
    cluster_summaries: list[dict],
) -> dict[str, Any]:
    metrics = global_metrics or {}
    available_metrics = sorted(
        key for key, value in metrics.items()
        if key != "algorithm" and value is not None
    )
    missing_metrics = sorted(
        key for key, value in metrics.items()
        if key != "algorithm" and value is None
    )

    top_clusters = sorted(
        cluster_summaries,
        key=lambda item: int(item.get("count") or 0),
        reverse=True,
    )[:10]

    return {
        "availableMetrics": available_metrics,
        "missingMetrics": missing_metrics,
        "labelDistribution": _label_distribution(labels),
        "topClusters": [
            {
                "clusterId": item.get("clusterId"),
                "count": item.get("count"),
                "relativeSize": item.get("relativeSize"),
                "dominantPfas": item.get("dominantPfas"),
            }
            for item in top_clusters
        ],
    }


def build_clustering_metadata(
    *,
    req: AnalysisRequest,
    x: np.ndarray,
    labels: np.ndarray,
    core_indices: np.ndarray | None,
    auto_params: dict | None,
    clustering_artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unique_clusters = sorted({int(v) for v in labels if int(v) != -1})
    noise_count = int(np.sum(labels == -1)) if req.algorithm in {"dbscan", "hdbscan"} else 0

    if req.algorithm == "kmeans":
        implementation = "MiniBatchKMeans" if len(x) > MINIBATCH_THRESHOLD else "KMeans"
        parameters = {
            "k": int(req.params.k),
            "maxIterations": int(req.params.maxIterations),
            "randomState": 42,
            "nInit": 1 if auto_params and auto_params.get("method") == "mssp_chn" else 10,
        }
    elif req.algorithm == "propos":
        implementation = "ProPos_master_tabular_adapter"
        parameters = {
            "k": int(req.params.k),
            "epochs": int(clustering_artifacts.get("epochs") or req.params.maxIterations)
            if clustering_artifacts
            else int(req.params.maxIterations),
            "latentReduction": "saint",
        }
    elif req.algorithm == "dbscan":
        implementation = (
            "DBSCAN_sampling_knn_propagation"
            if len(x) > DBSCAN_SAMPLE_THRESHOLD
            else "DBSCAN"
        )
        parameters = {
            "eps": float(req.params.eps),
            "minPts": int(req.params.minPts),
            "metric": "euclidean",
            "sampleThreshold": DBSCAN_SAMPLE_THRESHOLD,
            "timeoutSeconds": DBSCAN_TIMEOUT_SECONDS,
        }
    else:
        implementation = (
            "HDBSCAN"
            if clustering_artifacts is None
            else f"HDBSCAN_{clustering_artifacts.get('backend', 'unknown')}"
        )
        parameters = {
            "minClusterSize": int(req.params.minClusterSize),
            "minSamples": int(req.params.minSamples),
            "clusterSelectionMethod": req.params.clusterSelectionMethod,
            "metric": "euclidean",
        }

    return {
        "stage": "clustering",
        "algorithm": req.algorithm,
        "mode": req.mode,
        "implementation": implementation,
        "inputShape": [int(x.shape[0]), int(x.shape[1])],
        "parameters": parameters,
        "autoParams": json_safe(auto_params) if auto_params else None,
        "output": {
            "labelCount": int(len(labels)),
            "clusterCount": int(len(unique_clusters)),
            "noiseCount": noise_count,
            "labelDistribution": _label_distribution(labels),
        },
        "coreSampleCount": int(len(core_indices)) if core_indices is not None else None,
        "savedModelPath": clustering_artifacts.get("savedModelPath")
        if clustering_artifacts
        else None,
        "liveModelPath": clustering_artifacts.get("liveModelPath")
        if clustering_artifacts
        else None,
    }


def build_condensation_metadata(
    *,
    condensed_bubbles: list[dict],
    birch_preprocessing: str,
    birch_threshold: float,
    birch_branching_factor: int,
    source_cluster_count: int,
    display_mode: str,
) -> dict[str, Any]:
    return {
        "stage": "condensation",
        "enabled": True,
        "method": "Birch",
        "preprocessing": birch_preprocessing,
        "threshold": float(birch_threshold),
        "branchingFactor": int(birch_branching_factor),
        "sourceClusterCount": int(source_cluster_count),
        "outputBubbleCount": int(len(condensed_bubbles)),
        "displayMode": display_mode,
    }


def enrich_parameters_with_traceability(
    parameters_json: dict[str, Any],
    *,
    feature_metadata: dict[str, Any],
    effective_params: AnalysisParams,
) -> dict[str, Any]:
    enriched = dict(parameters_json)
    enriched["params"] = json_safe(effective_params.model_dump())
    enriched["resolvedModelPfas"] = {
        "columns": feature_metadata.get("resolvedPfasColumns") or [],
        "labels": feature_metadata.get("resolvedPfasLabels") or [],
        "count": feature_metadata.get("resolvedPfasColumnCount"),
    }
    enriched["featureMatrix"] = {
        "reduction": feature_metadata.get("effectiveReduction"),
        "embeddingSource": feature_metadata.get("embeddingSource"),
        "saintLiveCacheKey": feature_metadata.get("saintLiveCacheKey"),
        "outputFeatureNames": feature_metadata.get("outputFeatureNames") or [],
        "outputShape": feature_metadata.get("outputShape"),
    }
    return json_safe(enriched)


def build_request_snapshot(
    *,
    parameters_json: dict[str, Any],
    filters_json: dict[str, Any],
    cache_key: str,
    params_hash: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": "analysis_trace_v1",
        "pipelineVersion": PIPELINE_VERSION,
        "cacheKey": cache_key,
        "paramsHash": params_hash,
        "analysisType": parameters_json.get("algorithm"),
        "parameters": json_safe(parameters_json),
        "filters": json_safe(filters_json),
    }


def build_run_metadata(
    *,
    cache_key: str,
    params_hash: str,
    req: AnalysisRequest,
    parameters_json: dict[str, Any],
    filters_json: dict[str, Any],
    feature_metadata: dict[str, Any],
    clustering_metadata: dict[str, Any],
    condensation_metadata: dict[str, Any],
    metrics_summary: dict[str, Any],
    analyzed_points: int,
) -> dict[str, Any]:
    return {
        "schemaVersion": "analysis_trace_v1",
        "pipelineVersion": PIPELINE_VERSION,
        "cacheKey": cache_key,
        "paramsHash": params_hash,
        "analysisType": req.algorithm,
        "mode": req.mode,
        "analyzedPoints": int(analyzed_points),
        "request": build_request_snapshot(
            parameters_json=parameters_json,
            filters_json=filters_json,
            cache_key=cache_key,
            params_hash=params_hash,
        ),
        "stages": {
            "reduction": json_safe(feature_metadata),
            "clustering": json_safe(clustering_metadata),
            "condensation": json_safe(condensation_metadata),
        },
        "metricsSummary": json_safe(metrics_summary),
    }


def _empty_bubble_context(max_distance_km: float) -> dict:
    return {
        "summary": {
            "measurementCount": 0,
            "producerCount": 0,
            "userCount": 0,
            "presumedCount": 0,
            "maxDistanceKm": float(max_distance_km),
        },
        "producers": [],
        "users": [],
        "presumptives": [],
    }


def _normalize_point_ids(values: list[Any]) -> list[int]:
    out: list[int] = []

    for value in values or []:
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            continue

        out.append(ivalue)

    return sorted(set(out))


def _build_bubble_context(
    point_ids: list[Any],
    max_distance_km: float = 50.0,
    limit_per_category: int = 20,
) -> dict:
    normalized_ids = _normalize_point_ids(point_ids)

    if not normalized_ids:
        return _empty_bubble_context(max_distance_km)

    limit_per_category = max(1, int(limit_per_category))

    measurement_count_sql = text("""
        WITH selected_ids AS (
            SELECT unnest(CAST(:point_ids AS int[])) AS point_id
        )
        SELECT COUNT(*) AS measurement_count
        FROM public.metadonnee m
        JOIN selected_ids s
          ON s.point_id = m.point_id
        WHERE TRIM(m.category) = 'Measurement'
          AND m.lat IS NOT NULL
          AND m.lon IS NOT NULL
    """)

    context_sql = text("""
        WITH selected_ids AS (
            SELECT unnest(CAST(:point_ids AS int[])) AS point_id
        ),
        measurement_points AS (
            SELECT m.point_id, m.lat, m.lon
            FROM public.metadonnee m
            JOIN selected_ids s
              ON s.point_id = m.point_id
            WHERE TRIM(m.category) = 'Measurement'
              AND m.lat IS NOT NULL
              AND m.lon IS NOT NULL
        ),
        related_entities AS (
            SELECT
                point_id,
                name,
                dataset_name,
                TRIM(category) AS category,
                lat,
                lon
            FROM public.metadonnee
            WHERE TRIM(category) IN (
                'Known PFAS user',
                'PFAS production facility',
                'Presumptive'
            )
              AND lat IS NOT NULL
              AND lon IS NOT NULL
        ),
        pair_distances AS (
            SELECT
                e.point_id,
                e.name,
                e.dataset_name,
                e.category,
                e.lat,
                e.lon,
                6371.0 * acos(
                    LEAST(1.0, GREATEST(-1.0,
                        cos(radians(m.lat)) *
                        cos(radians(e.lat)) *
                        cos(radians(e.lon) - radians(m.lon)) +
                        sin(radians(m.lat)) *
                        sin(radians(e.lat))
                    ))
                ) AS distance_km
            FROM measurement_points m
            CROSS JOIN related_entities e
        ),
        ranked_entities AS (
            SELECT
                point_id,
                name,
                dataset_name,
                category,
                lat,
                lon,
                COUNT(*) FILTER (WHERE distance_km <= :max_distance_km) AS support_count,
                AVG(distance_km) FILTER (WHERE distance_km <= :max_distance_km) AS avg_distance_km,
                MIN(distance_km) AS min_distance_km
            FROM pair_distances
            GROUP BY
                point_id,
                name,
                dataset_name,
                category,
                lat,
                lon
        )
        SELECT
            point_id,
            name,
            dataset_name,
            category,
            lat,
            lon,
            support_count,
            avg_distance_km,
            min_distance_km
        FROM ranked_entities
        WHERE support_count > 0
        ORDER BY
            support_count DESC,
            avg_distance_km ASC NULLS LAST,
            name ASC
    """)

    with engine.connect() as conn:
        measurement_count = conn.execute(
            measurement_count_sql,
            {"point_ids": normalized_ids},
        ).scalar() or 0

        if measurement_count == 0:
            return _empty_bubble_context(max_distance_km)

        related_rows = conn.execute(
            context_sql,
            {
                "point_ids": normalized_ids,
                "max_distance_km": float(max_distance_km),
            },
        ).mappings().all()

    producers: list[dict] = []
    users: list[dict] = []
    presumptives: list[dict] = []

    for row in related_rows:
        item = {
            "pointId": int(row["point_id"]) if row["point_id"] is not None else None,
            "name": str(row["name"]) if row["name"] is not None else "-",
            "datasetName": str(row["dataset_name"]) if row["dataset_name"] is not None else "-",
            "category": str(row["category"]) if row["category"] is not None else "-",
            "lat": float(row["lat"]) if row["lat"] is not None else None,
            "lon": float(row["lon"]) if row["lon"] is not None else None,
            "supportCount": int(row["support_count"]) if row["support_count"] is not None else 0,
            "avgDistanceKm": round(float(row["avg_distance_km"]), 2)
            if row["avg_distance_km"] is not None else None,
            "distanceKm": round(float(row["min_distance_km"]), 2)
            if row["min_distance_km"] is not None else None,
        }

        category = item["category"]

        if category == "PFAS production facility":
            producers.append(item)
        elif category == "Known PFAS user":
            users.append(item)
        elif category == "Presumptive":
            presumptives.append(item)

    return {
        "summary": {
            "measurementCount": int(measurement_count),
            "producerCount": len(producers),
            "userCount": len(users),
            "presumedCount": len(presumptives),
            "maxDistanceKm": float(max_distance_km),
        },
        "producers": producers[:limit_per_category],
        "users": users[:limit_per_category],
        "presumptives": presumptives[:limit_per_category],
    }

#............ROUTES...............#

@app.post("/bubble-context")
def bubble_context(payload: dict = Body(...)):
    point_ids = payload.get("pointIds") or []
    max_distance_km = float(payload.get("maxDistanceKm", 50))
    limit_per_category = int(payload.get("limitPerCategory", 20))

    return _build_bubble_context(
        point_ids=point_ids,
        max_distance_km=max_distance_km,
        limit_per_category=limit_per_category,
    )

@app.get("/")
def root():
    return {"message": "api python ok"}


@app.get("/gettest")
def gettest():
    return {"message": "helloword"}


@app.get("/health")
def health():
    df = load_dataframe()
    return {
        "status": "ok",
        "rows": int(len(df)),
        "source": "postgresql",
        "table": PFAS_SOURCE_TABLE,
    }

@app.get("/pfas-columns")
def get_pfas_columns():
    with engine.connect() as conn:
        db_info = conn.execute(text("""
            SELECT current_database(), current_user, current_schema()
        """)).fetchone()

        rows = conn.execute(text("""
            SELECT table_schema, table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'point'
              AND column_name ILIKE 'pfas%'
            ORDER BY ordinal_position
        """)).fetchall()

    cols = [row[2] for row in rows]

    return {
        "db_info": list(db_info),
        "columns": cols,
        "count": len(cols),
        "debug_rows": [list(r) for r in rows[:10]]
    }

@app.post("/visualization/temporal")
def visualization_temporal(payload: dict = Body(...)):
    print("=== /visualization/temporal payload ===")
    print(payload)

    df = load_dataframe()
    ref = load_substance_ref()

    result = build_temporal_visualization(
        df=df,
        substance_ref=ref,
        selected_pfas=payload.get("selectedPfas", ["All"]),
        temporal_mode=payload.get("temporalMode", "global"),
        cluster_assignments=payload.get("assignments"),
        cluster_id=payload.get("clusterId"),
        point_ids=payload.get("pointIds"),
        aggregation=payload.get("aggregation", "mean"),
        top_n=payload.get("topN", 5),
    )

    print("=== /visualization/temporal result ===")
    print(result)

    return result

@app.post("/analysis/condense-birch")
def analysis_condense_birch(req: BirchCondenseRequest):
    df = load_dataframe()

    fake_req = AnalysisRequest(
        algorithm="kmeans",
        filters=req.filters,
        viewport=req.viewport,
        selectedModelPfas=req.selectedModelPfas,
        params=AnalysisParams(
            preprocessing=req.preprocessing,
        ),
        mode="expert",
    )

    filtered = apply_filters(df, fake_req)

    if filtered.empty:
        return {
            "condensedBubbles": [],
            "summary": {
                "groupCount": 0,
                "message": "Aucun point à condenser."
            }
        }

    if not req.assignments:
        raise HTTPException(status_code=400, detail="Assignments manquants.")

    filtered = filtered.copy()
    filtered["clusterId"] = filtered["point_id"].astype(str).map(req.assignments)

    mapped_count = int(filtered["clusterId"].notna().sum())
    if mapped_count == 0:
        sample_point_ids = [str(v) for v in filtered["point_id"].head(5).tolist()]
        sample_assignment_keys = list(req.assignments.keys())[:5]
        raise HTTPException(
            status_code=400,
            detail=(
                "Aucun point n'a pu être relié aux assignments. "
                f"Exemples point_id={sample_point_ids}, "
                f"exemples assignment keys={sample_assignment_keys}"
            ),
        )

    filtered = filtered.dropna(subset=["clusterId"]).copy()
    filtered["clusterId"] = filtered["clusterId"].astype(int)

    substance_ref = load_substance_ref()

    bubbles = compute_birch_condensed_groups(
        df=filtered,
        global_labels=filtered["clusterId"].to_numpy(),
        selected_model_pfas=req.selectedModelPfas,
        substance_ref=substance_ref,
        preprocessing=req.preprocessing,
        birch_threshold=req.birchThreshold,
        birch_branching_factor=req.birchBranchingFactor,
    )
    print(
        f"[analysis/condense-birch] filtered={len(filtered)} "
        f"mapped={mapped_count} bubbles={len(bubbles)}"
    )
    source_cluster_count = len(set(int(v) for v in filtered["clusterId"].to_numpy()))
    condensation_metadata = build_condensation_metadata(
        condensed_bubbles=bubbles,
        birch_preprocessing=req.preprocessing,
        birch_threshold=req.birchThreshold,
        birch_branching_factor=req.birchBranchingFactor,
        source_cluster_count=source_cluster_count,
        display_mode="condensed" if bubbles else "points",
    )

    return {
        "condensedBubbles": [json_safe(b) for b in bubbles],
        "condensationMeta": json_safe(condensation_metadata),
        "summary": {
            "groupCount": len(bubbles),
            "message": "Condensation BIRCH terminée."
        }
    }

@app.post("/visualization/radar")
def visualization_radar(payload: dict = Body(...)):
    df = load_dataframe()
    ref = load_substance_ref()

    return build_radar_visualization(
        df=df,
        substance_ref=ref,
        mode=payload.get("mode", "selected"),
        axes_pfas=payload.get("axesPfas"),
        cluster_assignments=payload.get("assignments"),
        cluster_id=payload.get("clusterId"),
        point_ids=payload.get("pointIds"),
        normalize=payload.get("normalize", True),
        top_n=payload.get("topN", 10),
    )


@app.post("/analysis/run")
def analysis_run(req: AnalysisRequest):
    started = time.perf_counter()

    try:
        df = load_dataframe()
    except Exception as exc:
        print(f"[analysis/run] Erreur chargement données: {exc}")
        raise HTTPException(status_code=500, detail=f"Erreur chargement données: {exc}")

    try:
        filtered = apply_filters(df, req)
    except Exception as exc:
        print(f"[analysis/run] Erreur filtrage: {exc}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du filtrage: {exc}")

    analyzed_points = len(filtered)
    if analyzed_points == 0:
        return {
            "assignments": {},
            "summary": {
                "analyzedPoints": 0,
                "clusterCount": 0,
                "noiseCount": 0,
                "durationMs": 0,
                "tooMany": False,
                "message": "Aucun point à analyser avec ces filtres.",
            },
            "clusterSummaries": [],
            "globalMetrics": None,
            "autoParams": None,
            "effectiveParams": {
                "reduction": _resolve_effective_reduction(req),
            },
            "condensedBubbles": [],
            "displayMode": "points",
            "birchMeta": None,
            "analysisId": None,
            "cacheKey": None,
            "paramsHash": None,
            "cached": False,
        }

    effective_params = req.params.model_copy(deep=True)
    effective_params.reduction = _resolve_effective_reduction(req)

    substance_ref = load_substance_ref()
    fallback_message = None

    birch_preprocessing = effective_params.preprocessing
    if birch_preprocessing == "none":
        birch_preprocessing = "standardize"

    birch_threshold = 0.25 if birch_preprocessing == "normalize" else 0.9
    birch_branching_factor = 50

    parameters_json, filters_json = build_cache_session_payload(
        req=req,
        effective_reduction=effective_params.reduction,
        birch_preprocessing=birch_preprocessing,
        birch_threshold=birch_threshold,
        birch_branching_factor=birch_branching_factor,
    )

    params_hash = build_run_cache_hash(
        req=req,
        effective_reduction=effective_params.reduction,
        birch_preprocessing=birch_preprocessing,
        birch_threshold=birch_threshold,
        birch_branching_factor=birch_branching_factor,
    )
    cache_key = params_hash

    cached_session = fetch_analysis_session(cache_key)
    if cached_session is not None and cached_session.get("status") == "ready":
        touched = touch_analysis_session(cache_key) or cached_session
        return json_safe(build_cached_response_from_session(touched, cached=True))

    cached_session = hydrate_analysis_session_from_file_cache(
        cache_key=cache_key,
        analysis_type=req.algorithm,
        parameters_json=parameters_json,
        filters_json=filters_json,
    )
    if cached_session is not None:
        touched = touch_analysis_session(cache_key) or cached_session
        return json_safe(build_cached_response_from_session(touched, cached=True))

    cached_session = hydrate_analysis_session_from_preserved_default_cache(
        req=req,
        cache_key=cache_key,
        params_hash=params_hash,
        effective_reduction=effective_params.reduction,
        parameters_json=parameters_json,
        filters_json=filters_json,
    )
    if cached_session is not None:
        touched = touch_analysis_session(cache_key) or cached_session
        return json_safe(build_cached_response_from_session(touched, cached=True))

    feature_metadata: dict[str, Any] | None = None

    try:
        x, _used_pfas_cols, feature_metadata = build_feature_matrix_with_metadata(
            filtered,
            effective_params,
            req.selectedModelPfas,
            substance_ref,
        )
    except Exception as exc:
        exc_text = str(exc)

        can_fallback_to_pca = (
            effective_params.reduction == "saint"
            and req.algorithm != "propos"
            and _is_all_selected_model_pfas(req.selectedModelPfas)
            and "embeddings SAINT" in exc_text
        )

        if can_fallback_to_pca:
            print(f"[analysis/run] SAINT indisponible, fallback PCA: {exc_text}")
            effective_params.reduction = "pca"

            parameters_json, filters_json = build_cache_session_payload(
                req=req,
                effective_reduction=effective_params.reduction,
                birch_preprocessing=birch_preprocessing,
                birch_threshold=birch_threshold,
                birch_branching_factor=birch_branching_factor,
            )

            fallback_params_hash = build_run_cache_hash(
                req=req,
                effective_reduction=effective_params.reduction,
                birch_preprocessing=birch_preprocessing,
                birch_threshold=birch_threshold,
                birch_branching_factor=birch_branching_factor,
            )
            fallback_cache_key = fallback_params_hash

            cached_session = fetch_analysis_session(fallback_cache_key)
            if cached_session is not None and cached_session.get("status") == "ready":
                touched = touch_analysis_session(fallback_cache_key) or cached_session
                return json_safe(build_cached_response_from_session(touched, cached=True))

            cached_session = hydrate_analysis_session_from_file_cache(
                cache_key=fallback_cache_key,
                analysis_type=req.algorithm,
                parameters_json=parameters_json,
                filters_json=filters_json,
            )
            if cached_session is not None:
                touched = touch_analysis_session(fallback_cache_key) or cached_session
                return json_safe(build_cached_response_from_session(touched, cached=True))

            x, _used_pfas_cols, feature_metadata = build_feature_matrix_with_metadata(
                filtered,
                effective_params,
                req.selectedModelPfas,
                substance_ref,
            )

            fallback_message = (
                "Embeddings SAINT indisponibles pour tous les points : "
                "fallback automatique vers PCA."
            )

            params_hash = fallback_params_hash
            cache_key = fallback_cache_key
        else:
            print(f"[analysis/run] Erreur construction matrice: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Erreur construction matrice de features: {exc}"
            )

    parameters_json = enrich_parameters_with_traceability(
        parameters_json,
        feature_metadata=feature_metadata or {},
        effective_params=effective_params,
    )

    upsert_analysis_session(
        cache_key=cache_key,
        analysis_type=req.algorithm,
        parameters_json=parameters_json,
        filters_json=filters_json,
        results_json=None,
        version=PIPELINE_VERSION,
        status="pending",
        last_opened=False,
    )

    try:
        effective_req = req.model_copy(deep=True)
        effective_req.params = effective_params

        labels, core_indices, auto_params, clustering_artifacts = run_clustering(x, effective_req)

    except HTTPException:
        mark_analysis_session_failed(
            cache_key,
            error_message="Erreur HTTP pendant le clustering.",
        )
        raise
    except Exception as exc:
        print(f"[analysis/run] Erreur clustering ({req.algorithm}, {analyzed_points} pts): {exc}")
        mark_analysis_session_failed(
            cache_key,
            error_message=f"Erreur pendant le clustering: {exc}",
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erreur pendant le clustering ({req.algorithm}, {analyzed_points} points): {exc}",
        )

    filtered = filtered.copy()
    filtered["clusterId"] = labels

    if req.algorithm == "propos" and req.mode == "simple" and clustering_artifacts is not None:
        if clustering_artifacts.get("usedSavedReference"):
            clustering_artifacts["savedModelPath"] = str(PROPOS_REFERENCE_ARTIFACT.resolve())
        else:
            saved_model_path = _save_propos_artifact(
                PROPOS_REFERENCE_ARTIFACT,
                clustering_artifacts,
                feature_metadata=feature_metadata,
                purpose="reference",
            )
            if saved_model_path:
                clustering_artifacts["savedModelPath"] = saved_model_path

        live_model_path = _save_propos_artifact(
            PROPOS_LIVE_DIR / f"{cache_key}.pt",
            clustering_artifacts,
            feature_metadata=feature_metadata,
            source_model_path=clustering_artifacts.get("savedModelPath"),
            purpose="live",
        )
        if live_model_path:
            clustering_artifacts["liveModelPath"] = live_model_path

    summary_x = (
        np.asarray(clustering_artifacts["summaryFeatures"], dtype=float)
        if clustering_artifacts is not None and clustering_artifacts.get("summaryFeatures") is not None
        else x
    )

    unique_clusters = sorted({int(v) for v in labels if int(v) != -1})
    cluster_count = len(unique_clusters)
    noise_count = int(np.sum(labels == -1)) if req.algorithm in {"dbscan", "hdbscan"} else 0
    duration_ms = int((time.perf_counter() - started) * 1000)

    cluster_summaries = compute_cluster_summaries(
        filtered, labels, summary_x, req.algorithm, core_indices, clustering_artifacts
    )

    global_metrics = _compute_global_metrics(summary_x, labels, req.algorithm, clustering_artifacts)
    clustering_metadata = build_clustering_metadata(
        req=effective_req,
        x=summary_x,
        labels=labels,
        core_indices=core_indices,
        auto_params=auto_params,
        clustering_artifacts=clustering_artifacts,
    )

    point_ids = filtered["point_id"].to_numpy()
    point_annotations = _build_point_annotations(point_ids, clustering_artifacts)
    assignments: dict[str, int] = {}
    for pid, cid in zip(point_ids, labels):
        assignments[str(json_safe(pid))] = int(cid)

    print(
        f"[analysis/run] OK — {analyzed_points} pts, "
        f"{cluster_count} clusters, {noise_count} noise, {duration_ms} ms"
    )

    condensed_bubbles = compute_birch_condensed_groups(
        df=filtered,
        global_labels=labels,
        selected_model_pfas=req.selectedModelPfas,
        substance_ref=substance_ref,
        preprocessing=birch_preprocessing,
        birch_threshold=birch_threshold,
        birch_branching_factor=birch_branching_factor,
    )
    display_mode = "condensed" if len(condensed_bubbles) > 0 else "points"
    condensation_metadata = build_condensation_metadata(
        condensed_bubbles=condensed_bubbles,
        birch_preprocessing=birch_preprocessing,
        birch_threshold=birch_threshold,
        birch_branching_factor=birch_branching_factor,
        source_cluster_count=cluster_count,
        display_mode=display_mode,
    )
    metrics_summary = build_metrics_summary(
        global_metrics=global_metrics,
        labels=labels,
        cluster_summaries=cluster_summaries,
    )
    request_snapshot = build_request_snapshot(
        parameters_json=parameters_json,
        filters_json=filters_json,
        cache_key=cache_key,
        params_hash=params_hash,
    )
    run_metadata = build_run_metadata(
        cache_key=cache_key,
        params_hash=params_hash,
        req=effective_req,
        parameters_json=parameters_json,
        filters_json=filters_json,
        feature_metadata=feature_metadata or {},
        clustering_metadata=clustering_metadata,
        condensation_metadata=condensation_metadata,
        metrics_summary=metrics_summary,
        analyzed_points=analyzed_points,
    )

    payload = {
        "assignments": assignments,
        "summary": {
            "analyzedPoints": analyzed_points,
            "clusterCount": cluster_count,
            "noiseCount": noise_count,
            "durationMs": duration_ms,
            "tooMany": False,
            "message": fallback_message or "Analyse terminée.",
        },
        "clusterSummaries": [json_safe(s) for s in cluster_summaries],
        "globalMetrics": json_safe(global_metrics),
        "metricsSummary": json_safe(metrics_summary),
        "autoParams": json_safe(auto_params) if auto_params else None,
        "pointAnnotations": json_safe(point_annotations),
        "effectiveParams": json_safe(effective_params.model_dump()),
        "requestSnapshot": json_safe(request_snapshot),
        "runMetadata": json_safe(run_metadata),
        "reductionMeta": json_safe(feature_metadata),
        "clusteringMeta": json_safe(clustering_metadata),
        "condensationMeta": json_safe(condensation_metadata),
        "condensedBubbles": json_safe(condensed_bubbles),
        "displayMode": display_mode,
        "birchMeta": {
            "preprocessing": birch_preprocessing,
            "threshold": birch_threshold,
            "branchingFactor": birch_branching_factor,
        },
        "analysisId": cache_key,
        "cacheKey": cache_key,
        "paramsHash": params_hash,
        "cached": False,
    }

    save_cached_analysis(cache_key, payload)
    session_row = upsert_analysis_session(
        cache_key=cache_key,
        analysis_type=req.algorithm,
        parameters_json=parameters_json,
        filters_json=filters_json,
        results_json=json_safe(payload),
        version=PIPELINE_VERSION,
        status="ready",
        last_opened=True,
    )

    payload["historyEntry"] = serialize_history_entry(session_row, include_result=False)
    payload["status"] = session_row.get("status")
    payload["version"] = session_row.get("version")
    payload["hitCount"] = int(session_row.get("hit_count") or 0)
    payload["createdAt"] = datetime_to_iso(session_row.get("created_at"))
    payload["lastOpenedAt"] = datetime_to_iso(session_row.get("last_opened_at"))
    return json_safe(payload)


@app.post("/cache/clear")
def clear_cache():
    load_dataframe.cache_clear()
    load_substance_ref.cache_clear()

    deleted = 0
    for path in CACHE_DIR.glob("*.json"):
        try:
            path.unlink()
            deleted += 1
        except Exception:
            pass

    deleted_sessions = clear_analysis_sessions()

    return {
        "message": "Caches vidés.",
        "dataframeCacheCleared": True,
        "substanceRefCacheCleared": True,
        "analysisFilesDeleted": deleted,
        "analysisSessionsDeleted": deleted_sessions,
    }

class HistoryLoadRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    analysisId: str | None = None
    cacheKey: str | None = None


class HistoryStateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    analysisId: str | None = None
    cacheKey: str | None = None
    mapState: dict[str, Any] | None = None
    panelState: dict[str, Any] | None = None


class HistoryRenameRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    analysisId: str | None = None
    cacheKey: str | None = None
    name: str | None = None


class HistoryDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    analysisId: str | None = None
    cacheKey: str | None = None


def resolve_history_cache_key(analysis_id: str | None, cache_key: str | None) -> str:
    key = cache_key or analysis_id
    if not key:
        raise HTTPException(status_code=400, detail="analysisId ou cacheKey requis.")
    return key


@app.get("/analysis/history/list")
def analysis_history_list(limit: int = ANALYSIS_HISTORY_LIMIT):
    rows = list_analysis_sessions(limit=limit)
    return {
        "entries": [serialize_history_entry(row, include_result=False) for row in rows],
        "limit": max(1, min(int(limit), 100)),
        "version": PIPELINE_VERSION,
    }

@app.post("/analysis/history/load")
def analysis_history_load(req: HistoryLoadRequest):
    key = resolve_history_cache_key(req.analysisId, req.cacheKey)

    cached_session = fetch_analysis_session(key)
    if cached_session is not None and cached_session.get("status") == "ready":
        touched = touch_analysis_session(key) or cached_session
        return json_safe(build_cached_response_from_session(touched, cached=True))

    cached = load_cached_analysis(key)
    if not cached:
        raise HTTPException(status_code=404, detail="Analyse en cache introuvable.")

    request_snapshot = cached.get("requestSnapshot") or (cached.get("runMetadata") or {}).get("request") or {}
    snapshot_parameters = request_snapshot.get("parameters") or {}
    snapshot_filters = request_snapshot.get("filters") or {}
    inferred_algorithm = (
        snapshot_parameters.get("algorithm")
        or cached.get("historyEntry", {}).get("algorithm")
        or (cached.get("globalMetrics") or {}).get("algorithm")
        or "kmeans"
    )
    legacy_params = (
        cached.get("historyEntry", {}).get("snapshot", {}).get("params")
        if isinstance(cached.get("historyEntry"), dict)
        else {}
    )

    hydrated = upsert_analysis_session(
        cache_key=key,
        analysis_type=inferred_algorithm,
        parameters_json=snapshot_parameters or {
            "algorithm": inferred_algorithm,
            "mode": "expert",
            "selectedModelPfas": ["All"],
            "params": json_safe(legacy_params or {}),
            "birch": {},
        },
        filters_json=snapshot_filters or {},
        results_json=json_safe(cached),
        version=PIPELINE_VERSION,
        status="ready",
        last_opened=False,
    )
    touched = touch_analysis_session(key) or hydrated
    return json_safe(build_cached_response_from_session(touched, cached=True))


@app.post("/analysis/history/state")
def analysis_history_state(req: HistoryStateRequest):
    key = resolve_history_cache_key(req.analysisId, req.cacheKey)
    row = update_analysis_session_state(
        key,
        map_state_json=json_safe(req.mapState) if req.mapState is not None else None,
        panel_state_json=json_safe(req.panelState) if req.panelState is not None else None,
    )

    if row is None:
        raise HTTPException(status_code=404, detail="Session d'analyse introuvable.")

    return {
        "ok": True,
        "entry": serialize_history_entry(row, include_result=False),
    }


@app.post("/analysis/history/rename")
def analysis_history_rename(req: HistoryRenameRequest):
    key = resolve_history_cache_key(req.analysisId, req.cacheKey)
    row = rename_analysis_session(key, req.name)

    if row is None:
        raise HTTPException(status_code=404, detail="Session d'analyse introuvable.")

    return {
        "ok": True,
        "entry": serialize_history_entry(row, include_result=False),
    }


@app.post("/analysis/history/delete")
def analysis_history_delete(req: HistoryDeleteRequest):
    key = resolve_history_cache_key(req.analysisId, req.cacheKey)
    deleted = delete_analysis_session(key)

    if not deleted:
        raise HTTPException(status_code=404, detail="Session d'analyse introuvable.")

    return {"ok": True, "cacheKey": key}


@app.post("/analysis/history/clear")
def analysis_history_clear():
    deleted = clear_analysis_sessions()
    return {"ok": True, "deleted": deleted}


class ShapRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    algorithm: Literal["kmeans", "dbscan", "hdbscan", "propos"]
    filters: Filters = Field(default_factory=Filters)
    selectedModelPfas: list[str] = Field(default_factory=lambda: ["All"])
    params: AnalysisParams = Field(default_factory=AnalysisParams)
    mode: Literal["simple", "expert"] = "expert"
    clusterId: int | None = None  # None = global, int = local for that cluster
    assignments: dict[str, int] | list[AssignmentItem] = Field(default_factory=dict)


class ClampParams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    explainerType: str = "dtexp"
    boundingBoxSelection: str = "centroids"
    descriptionPointsRatio: float = 5
    maxRulesPerCluster: int = 5
    ignoreNoise: bool = True


class ClampRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    filters: Filters = Field(default_factory=Filters)
    selectedModelPfas: list[str] = Field(default_factory=lambda: ["All"])
    assignments: dict[str, int] | list[AssignmentItem] = Field(default_factory=list)
    clusterId: int | None = None
    params: ClampParams = Field(default_factory=ClampParams)



def _mean_abs_shap_importance(shap_values: Any, class_idx: int | None = None) -> np.ndarray:
    """
    Gère les formats SHAP possibles :
    - list[np.ndarray]                              -> ancien multi-classe
    - np.ndarray (n_samples, n_features)           -> binaire / régression
    - np.ndarray (n_samples, n_features, n_classes)-> nouveau multi-classe
    """
    if isinstance(shap_values, list):
        if class_idx is None:
            arr = np.stack([np.abs(sv).mean(axis=0) for sv in shap_values], axis=0)
            return arr.mean(axis=0)

        class_idx = max(0, min(int(class_idx), len(shap_values) - 1))
        return np.abs(shap_values[class_idx]).mean(axis=0)

    arr = np.asarray(shap_values)

    if arr.ndim == 2:
        return np.abs(arr).mean(axis=0)

    if arr.ndim == 3:
        # format récent : (samples, features, classes)
        if class_idx is None:
            return np.abs(arr).mean(axis=(0, 2))

        class_idx = max(0, min(int(class_idx), arr.shape[2] - 1))
        return np.abs(arr[:, :, class_idx]).mean(axis=0)

    raise ValueError(f"Format SHAP inattendu: shape={arr.shape}")

@app.post("/analysis/shap")
def analysis_shap(req: ShapRequest):
    if not SHAP_AVAILABLE:
        raise HTTPException(status_code=501, detail="SHAP non disponible.")

    effective_params = req.params.model_copy(deep=True)

    tmp_effective_req = AnalysisRequest(
        algorithm=req.algorithm,
        filters=req.filters,
        selectedModelPfas=req.selectedModelPfas,
        params=effective_params,
        mode=req.mode,
        viewport=None,
    )

    effective_params.reduction = _resolve_effective_reduction(tmp_effective_req)

    df = load_dataframe()

    tmp_req = AnalysisRequest(
        algorithm=req.algorithm,
        filters=req.filters,
        selectedModelPfas=req.selectedModelPfas,
        params=effective_params,
        mode=req.mode,
        viewport=None,
    )

    filtered = apply_filters(df, tmp_req)

    if len(filtered) < 10:
        raise HTTPException(status_code=400, detail="Pas assez de points pour SHAP.")

    substance_ref = load_substance_ref()
    fallback_message = None
    normalized_assignments = normalize_assignments_payload(req.assignments)

    shap_reduction_meta: dict[str, Any] | None = None

    try:
        shap_matrix, feature_keys, feature_labels = build_shap_matrix_from_raw_pfas(
            filtered,
            effective_params,
            req.selectedModelPfas,
            substance_ref,
        )
    except Exception as exc:
        print(f"[analysis/shap] Erreur construction matrice SHAP brute: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur construction matrice SHAP sur PFAS bruts: {exc}"
        )

    if normalized_assignments:
        filtered = filtered.copy()
        filtered["clusterId"] = filtered["point_id"].astype(str).map(normalized_assignments)

        mapped_count = int(filtered["clusterId"].notna().sum())
        if mapped_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Lancez d'abord une analyse de clustering.",
            )

        filtered = filtered.dropna(subset=["clusterId"]).copy()
        filtered["clusterId"] = filtered["clusterId"].astype(int)
        labels = filtered["clusterId"].to_numpy(dtype=int)
        shap_matrix = shap_matrix[filtered.index.to_numpy()]
        fallback_message = "SHAP calculé à partir des assignments du dernier run."
    else:
        # Fallback rétrocompatible: si aucun assignment n'est fourni, on relance la partie clustering.
        try:
            clustering_matrix, _, shap_reduction_meta = build_feature_matrix_with_metadata(
                filtered,
                effective_params,
                req.selectedModelPfas,
                substance_ref,
            )
        except Exception as exc:
            exc_text = str(exc)

            can_fallback_to_pca = (
                effective_params.reduction == "saint"
                and req.algorithm != "propos"
                and _is_all_selected_model_pfas(req.selectedModelPfas)
                and "embeddings SAINT" in exc_text
            )

            if can_fallback_to_pca:
                print(f"[analysis/shap] SAINT indisponible, fallback PCA: {exc_text}")
                effective_params.reduction = "pca"

                clustering_matrix, _, shap_reduction_meta = build_feature_matrix_with_metadata(
                    filtered,
                    effective_params,
                    req.selectedModelPfas,
                    substance_ref,
                )

                fallback_message = (
                    "Embeddings SAINT indisponibles pour tous les points : "
                    "clustering fallback sur PCA, SHAP calculé sur PFAS bruts."
                )
            else:
                print(f"[analysis/shap] Erreur construction matrice clustering: {exc}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Erreur construction matrice clustering pour SHAP: {exc}"
                )

        cluster_req = AnalysisRequest(
            algorithm=req.algorithm,
            filters=req.filters,
            selectedModelPfas=req.selectedModelPfas,
            params=effective_params,
            mode=req.mode,
            viewport=None,
        )

        labels, _, _, _ = run_clustering(clustering_matrix, cluster_req)

    # 4) SHAP sur PFAS bruts, target = labels de clustering
    mask = labels != -1
    x_train = shap_matrix[mask]
    y_train = labels[mask]

    if len(x_train) < 10:
        raise HTTPException(
            status_code=400,
            detail=(
                "Analyse explicable impossible : tous les points sont bruit -1."
                if len(labels) > 0 and int(np.sum(mask)) == 0
                else "Pas assez de points non-noise pour SHAP."
            )
        )

    unique_labels = sorted(set(int(v) for v in y_train))
    if len(unique_labels) < 2:
        raise HTTPException(
            status_code=400,
            detail="Analyse explicable impossible : au moins deux clusters sont nécessaires."
        )

    rf = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=42,
        n_jobs=-1,
    )
    rf.fit(x_train, y_train)

    fidelity = float(rf.score(x_train, y_train))

    if fidelity < 0.5:
        return json_safe({
            "fidelity": fidelity,
            "message": "Fidélité du surrogate trop basse pour SHAP fiable.",
            "effectiveReduction": effective_params.reduction,
            "surrogate": {
                "model": "RandomForestClassifier",
                "nEstimators": 100,
                "maxDepth": 10,
                "randomState": 42,
                "nJobs": -1,
                "trainingRows": int(len(x_train)),
            },
            "reductionMeta": json_safe(shap_reduction_meta),
            "globalImportances": [],
            "localImportances": None,
        })

    sample_size = min(500, len(x_train))
    rng = np.random.RandomState(42)
    sample_idx = rng.choice(len(x_train), sample_size, replace=False)
    x_sample = x_train[sample_idx]

    explainer = shap.TreeExplainer(rf)
    shap_values = explainer.shap_values(x_sample)

    global_imp = _mean_abs_shap_importance(shap_values)
    sorted_indices = np.argsort(global_imp)[::-1].astype(int)

    global_importances = [
        {
            "featureKey": str(feature_keys[int(i)]),
            "featureLabel": str(feature_labels[int(i)]),
            "importance": float(global_imp[int(i)]),
        }
        for i in sorted_indices[:20]
    ]

    local_importances = None
    if req.clusterId is not None and req.clusterId in unique_labels:
        cluster_mask = y_train == req.clusterId
        cluster_x = x_train[cluster_mask]

        if len(cluster_x) >= 20:
            local_sample = cluster_x[:min(100, len(cluster_x))]
            local_shap = explainer.shap_values(local_sample)

            class_idx = list(rf.classes_).index(req.clusterId) if req.clusterId in rf.classes_ else 0
            local_imp = _mean_abs_shap_importance(local_shap, class_idx=class_idx)

            local_sorted = np.argsort(local_imp)[::-1].astype(int)
            local_importances = [
                {
                    "featureKey": str(feature_keys[int(i)]),
                    "featureLabel": str(feature_labels[int(i)]),
                    "importance": float(local_imp[int(i)]),
                }
                for i in local_sorted[:20]
            ]

    return json_safe({
        "fidelity": fidelity,
        "message": (
            fallback_message
            or f"Surrogate RandomForest — fidélité: {fidelity:.2%}"
        ),
        "effectiveReduction": effective_params.reduction,
        "shapInput": "raw_pfas",
        "surrogate": {
            "model": "RandomForestClassifier",
            "nEstimators": 100,
            "maxDepth": 10,
            "randomState": 42,
            "nJobs": -1,
            "trainingRows": int(len(x_train)),
            "sampleRows": int(sample_size),
            "classes": [int(v) for v in unique_labels],
        },
        "reductionMeta": json_safe(shap_reduction_meta),
        "globalImportances": global_importances,
        "localImportances": local_importances,
    })


@app.post("/analysis/clamp")
def analysis_clamp(req: ClampRequest):
    df = load_dataframe()

    fake_req = AnalysisRequest(
        algorithm="kmeans",
        filters=req.filters,
        viewport=None,
        selectedModelPfas=req.selectedModelPfas,
        params=AnalysisParams(),
        mode="expert",
    )

    filtered = apply_filters(df, fake_req)
    if filtered.empty:
        raise HTTPException(status_code=400, detail="Lancez d'abord une analyse de clustering.")

    substance_ref = load_substance_ref()

    try:
        return json_safe(
            compute_clamp_explanation(
                df_filtered=filtered,
                assignments=req.assignments,
                selected_model_pfas=req.selectedModelPfas,
                cluster_id=req.clusterId,
                explainer_type=req.params.explainerType,
                bounding_box_selection=req.params.boundingBoxSelection,
                description_points_ratio=req.params.descriptionPointsRatio,
                max_rules_per_cluster=req.params.maxRulesPerCluster,
                ignore_noise=req.params.ignoreNoise,
                substance_ref=substance_ref,
            )
        )
    except ClampServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        print(f"[analysis/clamp] Erreur ClAMP: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur pendant le calcul ClAMP: {exc}",
        )

def _prepare_mssp_matrix(x: np.ndarray) -> np.ndarray:
    """
    Adaptation PFAS:
    - concentrations seulement
    - log1p pour réduire l'asymétrie
    - standardisation pour la similarité de profils
    """
    x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
    x = np.maximum(x, 0.0)
    x = np.log1p(x)
    x = StandardScaler().fit_transform(x)
    return x


def _sample_for_mssp(x: np.ndarray, max_points: int = MSSP_MAX_POINTS) -> tuple[np.ndarray, np.ndarray]:
    n = len(x)
    if n <= max_points:
        return x, np.arange(n)

    rng = np.random.RandomState(42)
    idx = rng.choice(n, size=max_points, replace=False)
    return x[idx], idx


def _build_conflict_matrix(
    x: np.ndarray,
    knn: int = MSSP_KNN,
    theta: float = MSSP_THETA,
) -> np.ndarray:
    """
    Graphe de conflit:
    arête = deux profils PFAS trop similaires -> ne doivent pas être choisis ensemble
    dans le stable set.
    """
    n = len(x)
    if n < 2:
        return np.zeros((n, n), dtype=bool)

    n_neighbors = min(knn + 1, n)
    nn = NearestNeighbors(metric="cosine", n_neighbors=n_neighbors, n_jobs=-1)
    nn.fit(x)
    distances, indices = nn.kneighbors(x)

    conflict = np.zeros((n, n), dtype=bool)
    similarities = 1.0 - distances

    for i in range(n):
        for j, sim in zip(indices[i, 1:], similarities[i, 1:]):
            j = int(j)
            if sim >= theta:
                conflict[i, j] = True
                conflict[j, i] = True

    np.fill_diagonal(conflict, False)
    return conflict


def _chn_relaxation(
    conflict: np.ndarray,
    max_iter: int = 500,
    lam: float = 1.25,
    beta: float = 4.0,
    tol: float = 1e-4,
) -> np.ndarray:
    """
    Relaxation continue inspirée CHN.
    On maximise implicitement:
      sélection élevée
      pénalisation des couples en conflit
    """
    n = conflict.shape[0]
    if n == 0:
        return np.empty((0,), dtype=float)

    C = conflict.astype(float)
    rng = np.random.RandomState(42)
    v = 0.9 + 1e-3 * rng.randn(n)
    v = np.clip(v, 1e-3, 1 - 1e-3)

    for _ in range(max_iter):
        inhibition = C @ v
        net = 1.0 - 2.0 * lam * inhibition
        v_new = 1.0 / (1.0 + np.exp(-beta * net))
        v_new = 0.7 * v + 0.3 * v_new

        if np.max(np.abs(v_new - v)) < tol:
            v = v_new
            break
        v = v_new

    return v


def _repair_to_stable_set(conflict: np.ndarray, scores: np.ndarray) -> np.ndarray:
    """
    Réparation gloutonne:
    on transforme la solution continue en vrai stable set.
    """
    n = len(scores)
    order = np.argsort(scores)[::-1]
    blocked = np.zeros(n, dtype=bool)
    selected: list[int] = []

    for idx in order:
        idx = int(idx)
        if blocked[idx]:
            continue
        selected.append(idx)
        blocked[idx] = True
        blocked |= conflict[idx]

    return np.array(selected, dtype=int)

def _is_all_selected_model_pfas(selected_model_pfas: list[str]) -> bool:
    return (not selected_model_pfas) or ("All" in selected_model_pfas)


def _resolve_effective_reduction(req: AnalysisRequest) -> str:
    if req.algorithm == "propos":
        return "saint"

    if req.mode == "simple":
        return "saint"

    return req.params.reduction
