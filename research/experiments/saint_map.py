import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sklearn.cluster import KMeans

import folium
from folium import FeatureGroup, LayerControl
from folium.plugins import Fullscreen

# =========================================================
# CONFIG
# =========================================================

load_dotenv(Path(__file__).resolve().parents[2] / ".local/project.env")

PG_PARAMS = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "dbname": os.getenv("DB_NAME", "DAE-PFAS"),
}

# Chemin vers ton fichier embeddings SAINT
EMBEDDINGS_PATH = Path(__file__).resolve().parents[2] / "artifacts/embeddings/saint/saint_pfas_latent_mean.parquet"

# Sortie HTML
OUTPUT_HTML = Path(__file__).resolve().parents[2] / "artifacts/embeddings/saint/saint_pfas_map.html"

# Si le parquet ne contient pas de label cluster, on le recalcule ici
DEFAULT_K = 5

# Pour éviter une carte trop lourde
MAX_POINTS_TO_RENDER = None   # ex: 10000, ou None pour tout afficher

# Filtre éventuel
CATEGORY_FILTER = "Measurement"   # ou None


# =========================================================
# CONNEXION POSTGRESQL
# =========================================================

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


# =========================================================
# CHARGER EMBEDDINGS SAINT
# =========================================================

if not EMBEDDINGS_PATH.exists():
    raise FileNotFoundError(f"Fichier introuvable: {EMBEDDINGS_PATH}")

embeddings_df = pd.read_parquet(EMBEDDINGS_PATH)
print("Embeddings chargés :", embeddings_df.shape)

if "point_id" not in embeddings_df.columns:
    raise RuntimeError("Le parquet doit contenir une colonne point_id")

embedding_cols = [c for c in embeddings_df.columns if c.startswith("z")]
if not embedding_cols:
    raise RuntimeError("Aucune colonne z* trouvée dans le parquet SAINT")

# Détection du nom de colonne cluster existante
cluster_col = None
for candidate in ["cluster", "kmeans_cluster", "cluster_id"]:
    if candidate in embeddings_df.columns:
        cluster_col = candidate
        break

# Si pas de cluster existant, on calcule KMeans
if cluster_col is None:
    print("Aucun cluster trouvé dans le parquet. Calcul KMeans...")
    X = embeddings_df[embedding_cols].to_numpy(dtype=float)
    km = KMeans(n_clusters=DEFAULT_K, random_state=42, n_init=10)
    embeddings_df["cluster"] = km.fit_predict(X)
    cluster_col = "cluster"

print("Colonne cluster utilisée :", cluster_col)


# =========================================================
# CHARGER METADONNÉES CARTOGRAPHIQUES
# =========================================================

params = {}
where_sql = "WHERE p.lat IS NOT NULL AND p.lon IS NOT NULL"

if CATEGORY_FILTER is not None:
    where_sql += " AND p.category = :category_filter"
    params["category_filter"] = CATEGORY_FILTER

query = text(f"""
    SELECT
        p.id AS point_id,
        p.lat,
        p.lon,
        p.year,
        p.matrix,
        p.dataset_id,
        p.pfas_sum,
        p.category
    FROM public.pfas_points p
    {where_sql}
""")

meta_df = pd.read_sql(query, engine, params=params)
print("Meta chargée :", meta_df.shape)


# =========================================================
# MERGE
# =========================================================

map_df = embeddings_df.merge(meta_df, on="point_id", how="inner").copy()

map_df["lat"] = pd.to_numeric(map_df["lat"], errors="coerce")
map_df["lon"] = pd.to_numeric(map_df["lon"], errors="coerce")
map_df = map_df.dropna(subset=["lat", "lon"]).copy()

if MAX_POINTS_TO_RENDER is not None and len(map_df) > MAX_POINTS_TO_RENDER:
    map_df = map_df.sample(MAX_POINTS_TO_RENDER, random_state=42).copy()

print("Données carte finales :", map_df.shape)

if map_df.empty:
    raise RuntimeError("Aucun point à afficher sur la carte après merge")


# =========================================================
# CARTE
# =========================================================

cluster_values = sorted(map_df[cluster_col].dropna().unique().tolist())

palette = [
    "#440154", "#3b528b", "#21918c", "#5ec962", "#fde725",
    "#ff7f0e", "#d62728", "#9467bd", "#8c564b", "#17becf"
]

cluster_to_color = {
    cluster: palette[i % len(palette)]
    for i, cluster in enumerate(cluster_values)
}

center_lat = float(map_df["lat"].median())
center_lon = float(map_df["lon"].median())

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=5,
    tiles="CartoDB positron",
    control_scale=True,
)

Fullscreen().add_to(m)

# Couches par cluster
for cluster in cluster_values:
    fg = FeatureGroup(name=f"Cluster {cluster}", show=True)

    subset = map_df[map_df[cluster_col] == cluster]

    for _, row in subset.iterrows():
        popup_html = f"""
        <b>point_id:</b> {row['point_id']}<br>
        <b>cluster:</b> {row[cluster_col]}<br>
        <b>year:</b> {row.get('year', '')}<br>
        <b>matrix:</b> {row.get('matrix', '')}<br>
        <b>dataset_id:</b> {row.get('dataset_id', '')}<br>
        <b>pfas_sum:</b> {row.get('pfas_sum', '')}<br>
        """

        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=3,
            color=cluster_to_color[cluster],
            fill=True,
            fill_color=cluster_to_color[cluster],
            fill_opacity=0.65,
            weight=0.6,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"Cluster {cluster} | point {row['point_id']}",
        ).add_to(fg)

    fg.add_to(m)

LayerControl(collapsed=False).add_to(m)

# Petite légende HTML
legend_items = "".join(
    [
        f"""
        <div style="margin-bottom:4px;">
            <span style="
                display:inline-block;
                width:12px;
                height:12px;
                background:{cluster_to_color[c]};
                margin-right:6px;
                border:1px solid #333;">
            </span>
            Cluster {c}
        </div>
        """
        for c in cluster_values
    ]
)

legend_html = f"""
<div style="
position: fixed;
bottom: 30px;
left: 30px;
z-index: 9999;
background: white;
padding: 12px 14px;
border: 1px solid #999;
border-radius: 8px;
box-shadow: 0 2px 8px rgba(0,0,0,0.2);
font-size: 13px;
">
<b>Clusters SAINT</b><br><br>
{legend_items}
</div>
"""

m.get_root().html.add_child(folium.Element(legend_html))

OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
m.save(str(OUTPUT_HTML))

print(f"Carte enregistrée : {OUTPUT_HTML.resolve()}")