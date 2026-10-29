import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import pydeck as pdk


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

EMBEDDINGS_PATH = Path(__file__).resolve().parents[2] / "artifacts/embeddings/saint/saint_pfas_latent_mean.parquet"
OUTPUT_HTML = Path(__file__).resolve().parents[2] / "artifacts/embeddings/saint/saint_pfas_map_3d_clean.html"

CATEGORY_FILTER = "Measurement"

# =============================
# FILTRES DE VISUALISATION
# =============================

# Mets None pour tout afficher
SELECTED_CLUSTER = 4          # ex: 4, ou None
SELECTED_MATRIX = None        # ex: "Groundwater", ou None
YEAR_MIN = None               # ex: 2018, ou None
YEAR_MAX = None               # ex: 2023, ou None

# Axe Z
Z_MODE = "pfas_sum"           # ou "pfas_376"
USE_LOG_Z = True

# Coupe les valeurs extrêmes pour une meilleure lisibilité
CLIP_Z_PERCENTILE = 99.0

# Taille / rendu
MAX_POINTS = 8000
COLUMN_RADIUS = 1800
ELEVATION_SCALE = 18000

# Vue caméra
MAP_STYLE = pdk.map_styles.CARTO_DARK
INITIAL_ZOOM = 5
INITIAL_PITCH = 55
INITIAL_BEARING = 20


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
# CHARGER EMBEDDINGS
# =========================================================

if not EMBEDDINGS_PATH.exists():
    raise FileNotFoundError(f"Fichier introuvable: {EMBEDDINGS_PATH}")

embeddings_df = pd.read_parquet(EMBEDDINGS_PATH)
print("Embeddings chargés :", embeddings_df.shape)

if "point_id" not in embeddings_df.columns:
    raise RuntimeError("Le parquet SAINT doit contenir point_id")

cluster_col = None
for c in ["cluster", "kmeans_cluster", "cluster_id"]:
    if c in embeddings_df.columns:
        cluster_col = c
        break

if cluster_col is None:
    raise RuntimeError("Aucune colonne cluster trouvée dans le parquet")

embeddings_df[cluster_col] = embeddings_df[cluster_col].astype(int)


# =========================================================
# CHARGER META
# =========================================================

params = {}
where_sql = "WHERE p.lat IS NOT NULL AND p.lon IS NOT NULL"

if CATEGORY_FILTER is not None:
    where_sql += " AND p.category = :category_filter"
    params["category_filter"] = CATEGORY_FILTER

if Z_MODE == "pfas_sum":
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
    meta_df["z_value"] = pd.to_numeric(meta_df["pfas_sum"], errors="coerce").fillna(0.0)

elif Z_MODE.startswith("pfas_"):
    query = text(f"""
        SELECT
            p.id AS point_id,
            p.lat,
            p.lon,
            p.year,
            p.matrix,
            p.dataset_id,
            p.pfas_sum,
            p.category,
            v."{Z_MODE}" AS selected_pfas
        FROM public.pfas_points p
        JOIN public.point v
          ON v.point_id = p.id
        {where_sql}
    """)
    meta_df = pd.read_sql(query, engine, params=params)
    meta_df["z_value"] = pd.to_numeric(meta_df["selected_pfas"], errors="coerce").fillna(0.0)

else:
    raise ValueError("Z_MODE doit être 'pfas_sum' ou une colonne pfas_*")

print("Meta chargée :", meta_df.shape)


# =========================================================
# MERGE
# =========================================================

df = embeddings_df.merge(meta_df, on="point_id", how="inner").copy()

df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
df["year"] = pd.to_numeric(df["year"], errors="coerce")
df["z_value"] = pd.to_numeric(df["z_value"], errors="coerce")

df = df.dropna(subset=["lat", "lon", "z_value"]).copy()
df["z_value"] = df["z_value"].clip(lower=0.0)

# =========================================================
# FILTRES
# =========================================================

if SELECTED_CLUSTER is not None:
    df = df[df[cluster_col] == int(SELECTED_CLUSTER)].copy()

if SELECTED_MATRIX is not None:
    df = df[df["matrix"] == SELECTED_MATRIX].copy()

if YEAR_MIN is not None:
    df = df[df["year"] >= YEAR_MIN].copy()

if YEAR_MAX is not None:
    df = df[df["year"] <= YEAR_MAX].copy()

if MAX_POINTS is not None and len(df) > MAX_POINTS:
    df = df.sample(MAX_POINTS, random_state=42).copy()

if df.empty:
    raise RuntimeError("Aucun point à afficher après filtres")

print("Données finales :", df.shape)


# =========================================================
# TRANSFORMATION Z
# =========================================================

if USE_LOG_Z:
    df["z_plot_raw"] = np.log1p(df["z_value"])
    z_label = f"log1p({Z_MODE})"
else:
    df["z_plot_raw"] = df["z_value"]
    z_label = Z_MODE

# Coupe percentile haut pour éviter qu'une poignée de points domine tout
z_cap = np.percentile(df["z_plot_raw"], CLIP_Z_PERCENTILE)
df["z_plot"] = np.minimum(df["z_plot_raw"], z_cap)

# Normalisation pour hauteur visuelle
z_max = df["z_plot"].max()
if z_max > 0:
    df["elevation"] = (df["z_plot"] / z_max) * ELEVATION_SCALE
else:
    df["elevation"] = 1.0


# =========================================================
# COULEURS
# =========================================================

palette = {
    0: [68, 1, 84, 210],
    1: [59, 82, 139, 210],
    2: [33, 145, 140, 210],
    3: [94, 201, 98, 210],
    4: [253, 231, 37, 230],
    5: [255, 127, 14, 210],
    6: [214, 39, 40, 210],
    7: [148, 103, 189, 210],
    8: [140, 86, 75, 210],
    9: [23, 190, 207, 210],
}

df["color"] = df[cluster_col].apply(lambda x: palette.get(int(x), [180, 180, 180, 200]))


# =========================================================
# TOOLTIP
# =========================================================

tooltip = {
    "html": """
    <b>point_id:</b> {point_id}<br/>
    <b>cluster:</b> """ + cluster_col + """<br/>
    <b>year:</b> {year}<br/>
    <b>matrix:</b> {matrix}<br/>
    <b>dataset_id:</b> {dataset_id}<br/>
    <b>pfas_sum:</b> {pfas_sum}<br/>
    <b>z_value:</b> {z_value}
    """,
    "style": {
        "backgroundColor": "rgba(20,20,20,0.9)",
        "color": "white",
        "fontSize": "12px"
    }
}


# =========================================================
# VUE
# =========================================================

view_state = pdk.ViewState(
    latitude=float(df["lat"].median()),
    longitude=float(df["lon"].median()),
    zoom=INITIAL_ZOOM,
    pitch=INITIAL_PITCH,
    bearing=INITIAL_BEARING,
)

column_layer = pdk.Layer(
    "ColumnLayer",
    data=df,
    get_position=["lon", "lat"],
    get_elevation="elevation",
    elevation_scale=1,
    radius=COLUMN_RADIUS,
    get_fill_color="color",
    get_line_color=[0, 0, 0, 100],
    pickable=True,
    auto_highlight=True,
    extruded=True,
)

scatter_layer = pdk.Layer(
    "ScatterplotLayer",
    data=df,
    get_position=["lon", "lat"],
    get_fill_color="color",
    get_radius=600,
    opacity=0.25,
    pickable=False,
)

deck = pdk.Deck(
    layers=[column_layer, scatter_layer],
    initial_view_state=view_state,
    tooltip=tooltip,
    map_provider="carto",
    map_style=MAP_STYLE,
)

OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
deck.to_html(str(OUTPUT_HTML), notebook_display=False)

print(f"Carte 3D enregistrée : {OUTPUT_HTML.resolve()}")