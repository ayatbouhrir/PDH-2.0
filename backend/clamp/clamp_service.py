from __future__ import annotations

import importlib.util
import math
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd

from visualization import build_substance_maps


CLAMP_MAX_FIT_SAMPLES = 12_000
CLAMP_MIN_SUPPORT = 30
CLAMP_MIN_PRECISION = 0.60
CLAMP_MIN_CLUSTER_COVERAGE = 0.02
CLAMP_MAX_SUPPORT_RATIO = 0.50


class ClampServiceError(Exception):
    pass


def _clean_feature_label(label: str) -> str:
    return re.sub(r"\s*\[[^\]]*\]\s*$", "", str(label or "")).strip() or str(label)


def _format_numeric_value(value: float) -> str:
    numeric_value = float(value)
    if math.isclose(numeric_value, round(numeric_value), rel_tol=0.0, abs_tol=1e-9):
        return str(int(round(numeric_value)))

    text = f"{numeric_value:.4f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _resolve_selected_pfas_columns(
    df: pd.DataFrame,
    selected_model_pfas: list[str],
    substance_ref: pd.DataFrame,
) -> list[str]:
    all_pfas_cols = [
        c
        for c in df.columns
        if c.startswith("pfas_")
        and len(c.split("_")) == 2
        and c.split("_")[1].isdigit()
    ]
    all_pfas_cols = sorted(all_pfas_cols, key=lambda c: int(c.split("_")[1]))

    if not all_pfas_cols:
        raise ClampServiceError("Aucune colonne PFAS trouvée.")

    if not selected_model_pfas or "All" in selected_model_pfas:
        return all_pfas_cols

    name_to_col, _ = build_substance_maps(substance_ref)
    lower_df = {c.lower(): c for c in all_pfas_cols}
    selected_cols: list[str] = []

    for item in selected_model_pfas:
        if not item:
            continue

        if item in all_pfas_cols:
            selected_cols.append(item)
            continue

        mapped = name_to_col.get(str(item))
        if mapped and mapped in df.columns:
            selected_cols.append(mapped)
            continue

        direct = lower_df.get(str(item).lower())
        if direct:
            selected_cols.append(direct)

    selected_cols = list(dict.fromkeys(selected_cols))
    if not selected_cols:
        raise ClampServiceError("Aucune colonne PFAS ne correspond à selectedModelPfas.")

    return selected_cols


def _pfas_columns_to_display_names(
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

    cleaned_labels: list[str] = []
    seen: dict[str, int] = {}
    for col in pfas_cols:
        base = _clean_feature_label(idx_to_name.get(col, col))
        count = seen.get(base, 0)
        seen[base] = count + 1
        cleaned_labels.append(base if count == 0 else f"{base} ({count + 1})")

    return cleaned_labels


def _feature_units_map(
    pfas_cols: list[str],
    feature_labels: list[str],
    substance_ref: pd.DataFrame,
) -> dict[str, str | None]:
    column_to_unit: dict[str, str | None] = {}

    for _, row in substance_ref.iterrows():
        col = f"pfas_{int(row['pfas_index'])}"
        unit = row.get("unit_ref")
        if unit is None:
            column_to_unit[col] = None
            continue

        unit_text = str(unit).strip()
        column_to_unit[col] = unit_text or None

    return {
        label: column_to_unit.get(column)
        for column, label in zip(pfas_cols, feature_labels)
    }


def _normalize_assignments(assignments: Any) -> dict[str, int]:
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
        for row in assignments:
            if not isinstance(row, dict):
                continue
            point_id = row.get("pointId")
            cluster_id = row.get("cluster")
            if point_id is None or cluster_id is None:
                continue
            try:
                normalized[str(point_id)] = int(cluster_id)
            except (TypeError, ValueError):
                continue
    return normalized


def _build_rule_string(conditions: list[dict[str, Any]]) -> str:
    if not conditions:
        return "TRUE"

    parts = []
    for condition in conditions:
        value = _format_numeric_value(float(condition["value"]))
        parts.append(f"{condition['feature']} {condition['operator']} {value}")
    return " AND ".join(parts)


def _parse_rule_conditions(rule: str) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    for chunk in str(rule).split("AND"):
        match = re.match(
            r"^\s*(?P<feature>.+?)\s*(?P<operator><=|>=|<|>|=)\s*(?P<value>-?\d+(?:\.\d+)?)\s*$",
            chunk.strip(),
        )
        if not match:
            continue
        conditions.append(
            {
                "feature": match.group("feature").strip(),
                "operator": match.group("operator"),
                "value": float(match.group("value")),
            }
        )
    return conditions


def _apply_conditions(df: pd.DataFrame, conditions: list[dict[str, Any]]) -> pd.Series:
    mask = pd.Series(True, index=df.index, dtype=bool)
    for condition in conditions:
        feature = condition["feature"]
        if feature not in df.columns:
            return pd.Series(False, index=df.index, dtype=bool)

        value = float(condition["value"])
        operator = condition["operator"]

        if operator == "<=":
            mask &= df[feature] <= value
        elif operator == ">=":
            mask &= df[feature] >= value
        elif operator == "<":
            mask &= df[feature] < value
        elif operator == ">":
            mask &= df[feature] > value
        else:
            mask &= df[feature] == value

    return mask


def _sample_for_fit(df: pd.DataFrame, max_samples: int) -> pd.DataFrame:
    if len(df) <= max_samples:
        return df.reset_index(drop=True)

    rng = np.random.RandomState(42)
    grouped = df.groupby("cluster", sort=True)
    total = len(df)
    sampled_parts: list[pd.DataFrame] = []

    for _, group in grouped:
        proportional = int(round((len(group) / total) * max_samples))
        target = max(2, proportional)
        target = min(len(group), target)
        if target >= len(group):
            sampled_parts.append(group)
            continue
        sampled_parts.append(group.sample(n=target, random_state=int(rng.randint(0, 1_000_000))))

    sampled = pd.concat(sampled_parts, axis=0).reset_index(drop=True)
    if len(sampled) > max_samples:
        sampled = sampled.sample(n=max_samples, random_state=42).reset_index(drop=True)
    return sampled


def _ensure_optional_module(module_name: str, module: ModuleType) -> None:
    if module_name not in sys.modules:
        sys.modules[module_name] = module


def _has_module(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _install_optional_stubs() -> None:
    if not _has_module("anchor") and "anchor" not in sys.modules:
        anchor_module = ModuleType("anchor")
        anchor_module.anchor_tabular = object()
        _ensure_optional_module("anchor", anchor_module)

    if not _has_module("lux") and "lux" not in sys.modules:
        lux_module = ModuleType("lux")

        class _StubLUX:
            def __init__(self, *args: Any, **kwargs: Any):
                raise RuntimeError("LUX non disponible dans cet environnement.")

        lux_module.LUX = _StubLUX
        _ensure_optional_module("lux", lux_module)

    if not _has_module("xgboost") and "xgboost" not in sys.modules:
        xgboost_module = ModuleType("xgboost")
        _ensure_optional_module("xgboost", xgboost_module)

    if not _has_module("sklearn_extra.cluster") and "sklearn_extra.cluster" not in sys.modules:
        sklearn_extra_module = ModuleType("sklearn_extra")
        sklearn_extra_cluster_module = ModuleType("sklearn_extra.cluster")

        class _FallbackKMedoids:
            def __init__(self, n_clusters: int = 1, random_state: int | None = None):
                self.n_clusters = n_clusters
                self.random_state = random_state
                self.cluster_centers_: np.ndarray | None = None

            def fit(self, x: Any):
                values = np.asarray(x, dtype=float)
                if values.ndim != 2 or values.shape[0] == 0:
                    raise ValueError("KMedoids requiert une matrice 2D non vide.")

                centroid = values.mean(axis=0)
                distances = np.linalg.norm(values - centroid, axis=1)
                medoid = values[int(np.argmin(distances))]
                self.cluster_centers_ = medoid.reshape(1, -1)
                return self

        sklearn_extra_cluster_module.KMedoids = _FallbackKMedoids
        sklearn_extra_module.cluster = sklearn_extra_cluster_module
        _ensure_optional_module("sklearn_extra", sklearn_extra_module)
        _ensure_optional_module("sklearn_extra.cluster", sklearn_extra_cluster_module)


def _load_clamp_class():
    module_name = "clamp_runtime_module"
    if module_name in sys.modules:
        return sys.modules[module_name].CLAMP

    _install_optional_stubs()

    clamp_path = Path(__file__).resolve().parent / "clamp.py"
    spec = importlib.util.spec_from_file_location(module_name, clamp_path)
    if spec is None or spec.loader is None:
        raise ClampServiceError("Impossible de charger clamp.py.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.CLAMP


def _extract_tree_rules(
    tree_model: Any,
    feature_names: list[str],
    x_full: pd.DataFrame,
    y_full: pd.Series,
) -> list[dict[str, Any]]:
    estimator = getattr(tree_model, "explainer", tree_model)
    tree = getattr(estimator, "tree_", None)
    classes = getattr(estimator, "classes_", None)

    if tree is None or classes is None:
        raise ClampServiceError("Impossible d'extraire les règles de l'arbre ClAMP.")

    class_totals = y_full.value_counts().to_dict()
    rules: list[dict[str, Any]] = []

    def walk(node_id: int, conditions: list[dict[str, Any]]) -> None:
        left = tree.children_left[node_id]
        right = tree.children_right[node_id]

        if left == right:
            counts = tree.value[node_id][0]
            if counts.size == 0 or tree.n_node_samples[node_id] <= 0:
                return

            class_index = int(np.argmax(counts))
            cluster = int(classes[class_index])
            support = int(tree.n_node_samples[node_id])
            class_support = float(counts[class_index])
            total_class = max(1, int(class_totals.get(cluster, 0)))
            precision = class_support / max(1, support)
            coverage = class_support / total_class
            score = precision * coverage

            rules.append(
                {
                    "cluster": cluster,
                    "conditions": [dict(condition) for condition in conditions],
                    "precision": float(precision),
                    "coverage": float(coverage),
                    "score": float(score),
                    "support": support,
                }
            )
            return

        feature_index = int(tree.feature[node_id])
        threshold = float(tree.threshold[node_id])
        feature_name = feature_names[feature_index]

        left_conditions = [
            *conditions,
            {"feature": feature_name, "operator": "<=", "value": threshold},
        ]
        right_conditions = [
            *conditions,
            {"feature": feature_name, "operator": ">", "value": threshold},
        ]

        walk(left, left_conditions)
        walk(right, right_conditions)

    walk(0, [])
    return rules


def _rules_from_justify_dataframe(
    rules_df: pd.DataFrame,
    x_full: pd.DataFrame,
    y_full: pd.Series,
) -> list[dict[str, Any]]:
    class_totals = y_full.value_counts().to_dict()
    prepared_rules: list[dict[str, Any]] = []

    for _, row in rules_df.iterrows():
        try:
            cluster = int(row["Cluster"])
        except Exception:
            continue

        conditions = _parse_rule_conditions(str(row.get("Rule", "")))
        mask = _apply_conditions(x_full, conditions)
        support = int(mask.sum())
        if support <= 0:
            continue

        cluster_support = int((y_full[mask] == cluster).sum())
        precision = cluster_support / max(1, support)
        coverage = cluster_support / max(1, int(class_totals.get(cluster, 0)))
        score = precision * coverage

        prepared_rules.append(
            {
                "cluster": cluster,
                "conditions": conditions,
                "precision": float(row.get("Precision", precision) or precision),
                "coverage": float(row.get("Coverage", coverage) or coverage),
                "score": float(score),
                "support": support,
            }
        )

    return prepared_rules


def compute_clamp_explanation(
    df_filtered: pd.DataFrame,
    assignments: Any,
    selected_model_pfas: list[str],
    cluster_id: int | None = None,
    explainer_type: str = "dtexp",
    bounding_box_selection: str = "centroids",
    description_points_ratio: float = 5,
    max_rules_per_cluster: int = 5,
    ignore_noise: bool = True,
    substance_ref: pd.DataFrame | None = None,
) -> dict[str, Any]:
    normalized_assignments = _normalize_assignments(assignments)
    if not normalized_assignments:
        raise ClampServiceError("Lancez d'abord une analyse de clustering.")

    if substance_ref is None:
        raise ClampServiceError("La table de référence des PFAS est requise pour ClAMP.")

    explainer_type = str(explainer_type or "dtexp").lower()
    bounding_box_selection = str(bounding_box_selection or "centroids").lower()

    if explainer_type in {"anchor", "lux"}:
        raise ClampServiceError(
            f"Le mode ClAMP '{explainer_type}' n'est pas activé dans cet environnement. "
            "Utilisez 'dtexp' ou 'global'."
        )

    if explainer_type not in {"dtexp", "global"}:
        raise ClampServiceError(
            "Type d'explainer ClAMP non supporté. Choisissez 'dtexp' ou 'global'."
        )

    working = df_filtered.copy()
    working["cluster"] = working["point_id"].astype(str).map(normalized_assignments)
    working = working.dropna(subset=["cluster"]).copy()

    if working.empty:
        raise ClampServiceError("Aucun point n'a pu être relié aux assignments.")

    working["cluster"] = working["cluster"].astype(int)
    noise_count = int((working["cluster"] == -1).sum())

    if ignore_noise:
        working = working[working["cluster"] != -1].copy()

    if working.empty:
        raise ClampServiceError("Analyse explicable impossible : tous les points sont bruit -1.")

    available_clusters = sorted({int(v) for v in working["cluster"].tolist()})
    if len(available_clusters) < 2:
        raise ClampServiceError("Analyse explicable impossible : au moins deux clusters sont nécessaires.")

    if cluster_id is not None and int(cluster_id) not in available_clusters:
        raise ClampServiceError(f"Cluster cible introuvable : C{cluster_id}.")

    pfas_cols = _resolve_selected_pfas_columns(
        df=working,
        selected_model_pfas=selected_model_pfas,
        substance_ref=substance_ref,
    )
    feature_labels = _pfas_columns_to_display_names(pfas_cols, substance_ref)
    feature_units = _feature_units_map(pfas_cols, feature_labels, substance_ref)
    rename_map = dict(zip(pfas_cols, feature_labels))

    x_raw = (
        working[pfas_cols]
        .copy()
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )
    x_raw = x_raw.rename(columns=rename_map)
    x_raw = x_raw.astype(float)

    if x_raw.empty or x_raw.shape[1] == 0:
        raise ClampServiceError("Aucune variable PFAS numérique exploitable pour ClAMP.")

    prepared = x_raw.copy()
    prepared["cluster"] = working["cluster"].to_numpy(dtype=int)
    prepared["point_id"] = working["point_id"].tolist()

    sampled = _sample_for_fit(prepared, CLAMP_MAX_FIT_SAMPLES)
    x_fit = sampled.drop(columns=["cluster", "point_id"]).reset_index(drop=True)
    y_fit = sampled["cluster"].reset_index(drop=True)

    CLAMP = _load_clamp_class()
    clamp_model = CLAMP(
        bounding_box_selection=bounding_box_selection,
        description_points_ratio=max(1.0, float(description_points_ratio or 5)),
        explainer_type=explainer_type,
    )
    clamp_model.fit(x_fit.copy(), y_fit.to_numpy())

    extracted_rules: list[dict[str, Any]]
    if explainer_type in {"dtexp", "global"}:
        extracted_rules = _extract_tree_rules(
            tree_model=clamp_model.explainer,
            feature_names=list(x_fit.columns),
            x_full=x_raw.reset_index(drop=True),
            y_full=working["cluster"].reset_index(drop=True),
        )
    else:
        rules_df = clamp_model.justify()
        if not isinstance(rules_df, pd.DataFrame) or rules_df.empty:
            raise ClampServiceError("ClAMP n'a retourné aucune règle exploitable.")
        extracted_rules = _rules_from_justify_dataframe(
            rules_df=rules_df,
            x_full=x_raw.reset_index(drop=True),
            y_full=working["cluster"].reset_index(drop=True),
        )

    grouped_rules: dict[int, list[dict[str, Any]]] = {}
    for rule in extracted_rules:
        grouped_rules.setdefault(int(rule["cluster"]), []).append(rule)

    if cluster_id is not None:
        grouped_rules = {int(cluster_id): grouped_rules.get(int(cluster_id), [])}

    final_rules: list[dict[str, Any]] = []
    rules_by_cluster: dict[str, list[dict[str, Any]]] = {}
    covered_point_ids: dict[str, list[Any]] = {}
    feature_usage_counter: dict[str, int] = {}
    total_rules_seen = 0

    working_reset = working.reset_index(drop=True)
    x_eval = x_raw.reset_index(drop=True)
    total_points_analyzed = max(1, int(len(working_reset)))
    cluster_sizes = working_reset["cluster"].value_counts().to_dict()

    for current_cluster in sorted(grouped_rules.keys()):
        candidate_rules: list[dict[str, Any]] = []

        rules_by_cluster[str(current_cluster)] = []

        for rule in grouped_rules[current_cluster]:
            total_rules_seen += 1
            conditions = rule["conditions"]
            if not conditions:
                continue

            rule_mask = _apply_conditions(x_eval, conditions)
            point_ids = working_reset.loc[rule_mask, "point_id"].tolist()
            support = int(len(point_ids))
            if support <= 0:
                continue

            cluster_mask = working_reset["cluster"] == int(current_cluster)
            true_positive = int((cluster_mask & rule_mask).sum())
            support_ratio = support / total_points_analyzed
            precision = true_positive / max(1, support)
            coverage_cluster = true_positive / max(1, int(cluster_sizes.get(int(current_cluster), 0)))
            score = precision * coverage_cluster

            if (
                support < CLAMP_MIN_SUPPORT
                or precision < CLAMP_MIN_PRECISION
                or coverage_cluster < CLAMP_MIN_CLUSTER_COVERAGE
                or support_ratio > CLAMP_MAX_SUPPORT_RATIO
                or score <= 0
            ):
                continue

            features = []
            enriched_conditions: list[dict[str, Any]] = []
            for condition in conditions:
                feature = condition["feature"]
                if feature not in features:
                    features.append(feature)
                    feature_usage_counter[feature] = feature_usage_counter.get(feature, 0) + 1

                enriched_conditions.append(
                    {
                        "feature": feature,
                        "operator": condition["operator"],
                        "value": float(condition["value"]),
                        "unit": feature_units.get(feature),
                    }
                )

            candidate_rules.append(
                {
                    "cluster": int(current_cluster),
                    "rule": _build_rule_string(enriched_conditions),
                    "conditions": enriched_conditions,
                    "support": support,
                    "supportRatio": round(float(support_ratio), 4),
                    "precision": round(float(precision), 4),
                    "coverageCluster": round(float(coverage_cluster), 4),
                    "score": round(float(score), 4),
                    "coveredPointIds": point_ids,
                    "features": features,
                }
            )

        cluster_rules = sorted(
            candidate_rules,
            key=lambda item: (
                float(item["score"]),
                float(item["precision"]),
                float(item["coverageCluster"]),
                float(item["support"]),
            ),
            reverse=True,
        )[: max(1, int(max_rules_per_cluster or 5))]

        for index, rule_payload in enumerate(cluster_rules, start=1):
            rule_id = f"C{current_cluster}_R{index}"
            hydrated_rule = {
                "id": rule_id,
                **rule_payload,
            }

            final_rules.append(hydrated_rule)
            rules_by_cluster[str(current_cluster)].append(hydrated_rule)
            covered_point_ids[rule_id] = hydrated_rule["coveredPointIds"]

    for cluster in available_clusters:
        rules_by_cluster.setdefault(str(cluster), [])

    feature_usage = [
        {"feature": feature, "count": count}
        for feature, count in sorted(
            feature_usage_counter.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )
    ]

    explained_clusters = []
    best_rules_by_cluster: dict[str, str | None] = {}
    for cluster, rules in sorted(
        ((int(key), value) for key, value in rules_by_cluster.items()),
        key=lambda item: item[0],
    ):
        best_rules_by_cluster[str(cluster)] = rules[0]["id"] if rules else None
        if rules:
            explained_clusters.append(int(cluster))

    best_rule_id = None
    if final_rules:
        best_rule_id = sorted(
            final_rules,
            key=lambda item: (
                float(item["score"]),
                float(item["precision"]),
                float(item["coverageCluster"]),
                float(item["support"]),
            ),
            reverse=True,
        )[0]["id"]

    return {
        "method": "clamp",
        "status": "ok",
        "rules": final_rules,
        "rulesByCluster": rules_by_cluster,
        "coveredPointIds": covered_point_ids,
        "bestRuleId": best_rule_id,
        "bestRulesByCluster": best_rules_by_cluster,
        "featureUsage": feature_usage,
        "metadata": {
            "nSamples": int(len(working)),
            "nFeatures": int(x_raw.shape[1]),
            "fitSamples": int(len(sampled)),
            "clustersExplained": explained_clusters,
            "ignoredNoise": int(noise_count if ignore_noise else 0),
            "sourceSpace": "raw_pfas",
            "clusterSource": "assignments",
            "explainerType": explainer_type,
            "boundingBoxSelection": bounding_box_selection,
            "targetClusterId": int(cluster_id) if cluster_id is not None else None,
            "filteredRules": int(len(final_rules)),
            "totalRules": int(total_rules_seen),
        },
    }
