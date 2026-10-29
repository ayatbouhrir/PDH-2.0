# Run the local project on Windows

For the current automatic launcher on **Windows, macOS and Linux**, use
[INSTALL_RUN.md](INSTALL_RUN.md). Run `run.cmd` on Windows or `sh run.sh` on
macOS/Linux. This older setup note describes the first Windows test installation.
The automatic launcher now uses `.local/project.env` as its private configuration.

From `D:\pfas-data-hub-analytics-main`:

```powershell
npm run start:local
```

Open http://127.0.0.1:5173/ (web app) or http://127.0.0.1:8000/docs (analysis API).
The services run in the background; their logs are in `.local`.

## Separate PostgreSQL instance

The project uses **127.0.0.1:5434**, database **dae_pfas_local**, user **pfas_app**.
Its files are in `.local/postgres`. A random password is saved in the ignored
`PDHv2/.env` and `model/.env` files.

The existing Windows PostgreSQL service on port **5433** is independent.
The project setup and start scripts do not manage or alter that service.

## Data currently loaded

This installation contains a **partial extract of real public PDH data** downloaded
on 29 October 2026: 15,183 points, including 2,561 measurement points and 126
substance references. It is not the complete PFAS dataset or the user's private data.
The source is https://pdh.cnrs.fr/download/full.csv (approximately 3.5 GB).
The extract is `.local/pfas-sample.csv`; provenance is recorded in `.local/data-import.json`.
Administrative associations use the bundled NUTS 2016, 2021, and 2024 boundaries.

The historical bundled model embeddings and analysis results describe a different
dataset. This installation disables their automatic reuse and computes fresh
SAINT embeddings for the local data.

The import script refuses to replace a populated database. Do not run the original
notebook against a database containing other work: its initialization drops tables.

## Repeat the functional checks

```powershell
npm run test:local
cd PDHv2
npm run check
npm run build
```

The functional checks exercise real HTTP requests, filters, exports, four clustering
algorithms, five reductions, visualizations, explanations, and saved analysis history.
Clustering checks use the 94-point Danube dataset with PFOA/PFOS to keep them bounded.
They create saved test runs and delete only a specific test-created run.
Detailed results are saved in `.local/test-results.json`.

Interactive browser checks also covered dataset selection, history restoration,
running an analysis, the 3D map, and comparison of two saved analyses.

## Remaining limitations

- The complete source dataset has not been imported; this is a functional local test installation.
- WorldPop population lookup timed out during verification. The application reports
  a 502 timeout for that external service; core map and analysis features are independent of it.
- CARTO basemaps require a provider key in this environment. OpenStreetMap is the working
  default for 2D, comparison, and 3D maps. Optional CARTO selections remain in the layer menu.
- The dependency audit reports 22 advisories, including one critical advisory in MapLibre 5.
  Addressing it requires a major MapLibre upgrade; dependencies have not been force-upgraded.
- Three pre-existing unused CSS warnings remain. Type checking has zero errors.
- The research notebooks/scripts and optional CLAMP explainer variants are not all covered
  by the application smoke checks. The default CLAMP decision-tree explainer was exercised.

## Fresh installation prerequisites

Node.js 20+, PostgreSQL 18 binaries, and Python 3.12 are installed on this machine.
The application packages are in `PDHv2/node_modules`; Python packages are isolated in `.venv`.
Runtime dependencies are listed in `model/requirements.txt`.
CPU-only PyTorch can be installed from its official wheel index to avoid GPU dependencies.
