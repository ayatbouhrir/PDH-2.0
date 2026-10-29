import pandas as pd
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".local/project.env")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from main import load_dataframe, apply_filters, AnalysisRequest, Filters, AnalysisParams


req = AnalysisRequest(
    algorithm="kmeans",
    selectedModelPfas=["All"],
    mode="simple",
    filters=Filters(
        category="Measurement",
        datasetId=[],
        matrix=[],
        yearRange=[2003, 2025],
        lassoRegion=[],
        substances=[],
    ),
    params=AnalysisParams(
        k=5,
        maxIterations=100,
        eps=0.5,
        minPts=5,
        preprocessing="none",
        reduction="saint",
    ),
    viewport=None,
)

# les mêmes points que le backend
df = load_dataframe()
filtered = apply_filters(df, req)

print("Nb points application:", len(filtered))
print("Nb point_id uniques:", filtered["point_id"].nunique())

# Conserver  ce qui sert à SAINT
pfas_cols = [c for c in filtered.columns if c.startswith("pfas_")]
saint_input = filtered[["point_id", *pfas_cols]].copy()

print("Shape SAINT input:", saint_input.shape)

saint_input.to_parquet(Path(__file__).resolve().parents[2] / "artifacts/embeddings/saint/saint_input_from_app.parquet", index=False)
print("Export OK")
