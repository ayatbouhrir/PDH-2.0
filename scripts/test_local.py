"""Functional smoke checks against the isolated local project services."""
import argparse
import copy
import json
from pathlib import Path
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:5173"
BACKEND = "http://127.0.0.1:8000"
results = []
client = httpx.Client(timeout=300, trust_env=False)


def check(name, path, body=None, *, expected=200, validate=None, base=None):
    base = base or BASE
    started = time.monotonic()
    try:
        response = client.get(base + path, headers={"Accept": "text/html"} if path in ("/", "/analyse", "/analyse/comparaison") else {}) if body is None else client.post(base + path, json=body)
        assert response.status_code == expected, f"HTTP {response.status_code}: {response.text[:450]}"
        data = response.json() if "application/json" in response.headers.get("content-type", "") else response.text
        if validate:
            assert validate(data), str(data)[:350]
        results.append({"name": name, "ok": True, "seconds": round(time.monotonic() - started, 2)})
        print("PASS", name, flush=True)
        return data
    except Exception as exc:
        results.append({"name": name, "ok": False, "error": str(exc)[:700]})
        print("FAIL", name, str(exc)[:450], flush=True)
        return None


def run():
    global BASE, BACKEND
    args = argparse.ArgumentParser()
    args.add_argument("--web-only", action="store_true")
    args.add_argument("--frontend-url", default=BASE)
    args.add_argument("--backend-url", default=BACKEND)
    options = args.parse_args()
    BASE, BACKEND = options.frontend_url.rstrip('/'), options.backend_url.rstrip('/')
    f = {"category": "Measurement", "datasetId": [], "matrix": [], "yearRange": [2003, 2025],
         "lassoRegion": [], "substances": [], "nutsRegions": []}
    check("Home page", "/", validate=lambda d: "<!doctype html>" in d.lower())
    check("Analysis page", "/analyse", validate=lambda d: "<!doctype html>" in d.lower())
    check("Comparison page", "/analyse/comparaison", validate=lambda d: "<!doctype html>" in d.lower())
    check("Filter metadata", "/api/info", validate=lambda d: len(d["allSubstances"]) > 0)
    points = check("Measurement map", "/api/filter-points", {"filters": f, "areaMode": "NUTS"}, validate=lambda d: len(d) > 0)
    if not points:
        return
    dataset = {**f, "datasetId": ["11"]}
    subset = check("Dataset filter", "/api/filter-points", {"filters": dataset, "areaMode": "NUTS"}, validate=lambda d: len(d) == 94)
    check("Matrix filter", "/api/filter-points", {"filters": {**f, "matrix": ["Sea water"]}, "areaMode": "NUTS"}, validate=lambda d: 0 < len(d) < len(points))
    check("Year filter", "/api/filter-points", {"filters": {**f, "yearRange": [2019, 2019]}, "areaMode": "NUTS"}, validate=lambda d: all(p["year"] == 2019 for p in d) and len(d) > 0)
    polygon = [{"lat": 43, "lon": 8}, {"lat": 51, "lon": 8}, {"lat": 51, "lon": 24}, {"lat": 43, "lon": 24}]
    check("Lasso filter", "/api/filter-points", {"filters": {**f, "lassoRegion": polygon}, "areaMode": "LASSO"}, validate=lambda d: 0 < len(d) < len(points))
    check("NUTS country filter", "/api/filter-points", {"filters": {**f, "nutsRegions": [{"id": "DE", "year": 2024, "level": 0}]}, "areaMode": "NUTS"}, validate=lambda d: 0 < len(d) < len(points))
    check("Point details", "/api/fetch-point-details", {"pointIds": [points[0]["id"]]}, validate=lambda d: len(d) == 1 and "pfas_values" in d[0])
    check("Multi-point statistics", "/api/fetch-point-details", {"pointIds": [p["id"] for p in subset[:15]]}, validate=lambda d: len(d) > 0)
    check("Invalid point IDs", "/api/fetch-point-details", {"pointIds": []}, expected=400)
    check("Units", "/api/check-units", {"filters": f, "areaMode": "NUTS"}, validate=lambda d: len(d) > 0)
    check("Substance range", "/api/fetch-substance-range", {"substance": "PFOA", "unit": "ng/l", "category": "Measurement"}, validate=lambda d: float(d["raw"]["count"]) > 0)
    substance = {"name": "PFOA", "unit": "ng/l", "rangeMode": "raw", "rawRange": [0, 100000], "filteredRange": [0, 100000]}
    check("Substance filter", "/api/filter-points", {"filters": {**f, "substances": [substance]}, "areaMode": "NUTS"}, validate=lambda d: len(d) > 0 and "substances" in d[0])
    check("Substance histogram", "/api/substance-histogram", {"filters": f, "areaMode": "NUTS", "substance": "PFOA", "unit": "ng/l", "rangeLimit": [0, 10000]}, validate=lambda d: bool(d))
    check("CSV export", "/api/filter-points", {"filters": dataset, "areaMode": "NUTS", "exportMode": True, "fields": ["id", "category", "lat", "lon", "year"]}, validate=lambda d: "category" in d and len(d.splitlines()) == 95)
    check("Context sites", "/api/pfas-sites", {"categories": ["Known PFAS user", "Presumptive"], "filters": {}}, validate=lambda d: d["total"] > 0)
    check("Invalid population coordinates", "/api/local-population", {"lat": "invalid", "lon": 0}, expected=400)
    if options.web_only:
        return
    check("Python connectivity through web", "/api/python-status", validate=lambda d: d["ok"])
    check("Python health with database", "/health", base=BACKEND, validate=lambda d: d["rows"] > 0)
    check("PFAS columns", "/pfas-columns", base=BACKEND, validate=bool)
    run_body = {"algorithm": "kmeans", "filters": dataset, "selectedModelPfas": ["PFOA", "PFOS"],
                "mode": "expert", "params": {"k": 3, "maxIterations": 10, "reduction": "none", "preprocessing": "standardize"}}
    kmeans = check("KMeans clustering", "/api/analysis/run", run_body, validate=lambda d: len(d["assignments"]) == 94 and d["summary"]["clusterCount"] > 0)
    check("Repeated run uses cache", "/api/analysis/run", run_body, validate=lambda d: d["cached"])
    for algorithm in ("dbscan", "hdbscan", "propos"):
        body = copy.deepcopy(run_body)
        body["algorithm"] = algorithm
        body["params"].update({"eps": 0.5, "minPts": 3, "minClusterSize": 5, "minSamples": 3})
        check(f"{algorithm.upper()} clustering", "/api/analysis/run", body, validate=lambda d: len(d["assignments"]) == 94)
    for reduction in ("pca", "tsne", "autoencoder", "saint"):
        body = copy.deepcopy(run_body)
        body["params"]["reduction"] = reduction
        check(f"Reduction: {reduction}", "/api/analysis/run", body, validate=lambda d: len(d["assignments"]) == 94)
    simple = {**run_body, "mode": "simple"}
    check("Simple automatic analysis", "/api/analysis/run", simple, validate=lambda d: len(d["assignments"]) == 94)
    check("No matching observations", "/api/analysis/run", {**run_body, "filters": {**dataset, "yearRange": [2090, 2091]}}, validate=lambda d: d["summary"]["analyzedPoints"] == 0)
    check("Invalid algorithm validation", "/api/analysis/run", {**run_body, "algorithm": "invalid"}, expected=422)
    if kmeans:
        assignments = kmeans["assignments"]
        cluster_id = next(value for value in assignments.values() if value >= 0)
        ids = [int(key) for key in assignments]
        check("BIRCH condensation", "/api/analysis/condense-birch", {"filters": dataset, "selectedModelPfas": ["PFOA", "PFOS"], "assignments": assignments}, validate=bool)
        check("Temporal chart across years", "/api/visualization/temporal", {"selectedPfas": ["PFOA", "PFOS"], "pointIds": [p["id"] for p in points]}, validate=lambda d: len(d["series"]) > 0)
        check("Temporal chart single-year message", "/api/visualization/temporal", {"selectedPfas": ["PFOA", "PFOS"], "pointIds": ids, "assignments": assignments}, validate=lambda d: not d["series"] and "error" in d["meta"])
        check("Radar chart", "/api/visualization/radar", {"axesPfas": ["PFOA", "PFOS"], "pointIds": ids, "assignments": assignments}, validate=bool)
        check("SHAP explanation", "/api/analysis/shap", {**run_body, "assignments": assignments}, validate=bool)
        check("CLAMP explanation", "/api/analysis/clamp", {"filters": dataset, "selectedModelPfas": ["PFOA", "PFOS"], "assignments": assignments, "clusterId": cluster_id}, validate=bool)
        check("Bubble context", "/api/bubble-context", {"pointIds": ids[:5], "maxDistanceKm": 50}, validate=bool)
        key = kmeans["cacheKey"]
        check("History list", "/api/analysis/history/list", validate=bool)
        check("History reload", "/api/analysis/history/load", {"cacheKey": key}, validate=lambda d: len(d["assignments"]) == 94)
        check("History rename", "/api/analysis/history/rename", {"cacheKey": key, "name": "Functional check — Danube"}, validate=lambda d: d["ok"])
        check("History view-state save", "/api/analysis/history/state", {"cacheKey": key, "mapState": {"zoom": 6}, "panelState": {"tab": "summary"}}, validate=lambda d: d["ok"])
        # Delete only the specific disposable run made by this test.
        check("History delete test run", "/api/analysis/history/delete", {"cacheKey": key}, validate=lambda d: d["ok"])
        check("Deleted run can regenerate", "/api/analysis/run", run_body, validate=lambda d: len(d["assignments"]) == 94)


if __name__ == "__main__":
    try:
        run()
    finally:
        (ROOT / ".local" / "test-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        passed = sum(item["ok"] for item in results)
        print(f"{passed}/{len(results)} checks passed", flush=True)
    raise SystemExit(0 if results and all(item["ok"] for item in results) else 1)
