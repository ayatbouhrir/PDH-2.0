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
OUTPUT_HTML = Path(__file__).resolve().parents[2] / "artifacts/embeddings/saint/saint_pfas_map_3d.html"

CATEGORY_FILTER = "Measurement"   # ou None
MAX_POINTS = 10000                # réduis si c'est trop lourd
Z_MODE = "pfas_sum"               # ou "pfas_376" par exemple
USE_LOG_Z = True

# échelle verticale
ELEVATION_SCALE = 3000

# rayon des colonnes
COLUMN_RADIUS = 2500


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


# =========================================================
# CHARGER META GÉOGRAPHIQUES
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
    raise ValueError("Z_MODE doit être 'pfas_sum' ou un nom comme 'pfas_376'")

print("Meta chargée :", meta_df.shape)


# =========================================================
# MERGE
# =========================================================

df = embeddings_df.merge(meta_df, on="point_id", how="inner").copy()

df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
df["z_value"] = pd.to_numeric(df["z_value"], errors="coerce")
df = df.dropna(subset=["lat", "lon", "z_value"]).copy()

df["z_value"] = df["z_value"].clip(lower=0.0)

if MAX_POINTS is not None and len(df) > MAX_POINTS:
    df = df.sample(MAX_POINTS, random_state=42).copy()

if df.empty:
    raise RuntimeError("Aucun point à afficher")

print("Données finales :", df.shape)


# =========================================================
# TRANSFORMATION Z
# =========================================================

if USE_LOG_Z:
    df["z_plot"] = np.log1p(df["z_value"])
    z_label = f"log1p({Z_MODE})"
else:
    df["z_plot"] = df["z_value"]
    z_label = Z_MODE

# pour éviter colonnes plates
if df["z_plot"].max() > 0:
    df["elevation"] = (df["z_plot"] / df["z_plot"].max()) * ELEVATION_SCALE
else:
    df["elevation"] = 1.0


# =========================================================
# COULEURS PAR CLUSTER
# =========================================================

palette = {
    0: [68, 1, 84, 180],
    1: [59, 82, 139, 180],
    2: [33, 145, 140, 180],
    3: [94, 201, 98, 180],
    4: [253, 231, 37, 180],
    5: [255, 127, 14, 180],
    6: [214, 39, 40, 180],
    7: [148, 103, 189, 180],
    8: [140, 86, 75, 180],
    9: [23, 190, 207, 180],
}

df["cluster_int"] = df[cluster_col].astype(int)
df["color"] = df["cluster_int"].apply(lambda x: palette.get(x, [120, 120, 120, 180]))


# =========================================================
# TOOLTIP
# =========================================================

tooltip = {
    "html": """
    <b>point_id:</b> {point_id}<br/>
    <b>cluster:</b> {cluster_int}<br/>
    <b>year:</b> {year}<br/>
    <b>matrix:</b> {matrix}<br/>
    <b>dataset_id:</b> {dataset_id}<br/>
    <b>pfas_sum:</b> {pfas_sum}<br/>
    <b>z:</b> {z_value}
    """,
    "style": {
        "backgroundColor": "rgba(30,30,30,0.85)",
        "color": "white",
        "fontSize": "12px"
    }
}


# =========================================================
# CARTE 3D
# =========================================================

layer = pdk.Layer(
    "ColumnLayer",
    data=df,
    get_position=["lon", "lat"],
    get_elevation="elevation",
    elevation_scale=1,
    radius=COLUMN_RADIUS,
    get_fill_color="color",
    get_line_color=[0, 0, 0, 80],
    pickable=True,
    auto_highlight=True,
    extruded=True,
)

view_state = pdk.ViewState(
    latitude=float(df["lat"].median()),
    longitude=float(df["lon"].median()),
    zoom=4.5,
    pitch=50,
    bearing=0,
)

deck = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip=tooltip,
    map_provider="carto",
    map_style=pdk.map_styles.CARTO_LIGHT,
)

OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
deck.to_html(str(OUTPUT_HTML), notebook_display=False)

print(f"Carte 3D enregistrée : {OUTPUT_HTML.resolve()}")