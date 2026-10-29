from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def normalize_cluster_assignments(
    cluster_assignments: dict[str, int] | None,
) -> dict[str, int]:
    if not cluster_assignments:
        return {}

    normalized: dict[str, int] = {}
    for point_id, cluster_id in cluster_assignments.items():
        try:
            normalized[str(int(point_id))] = int(cluster_id)
        except (TypeError, ValueError):
            continue

    return normalized


def build_substance_maps(substance_ref: pd.DataFrame) -> tuple[dict[str, str], dict[str, str]]:
    ref = substance_ref.copy()
    ref["column"] = ref["pfas_index"].apply(lambda i: f"pfas_{int(i)}")

    name_to_col = {
        str(row["substance_name"]): str(row["column"])
        for _, row in ref.iterrows()
        if pd.notna(row["substance_name"]) and pd.notna(row["column"])
    }

    col_to_name = {
        str(row["column"]): str(row["substance_name"])
        for _, row in ref.iterrows()
        if pd.notna(row["substance_name"]) and pd.notna(row["column"])
    }

    return name_to_col, col_to_name
def get_reference_population(
        df: pd.DataFrame,
        cluster_assignments: dict[str, int] | None = None,
    ) -> pd.DataFrame:
        normalized_assignments = normalize_cluster_assignments(cluster_assignments)
        if not normalized_assignments:
            return df.copy()

        keep_ids = {int(pid) for pid in normalized_assignments.keys()}
        if "point_id" not in df.columns:
            return df.copy()

        ref_df = df[df["point_id"].astype(int).isin(keep_ids)].copy()
        return ref_df if not ref_df.empty else df.copy()

def compute_fixed_detected_axes(
    reference_df: pd.DataFrame,
    substance_ref: pd.DataFrame,
    top_n: int = 10,
) -> list[str]:
    _, col_to_name = build_substance_maps(substance_ref)
    pfas_cols = get_numeric_pfas_columns(reference_df)

    candidates: list[tuple[str, int, float]] = []

    for col in pfas_cols:
        series = pd.to_numeric(reference_df[col], errors="coerce")
        detected = int((series.fillna(0) > 0).sum())

        if detected <= 0:
            continue

        mean_val = float(series.fillna(0).mean())
        substance_name = col_to_name.get(col, col)
        candidates.append((substance_name, detected, mean_val))

    candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return [name for name, _, _ in candidates[:top_n]]
def compute_fixed_discriminant_axes(
    reference_df: pd.DataFrame,
    substance_ref: pd.DataFrame,
    cluster_assignments: dict[str, int],
    cluster_id: int,
    top_n: int = 10,
) -> list[str]:
    _, col_to_name = build_substance_maps(substance_ref)

    cluster_keep_ids = {
        int(pid)
        for pid, cid in cluster_assignments.items()
        if int(cid) == int(cluster_id)
    }

    rest_keep_ids = {
        int(pid)
        for pid, cid in cluster_assignments.items()
        if int(cid) != int(cluster_id)
    }

    cluster_df = reference_df[reference_df["point_id"].astype(int).isin(cluster_keep_ids)].copy()
    rest_df = reference_df[reference_df["point_id"].astype(int).isin(rest_keep_ids)].copy()

    if cluster_df.empty or rest_df.empty:
        return []

    pfas_cols = get_numeric_pfas_columns(reference_df)
    candidates: list[tuple[str, float, float, float]] = []

    for col in pfas_cols:
        cluster_vals = pd.to_numeric(cluster_df[col], errors="coerce").fillna(0.0)
        rest_vals = pd.to_numeric(rest_df[col], errors="coerce").fillna(0.0)
        global_vals = pd.to_numeric(reference_df[col], errors="coerce").fillna(0.0)

        mu_cluster = float(cluster_vals.mean())
        mu_rest = float(rest_vals.mean())
        sigma_global = float(global_vals.std())
        score = abs(mu_cluster - mu_rest) / (sigma_global + 1e-9)

        if score <= 1e-12:
            continue

        substance_name = col_to_name.get(col, col)
        direction = "higher_in_cluster" if mu_cluster >= mu_rest else "lower_in_cluster"
        candidates.append((substance_name, score, mu_cluster, mu_rest, direction))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _, _, _, _ in candidates[:top_n]]


def resolve_visualization_subset(
    df: pd.DataFrame,
    cluster_assignments: dict[str, int] | None = None,
    cluster_id: int | None = None,
    point_ids: list[int] | None = None,
) -> pd.DataFrame:
    out = df.copy()
    normalized_assignments = normalize_cluster_assignments(cluster_assignments)

    if point_ids:
        keep_ids = {int(x) for x in point_ids}
        if normalized_assignments:
            keep_ids &= {int(pid) for pid in normalized_assignments.keys()}
        if "point_id" not in out.columns:
            return out.iloc[0:0].copy()
        return out[out["point_id"].astype(int).isin(keep_ids)].copy()

    if cluster_id is not None and normalized_assignments:
        keep_ids = {
            int(pid)
            for pid, cid in normalized_assignments.items()
            if int(cid) == int(cluster_id)
        }
        if not keep_ids:
            return out.iloc[0:0].copy()
        return out[out["point_id"].astype(int).isin(keep_ids)].copy()

    if normalized_assignments:
        keep_ids = {int(pid) for pid in normalized_assignments.keys()}
        if "point_id" not in out.columns:
            return out.iloc[0:0].copy()
        return out[out["point_id"].astype(int).isin(keep_ids)].copy()

    return out

def get_numeric_pfas_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for c in df.columns:
        name = str(c)
        if name.startswith("pfas_"):
            parts = name.split("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                cols.append(name)
    return cols

def aggregate_series(work: pd.DataFrame, value_col: str, aggregation: str = "mean") -> pd.DataFrame:
    if aggregation == "median":
        grouped = (
            work.groupby("year", as_index=False)[value_col]
            .median()
            .sort_values("year")
        )
    else:
        grouped = (
            work.groupby("year", as_index=False)[value_col]
            .mean()
            .sort_values("year")
        )
    return grouped


def build_temporal_visualization(
    df: pd.DataFrame,
    substance_ref: pd.DataFrame,
    selected_pfas: list[str] | None,
    temporal_mode: str = "global",
    cluster_assignments: dict[str, int] | None = None,
    cluster_id: int | None = None,
    point_ids: list[int] | None = None,
    aggregation: str = "mean",
    top_n: int = 5,
) -> dict[str, Any]:
    subset = resolve_visualization_subset(
        df=df,
        cluster_assignments=cluster_assignments,
        cluster_id=cluster_id,
        point_ids=point_ids,
    )

    name_to_col, col_to_name = build_substance_maps(substance_ref)

    if subset.empty:
        return {
            "mode": "temporal",
            "series": [],
            "meta": {
                "count": 0,
                "clusterId": cluster_id,
                "temporalMode": temporal_mode,
                "error": "Sous-ensemble vide.",
            },
        }

    if "year" not in subset.columns:
        return {
            "mode": "temporal",
            "series": [],
            "meta": {
                "count": 0,
                "clusterId": cluster_id,
                "temporalMode": temporal_mode,
                "error": "La colonne year est absente.",
            },
        }

    subset = subset.copy()
    subset["year"] = pd.to_numeric(subset["year"], errors="coerce")
    subset = subset.dropna(subset=["year"])

    if subset.empty:
        return {
            "mode": "temporal",
            "series": [],
            "meta": {
                "count": 0,
                "clusterId": cluster_id,
                "temporalMode": temporal_mode,
                "error": "Aucune année disponible dans le sous-ensemble courant.",
            },
        }

    subset["year"] = subset["year"].astype(int)

    if temporal_mode == "global":
        if not selected_pfas or "All" in selected_pfas:
            candidates: list[tuple[str, int, float]] = []
            pfas_cols = get_numeric_pfas_columns(subset)

            for col in pfas_cols:
                values = pd.to_numeric(subset[col], errors="coerce")
                detected = int((values.fillna(0) > 0).sum())
                if detected <= 0:
                    continue

                mean_val = float(values.fillna(0).mean())
                substance_name = col_to_name.get(col, col)
                candidates.append((substance_name, detected, mean_val))

            candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
            selected_names = [name for name, _, _ in candidates[:top_n]]
        else:
            selected_names = [name for name in selected_pfas if name in name_to_col][:10]

        if not selected_names:
            return {
                "mode": "temporal",
                "series": [],
                "meta": {
                    "count": int(len(subset)),
                    "clusterId": cluster_id,
                    "temporalMode": temporal_mode,
                    "error": "Aucun PFAS valide sélectionné pour le mode global.",
                },
            }

        rows: list[dict[str, Any]] = []

        for substance_name in selected_names:
            col = name_to_col.get(substance_name)
            if not col or col not in subset.columns:
                continue

            work = subset[["year", col]].copy()
            work[col] = pd.to_numeric(work[col], errors="coerce")
            work = work.dropna(subset=[col])

            if work.empty:
                continue

            grouped = aggregate_series(work, col, aggregation)
            points = [{"x": int(row["year"]), "y": float(row[col])} for _, row in grouped.iterrows()]

            years_in_series = {p["x"] for p in points}
            if len(years_in_series) >= 2 and len(points) >= 2:
                rows.append({
                    "label": substance_name,
                    "points": points,
                })

        if not rows:
            return {
                "mode": "temporal",
                "series": [],
                "meta": {
                    "count": int(len(subset)),
                    "clusterId": cluster_id,
                    "temporalMode": temporal_mode,
                    "error": "Pas assez d’années distinctes pour afficher une évolution temporelle exploitable.",
                },
            }

        return {
            "mode": "temporal",
            "series": rows,
            "meta": {
                "count": int(len(subset)),
                "clusterId": cluster_id,
                "temporalMode": temporal_mode,
                "aggregation": aggregation,
            },
        }

    if temporal_mode == "cluster":
        if not cluster_assignments:
            return {
                "mode": "temporal",
                "series": [],
                "meta": {
                    "count": int(len(subset)),
                    "clusterId": cluster_id,
                    "temporalMode": temporal_mode,
                    "error": "Le mode cluster nécessite des assignments.",
                },
            }

        normalized_selected = []
        if selected_pfas:
            normalized_selected = [p for p in selected_pfas if p and p != "All"]

        if len(normalized_selected) != 1:
            return {
                "mode": "temporal",
                "series": [],
                "meta": {
                    "count": int(len(subset)),
                    "clusterId": cluster_id,
                    "temporalMode": temporal_mode,
                    "error": "Le mode cluster nécessite exactement un seul PFAS sélectionné.",
                },
            }

        chosen_pfas = normalized_selected[0]
        col = name_to_col.get(chosen_pfas)

        if not col or col not in subset.columns:
            return {
                "mode": "temporal",
                "series": [],
                "meta": {
                    "count": int(len(subset)),
                    "clusterId": cluster_id,
                    "temporalMode": temporal_mode,
                    "error": "PFAS invalide pour le mode cluster.",
                },
            }

        rows: list[dict[str, Any]] = []
        normalized_assignments = normalize_cluster_assignments(cluster_assignments)
        unique_clusters = sorted({int(cid) for cid in normalized_assignments.values()})

        for cid in unique_clusters:
            keep_ids = {
                int(pid)
                for pid, assigned_cid in normalized_assignments.items()
                if int(assigned_cid) == cid
            }

            if len(keep_ids) < 2:
                continue

            cluster_df = subset[subset["point_id"].astype(int).isin(keep_ids)].copy()
            if cluster_df.empty:
                continue

            work = cluster_df[["year", col]].copy()
            work[col] = pd.to_numeric(work[col], errors="coerce")
            work = work.dropna(subset=[col, "year"])

            if work.empty:
                continue

            distinct_years = work["year"].dropna().astype(int).nunique()
            if distinct_years < 2:
                continue

            grouped = aggregate_series(work, col, aggregation)
            points = [{"x": int(row["year"]), "y": float(row[col])} for _, row in grouped.iterrows()]

            if len(points) < 2:
                continue

            rows.append({
                "label": "Noise" if cid == -1 else f"Cluster {cid}",
                "points": points,
            })

        if len(rows) < 2:
            return {
                "mode": "temporal",
                "series": [],
                "meta": {
                    "count": int(len(subset)),
                    "clusterId": cluster_id,
                    "temporalMode": temporal_mode,
                    "error": "Pas assez de clusters exploitables avec au moins 2 années distinctes.",
                },
            }

        return {
            "mode": "temporal",
            "series": rows,
            "meta": {
                "count": int(len(subset)),
                "clusterId": cluster_id,
                "temporalMode": temporal_mode,
                "aggregation": aggregation,
                "pfas": chosen_pfas,
            },
        }

    return {
        "mode": "temporal",
        "series": [],
        "meta": {
            "count": int(len(subset)),
            "clusterId": cluster_id,
            "temporalMode": temporal_mode,
            "error": f"Mode temporel invalide: {temporal_mode}",
        },
    }

def build_radar_visualization(
    df: pd.DataFrame,
    substance_ref: pd.DataFrame,
    mode: str = "selected",
    axes_pfas: list[str] | None = None,
    cluster_assignments: dict[str, int] | None = None,
    cluster_id: int | None = None,
    point_ids: list[int] | None = None,
    normalize: bool = True,
    top_n: int = 10,
) -> dict[str, Any]:
    
    subset = resolve_visualization_subset(
        df=df,
        cluster_assignments=cluster_assignments,
        cluster_id=cluster_id,
        point_ids=point_ids,
    )
    name_to_col, col_to_name = build_substance_maps(substance_ref)

    if subset.empty:
        return {
            "mode": "radar",
            "axes": [],
            "series": [],
            "meta": {
                "count": 0,
                "clusterId": cluster_id,
                "normalized": bool(normalize),
                "radarMode": mode,
                "error": "Sous-ensemble vide.",
            },
        }

    reference_df = get_reference_population(df, cluster_assignments)
    name_to_col, _ = build_substance_maps(substance_ref)

    if mode == "selected":
        if not axes_pfas or "All" in axes_pfas:
            # All = tous les PFAS disponibles, mais on limite à 10 affichables
            axes = compute_fixed_detected_axes(
                reference_df=subset,
                substance_ref=substance_ref,
                top_n=10,
        )
        else:
            axes = [axis for axis in axes_pfas if axis in name_to_col][:10]

    elif mode == "detected":
        axes = compute_fixed_detected_axes(
            reference_df=subset,
            substance_ref=substance_ref,
            top_n=top_n,
        )

    elif mode == "discriminant":
            if cluster_id is None or cluster_assignments is None:
                return {
                    "mode": "radar",
                    "axes": [],
                    "series": [],
                    "meta": {
                        "count": int(len(subset)),
                        "clusterId": cluster_id,
                        "normalized": bool(normalize),
                        "radarMode": mode,
                        "error": "Le mode discriminant nécessite un cluster sélectionné.",
                    },
                }

            axes = compute_fixed_discriminant_axes(
                reference_df=reference_df,
                substance_ref=substance_ref,
                cluster_assignments=cluster_assignments,
                cluster_id=cluster_id,
                top_n=top_n,
            )

    else:
        return {
            "mode": "radar",
            "axes": [],
            "series": [],
            "meta": {
                "count": int(len(subset)),
                "clusterId": cluster_id,
                "normalized": bool(normalize),
                "radarMode": mode,
                "error": f"Mode radar invalide: {mode}",
            },
        }

    if not axes:
        return {
            "mode": "radar",
            "axes": [],
            "series": [],
            "meta": {
                "count": int(len(subset)),
                "clusterId": cluster_id,
                "normalized": bool(normalize),
                "radarMode": mode,
                "error": "Aucun axe PFAS valide.",
            },
        }

    raw_values: list[float] = []

    for axis_name in axes:
        col = name_to_col.get(axis_name)

        if not col or col not in subset.columns:
            raw_values.append(0.0)
            continue

        values = pd.to_numeric(subset[col], errors="coerce").dropna()
        if values.empty:
            raw_values.append(0.0)
        else:
            raw_values.append(float(values.mean()))

    values = raw_values.copy()

    if normalize:
        arr = np.array(values, dtype=float)
        max_val = float(np.nanmax(arr)) if arr.size > 0 else 0.0
        if max_val > 0:
            arr = arr / max_val
        values = [float(v) for v in arr]

    reference_df = df.copy()
    name_to_col, _ = build_substance_maps(substance_ref)


    if mode == "selected":
        label = "Selected PFAS"
    elif mode == "detected":
        label = f"Top {len(axes)} détectés (axes fixes)"
    else:
        label = f"Top {len(axes)} discriminants (axes fixes, valeurs du cluster)"

    return {
        "mode": "radar",
        "axes": axes,
        "series": [
            {
                "label": label,
                "values": values,
                "rawValues": raw_values,
            }
        ],
        "meta": {
            "count": int(len(subset)),
            "clusterId": cluster_id,
            "normalized": bool(normalize),
            "radarMode": mode,
        },
    }

